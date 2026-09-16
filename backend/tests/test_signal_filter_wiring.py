"""
Pruebas de Integración de los Filtros de Señal con la Configuración.

Los filtros llegaron con `origin/main` (commit 62fd94b) y esta batería cubre los huecos que
detectó la revisión posterior: interruptores declarados pero no consultados, y reserva de
memoria antes de validar el identificador del cliente.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.config import WKNNConfig
from backend.domain.building import Point2D
from backend.domain.fingerprint import RadioMapEntry, ReferencePoint
from backend.main import app, app_state
from backend.services.signal_filters import (
    DEFAULT_PROCESS_NOISE,
    MultiBSSIDKalmanFilter,
    TrajectoryKinematicFilter2D,
    select_adaptive_k,
)
from backend.tests.helpers import IsolatedAppStateMixin


class TestRejectedConnectionsLeakNothing(IsolatedAppStateMixin, unittest.TestCase):
    """
    Los filtros viven en diccionarios del estado global indexados por `student_id`, y la rama
    de rechazo retorna antes de la limpieza. Reservarlos antes de validar dejaba dos objetos
    colgados por intento, con claves elegidas por quien se conecta.
    """

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        app_state.mobile_kalman_filters.clear()
        app_state.mobile_trajectory_filters.clear()

    def test_rejected_identifiers_allocate_no_filters(self):
        for i in range(25):
            try:
                with self.client.websocket_connect(f"/ws/mobile/<intruso-{i}>") as ws:
                    ws.receive()
            except Exception:
                pass

        self.assertEqual(
            len(app_state.mobile_kalman_filters), 0,
            "Una conexión rechazada no debe reservar filtros de Kalman"
        )
        self.assertEqual(
            len(app_state.mobile_trajectory_filters), 0,
            "Una conexión rechazada no debe reservar filtros de trayectoria"
        )

    def test_accepted_connection_releases_its_filters(self):
        with self.client.websocket_connect("/ws/mobile/EST_08") as ws:
            ws.send_json({"timestamp": 1000.0, "target_room_id": "S302", "readings": {"ap_p3_west": -60.0}})
            ws.receive_json()

        self.assertNotIn("EST_08", app_state.mobile_kalman_filters)
        self.assertNotIn("EST_08", app_state.mobile_trajectory_filters)


class TestKalmanSwitchIsHonoured(IsolatedAppStateMixin, unittest.TestCase):
    """`enable_kalman_filter` estaba declarado pero no se consultaba en ninguna parte."""

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)

        # El repositorio aislado está vacío y el WKNN devolvería siempre su posición por
        # defecto, con lo que la prueba no distinguiría nada. Se calibran dos puntos separados
        # en el piso 3 para que el vector de entrada sí determine la coordenada.
        for rp_id, x, y, oeste, este in (
            ("RP_A", 4.0, 3.0, -40.0, -85.0),
            ("RP_B", 16.0, 3.0, -85.0, -40.0),
        ):
            rp = ReferencePoint(id=rp_id, floor_number=3, position=Point2D(x, y), label=rp_id)
            self.radio_map_repo.save_entry(RadioMapEntry(
                reference_point=rp,
                rssi_means={"ap_p3_west": oeste, "ap_p3_east": este},
                sample_count=15,
            ))

    def _position_for(self, kalman_enabled: bool):
        patched = WKNNConfig(k=2, enable_kalman_filter=kalman_enabled)
        with mock.patch("backend.api.websocket_handlers.config.wknn", patched):
            with self.client.websocket_connect("/ws/mobile/EST_08") as ws:
                posiciones = []
                # Varias lecturas: el filtro solo diverge del crudo a partir de la segunda,
                # porque la primera inicializa su estado con el propio valor medido.
                for t, rssi in enumerate([-40.0, -75.0, -75.0, -75.0], start=1):
                    ws.send_json({
                        "timestamp": 1000.0 + t * 1.5,
                        "target_room_id": "S302",
                        "readings": {"ap_p3_west": rssi, "ap_p3_east": -80.0},
                    })
                    r = ws.receive_json()
                    posiciones.append((r["position"]["x"], r["position"]["y"]))
                return posiciones

    def test_switch_changes_the_pipeline(self):
        con = self._position_for(True)
        sin = self._position_for(False)
        self.assertNotEqual(
            con, sin,
            "Activar o desactivar el filtro de Kalman debe cambiar el resultado; "
            "si no, el interruptor no se está consultando"
        )


class TestKalmanTuning(unittest.TestCase):
    """
    El ruido de proceso original (0.08) asumía un RSSI casi estático y se resistía al
    movimiento real del alumno.
    """

    def test_process_noise_is_not_the_original_value(self):
        self.assertGreater(
            DEFAULT_PROCESS_NOISE, 1.0,
            "Un ruido de proceso muy bajo hace que el filtro arrastre la posición estimada"
        )

    def test_filter_tracks_a_sustained_change(self):
        """Ante un cambio sostenido de RSSI, el filtro debe converger, no quedarse anclado."""
        kalman = MultiBSSIDKalmanFilter()
        kalman.filter_readings({"ap": -40.0}, 1.0)
        for i in range(2, 8):
            salida = kalman.filter_readings({"ap": -80.0}, float(i))
        self.assertLess(
            abs(salida["ap"] - (-80.0)), 2.0,
            f"Tras 6 lecturas sostenidas en -80 dBm el filtro devuelve {salida['ap']}"
        )


class TestAdaptiveKIsInertWithK2(unittest.TestCase):
    """
    Con `k = 2`, `select_adaptive_k(min_k=2, max_k=k)` no tiene margen y devuelve siempre 2.
    Darle margen real (max_k=4) empeora el error, así que el interruptor queda desactivado.
    """

    def test_returns_min_k_when_there_is_no_range(self):
        for d1 in (1.0, 5.0, 12.0, 40.0):
            vecinos = [(None, d1 + paso) for paso in (0, 2, 5, 9)]
            self.assertEqual(select_adaptive_k(vecinos, min_k=2, max_k=2), 2)

    def test_widens_k_when_given_range(self):
        dispersos = [(None, d) for d in (12.0, 14.0, 17.0, 21.0)]
        self.assertGreater(select_adaptive_k(dispersos, min_k=2, max_k=4), 2)

    def test_disabled_by_default(self):
        self.assertFalse(WKNNConfig().enable_adaptive_k)


class TestTrajectoryFilterDoesItsJob(unittest.TestCase):
    """
    El filtro cinemático sí cumple lo que promete: acota el salto de posición ante una lectura
    anómala. Medido sobre 30 trayectorias, recorta el peor caso de 8.67 m a 2.60 m.
    """

    def test_clamps_a_teleport(self):
        f = TrajectoryKinematicFilter2D()
        f.filter_position(Point2D(10.0, 5.0), 100.0)
        saltada = f.filter_position(Point2D(30.0, 5.0), 101.5)

        salto = Point2D(10.0, 5.0).distance_to(saltada)
        self.assertLess(salto, 5.0, f"Un salto de 20 m se acotó solo a {salto:.2f} m")

    def test_lets_normal_walking_through(self):
        f = TrajectoryKinematicFilter2D()
        f.filter_position(Point2D(10.0, 8.0), 100.0)
        for i, y in enumerate([7.4, 6.8, 6.2, 5.6], start=1):
            salida = f.filter_position(Point2D(10.0, y), 100.0 + i * 1.5)

        self.assertLess(
            abs(salida.y - 5.6), 1.0,
            f"El filtro se quedó en y={salida.y} cuando el alumno ya estaba en 5.6"
        )


if __name__ == "__main__":
    unittest.main()

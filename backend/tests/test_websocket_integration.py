"""
Pruebas de Integración: Flujo WebSocket Extremo a Extremo.
Verifica que un mensaje emitido por el sensor móvil desencadene
la actualización reactiva en la laptop del aula suscrita.
"""
import unittest
import asyncio
from fastapi.testclient import TestClient
from backend.main import app
from backend.domain.building import Point2D
from backend.domain.fingerprint import ReferencePoint, RadioMapEntry
from backend.tests.helpers import IsolatedAppStateMixin

class TestWebSocketIntegration(IsolatedAppStateMixin, unittest.TestCase):
    def setUp(self):
        # El mixin sustituye los repositorios globales por otros efímeros, de modo que el
        # punto de referencia sintético de abajo NO acabe escrito en data/radio_map.json.
        super().setUp()
        self.client = TestClient(app)
        # Añadir un punto de referencia para calibrar S302
        rp = ReferencePoint(id="RP_TEST_S302", floor_number=3, position=Point2D(10.0, 2.0), label="S302 Center")
        entry = RadioMapEntry(reference_point=rp, rssi_means={"ap_test_s302": -45.0})
        self.radio_map_repo.save_entry(entry)

    def test_end_to_end_websocket_flow(self):
        """
        Conecta un WebSocket simulando la laptop del Salón 302,
        luego un WebSocket simulando el móvil del estudiante enviando telemetría,
        y verifica la recepción del evento de proximidad en la laptop.
        """
        with self.client.websocket_connect("/ws/laptop/S302") as ws_laptop:
            # 1. Verificar snapshot inicial recibido por la laptop
            init_msg = ws_laptop.receive_json()
            self.assertEqual(init_msg["event"], "initial_state")
            self.assertEqual(init_msg["room_id"], "S302")

            # 2. Conectar móvil del alumno y enviar telemetría de proximidad
            with self.client.websocket_connect("/ws/mobile/EST_08") as ws_mobile:
                scan_payload = {
                    "timestamp": 1772700000.0,
                    "target_room_id": "S302",
                    "readings": {"ap_test_s302": -46.0},
                    "room_ap_rssi": -48.0
                }
                ws_mobile.send_json(scan_payload)

                # El móvil debe recibir la pista y la posición estimada
                mobile_resp = ws_mobile.receive_json()
                self.assertEqual(mobile_resp["event"], "location_update")
                self.assertEqual(mobile_resp["floor_number"], 3)
                self.assertIn("active_clue", mobile_resp)

            # 3. La laptop de S302 debe haber recibido la alerta reactiva del alumno
            laptop_event = ws_laptop.receive_json()
            self.assertEqual(laptop_event["event"], "student_proximity")
            self.assertEqual(laptop_event["student_id"], "EST_08")
            self.assertIn(laptop_event["status"], ["APPROACHING", "AT_DOOR", "PRESENT_CONFIRMED"])

    def test_concurrent_multi_student_websocket(self):
        """
        Verifica que múltiples dispositivos móviles puedan conectarse en simultáneo
        con distintos student_id sin bloquearse ni sobreescribir sus estados.
        """
        with self.client.websocket_connect("/ws/mobile/EST_01") as ws1:
            with self.client.websocket_connect("/ws/mobile/EST_02") as ws2:
                # Enviar escaneo desde EST_01 hacia S101
                ws1.send_json({
                    "timestamp": 1000.0,
                    "target_room_id": "S101",
                    "readings": {"ap_test_s302": -80.0}
                })
                resp1 = ws1.receive_json()
                self.assertEqual(resp1["student_id"], "EST_01")

                # Enviar escaneo desde EST_02 hacia S102
                ws2.send_json({
                    "timestamp": 1001.0,
                    "target_room_id": "S102",
                    "readings": {"ap_test_s302": -75.0}
                })
                resp2 = ws2.receive_json()
                self.assertEqual(resp2["student_id"], "EST_02")


class TestIdentifierValidation(IsolatedAppStateMixin, unittest.TestCase):
    """
    Los identificadores llegan como texto libre en la ruta del WebSocket y acaban en el tablero
    del aula. El backend los restringe a `^[A-Za-z0-9_-]{1,32}$` y cierra con el código 4400 si
    no encajan.
    """

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)

    def _assert_rejected(self, path: str):
        """
        La conexión debe aceptarse y cerrarse de inmediato con 4400.

        Cerrar *sin* aceptar haría que el servidor respondiera con un HTTP 403 al handshake y el
        código de aplicación nunca llegaría al cliente, que no podría distinguir "identificador
        inválido" de "servidor caído" y reintentaría en bucle.
        """
        with self.client.websocket_connect(path) as ws:
            message = ws.receive()
        self.assertEqual(message["type"], "websocket.close")
        self.assertEqual(message["code"], 4400)

    def test_rejects_student_id_with_markup(self):
        self._assert_rejected("/ws/mobile/<img src=x onerror=alert(1)>")

    def test_rejects_room_id_with_markup(self):
        self._assert_rejected("/ws/laptop/<script>")

    def test_rejects_overlong_identifier(self):
        self._assert_rejected(f"/ws/mobile/{'A' * 33}")

    def test_accepts_a_valid_identifier(self):
        """Control: un identificador correcto sí debe establecer la sesión."""
        with self.client.websocket_connect("/ws/laptop/S302") as ws:
            initial = ws.receive_json()
        self.assertEqual(initial["event"], "initial_state")


if __name__ == "__main__":
    unittest.main()

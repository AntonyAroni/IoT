"""
Pruebas de Control de Acceso a las Operaciones Destructivas.

`DELETE /api/v1/calibration/radio-map`, `POST /api/v1/calibration/record` y
`POST /api/v1/attendance/room/{id}/reset` estaban expuestas de forma anónima a toda la red local.
Una petición accidental durante una prueba bastaba para borrar la calibración del edificio.

No se valida autenticación de usuarios, que sigue pendiente, sino que las operaciones que
destruyen datos no estén al alcance de cualquiera en la red.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.api.security import ADMIN_TOKEN_HEADER
from backend.config import SecurityConfig
from backend.main import app
from backend.tests.helpers import IsolatedAppStateMixin

DESTRUCTIVE_REQUESTS = [
    ("delete", "/api/v1/calibration/radio-map", None),
    ("post", "/api/v1/attendance/room/S302/reset", None),
]


class TestDestructiveEndpointAccess(IsolatedAppStateMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # El host del cliente se fija al construir TestClient, no por petición. Se usan dos
        # clientes para poder distinguir una petición local de una que llega por la red.
        self.local = TestClient(app, client=("127.0.0.1", 50000))
        self.remote = TestClient(app, client=("192.168.1.77", 50000))

    @staticmethod
    def _send(client, method, path, payload, headers=None):
        # `delete` no admite cuerpo en el cliente de pruebas, así que solo se envía cuando lo hay.
        kwargs = {"headers": headers or {}}
        if payload is not None:
            kwargs["json"] = payload
        return getattr(client, method)(path, **kwargs)

    # ------------------------------------------------------------------
    # Modo por defecto: sin token configurado, solo desde la máquina local
    # ------------------------------------------------------------------

    def test_local_requests_are_allowed_without_token(self):
        """La demostración y el desarrollo deben seguir funcionando sin configurar nada."""
        with mock.patch("backend.api.security.config.security", SecurityConfig(admin_token=None)):
            for method, path, payload in DESTRUCTIVE_REQUESTS:
                with self.subTest(path=path):
                    response = self._send(self.local, method, path, payload)
                    self.assertEqual(response.status_code, 200, response.text)

    def test_remote_requests_are_rejected_without_token(self):
        """Sin token configurado, la red local no puede destruir datos."""
        with mock.patch("backend.api.security.config.security", SecurityConfig(admin_token=None)):
            for method, path, payload in DESTRUCTIVE_REQUESTS:
                with self.subTest(path=path):
                    response = self._send(self.remote, method, path, payload)
                    self.assertEqual(response.status_code, 403, response.text)
                    self.assertIn("IPS_ADMIN_TOKEN", response.json()["detail"])

    # ------------------------------------------------------------------
    # Modo con token configurado
    # ------------------------------------------------------------------

    def test_remote_request_with_valid_token_is_allowed(self):
        with mock.patch("backend.api.security.config.security", SecurityConfig(admin_token="s3cr3t")):
            for method, path, payload in DESTRUCTIVE_REQUESTS:
                with self.subTest(path=path):
                    response = self._send(
                        self.remote, method, path, payload,
                        headers={ADMIN_TOKEN_HEADER: "s3cr3t"},
                    )
                    self.assertEqual(response.status_code, 200, response.text)

    def test_wrong_token_is_rejected(self):
        with mock.patch("backend.api.security.config.security", SecurityConfig(admin_token="s3cr3t")):
            for method, path, payload in DESTRUCTIVE_REQUESTS:
                with self.subTest(path=path):
                    response = self._send(
                        self.remote, method, path, payload,
                        headers={ADMIN_TOKEN_HEADER: "equivocado"},
                    )
                    self.assertEqual(response.status_code, 401, response.text)

    def test_missing_token_is_rejected_even_from_localhost(self):
        """Con token configurado, ser local deja de ser suficiente."""
        with mock.patch("backend.api.security.config.security", SecurityConfig(admin_token="s3cr3t")):
            response = self._send(self.local, "delete", "/api/v1/calibration/radio-map", None)
            self.assertEqual(response.status_code, 401, response.text)

    def test_delete_calibration_point_lifecycle_and_security(self):
        """Verifica ciclo de vida de borrado de punto y control de acceso."""
        # 1. Crear punto de prueba
        payload = {
            "rp_id": "RP_TEMP_TEST",
            "floor_number": 2,
            "x": 5.0,
            "y": 3.0,
            "label": "Punto Temporal",
            "rssi_means": {"ap_p2_01": -60.0},
        }
        res_create = self.local.post("/api/v1/calibration/record", json=payload)
        self.assertEqual(res_create.status_code, 200)

        # 2. Intento remoto sin token -> 403
        with mock.patch("backend.api.security.config.security", SecurityConfig(admin_token=None)):
            res_remote = self.remote.delete("/api/v1/calibration/point/RP_TEMP_TEST")
            self.assertEqual(res_remote.status_code, 403)

        # 3. Borrado local exitoso -> 200
        res_delete = self.local.delete("/api/v1/calibration/point/RP_TEMP_TEST")
        self.assertEqual(res_delete.status_code, 200)
        self.assertIn("eliminado correctamente", res_delete.json()["message"])

        # 4. Segundo intento -> 404 No encontrado
        res_not_found = self.local.delete("/api/v1/calibration/point/RP_TEMP_TEST")
        self.assertEqual(res_not_found.status_code, 404)

    def test_remote_mobile_sensor_can_upload_calibration_record(self):
        """Un sensor móvil en la red local debe poder enviar huellas de calibración."""
        payload = {
            "rp_id": "RP_SENSOR_MOVIL",
            "floor_number": 1,
            "x": 2.0,
            "y": 4.0,
            "label": "Calibración Móvil",
            "rssi_means": {"ap_hotspot": -50.0},
        }
        res = self.remote.post("/api/v1/calibration/record", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("guardado correctamente", res.json()["message"])

    # ------------------------------------------------------------------
    # Las operaciones de solo lectura no deben quedar protegidas
    # ------------------------------------------------------------------

    def test_read_only_endpoints_remain_public(self):
        """El tablero de aula consulta la asistencia sin credenciales; no debe romperse."""
        for path in ("/health",
                     "/api/v1/attendance/room/S302",
                     "/api/v1/building/summary",
                     "/api/v1/calibration/radio-map"):
            with self.subTest(path=path):
                response = self.remote.get(path)
                self.assertEqual(response.status_code, 200, response.text)


class TestCorsPolicy(unittest.TestCase):
    """
    La configuración anterior combinaba `allow_origins=["*"]` con `allow_credentials=True`.
    Starlette lo resuelve reflejando el Origin de quien pregunta, así que no fallaba de forma
    visible: concedía acceso con credenciales a cualquier sitio web.
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_unknown_origin_is_not_reflected(self):
        response = self.client.get("/health", headers={"Origin": "https://atacante.example"})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(
            response.headers.get("access-control-allow-origin"),
            "https://atacante.example",
            "El servidor no debe autorizar a un origen arbitrario"
        )

    def test_credentials_are_not_granted_cross_origin(self):
        response = self.client.get("/health", headers={"Origin": "https://atacante.example"})
        self.assertNotEqual(response.headers.get("access-control-allow-credentials"), "true")


if __name__ == "__main__":
    unittest.main()

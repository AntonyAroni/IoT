"""
Pruebas de Credenciales de Dispositivo.

Hasta ahora el canal `/ws/mobile/{student_id}` aceptaba cualquier identificador que se le
declarara: marcar la asistencia de otro alumno era una línea de `websocat`. Estas pruebas cubren
que la identidad pase a ser verificable y que la migración no rompa a quien se conecta sin token
mientras no haya ningún dispositivo dado de alta.
"""
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.api.websocket_handlers import DEVICE_TOKEN_HEADER, WS_CLOSE_UNAUTHORIZED
from backend.domain.device import hash_token
from backend.main import app, app_state
from backend.repositories.device_repo import DeviceRegistry
from backend.tests.helpers import IsolatedAppStateMixin

ALTA = {
    "device_id": "MOVIL_01",
    "student_id": "EST_08",
    "student_name": "Diego Ramos",
    "enrolled_room": "S302",
}


class _RegistroAislado(IsolatedAppStateMixin):
    """Sustituye el registro global por uno efímero, para no escribir en data/."""

    def setUp(self):
        super().setUp()
        original = app_state.device_registry
        app_state.device_registry = DeviceRegistry()
        self.addCleanup(setattr, app_state, "device_registry", original)
        self.registry = app_state.device_registry
        self.client = TestClient(app, client=("127.0.0.1", 50000))


class TestEnrollment(_RegistroAislado, unittest.TestCase):
    def test_enroll_returns_the_token_once(self):
        r = self.client.post("/api/v1/devices/enroll", json=ALTA)
        self.assertEqual(r.status_code, 200, r.text)
        token = r.json()["token"]
        self.assertTrue(token)

        # El registro guarda la huella, nunca el token en claro
        guardado = self.registry.get("MOVIL_01")
        self.assertEqual(guardado.token_hash, hash_token(token))
        self.assertNotIn(token, guardado.token_hash)

    def test_listing_never_exposes_token_hashes(self):
        self.client.post("/api/v1/devices/enroll", json=ALTA)
        listado = self.client.get("/api/v1/devices").json()
        self.assertEqual(listado["total"], 1)
        self.assertNotIn("token_hash", listado["devices"][0])

    def test_enrollment_requires_admin(self):
        remoto = TestClient(app, client=("192.168.1.77", 50000))
        r = remoto.post("/api/v1/devices/enroll", json=ALTA)
        self.assertEqual(r.status_code, 403, r.text)

    def test_rejects_malformed_identifiers(self):
        invalido = dict(ALTA, student_id="<script>")
        r = self.client.post("/api/v1/devices/enroll", json=invalido)
        self.assertEqual(r.status_code, 422, r.text)

    def test_first_enrollment_announces_the_mode_change(self):
        r = self.client.post("/api/v1/devices/enroll", json=ALTA)
        self.assertIn("cambio_de_modo", r.json())

        segundo = self.client.post("/api/v1/devices/enroll", json=dict(ALTA, device_id="MOVIL_02"))
        self.assertNotIn("cambio_de_modo", segundo.json())


class TestPermissiveModeWhileEmpty(_RegistroAislado, unittest.TestCase):
    """
    Ocho consumidores se conectan hoy sin credencial. Exigir token de golpe los rompería, y lo
    previsible sería que alguien desactivara la comprobación entera.
    """

    def test_connection_without_token_is_accepted(self):
        self.assertFalse(self.registry.enforcement_enabled)
        with self.client.websocket_connect("/ws/mobile/EST_08") as ws:
            ws.send_json({"timestamp": 1000.0, "target_room_id": "S302", "readings": {"ap_p3_west": -60.0}})
            r = ws.receive_json()
        self.assertEqual(r["event"], "location_update")


class TestEnforcementOnceEnrolled(_RegistroAislado, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.token = self.registry.enroll("MOVIL_01", "EST_08", "Diego Ramos", "S302")

    def _connect(self, path, headers=None):
        return self.client.websocket_connect(path, headers=headers or {})

    def test_connection_without_token_is_rejected(self):
        with self._connect("/ws/mobile/EST_08") as ws:
            mensaje = ws.receive()
        self.assertEqual(mensaje["type"], "websocket.close")
        self.assertEqual(mensaje["code"], WS_CLOSE_UNAUTHORIZED)

    def test_connection_with_wrong_token_is_rejected(self):
        with self._connect("/ws/mobile/EST_08", {DEVICE_TOKEN_HEADER: "no-es-el-token"}) as ws:
            mensaje = ws.receive()
        self.assertEqual(mensaje["code"], WS_CLOSE_UNAUTHORIZED)

    def test_valid_token_in_header_is_accepted(self):
        with self._connect("/ws/mobile/EST_08", {DEVICE_TOKEN_HEADER: self.token}) as ws:
            ws.send_json({"timestamp": 1000.0, "target_room_id": "S302", "readings": {"ap_p3_west": -60.0}})
            r = ws.receive_json()
        self.assertEqual(r["event"], "location_update")

    def test_valid_token_in_query_is_accepted(self):
        """No todos los clientes de WebSocket permiten fijar cabeceras en el handshake."""
        with self._connect(f"/ws/mobile/EST_08?token={self.token}") as ws:
            ws.send_json({"timestamp": 1000.0, "target_room_id": "S302", "readings": {"ap_p3_west": -60.0}})
            r = ws.receive_json()
        self.assertEqual(r["event"], "location_update")

    def test_identity_comes_from_the_credential_not_the_path(self):
        """
        El núcleo del asunto: un dispositivo con credencial de EST_08 no puede marcar asistencia
        como EST_01 por el simple hecho de escribirlo en la ruta.
        """
        with self._connect("/ws/mobile/EST_01", {DEVICE_TOKEN_HEADER: self.token}) as ws:
            ws.send_json({"timestamp": 1000.0, "target_room_id": "S302", "readings": {"ap_p3_west": -60.0}})
            ws.receive_json()

        # El registro de asistencia debe haberse abierto para EST_08, no para el suplantado
        self.assertIsNotNone(self.attendance_repo.get_record("EST_08", "S302"))
        self.assertIsNone(self.attendance_repo.get_record("EST_01", "S302"))

    def test_revoked_device_loses_access_immediately(self):
        self.assertTrue(self.registry.revoke("MOVIL_01"))
        with self._connect("/ws/mobile/EST_08", {DEVICE_TOKEN_HEADER: self.token}) as ws:
            mensaje = ws.receive()
        self.assertEqual(mensaje["code"], WS_CLOSE_UNAUTHORIZED)

    def test_revoking_the_last_device_does_not_reopen_the_channel(self):
        """
        Revocar no puede devolver el sistema a modo permisivo. Si "exigir token" dependiera de
        que quede algún dispositivo activo, revocar el único móvil —justo lo que se hace cuando
        se sospecha que está comprometido— abriría el canal a cualquiera.
        """
        self.registry.revoke("MOVIL_01")
        self.assertTrue(
            self.registry.enforcement_enabled,
            "Tras revocar el último dispositivo, el token debe seguir siendo obligatorio"
        )

        with self._connect("/ws/mobile/EST_08") as ws:
            mensaje = ws.receive()
        self.assertEqual(mensaje["code"], WS_CLOSE_UNAUTHORIZED)

    def test_revoking_requires_admin(self):
        remoto = TestClient(app, client=("192.168.1.77", 50000))
        r = remoto.post("/api/v1/devices/MOVIL_01/revoke")
        self.assertEqual(r.status_code, 403, r.text)


class TestRegistryPersistence(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        os.unlink(self.path)
        self.addCleanup(lambda: os.path.exists(self.path) and os.unlink(self.path))

    def test_credentials_survive_a_restart(self):
        registro = DeviceRegistry(self.path)
        token = registro.enroll("MOVIL_01", "EST_08", "Diego Ramos", "S302")

        recargado = DeviceRegistry(self.path)
        self.assertTrue(recargado.enforcement_enabled)
        credencial = recargado.resolve_token(token)
        self.assertIsNotNone(credencial)
        self.assertEqual(credencial.student_id, "EST_08")

    def test_plaintext_token_is_never_written_to_disk(self):
        registro = DeviceRegistry(self.path)
        token = registro.enroll("MOVIL_01", "EST_08", "Diego Ramos", "S302")

        with open(self.path, encoding="utf-8") as f:
            contenido = f.read()
        self.assertNotIn(token, contenido, "El token en claro no debe llegar al disco")
        self.assertIn(hash_token(token), contenido)

    def test_revocation_survives_a_restart(self):
        registro = DeviceRegistry(self.path)
        token = registro.enroll("MOVIL_01", "EST_08", "Diego Ramos", "S302")
        registro.revoke("MOVIL_01")

        recargado = DeviceRegistry(self.path)
        self.assertIsNone(
            recargado.resolve_token(token),
            "Un token revocado no puede volver a ser válido tras reiniciar"
        )
        self.assertTrue(
            recargado.enforcement_enabled,
            "Reiniciar con todos los dispositivos revocados no debe reabrir el canal"
        )


if __name__ == "__main__":
    unittest.main()

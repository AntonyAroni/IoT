"""
Pruebas de la Asistencia Automática: el aula se decide en el servidor, no en la app.

El destino que elige el alumno solo guía la ruta. La asistencia se evalúa en el aula de la
credencial del móvil o en la asignada en el padrón; el destino solo cuenta si no hay ninguna.
"""
import unittest

from fastapi.testclient import TestClient

from backend.domain.attendance import Student, resolve_attendance_room
from backend.domain.building import Point2D
from backend.domain.fingerprint import RadioMapEntry, ReferencePoint
from backend.main import app
from backend.tests.helpers import IsolatedAppStateMixin

ROOMS = {"S302", "S303", "S402"}


class TestResolveAttendanceRoom(unittest.TestCase):
    def test_enrolled_room_wins_over_the_target(self):
        """Caso de campo del 29/10: destino S303 estando matriculado y presente en S302."""
        student = Student("EST_08", "Diego", "S302")
        self.assertEqual(resolve_attendance_room(student, "S303", None, ROOMS), "S302")

    def test_credential_room_wins_over_everything(self):
        student = Student("EST_08", "Diego", "S302")
        self.assertEqual(resolve_attendance_room(student, "S303", "S402", ROOMS), "S402")

    def test_auto_registered_student_follows_the_target(self):
        """Su enrolled_room es solo el primer destino que eligió: no lo ata a esa aula."""
        student = Student("EST_77", "Nuevo", "S302", auto_registered=True)
        self.assertEqual(resolve_attendance_room(student, "S303", None, ROOMS), "S303")

    def test_unknown_student_follows_the_target(self):
        self.assertEqual(resolve_attendance_room(None, "S303", None, ROOMS), "S303")

    def test_room_missing_from_the_building_falls_back_to_the_target(self):
        student = Student("EST_08", "Diego", "S999")
        self.assertEqual(resolve_attendance_room(student, "S302", "S998", ROOMS), "S302")


class TestAttendanceRoomOverWebSocket(IsolatedAppStateMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        rp = ReferencePoint(id="RP_TEST_S302", floor_number=3, position=Point2D(10.0, 2.0), label="S302 Center")
        self.radio_map_repo.save_entry(RadioMapEntry(reference_point=rp, rssi_means={"ap_test_s302": -45.0}))

    def _scan(self, ws, target):
        ws.send_json({"timestamp": 1772700000.0, "target_room_id": target, "readings": {"ap_test_s302": -46.0}})
        return ws.receive_json()

    def test_wrong_target_still_reports_to_the_enrolled_room(self):
        """EST_08 (S302) con el destino en S303: el tablero de la S302 recibe su asistencia."""
        with self.client.websocket_connect("/ws/laptop/S302") as ws_laptop:
            ws_laptop.receive_json()  # snapshot inicial
            with self.client.websocket_connect("/ws/mobile/EST_08") as ws_mobile:
                response = self._scan(ws_mobile, "S303")
                self.assertEqual(response["attendance_room_id"], "S302")
            event = ws_laptop.receive_json()
            self.assertEqual(event["student_id"], "EST_08")
            self.assertNotEqual(event["status"], "ABSENT")
        self.assertIsNotNone(self.attendance_repo.get_record("EST_08", "S302"))
        self.assertIsNone(self.attendance_repo.get_record("EST_08", "S303"))

    def test_navigation_still_uses_the_target(self):
        """La ruta sigue llevando al destino elegido, aunque la asistencia sea de otra aula."""
        with self.client.websocket_connect("/ws/mobile/EST_08") as ws_mobile:
            to_s302 = self._scan(ws_mobile, "S302")
            to_s303 = self._scan(ws_mobile, "S303")
        self.assertNotEqual(to_s302["distance_meters"], to_s303["distance_meters"])

    def test_auto_registered_student_is_flagged(self):
        with self.client.websocket_connect("/ws/mobile/EST_77") as ws_mobile:
            response = self._scan(ws_mobile, "S302")
        self.assertEqual(response["attendance_room_id"], "S302")
        self.assertTrue(self.attendance_repo.get_student("EST_77").auto_registered)


if __name__ == "__main__":
    unittest.main()

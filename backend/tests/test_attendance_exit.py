"""
Pruebas del Seguimiento tras la Confirmación: "Salió del aula".

Una asistencia confirmada no se pierde. Si el alumno pasa fuera del aula más del tiempo de
gracia de forma continuada, el estado pasa a LEFT_ROOM; si regresa, vuelve a PRESENT_CONFIRMED.
"""
import unittest
from unittest import mock

from backend.config import AttendanceConfig
from backend.domain.attendance import AttendanceRecord, AttendanceStatus, Student
from backend.domain.building import Point2D
from backend.repositories.attendance_repo import InMemoryAttendanceRepository
from backend.services.attendance_tracker import AttendanceTrackerService

INSIDE = Point2D(x=11.775, y=2.5)
OUTSIDE = Point2D(x=3.3, y=-1.0)      # Pasadizo frente a la 301: a ~10 m del centro de la 302
CENTER = Point2D(x=11.775, y=4.99)


class TestAttendanceExit(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryAttendanceRepository()
        self.tracker = AttendanceTrackerService(self.repo, AttendanceConfig(exit_grace_seconds=120.0))
        self.repo.register_student(Student("EST_11", "Renata Paredes", "S302"))
        patcher = mock.patch("backend.services.attendance_tracker.time.time")
        self.fake_time = patcher.start()
        self.addCleanup(patcher.stop)

    def _read(self, t, position, floor=3):
        self.fake_time.return_value = t
        return self.tracker.process_student_presence("EST_11", floor, position, "S302", 3, CENTER)

    def _confirm(self, start=1000.0):
        for i in range(3):
            record, _, _ = self._read(start + i * 1.5, INSIDE)
        self.assertEqual(record.status, AttendanceStatus.PRESENT_CONFIRMED)
        return record

    def test_short_absence_keeps_present(self):
        """Lecturas fuera durante menos del tiempo de gracia no marcan salida."""
        self._confirm()
        record, changed, _ = self._read(1100.0, OUTSIDE)
        record, changed, _ = self._read(1200.0, OUTSIDE)  # 100 s fuera
        self.assertEqual(record.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertFalse(changed)

    def test_continuous_absence_marks_left_and_keeps_attendance(self):
        record = self._confirm()
        confirmed_at = record.confirmed_at
        self._read(1100.0, OUTSIDE)
        record, changed, msg = self._read(1220.0, OUTSIDE)  # 120 s fuera
        self.assertTrue(changed)
        self.assertEqual(record.status, AttendanceStatus.LEFT_ROOM)
        self.assertEqual(record.left_at, 1100.0)            # cuándo salió, no cuándo se detectó
        self.assertEqual(record.confirmed_at, confirmed_at)  # la asistencia no se toca
        self.assertTrue(record.status.counts_as_attended)
        self.assertIn("SALIÓ DEL AULA", msg)

    def test_one_reading_inside_restarts_the_grace(self):
        """Una lectura dentro interrumpe la racha: una mala estimación no acumula ausencia."""
        self._confirm()
        self._read(1100.0, OUTSIDE)
        self._read(1150.0, INSIDE)
        record, _, _ = self._read(1230.0, OUTSIDE)           # 130 s desde la primera, 0 desde la última
        self.assertEqual(record.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertEqual(record.outside_since, 1230.0)

    def test_return_restores_present(self):
        self._confirm()
        self._read(1100.0, OUTSIDE)
        self._read(1220.0, OUTSIDE)
        record, changed, msg = self._read(1400.0, INSIDE)
        self.assertTrue(changed)
        self.assertEqual(record.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertIsNone(record.left_at)
        self.assertIsNone(record.outside_since)
        self.assertIn("REGRESÓ", msg)

    def test_other_floor_counts_as_outside(self):
        self._confirm()
        self._read(1100.0, INSIDE, floor=2)
        record, _, _ = self._read(1220.0, INSIDE, floor=2)
        self.assertEqual(record.status, AttendanceStatus.LEFT_ROOM)

    def test_zero_grace_disables_exit_tracking(self):
        self.tracker = AttendanceTrackerService(self.repo, AttendanceConfig(exit_grace_seconds=0.0))
        self._confirm()
        self._read(1100.0, OUTSIDE)
        record, _, _ = self._read(5000.0, OUTSIDE)
        self.assertEqual(record.status, AttendanceStatus.PRESENT_CONFIRMED)

    def test_record_round_trip_keeps_exit_fields(self):
        record = AttendanceRecord("EST_11", "Renata", "S302", AttendanceStatus.LEFT_ROOM, 1.0,
                                  confirmed_at=0.5, outside_since=0.8, left_at=0.8)
        restored = AttendanceRecord.from_dict(record.to_dict())
        self.assertEqual(restored.status, AttendanceStatus.LEFT_ROOM)
        self.assertEqual((restored.outside_since, restored.left_at), (0.8, 0.8))

    def test_old_files_without_exit_fields_still_load(self):
        data = AttendanceRecord("EST_11", "Renata", "S302", AttendanceStatus.PRESENT_CONFIRMED, 1.0).to_dict()
        del data["outside_since"], data["left_at"]
        restored = AttendanceRecord.from_dict(data)
        self.assertIsNone(restored.left_at)


if __name__ == "__main__":
    unittest.main()

"""
Pruebas de Persistencia del Registro de Asistencia.

Regresión frente al defecto detectado en la auditoría: `InMemoryAttendanceRepository`
implementaba `save_to_file()` pero nunca `load_from_file()`, de modo que
`data/attendance_log.json` era de solo escritura y un reinicio del servidor perdía toda la
asistencia del día, pese a documentarse como registro persistente.
"""
import json
import os
import tempfile
import unittest

from backend.domain.attendance import AttendanceRecord, AttendanceStatus, Student
from backend.repositories.attendance_repo import InMemoryAttendanceRepository


class TestAttendancePersistence(unittest.TestCase):
    def setUp(self):
        handle, self.storage_path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        os.unlink(self.storage_path)  # que el repositorio lo cree desde cero
        self.addCleanup(self._remove_storage)

    def _remove_storage(self):
        if os.path.exists(self.storage_path):
            os.unlink(self.storage_path)

    def test_confirmed_attendance_survives_restart(self):
        """Confirmar, 'reiniciar' el servidor y comprobar que el registro sigue confirmado."""
        repo = InMemoryAttendanceRepository(self.storage_path)
        record = repo.get_record("EST_08", "S302")
        self.assertIsNotNone(record, "El padrón sembrado debe incluir a EST_08 en S302")

        record.status = AttendanceStatus.PRESENT_CONFIRMED
        record.confirmed_at = 1772700000.0
        record.last_rssi = -48.0
        record.samples_in_window = 3
        repo.save_record(record)

        # Simular reinicio: instancia nueva sobre el mismo fichero
        reloaded_repo = InMemoryAttendanceRepository(self.storage_path)
        reloaded = reloaded_repo.get_record("EST_08", "S302")

        self.assertEqual(reloaded.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertEqual(reloaded.confirmed_at, 1772700000.0)
        self.assertEqual(reloaded.last_rssi, -48.0)
        self.assertEqual(reloaded.samples_in_window, 3)

    def test_confirmation_is_written_immediately(self):
        """
        Una confirmación no puede quedarse en el buffer de escritura diferida:
        es el dato que no se puede perder ante una caída del proceso.
        """
        repo = InMemoryAttendanceRepository(self.storage_path, write_debounce_seconds=3600.0)
        record = repo.get_record("EST_08", "S302")
        record.status = AttendanceStatus.PRESENT_CONFIRMED
        record.confirmed_at = 1772700001.0
        repo.save_record(record)

        self.assertTrue(os.path.exists(self.storage_path))
        with open(self.storage_path, encoding="utf-8") as f:
            persisted = {r["student_id"]: r for r in json.load(f)}
        self.assertEqual(persisted["EST_08"]["status"], "PRESENT_CONFIRMED")
        self.assertFalse(repo.has_pending_write())

    def test_telemetry_updates_are_debounced(self):
        """Las actualizaciones de telemetría no deben reescribir el fichero en cada escaneo."""
        repo = InMemoryAttendanceRepository(self.storage_path, write_debounce_seconds=3600.0)
        repo.flush()  # estado base en disco
        mtime_before = os.path.getmtime(self.storage_path)

        record = repo.get_record("EST_08", "S302")
        for rssi in (-70.0, -68.0, -66.0):
            record.status = AttendanceStatus.APPROACHING
            record.last_rssi = rssi
            repo.save_record(record)

        self.assertEqual(
            os.path.getmtime(self.storage_path), mtime_before,
            "Con debounce activo, la telemetría no debe provocar escrituras a disco"
        )
        self.assertTrue(repo.has_pending_write())

        repo.flush()
        with open(self.storage_path, encoding="utf-8") as f:
            persisted = {r["student_id"]: r for r in json.load(f)}
        self.assertEqual(persisted["EST_08"]["last_rssi"], -66.0)
        self.assertFalse(repo.has_pending_write())

    def test_unknown_students_in_file_are_preserved(self):
        """Un registro persistido de un alumno fuera del padrón demo no debe descartarse."""
        seed_repo = InMemoryAttendanceRepository(self.storage_path)
        external = AttendanceRecord(
            student_id="EST_EXTERNO",
            student_name="Alumna Externa",
            room_id="S201",
            status=AttendanceStatus.PRESENT_CONFIRMED,
            last_seen=1772700002.0,
            confirmed_at=1772700002.0
        )
        seed_repo.save_record(external)

        reloaded = InMemoryAttendanceRepository(self.storage_path)
        recovered = reloaded.get_record("EST_EXTERNO", "S201")
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertEqual(recovered.student_name, "Alumna Externa")

    def test_repository_without_storage_path_never_writes(self):
        """El repositorio efímero usado en pruebas no debe tocar el disco."""
        repo = InMemoryAttendanceRepository()
        repo.register_student(Student("EST_TMP", "Temporal", "S101"))
        record = repo.get_record("EST_TMP", "S101")
        record.status = AttendanceStatus.PRESENT_CONFIRMED
        repo.save_record(record)
        repo.flush()

        self.assertFalse(os.path.exists(self.storage_path))
        self.assertFalse(repo.has_pending_write())


if __name__ == "__main__":
    unittest.main()

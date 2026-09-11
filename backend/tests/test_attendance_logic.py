"""
Pruebas Unitarias de Verificación: Lógica de Asistencia por Ventana de Permanencia.
Audita la máquina de estados reactiva (ABSENT -> APPROACHING -> AT_DOOR -> PRESENT_CONFIRMED)
y la inmunidad ante falsos positivos transitorios.
"""
import unittest
from backend.domain.building import Point2D
from backend.domain.attendance import AttendanceStatus, Student
from backend.repositories.attendance_repo import InMemoryAttendanceRepository
from backend.services.attendance_tracker import AttendanceTrackerService
from backend.config import AttendanceConfig

class TestAttendanceLogic(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryAttendanceRepository()
        self.config = AttendanceConfig(
            approaching_threshold_dbm=-70.0,
            classroom_threshold_dbm=-55.0,
            confirmation_window_scans=3
        )
        self.tracker = AttendanceTrackerService(self.repo, self.config)

        self.student_id = "EST_TEST"
        self.repo.register_student(Student(self.student_id, "Alumno Prueba", "S302"))
        self.target_center = Point2D(x=10.0, y=2.0)

    def test_approaching_transition(self):
        """Verifica que al detectar RSSI moderado (-65 dBm), el estado pase a APPROACHING."""
        pos = Point2D(x=10.0, y=7.0)  # En pasillo frente al aula
        record, changed, msg = self.tracker.process_student_presence(
            student_id=self.student_id,
            detected_floor=3,
            position=pos,
            target_room_id="S302",
            target_room_floor=3,
            target_room_center=self.target_center,
            strongest_rssi_to_room_ap=-65.0
        )
        self.assertTrue(changed)
        self.assertEqual(record.status, AttendanceStatus.APPROACHING)

    def test_permanence_window_confirmation(self):
        """
        Verifica que se requieran 3 escaneos continuos en la zona del aula
        para confirmar la asistencia definitivamente.
        """
        pos_inside = Point2D(x=10.0, y=2.5)  # Dentro del salón

        # Muestra 1: Pasa a AT_DOOR (1/3)
        rec1, ch1, _ = self.tracker.process_student_presence(
            self.student_id, 3, pos_inside, "S302", 3, self.target_center, strongest_rssi_to_room_ap=-50.0
        )
        self.assertEqual(rec1.status, AttendanceStatus.AT_DOOR)
        self.assertEqual(rec1.samples_in_window, 1)

        # Muestra 2: Permanece en AT_DOOR (2/3)
        rec2, ch2, _ = self.tracker.process_student_presence(
            self.student_id, 3, pos_inside, "S302", 3, self.target_center, strongest_rssi_to_room_ap=-49.0
        )
        self.assertEqual(rec2.status, AttendanceStatus.AT_DOOR)
        self.assertEqual(rec2.samples_in_window, 2)

        # Muestra 3: Completa ventana -> PRESENT_CONFIRMED
        rec3, ch3, msg = self.tracker.process_student_presence(
            self.student_id, 3, pos_inside, "S302", 3, self.target_center, strongest_rssi_to_room_ap=-48.0
        )
        self.assertTrue(ch3)
        self.assertEqual(rec3.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertIsNotNone(rec3.confirmed_at)

    def test_spurious_walkby_rejected(self):
        """
        Verifica que un estudiante que solo camina frente a la puerta (1 escaneo fuerte)
        y luego se aleja, NO sea confirmado como asistente (anti falsos positivos).
        """
        pos_door = Point2D(x=10.0, y=4.0)
        # 1 escaneo en puerta
        rec1, _, _ = self.tracker.process_student_presence(
            self.student_id, 3, pos_door, "S302", 3, self.target_center, strongest_rssi_to_room_ap=-52.0
        )
        self.assertEqual(rec1.status, AttendanceStatus.AT_DOOR)

        # Se aleja a otro piso (Piso 1)
        rec2, _, _ = self.tracker.process_student_presence(
            self.student_id, 1, Point2D(2.0, 5.0), "S302", 3, self.target_center, strongest_rssi_to_room_ap=-90.0
        )
        self.assertEqual(rec2.status, AttendanceStatus.ABSENT)
        self.assertEqual(rec2.samples_in_window, 0)
        self.assertIsNone(rec2.confirmed_at)

if __name__ == "__main__":
    unittest.main()

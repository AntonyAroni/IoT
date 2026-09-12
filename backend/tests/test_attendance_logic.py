"""
Pruebas Unitarias de Verificación: Lógica de Asistencia por Ventana de Permanencia.
Audita la máquina de estados reactiva (ABSENT -> APPROACHING -> AT_DOOR -> PRESENT_CONFIRMED)
y la inmunidad ante falsos positivos transitorios.
"""
import unittest
from unittest import mock
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


class TestPermanenceWindowExpiry(unittest.TestCase):
    """
    Audita la caducidad de la ventana de permanencia (AttendanceConfig.window_timeout_seconds).

    Sin ella el contador de muestras nunca expira y bastaría con pasar tres veces frente a la
    puerta, aunque fuera en días distintos, para confirmar la asistencia.
    """

    def setUp(self):
        self.repo = InMemoryAttendanceRepository()
        self.config = AttendanceConfig(
            confirmation_window_scans=3,
            window_timeout_seconds=15.0
        )
        self.tracker = AttendanceTrackerService(self.repo, self.config)
        self.student_id = "EST_TEST"
        self.repo.register_student(Student(self.student_id, "Alumno Prueba", "S302"))
        self.target_center = Point2D(x=10.0, y=2.0)
        self.pos_inside = Point2D(x=10.0, y=2.5)

    def _scan(self, rssi=-50.0):
        return self.tracker.process_student_presence(
            self.student_id, 3, self.pos_inside, "S302", 3, self.target_center,
            strongest_rssi_to_room_ap=rssi
        )

    def test_window_expires_after_timeout(self):
        """Dos muestras válidas, un hueco de 60 s, y la tercera NO debe confirmar."""
        with mock.patch("backend.services.attendance_tracker.time.time") as fake_time:
            fake_time.return_value = 1000.0
            rec, _, _ = self._scan()
            self.assertEqual(rec.samples_in_window, 1)

            fake_time.return_value = 1002.0
            rec, _, _ = self._scan()
            self.assertEqual(rec.samples_in_window, 2)

            # Hueco de 60 s: supera window_timeout_seconds, la racha se rompe.
            fake_time.return_value = 1062.0
            rec, _, _ = self._scan()

        self.assertEqual(
            rec.samples_in_window, 1,
            "La ventana debía reiniciarse tras superar window_timeout_seconds"
        )
        self.assertEqual(rec.status, AttendanceStatus.AT_DOOR)
        self.assertIsNone(
            rec.confirmed_at,
            "Tres lecturas no consecutivas NO deben confirmar la asistencia"
        )

    def test_window_survives_readings_within_timeout(self):
        """Tres muestras separadas por menos del timeout sí deben confirmar."""
        with mock.patch("backend.services.attendance_tracker.time.time") as fake_time:
            fake_time.return_value = 2000.0
            self._scan()
            fake_time.return_value = 2005.0
            self._scan()
            fake_time.return_value = 2010.0
            rec, changed, _ = self._scan()

        self.assertEqual(rec.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertTrue(changed)
        self.assertIsNotNone(rec.confirmed_at)


class TestClassroomCriterion(unittest.TestCase):
    """
    Audita que el umbral RSSI influya realmente en la decisión.

    Antes, la condición de zona de aula era `rssi >= umbral OR distancia <= 3.0`, de modo que la
    posición estimada confirmaba por sí sola y el umbral era decorativo.
    """

    def setUp(self):
        self.repo = InMemoryAttendanceRepository()
        self.student_id = "EST_TEST"
        self.repo.register_student(Student(self.student_id, "Alumno Prueba", "S302"))
        self.target_center = Point2D(x=10.0, y=2.0)

    def _confirm_attempts(self, threshold_dbm, rssi, position, scans=4):
        config = AttendanceConfig(
            classroom_threshold_dbm=threshold_dbm,
            confirmation_window_scans=3
        )
        repo = InMemoryAttendanceRepository()
        repo.register_student(Student(self.student_id, "Alumno Prueba", "S302"))
        tracker = AttendanceTrackerService(repo, config)
        record = None
        for _ in range(scans):
            record, _, _ = tracker.process_student_presence(
                self.student_id, 3, position, "S302", 3, self.target_center,
                strongest_rssi_to_room_ap=rssi
            )
        return record

    def test_measured_rssi_below_threshold_blocks_confirmation(self):
        """Dentro del radio geométrico pero con potencia medida insuficiente: no se confirma."""
        record = self._confirm_attempts(
            threshold_dbm=-55.0, rssi=-70.0, position=Point2D(10.0, 2.5)
        )
        self.assertNotEqual(
            record.status, AttendanceStatus.PRESENT_CONFIRMED,
            "Una potencia medida por debajo del umbral no debe confirmar asistencia"
        )

    def test_threshold_actually_changes_the_outcome(self):
        """El mismo escenario con distinto umbral debe producir distinto resultado."""
        strict = self._confirm_attempts(-45.0, rssi=-52.0, position=Point2D(10.0, 2.5))
        lenient = self._confirm_attempts(-60.0, rssi=-52.0, position=Point2D(10.0, 2.5))

        self.assertNotEqual(strict.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertEqual(lenient.status, AttendanceStatus.PRESENT_CONFIRMED)

    def test_estimated_rssi_falls_back_to_geometry(self):
        """Sin potencia medida se decide por geometría y el registro queda marcado como estimado."""
        config = AttendanceConfig(confirmation_window_scans=3)
        tracker = AttendanceTrackerService(self.repo, config)
        record = None
        for _ in range(3):
            record, _, _ = tracker.process_student_presence(
                self.student_id, 3, Point2D(10.0, 2.5), "S302", 3, self.target_center,
                strongest_rssi_to_room_ap=None
            )
        self.assertEqual(record.status, AttendanceStatus.PRESENT_CONFIRMED)
        self.assertFalse(
            record.rssi_is_measured,
            "Un RSSI derivado de la posición debe quedar marcado como no medido"
        )


if __name__ == "__main__":
    unittest.main()

"""
Servicio de Detección de Proximidad y Asistencia Inteligente por Ventana de Permanencia.
Implementa el criterio científico de Horus / Smart Campus:
Exige persistencia temporal (N escaneos continuos sobre el umbral en ventana de tiempo)
para evitar falsos positivos producidos por alumnos que solo caminan frente a la puerta.
"""
import time
from typing import Optional, Dict, Tuple
from ..domain.attendance import AttendanceRecord, AttendanceStatus, Student
from ..domain.building import Point2D
from ..repositories.base import IAttendanceRepository
from ..config import AttendanceConfig

class AttendanceTrackerService:
    def __init__(self, attendance_repo: IAttendanceRepository, config: Optional[AttendanceConfig] = None):
        self.attendance_repo = attendance_repo
        self.config = config or AttendanceConfig()

    def process_student_presence(
        self,
        student_id: str,
        detected_floor: int,
        position: Point2D,
        target_room_id: str,
        target_room_floor: int,
        target_room_center: Point2D,
        strongest_rssi_to_room_ap: Optional[float] = None
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        """
        Evalúa la proximidad del estudiante respecto a su salón de clase asignado.
        
        Retorna:
            (record: AttendanceRecord, status_changed: bool, message: Optional[str])
        """
        now = time.time()
        record = self.attendance_repo.get_record(student_id, target_room_id)
        if not record:
            student = self.attendance_repo.get_student(student_id)
            student_name = student.name if student else f"Alumno {student_id}"
            record = AttendanceRecord(
                student_id=student_id,
                student_name=student_name,
                room_id=target_room_id,
                status=AttendanceStatus.ABSENT,
                last_seen=now
            )

        previous_status = record.status
        distance_to_center = position.distance_to(target_room_center) if detected_floor == target_room_floor else 999.0

        # Si no se pasó RSSI directo del AP del salón, estimar proxy inversamente proporcional a la distancia
        if strongest_rssi_to_room_ap is None:
            # Aproximación Log-Distance típica en interiores: -40 dBm a 1m, ~ -55 dBm a 3m, ~ -70 dBm a 8m
            if detected_floor != target_room_floor:
                effective_rssi = -95.0
            else:
                effective_rssi = -40.0 - 25.0 * (max(0.5, distance_to_center) / 3.0)
        else:
            effective_rssi = strongest_rssi_to_room_ap

        record.last_rssi = round(effective_rssi, 1)
        record.last_seen = now

        # Si ya fue confirmado previamente, mantener confirmado
        if record.status == AttendanceStatus.PRESENT_CONFIRMED:
            self.attendance_repo.save_record(record)
            return record, False, None

        # Evaluar umbrales
        is_in_classroom_zone = (
            detected_floor == target_room_floor and
            (effective_rssi >= self.config.classroom_threshold_dbm or distance_to_center <= 3.0)
        )

        is_in_approaching_zone = (
            detected_floor == target_room_floor and
            (effective_rssi >= self.config.approaching_threshold_dbm or distance_to_center <= 9.0)
        )

        status_changed = False
        audit_msg = None

        if is_in_classroom_zone:
            # Incrementar contador de muestras continuas en ventana
            record.samples_in_window += 1
            if record.samples_in_window >= self.config.confirmation_window_scans:
                record.status = AttendanceStatus.PRESENT_CONFIRMED
                record.confirmed_at = now
                status_changed = True
                audit_msg = f"✅ ASISTENCIA CONFIRMADA: {record.student_name} validó permanencia ({record.samples_in_window} muestras, RSSI={record.last_rssi} dBm)."
            else:
                if record.status != AttendanceStatus.AT_DOOR:
                    record.status = AttendanceStatus.AT_DOOR
                    status_changed = True
                    audit_msg = f"🚪 EN PUERTA: {record.student_name} en umbral ({record.samples_in_window}/{self.config.confirmation_window_scans} muestras)."
        elif is_in_approaching_zone:
            # Resetea ventana si retrocede a zona de aproximación
            record.samples_in_window = max(0, record.samples_in_window - 1)
            if record.status != AttendanceStatus.APPROACHING:
                record.status = AttendanceStatus.APPROACHING
                status_changed = True
                audit_msg = f"📡 APROXIMÁNDOSE: {record.student_name} detectado en pasillo hacia {target_room_id} (RSSI={record.last_rssi} dBm)."
        else:
            # Fuera de rango
            record.samples_in_window = 0
            if record.status != AttendanceStatus.ABSENT:
                record.status = AttendanceStatus.ABSENT
                status_changed = True
                audit_msg = f"⚪ FUERA DE RANGO: {record.student_name} fuera de cobertura del salón {target_room_id}."

        self.attendance_repo.save_record(record)
        return record, status_changed, audit_msg

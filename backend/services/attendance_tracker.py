"""
Servicio de Detección de Proximidad y Asistencia Inteligente por Ventana de Permanencia.
Implementa el criterio científico de Horus / Smart Campus:
Exige persistencia temporal (N escaneos continuos sobre el umbral en ventana de tiempo)
para evitar falsos positivos producidos por alumnos que solo caminan frente a la puerta.

Criterio de decisión
--------------------
Se dispone de dos señales para decidir si un alumno está dentro del aula:

1. **Potencia medida** del AP del aula (`strongest_rssi_to_room_ap`), cuando el cliente la envía.
2. **Posición estimada** por el motor WKNN, de la que se deriva la distancia al centro del aula.

Cuando ambas están disponibles se exigen **las dos** (conjunción): es el criterio conservador
que persigue el proyecto, minimizar falsos positivos. Un `or` haría que la posición estimada
confirmara por sí sola la asistencia ignorando la potencia, que era el comportamiento anterior y
volvía irrelevante el umbral RSSI.

Cuando el cliente **no** envía la potencia medida, el RSSI se deriva de la distancia y por tanto
no es una señal independiente: exigir ambas sería redundante. En ese caso se decide solo por
geometría y se marca el registro como estimado (`rssi_is_measured = False`) para que la interfaz
no presente un valor calculado como si fuera medido.
"""
import time
from typing import Optional, Tuple

from ..config import AttendanceConfig
from ..domain.attendance import AttendanceRecord, AttendanceStatus
from ..domain.building import Point2D
from ..repositories.base import IAttendanceRepository

# Distancia asignada cuando el alumno está en otro piso: fuerza la salida de todas las zonas.
OFF_FLOOR_DISTANCE_METERS = 999.0
OFF_FLOOR_RSSI_DBM = -95.0


class AttendanceTrackerService:
    def __init__(self, attendance_repo: IAttendanceRepository, config: Optional[AttendanceConfig] = None):
        self.attendance_repo = attendance_repo
        self.config = config or AttendanceConfig()

    def _estimate_rssi_from_distance(self, distance_meters: float) -> float:
        """
        Proxy log-distance usado solo cuando el cliente no envía la potencia medida.
        Aproximación típica en interiores: -40 dBm a 1 m, ~-55 dBm a 3 m, ~-70 dBm a 8 m.
        """
        return -40.0 - 25.0 * (max(0.5, distance_meters) / 3.0)

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

        # Instante de la lectura anterior: necesario para medir el hueco temporal ANTES de
        # sobrescribir last_seen con la lectura actual.
        previous_last_seen = record.last_seen

        on_target_floor = detected_floor == target_room_floor
        distance_to_center = (
            position.distance_to(target_room_center) if on_target_floor else OFF_FLOOR_DISTANCE_METERS
        )

        rssi_is_measured = strongest_rssi_to_room_ap is not None
        if rssi_is_measured:
            effective_rssi = strongest_rssi_to_room_ap
        elif not on_target_floor:
            effective_rssi = OFF_FLOOR_RSSI_DBM
        else:
            effective_rssi = self._estimate_rssi_from_distance(distance_to_center)

        record.last_rssi = round(effective_rssi, 1)
        record.rssi_is_measured = rssi_is_measured
        record.last_seen = now

        # Si ya fue confirmado previamente, mantener confirmado
        if record.status == AttendanceStatus.PRESENT_CONFIRMED:
            self.attendance_repo.save_record(record)
            return record, False, None

        # ------------------------------------------------------------------
        # Caducidad de la ventana de permanencia
        # ------------------------------------------------------------------
        # La ventana exige N lecturas CONSECUTIVAS. Si entre dos lecturas transcurre más tiempo
        # del permitido, la racha se rompe: de lo contrario el contador nunca expira y tres
        # pasadas frente a la puerta en días distintos confirmarían la asistencia.
        window_expired = (
            record.samples_in_window > 0
            and previous_last_seen > 0.0
            and (now - previous_last_seen) > self.config.window_timeout_seconds
        )
        if window_expired:
            record.reset_window()

        # ------------------------------------------------------------------
        # Evaluación de zonas
        # ------------------------------------------------------------------
        within_classroom_radius = distance_to_center <= self.config.classroom_radius_meters
        within_approaching_radius = distance_to_center <= self.config.approaching_radius_meters
        above_classroom_threshold = effective_rssi >= self.config.classroom_threshold_dbm
        above_approaching_threshold = effective_rssi >= self.config.approaching_threshold_dbm

        # La zona de aula GOBIERNA la confirmación de asistencia: criterio conservador.
        # Con potencia medida, ésta y la geometría son señales independientes y se exigen ambas.
        # Sin potencia medida el RSSI se derivó de la distancia, así que exigir ambas sería
        # exigir dos veces la misma condición.
        if rssi_is_measured:
            is_in_classroom_zone = on_target_floor and above_classroom_threshold and within_classroom_radius
        else:
            is_in_classroom_zone = on_target_floor and within_classroom_radius

        # La zona de aproximación es puramente INFORMATIVA: alimenta el radar del aula y no
        # concede asistencia. Un falso "aproximándose" no tiene coste, mientras que exigir la
        # conjunción dejaría el radar vacío (a 9 m el AP del aula ya no es legible: el modelo
        # log-distance predice -115 dBm, por debajo de la sensibilidad del receptor).
        # Por eso aquí se mantiene la disyunción.
        is_in_approaching_zone = on_target_floor and (
            above_approaching_threshold or within_approaching_radius
        )

        status_changed = False
        audit_msg = None

        if is_in_classroom_zone:
            record.add_window_sample(now)

            # La confirmación exige recuento **y**, si se ha configurado, permanencia: cuántas
            # veces se ha visto al alumno y cuánto tiempo lleva dentro son cosas distintas.
            has_enough_samples = record.samples_in_window >= self.config.confirmation_window_scans
            has_enough_dwell = record.dwell_seconds >= self.config.minimum_dwell_seconds

            if has_enough_samples and has_enough_dwell:
                record.status = AttendanceStatus.PRESENT_CONFIRMED
                record.confirmed_at = now
                status_changed = True
                dwell_note = (
                    f", {record.dwell_seconds:.0f} s de permanencia"
                    if self.config.minimum_dwell_seconds > 0 else ""
                )
                audit_msg = (
                    f"✅ ASISTENCIA CONFIRMADA: {record.student_name} validó permanencia "
                    f"({record.samples_in_window} muestras{dwell_note}, RSSI={record.last_rssi} dBm"
                    f"{'' if rssi_is_measured else ', estimado'})."
                )
            else:
                entering_door = record.status != AttendanceStatus.AT_DOOR or window_expired

                # El alumno ya ha aportado las N muestras pero le falta permanencia. Sin este
                # aviso el tablero mostraría "3/3 muestras" sin confirmar y sin explicar por qué,
                # y el mensaje solo se emite al entrar al estado, así que nunca se vería.
                # Se reporta una sola vez por racha, al alcanzar el recuento exigido.
                dwell_pending_reached = (
                    has_enough_samples
                    and not has_enough_dwell
                    and record.samples_in_window == self.config.confirmation_window_scans
                )

                record.status = AttendanceStatus.AT_DOOR

                if entering_door or dwell_pending_reached:
                    status_changed = entering_door
                    expiry_note = " — ventana reiniciada por inactividad" if window_expired else ""
                    if has_enough_samples and not has_enough_dwell:
                        pending = self.config.minimum_dwell_seconds - record.dwell_seconds
                        detail = (
                            f"{record.samples_in_window} muestras, faltan {pending:.0f} s "
                            f"de permanencia"
                        )
                    else:
                        detail = (
                            f"{record.samples_in_window}/"
                            f"{self.config.confirmation_window_scans} muestras"
                        )
                    audit_msg = f"🚪 EN PUERTA: {record.student_name} en umbral ({detail}){expiry_note}."
        elif is_in_approaching_zone:
            # Retroceder al pasillo descuenta la lectura más antigua de la racha
            record.drop_oldest_window_sample()
            if record.status != AttendanceStatus.APPROACHING:
                record.status = AttendanceStatus.APPROACHING
                status_changed = True
                audit_msg = (
                    f"📡 APROXIMÁNDOSE: {record.student_name} detectado en pasillo hacia "
                    f"{target_room_id} (RSSI={record.last_rssi} dBm)."
                )
        else:
            # Fuera de rango
            record.reset_window()
            if record.status != AttendanceStatus.ABSENT:
                record.status = AttendanceStatus.ABSENT
                status_changed = True
                audit_msg = (
                    f"⚪ FUERA DE RANGO: {record.student_name} fuera de cobertura del salón "
                    f"{target_room_id}."
                )

        self.attendance_repo.save_record(record)
        return record, status_changed, audit_msg

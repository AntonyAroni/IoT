"""
Implementación del Repositorio de Asistencia.
Gestiona el padrón escolar y los estados de asistencia en tiempo real.

Persistencia
------------
El fichero de asistencia se **carga** al arrancar, no solo se escribe: antes era de solo
escritura y un reinicio del servidor perdía toda la asistencia del día pese a anunciarse como
registro persistente.

La escritura está fuera del camino crítico. Cada lectura Wi-Fi de cada alumno provocaba una
reescritura completa del fichero, I/O síncrono bloqueando el bucle de eventos en cada mensaje
WebSocket. Ahora se agrupan las escrituras con un intervalo mínimo, salvo las confirmaciones de
asistencia, que se persisten de inmediato por ser el dato que no se puede perder.
"""
import json
import os
import time
from typing import Dict, List, Optional

from ..domain.attendance import AttendanceRecord, AttendanceStatus, Student
from .base import IAttendanceRepository

DEFAULT_WRITE_DEBOUNCE_SECONDS = 2.0


class InMemoryAttendanceRepository(IAttendanceRepository):
    def __init__(
        self,
        storage_path: Optional[str] = None,
        write_debounce_seconds: float = DEFAULT_WRITE_DEBOUNCE_SECONDS
    ):
        self._students: Dict[str, Student] = {}
        # Clave: (student_id, room_id)
        self._records: Dict[str, AttendanceRecord] = {}
        self.storage_path = storage_path
        self.write_debounce_seconds = write_debounce_seconds
        self._last_write_at = 0.0
        self._pending_write = False

        # Inicializar estudiantes de demostración para los salones
        self._seed_default_students()

        # El estado persistido tiene prioridad sobre los registros vacíos recién sembrados.
        if storage_path and os.path.exists(storage_path):
            self.load_from_file(storage_path)

    def _seed_default_students(self) -> None:
        """Crea alumnos demo para cada uno de los 12 salones del colegio."""
        demo_students = [
            # Alumnos para Piso 1
            Student("EST_01", "Antony Mendoza", "S101"),
            Student("EST_02", "Valeria Gómez", "S102"),
            Student("EST_03", "Carlos Quispe", "S103"),
            # Alumnos para Piso 2
            Student("EST_04", "Lucía Morales", "S201"),
            Student("EST_05", "Mateo Flores", "S202"),
            Student("EST_06", "Sofía Vargas", "S203"),
            # Alumnos para Piso 3 (Ruta Principal de la Demo hacia S302)
            Student("EST_07", "Alejandro Silva", "S301"),
            Student("EST_08", "Diego Ramos (Demo Player)", "S302"),
            Student("EST_09", "Camila Castro", "S303"),
            # Alumnos para Piso 4
            Student("EST_10", "Joaquín Herrera", "S401"),
            Student("EST_11", "Renata Paredes", "S402"),
            Student("EST_12", "Gabriel Medina", "S403"),
        ]
        for s in demo_students:
            self.register_student(s)

    @staticmethod
    def _key(student_id: str, room_id: str) -> str:
        return f"{student_id}:{room_id}"

    def register_student(self, student: Student) -> None:
        self._students[student.id] = student
        key = self._key(student.id, student.enrolled_room)
        if key not in self._records:
            self._records[key] = AttendanceRecord(
                student_id=student.id,
                student_name=student.name,
                room_id=student.enrolled_room,
                status=AttendanceStatus.ABSENT,
                last_seen=0.0
            )

    def get_student(self, student_id: str) -> Optional[Student]:
        return self._students.get(student_id)

    def get_record(self, student_id: str, room_id: str) -> Optional[AttendanceRecord]:
        return self._records.get(self._key(student_id, room_id))

    def save_record(self, record: AttendanceRecord) -> None:
        self._records[self._key(record.student_id, record.room_id)] = record
        if not self.storage_path:
            return

        # Las confirmaciones son el dato que no se puede perder: se escriben de inmediato.
        # El resto (telemetría de posición y RSSI) tolera el agrupamiento.
        if record.status == AttendanceStatus.PRESENT_CONFIRMED:
            self.flush()
            return

        self._pending_write = True
        if (time.time() - self._last_write_at) >= self.write_debounce_seconds:
            self.flush()

    def get_room_records(self, room_id: str) -> List[AttendanceRecord]:
        return [
            rec for rec in self._records.values()
            if rec.room_id == room_id
        ]

    def get_students_for_room(self, room_id: str) -> List[Student]:
        return [
            s for s in self._students.values()
            if s.enrolled_room == room_id
        ]

    def load_from_file(self, filepath: str) -> None:
        """
        Carga los registros persistidos, sustituyendo los sembrados por defecto.

        Los alumnos desconocidos presentes en el fichero se conservan: puede tratarse de un
        padrón cargado por otra vía. No se inventan entradas de `Student` para ellos.
        """
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            record = AttendanceRecord.from_dict(item)
            self._records[self._key(record.student_id, record.room_id)] = record

    def flush(self) -> None:
        """Vuelca a disco de forma inmediata el estado en memoria."""
        if not self.storage_path:
            return
        self.save_to_file(self.storage_path)
        self._last_write_at = time.time()
        self._pending_write = False

    def has_pending_write(self) -> bool:
        """True si hay cambios en memoria todavía no volcados a disco."""
        return self._pending_write

    def get_all_students(self) -> List[Student]:
        """Padrón completo. Lo usa la selección dinámica de alumno multidispositivo."""
        return list(self._students.values())

    def save_to_file(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        data = [rec.to_dict() for rec in self._records.values()]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

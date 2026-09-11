"""
Implementación del Repositorio de Asistencia.
Gestiona el padrón escolar y los estados de asistencia en tiempo real.
"""
import json
import os
import time
from typing import List, Dict, Optional
from ..domain.attendance import AttendanceRecord, Student, AttendanceStatus
from .base import IAttendanceRepository

class InMemoryAttendanceRepository(IAttendanceRepository):
    def __init__(self, storage_path: Optional[str] = None):
        self._students: Dict[str, Student] = {}
        # Clave: (student_id, room_id)
        self._records: Dict[str, AttendanceRecord] = {}
        self.storage_path = storage_path

        # Inicializar estudiantes de demostración para los salones
        self._seed_default_students()

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

    def register_student(self, student: Student) -> None:
        self._students[student.id] = student
        key = f"{student.id}:{student.enrolled_room}"
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
        key = f"{student_id}:{room_id}"
        return self._records.get(key)

    def save_record(self, record: AttendanceRecord) -> None:
        key = f"{record.student_id}:{record.room_id}"
        self._records[key] = record
        if self.storage_path:
            self.save_to_file(self.storage_path)

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

    def save_to_file(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        data = [rec.to_dict() for rec in self._records.values()]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

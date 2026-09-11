"""
Interfaces / Protocolos de Persistencia (Principios SOLID - Dependency Inversion).
Define contratos abstractos para desacoplar los servicios de la base de datos o sistema de archivos.
"""
from typing import Protocol, List, Optional, Dict
from ..domain.fingerprint import RadioMapEntry
from ..domain.attendance import AttendanceRecord, Student

class IRadioMapRepository(Protocol):
    def save_entry(self, entry: RadioMapEntry) -> None:
        """Guarda o actualiza un punto de referencia en el radio-mapa."""
        ...

    def get_all_entries(self) -> List[RadioMapEntry]:
        """Obtiene todas las huellas de señal calibradas."""
        ...

    def get_entries_by_floor(self, floor_number: int) -> List[RadioMapEntry]:
        """Obtiene huellas correspondientes a un piso específico."""
        ...

    def clear(self) -> None:
        """Limpia el radio-mapa en memoria."""
        ...

    def load_from_file(self, filepath: str) -> None:
        """Carga huellas persistidas desde disco."""
        ...

    def save_to_file(self, filepath: str) -> None:
        """Guarda huellas en disco en formato JSON."""
        ...

class IAttendanceRepository(Protocol):
    def get_record(self, student_id: str, room_id: str) -> Optional[AttendanceRecord]:
        """Obtiene el registro actual de un alumno en un aula."""
        ...

    def save_record(self, record: AttendanceRecord) -> None:
        """Persiste o actualiza el registro de asistencia."""
        ...

    def get_room_records(self, room_id: str) -> List[AttendanceRecord]:
        """Obtiene todos los registros asociados a un salón."""
        ...

    def get_students_for_room(self, room_id: str) -> List[Student]:
        """Obtiene la lista de alumnos matriculados en un salón."""
        ...

    def register_student(self, student: Student) -> None:
        """Registra un alumno en el padrón escolar."""
        ...

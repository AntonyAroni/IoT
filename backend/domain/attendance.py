"""
Entidades del Dominio: Asistencia Inteligente y Estado de Presencia.
Gestiona estudiantes, estados de aproximación y confirmación por umbrales RSSI.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict

class AttendanceStatus(str, Enum):
    ABSENT = "ABSENT"                     # No detectado o fuera de rango
    APPROACHING = "APPROACHING"           # RSSI en rango preliminar (-70 a -56 dBm)
    AT_DOOR = "AT_DOOR"                   # RSSI fuerte (>= -55 dBm), iniciando ventana de permanencia
    PRESENT_CONFIRMED = "PRESENT_CONFIRMED" # Permanencia validada, asistencia confirmada

@dataclass
class Student:
    id: str                               # Ej. "EST_2026_01"
    name: str                             # Ej. "Antony Mendoza"
    enrolled_room: str                    # Aula donde le corresponde asistir hoy (ej. "S302")

@dataclass
class AttendanceRecord:
    student_id: str
    student_name: str
    room_id: str
    status: AttendanceStatus
    last_seen: float
    confirmed_at: Optional[float] = None
    last_rssi: Optional[float] = None
    samples_in_window: int = 0

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "student_name": self.student_name,
            "room_id": self.room_id,
            "status": self.status.value,
            "last_seen": self.last_seen,
            "confirmed_at": self.confirmed_at,
            "last_rssi": self.last_rssi,
            "samples_in_window": self.samples_in_window
        }

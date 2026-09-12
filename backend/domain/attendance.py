"""
Entidades del Dominio: Asistencia Inteligente y Estado de Presencia.
Gestiona estudiantes, estados de aproximación y confirmación por umbrales RSSI.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict

class AttendanceStatus(str, Enum):
    ABSENT = "ABSENT"                     # No detectado o fuera de rango
    APPROACHING = "APPROACHING"           # RSSI en rango preliminar (zona informativa del radar: RSSI >= -70 dBm o <= 9 m del centro)
    AT_DOOR = "AT_DOOR"                   # Dentro del aula (RSSI >= -70 dBm Y <= 4 m del centro), iniciando ventana de permanencia
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
    # False cuando `last_rssi` no es una medición sino un valor derivado de la posición
    # estimada. La interfaz no debe presentar un valor calculado como si fuera medido.
    rssi_is_measured: bool = False

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "student_name": self.student_name,
            "room_id": self.room_id,
            "status": self.status.value,
            "last_seen": self.last_seen,
            "confirmed_at": self.confirmed_at,
            "last_rssi": self.last_rssi,
            "samples_in_window": self.samples_in_window,
            "rssi_is_measured": self.rssi_is_measured
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AttendanceRecord":
        """Reconstruye un registro persistido en disco."""
        return cls(
            student_id=data["student_id"],
            student_name=data["student_name"],
            room_id=data["room_id"],
            status=AttendanceStatus(data["status"]),
            last_seen=data.get("last_seen", 0.0),
            confirmed_at=data.get("confirmed_at"),
            last_rssi=data.get("last_rssi"),
            samples_in_window=data.get("samples_in_window", 0),
            rssi_is_measured=data.get("rssi_is_measured", False)
        )

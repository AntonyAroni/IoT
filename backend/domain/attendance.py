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
    # False cuando `last_rssi` no es una medición sino un valor derivado de la posición
    # estimada. La interfaz no debe presentar un valor calculado como si fuera medido.
    rssi_is_measured: bool = False

    # Marcas de tiempo de las lecturas que cumplen el criterio de aula y forman la racha actual.
    # Antes solo se guardaba un contador, que permite exigir "N lecturas seguidas" pero no
    # "N lecturas a lo largo de al menos T segundos": con un contador no se sabe cuánto tiempo
    # lleva el alumno en el aula, solo cuántas veces se le ha visto.
    window_sample_times: List[float] = field(default_factory=list)

    @property
    def samples_in_window(self) -> int:
        """Número de lecturas de la racha actual."""
        return len(self.window_sample_times)

    @property
    def dwell_seconds(self) -> float:
        """Tiempo transcurrido entre la primera y la última lectura de la racha actual."""
        if len(self.window_sample_times) < 2:
            return 0.0
        return self.window_sample_times[-1] - self.window_sample_times[0]

    def add_window_sample(self, timestamp: float) -> None:
        self.window_sample_times.append(timestamp)

    def drop_oldest_window_sample(self) -> None:
        """Descuenta una lectura de la racha; usado cuando el alumno retrocede al pasillo."""
        if self.window_sample_times:
            self.window_sample_times.pop(0)

    def reset_window(self) -> None:
        self.window_sample_times.clear()

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
            "dwell_seconds": round(self.dwell_seconds, 1),
            "rssi_is_measured": self.rssi_is_measured,
            "window_sample_times": self.window_sample_times
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AttendanceRecord":
        """
        Reconstruye un registro persistido en disco.

        Compatibilidad con ficheros anteriores: si solo traen el contador `samples_in_window` y
        no las marcas de tiempo, se reconstruye una racha de esa longitud situada toda en
        `last_seen`. El recuento se conserva y la permanencia calculada queda en 0 s, que es lo
        honesto cuando no se guardó cuándo ocurrieron esas lecturas.
        """
        sample_times = data.get("window_sample_times")
        if sample_times is None:
            legacy_count = data.get("samples_in_window", 0)
            last_seen = data.get("last_seen", 0.0)
            sample_times = [last_seen] * legacy_count

        return cls(
            student_id=data["student_id"],
            student_name=data["student_name"],
            room_id=data["room_id"],
            status=AttendanceStatus(data["status"]),
            last_seen=data.get("last_seen", 0.0),
            confirmed_at=data.get("confirmed_at"),
            last_rssi=data.get("last_rssi"),
            rssi_is_measured=data.get("rssi_is_measured", False),
            window_sample_times=list(sample_times)
        )

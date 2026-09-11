"""
Entidades del Dominio: Huellas de Señal Wi-Fi (Fingerprinting) y Mapa de Radio.
Modela vectores RSSI, puntos de referencia (RPs) y el radio-mapa de calibración.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from .building import Point2D

@dataclass(frozen=True)
class ScanReading:
    """Una lectura individual de un Access Point detectado en un escaneo."""
    bssid: str            # Dirección MAC única del AP (ej. "aa:bb:cc:11:22:33")
    ssid: str             # Nombre de la red Wi-Fi (ej. "ESCUELA_DOCENTES")
    rssi: float           # Intensidad de la señal en dBm (típicamente entre -30 y -95)
    frequency: Optional[int] = None  # 2412, 5180 MHz, etc.

@dataclass
class FingerprintVector:
    """Vector de intensidades de señal recibido en un instante de tiempo."""
    timestamp: float
    device_id: str
    readings: Dict[str, float]  # Mapeo BSSID -> RSSI (dBm)

    def get_rssi(self, bssid: str, default: float = -105.0) -> float:
        return self.readings.get(bssid.lower(), default)

@dataclass
class ReferencePoint:
    """Punto físico calibrado en el edificio (RP - Reference Point)."""
    id: str                    # Ej. "RP_P1_S101_Center", "RP_P2_Hall_1"
    floor_number: int          # 1 a 4
    position: Point2D          # Coordenada métrica 2D
    label: str                 # Descripción amigable
    room_id: Optional[str] = None  # Si está asociado a un aula específica

@dataclass
class RadioMapEntry:
    """Registro estadístico calibrado de un RP en la base de datos."""
    reference_point: ReferencePoint
    rssi_means: Dict[str, float]       # BSSID -> Media de RSSI
    rssi_std: Dict[str, float] = field(default_factory=dict) # Desviación estándar
    sample_count: int = 1

    def to_dict(self) -> dict:
        return {
            "id": self.reference_point.id,
            "floor_number": self.reference_point.floor_number,
            "position": {"x": self.reference_point.position.x, "y": self.reference_point.position.y},
            "label": self.reference_point.label,
            "room_id": self.reference_point.room_id,
            "rssi_means": self.rssi_means,
            "rssi_std": self.rssi_std,
            "sample_count": self.sample_count
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RadioMapEntry":
        pos = Point2D(x=data["position"]["x"], y=data["position"]["y"])
        rp = ReferencePoint(
            id=data["id"],
            floor_number=data["floor_number"],
            position=pos,
            label=data["label"],
            room_id=data.get("room_id")
        )
        return cls(
            reference_point=rp,
            rssi_means=data["rssi_means"],
            rssi_std=data.get("rssi_std", {}),
            sample_count=data.get("sample_count", 1)
        )

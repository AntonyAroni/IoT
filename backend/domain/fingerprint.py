"""
Entidades del Dominio: Huellas de Señal Wi-Fi (Fingerprinting) y Mapa de Radio.
Modela vectores RSSI, puntos de referencia (RPs) y el radio-mapa de calibración.
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
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

# Aportación de las huellas guardadas antes de que existieran las aportaciones por móvil.
LEGACY_DEVICE_ID = "anterior"


def merge_contributions(contributions: Dict[str, dict]) -> Tuple[Dict[str, float], Dict[str, float], int]:
    """
    Combina las huellas de varios móviles en una sola, ponderando por número de muestras.

    Cada AP se promedia solo entre los móviles que lo vieron. Imputarle -105 dBm al que no lo
    detectó castigaría la diferencia de antenas, no la distancia: en la prueba del 29/10 la
    puerta (móvil A) y el centro (móvil B) de la S302 solo compartían 4 de 24 AP.
    La desviación combinada suma la varianza de cada móvil y la dispersión entre sus medias.
    """
    means: Dict[str, float] = {}
    stds: Dict[str, float] = {}
    bssids = {b for c in contributions.values() for b in c["rssi_means"]}
    for bssid in bssids:
        parts = [
            (c["sample_count"], c["rssi_means"][bssid], c["rssi_std"].get(bssid, 0.0))
            for c in contributions.values() if bssid in c["rssi_means"]
        ]
        total = sum(n for n, _, _ in parts)
        mean = sum(n * m for n, m, _ in parts) / total
        variance = sum(n * (s ** 2 + (m - mean) ** 2) for n, m, s in parts) / total
        means[bssid] = round(mean, 2)
        stds[bssid] = round(math.sqrt(variance), 2)
    return means, stds, sum(c["sample_count"] for c in contributions.values())


@dataclass
class RadioMapEntry:
    """Registro estadístico calibrado de un RP en la base de datos."""
    reference_point: ReferencePoint
    rssi_means: Dict[str, float]       # BSSID -> Media de RSSI
    rssi_std: Dict[str, float] = field(default_factory=dict) # Desviación estándar
    sample_count: int = 1
    # Huella de cada móvil que calibró el punto (device_id -> rssi_means, rssi_std,
    # sample_count, updated_at). `rssi_means` es su combinación y es lo único que lee el WKNN.
    contributions: Dict[str, dict] = field(default_factory=dict)

    def add_contribution(self, device_id: str, rssi_means: Dict[str, float],
                         rssi_std: Dict[str, float], sample_count: int, updated_at: float) -> None:
        """Añade la huella de un móvil, o sustituye la anterior del mismo móvil (recalibración)."""
        if not self.contributions and self.rssi_means:
            self.contributions[LEGACY_DEVICE_ID] = {
                "rssi_means": dict(self.rssi_means), "rssi_std": dict(self.rssi_std),
                "sample_count": self.sample_count, "updated_at": None,
            }
        self.contributions[device_id] = {
            "rssi_means": dict(rssi_means), "rssi_std": dict(rssi_std),
            "sample_count": sample_count, "updated_at": updated_at,
        }
        self._recompute()

    def remove_contribution(self, device_id: str) -> bool:
        if device_id not in self.contributions:
            return False
        del self.contributions[device_id]
        self._recompute()
        return True

    def _recompute(self) -> None:
        if self.contributions:
            self.rssi_means, self.rssi_std, self.sample_count = merge_contributions(self.contributions)
        else:
            self.rssi_means, self.rssi_std, self.sample_count = {}, {}, 0

    def to_dict(self) -> dict:
        return {
            "id": self.reference_point.id,
            "floor_number": self.reference_point.floor_number,
            "x": self.reference_point.position.x,
            "y": self.reference_point.position.y,
            "position": {"x": self.reference_point.position.x, "y": self.reference_point.position.y},
            "label": self.reference_point.label,
            "room_id": self.reference_point.room_id,
            "rssi_means": self.rssi_means,
            "rssi_std": self.rssi_std,
            "sample_count": self.sample_count,
            "contributions": self.contributions
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RadioMapEntry":
        if "position" in data and isinstance(data["position"], dict):
            pos = Point2D(x=data["position"]["x"], y=data["position"]["y"])
        else:
            pos = Point2D(x=data.get("x", 0.0), y=data.get("y", 0.0))
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
            sample_count=data.get("sample_count", 1),
            contributions=data.get("contributions", {})
        )

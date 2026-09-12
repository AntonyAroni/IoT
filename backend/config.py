"""
Módulo de Configuración Central del Sistema IPS y Asistencia IoT.
Define hiperparámetros para WKNN, umbrales de proximidad de radiofrecuencia y ajustes de red.
"""
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass(frozen=True)
class WKNNConfig:
    """Configuración para el algoritmo Weighted k-Nearest Neighbors."""
    k: int = 3
    epsilon: float = 1e-6
    default_absent_rssi: float = -105.0  # RSSI asignado cuando un AP no es detectado
    metric: str = "euclidean"  # 'euclidean' o 'manhattan'
    enable_kalman_filter: bool = True
    enable_adaptive_k: bool = True

@dataclass(frozen=True)
class AttendanceConfig:
    """Umbrales de proximidad y permanencia para la confirmación de asistencia."""
    approaching_threshold_dbm: float = -70.0  # Alumno en radio de detección
    classroom_threshold_dbm: float = -55.0    # Alumno dentro o en puerta del salón
    confirmation_window_scans: int = 3        # Muestras continuas requeridas sobre el umbral
    window_timeout_seconds: float = 15.0      # Tiempo máximo entre lecturas consecutivas

@dataclass(frozen=True)
class ServerConfig:
    """Configuración del servidor FastAPI y WebSockets."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    radio_map_file: str = "data/radio_map.json"
    attendance_log_file: str = "data/attendance_log.json"
    building_config_file: str = "data/building_model.json"

@dataclass
class SystemConfig:
    wknn: WKNNConfig = field(default_factory=WKNNConfig)
    attendance: AttendanceConfig = field(default_factory=AttendanceConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

# Instancia global por defecto
config = SystemConfig()

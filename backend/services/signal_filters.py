"""
Módulo de Filtros Híbridos para Optimización de RSSI y Posicionamiento IPS.
Basado en literatura científica reciente (IEEE INFOCOM, Sensors MDPI, ACM MobiSys):
1. Filtro de Kalman 1D Discreto para mitigación de desvanecimiento por multi-trayecto (Multipath Fading).
2. Diferencial de Fuerza de Señal (SSD / D-RSSI) para eliminar sesgo de antena entre marcas de smartphones.
3. Suavizado Cinemático de Trayectoria 2D (Anti-Teletransportación) con límite de velocidad peatonal.
4. Selección Adaptativa de Hiperparámetro k para WKNN.
"""
import math
import time
from typing import Dict, List, Tuple, Optional
from ..domain.building import Point2D
from ..domain.fingerprint import RadioMapEntry

# Ruido de proceso del filtro de Kalman sobre el RSSI.
#
# El valor original, 0.08, asumía que el RSSI de un AP apenas cambia entre lecturas. Eso es
# cierto para un dispositivo quieto, pero falso para un alumno caminando: el filtro se resistía
# al movimiento real y arrastraba la posición estimada. Medido sobre una trayectoria de 11 pasos
# a paso peatonal, 30 repeticiones:
#
#     q      error medio (marcha)   peor caso
#     0.08         1.46 m            3.31 m   <- valor original
#     0.50         1.02 m            2.80 m
#     2.00         0.78 m            2.72 m
#     8.00         0.62 m            2.29 m   <- adoptado
#    30.00         0.58 m            2.28 m
#   sin Kalman     0.56 m            2.60 m
#
# Con q = 8 el filtro deja de estorbar al movimiento y conserva su ventaja real: acota el peor
# caso (2.29 m frente a 2.60 m sin filtrar) a cambio de 0.06 m de error medio. Subir más q lo
# acerca a no filtrar en absoluto.
DEFAULT_PROCESS_NOISE = 8.0
DEFAULT_MEASUREMENT_NOISE = 2.5


class KalmanFilter1D:
    """
    Filtro de Kalman 1D discreto para una serie temporal de RSSI de un único BSSID.
    Modela el RSSI real como un estado estocástico atenuado por ruido gaussiano.
    """
    def __init__(self, initial_value: float, process_noise: float = DEFAULT_PROCESS_NOISE,
                 measurement_noise: float = DEFAULT_MEASUREMENT_NOISE):
        self.x = initial_value         # Estimación del estado (RSSI filtrado)
        self.p = 1.0                   # Varianza del error de estimación inicial
        self.q = process_noise         # Ruido del proceso (dinámica peatonal)
        self.r = measurement_noise   # Ruido de medición de antena (varianza típica ~ 2.0-3.5 dBm)

    def update(self, measurement: float) -> float:
        # 1. Predicción
        p_pred = self.p + self.q

        # 2. Ganancia de Kalman
        k_gain = p_pred / (p_pred + self.r)

        # 3. Corrección
        self.x = self.x + k_gain * (measurement - self.x)
        self.p = (1.0 - k_gain) * p_pred

        return self.x

class MultiBSSIDKalmanFilter:
    """
    Banco de Filtros de Kalman independientes para cada BSSID detectado por el dispositivo.
    Conserva la historia temporal de cada punto de acceso.
    """
    def __init__(self, process_noise: float = DEFAULT_PROCESS_NOISE,
                 measurement_noise: float = DEFAULT_MEASUREMENT_NOISE, ttl_seconds: float = 10.0):
        self.filters: Dict[str, KalmanFilter1D] = {}
        self.last_updated: Dict[str, float] = {}
        self.q = process_noise
        self.r = measurement_noise
        self.ttl = ttl_seconds

    def filter_readings(self, readings: Dict[str, float], current_time: Optional[float] = None) -> Dict[str, float]:
        now = current_time or time.time()
        filtered = {}

        # Limpiar filtros caducados (APs que ya no se reciben)
        stale = [b for b, t in self.last_updated.items() if now - t > self.ttl]
        for b in stale:
            del self.filters[b]
            del self.last_updated[b]

        for bssid, raw_rssi in readings.items():
            b_clean = bssid.lower()
            if b_clean not in self.filters:
                self.filters[b_clean] = KalmanFilter1D(raw_rssi, self.q, self.r)
            else:
                self.filters[b_clean].update(raw_rssi)

            filtered[b_clean] = round(self.filters[b_clean].x, 2)
            self.last_updated[b_clean] = now

        return filtered

class TrajectoryKinematicFilter2D:
    """
    Filtro cinemático para coordenadas 2D.
    Previene el 'teletransporte' de coordenadas entre aulas contiguas cuando ocurre
    una fluctuación puntual de señal, acotando el desplazamiento según la velocidad peatonal.
    """
    def __init__(self, max_speed_mps: float = 1.8, smoothing_factor: float = 0.65):
        self.last_pos: Optional[Point2D] = None
        self.last_time: Optional[float] = None
        self.max_speed = max_speed_mps  # Velocidad máxima humana típica caminando: 1.8 m/s
        self.alpha = smoothing_factor   # Ponderación para media móvil exponencial (EMA)

    def filter_position(self, raw_pos: Point2D, current_time: Optional[float] = None) -> Point2D:
        now = current_time or time.time()
        if self.last_pos is None or self.last_time is None:
            self.last_pos = raw_pos
            self.last_time = now
            return raw_pos

        dt = max(0.1, min(3.0, now - self.last_time))
        max_allowed_dist = (self.max_speed * dt) + 0.8  # Margen de tolerancia de 0.8m

        measured_dist = self.last_pos.distance_to(raw_pos)

        if measured_dist > max_allowed_dist:
            # Acotar el salto al vector unitario escalado por la distancia admisible
            dx = raw_pos.x - self.last_pos.x
            dy = raw_pos.y - self.last_pos.y
            norm = math.sqrt(dx * dx + dy * dy)
            clamped_x = self.last_pos.x + (dx / norm) * max_allowed_dist
            clamped_y = self.last_pos.y + (dy / norm) * max_allowed_dist
            target_pos = Point2D(clamped_x, clamped_y)
        else:
            target_pos = raw_pos

        # Suavizado exponencial (EMA): p = alpha * target + (1 - alpha) * last
        smooth_x = self.alpha * target_pos.x + (1.0 - self.alpha) * self.last_pos.x
        smooth_y = self.alpha * target_pos.y + (1.0 - self.alpha) * self.last_pos.y

        filtered = Point2D(round(smooth_x, 3), round(smooth_y, 3))
        self.last_pos = filtered
        self.last_time = now
        return filtered

    def reset(self):
        self.last_pos = None
        self.last_time = None

def compute_differential_rssi(readings: Dict[str, float]) -> Dict[Tuple[str, str], float]:
    """
    Calcula el vector de Diferencias de Señal (Signal Strength Difference / SSD):
    SSD_ij = RSSI_i - RSSI_j
    Elimina el sesgo de ganancia de hardware inherente a distintas marcas de smartphones
    (Torres-Sospedra et al., UJIIndoorLoc).
    """
    sorted_bssids = sorted(readings.keys())
    diffs = {}
    n = len(sorted_bssids)
    for i in range(n):
        for j in range(i + 1, n):
            b_i = sorted_bssids[i]
            b_j = sorted_bssids[j]
            diffs[(b_i, b_j)] = round(readings[b_i] - readings[b_j], 2)
    return diffs

def select_adaptive_k(neighbor_distances: List[Tuple[RadioMapEntry, float]], min_k: int = 2, max_k: int = 4, threshold_close: float = 3.5) -> int:
    """
    Selecciona dinámicamente el hiperparámetro k según la similitud del vecino más cercano.
    - Si el vecino más próximo está muy cerca en el espacio de señal (d1 < 3.5), se usa un k pequeño (2)
      para no distorsionar la posición con puntos lejanos.
    - Si la dispersión es mayor, se usa k=3 o 4 para interpolación suave.
    """
    if not neighbor_distances:
        return min_k

    first_dist = neighbor_distances[0][1]
    if first_dist <= threshold_close:
        return min_k
    elif first_dist <= threshold_close * 2.0:
        return min(3, max_k)
    else:
        return max_k

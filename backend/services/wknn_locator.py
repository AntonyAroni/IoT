"""
Servicio de Localización 2D: Weighted k-Nearest Neighbors (WKNN).
Calcula la coordenada métrica continua (x, y) en el plano del piso identificado
a partir del espacio de características RSSI.
"""
import math
from typing import List, Tuple, Optional, Dict
from ..domain.building import Point2D
from ..domain.fingerprint import FingerprintVector, RadioMapEntry
from ..repositories.base import IRadioMapRepository
from ..config import WKNNConfig

class WKNNPositioningService:
    def __init__(self, radio_map_repo: IRadioMapRepository, config: Optional[WKNNConfig] = None):
        self.radio_map_repo = radio_map_repo
        self.config = config or WKNNConfig()

    def estimate_position(self, floor_number: int, vector: FingerprintVector) -> Tuple[Point2D, List[Tuple[RadioMapEntry, float]]]:
        """
        Estima la coordenada (x, y) en el piso especificado mediante WKNN.
        
        Retorna:
            (posicion_estimada: Point2D, lista de los k vecinos más cercanos con su distancia RSSI)
        """
        floor_entries = self.radio_map_repo.get_entries_by_floor(floor_number)
        if not floor_entries:
            # Si no hay huellas en ese piso, retornar centroide por defecto (ej. 10.0, 5.0)
            return Point2D(10.0, 5.0), []

        online_readings = {k.lower(): v for k, v in vector.readings.items()}
        neighbor_distances: List[Tuple[RadioMapEntry, float]] = []

        for entry in floor_entries:
            # Calcular distancia en espacio de radiofrecuencia (espacio RSSI)
            dist_sq = 0.0
            all_bssids = set(online_readings.keys()).union(entry.rssi_means.keys())
            
            if not all_bssids:
                continue

            for bssid in all_bssids:
                r_online = online_readings.get(bssid, self.config.default_absent_rssi)
                r_offline = entry.rssi_means.get(bssid, self.config.default_absent_rssi)
                delta = r_online - r_offline

                # Ponderación por varianza (Horus): normalizar la discrepancia por la
                # desviación estándar medida en calibración, para que un AP inestable no
                # contamine la distancia tanto como uno estable.
                if self.config.use_std_weighting:
                    std = entry.rssi_std.get(bssid)
                    if std is not None:
                        delta /= max(std, self.config.min_std_dbm)

                if self.config.metric == "manhattan":
                    dist_sq += abs(delta)
                else:
                    dist_sq += delta ** 2

            dist = dist_sq if self.config.metric == "manhattan" else math.sqrt(dist_sq)
            neighbor_distances.append((entry, dist))

        if not neighbor_distances:
            first_pos = floor_entries[0].reference_point.position
            return Point2D(first_pos.x, first_pos.y), []

        # Ordenar por menor distancia de señal (mayor similitud)
        neighbor_distances.sort(key=lambda item: item[1])

        # Tomar los k vecinos más cercanos
        k_val = min(self.config.k, len(neighbor_distances))
        top_k = neighbor_distances[:k_val]

        # Ponderación inversa a la distancia: w_i = 1 / (d_i + epsilon)
        weights: List[float] = []
        for _, d in top_k:
            w = 1.0 / (d + self.config.epsilon)
            weights.append(w)

        total_weight = sum(weights)
        if total_weight == 0:
            total_weight = 1.0

        est_x = sum(w * entry.reference_point.position.x for (entry, _), w in zip(top_k, weights)) / total_weight
        est_y = sum(w * entry.reference_point.position.y for (entry, _), w in zip(top_k, weights)) / total_weight

        return Point2D(round(est_x, 2), round(est_y, 2)), top_k

"""
Generador de Radio-Mapa de Calibración para el Edificio Escolar (4 Pisos, 12 Salones).
Genera la base de datos de huellas de señal (Radio Map) con 40 Puntos de Referencia (RPs)
utilizando el modelo físico de propagación en interiores (RADAR / Horus).

Muestreo
--------
Cada punto de referencia se calibra tomando una ráfaga de lecturas, igual que hace el modo
calibrador del cliente Android, y se guardan media y desviación estándar por BSSID. La versión
anterior declaraba `sample_count=15` pero tomaba **una sola** lectura de `calculate_rssi`, de
modo que la "media" era un único valor ruidoso y `rssi_std` quedaba vacío en las 40 entradas.

Los AP que no se detectan en una ráfaga concreta aportan `ABSENT_RSSI_DBM` a la media, en lugar
de excluirse. Excluirlos produce sesgo de supervivencia: un AP visto en 2 de 15 ráfagas recibiría
la media de sus dos lecturas más fuertes. El criterio replica el del cliente Android.
"""
import argparse
import json
import os
import random
from statistics import mean, pstdev
from typing import Dict, List

from backend.domain.building import Point2D
from backend.domain.fingerprint import ReferencePoint, RadioMapEntry
from backend.domain.graph import create_default_school_graph
from mobile_app.virtual_sensor.virtual_scanner import SimulatedAP
from calibration_tools.console import enable_unicode_output

DEFAULT_OUTPUT = "data/radio_map.json"
DEFAULT_SEED = 42
DEFAULT_SAMPLES = 15

DETECTION_THRESHOLD_DBM = -95.0   # Sensibilidad del receptor
ABSENT_RSSI_DBM = -105.0          # Igual que WKNNConfig.default_absent_rssi
MIN_DETECTION_RATE = 0.30         # Igual que CalibratorManager.MIN_DETECTION_RATE


def _calibrate_point(aps: List[SimulatedAP], floor: int, position: Point2D, samples: int):
    """
    Simula una ráfaga de calibración en un punto y devuelve (medias, desviaciones).

    Replica el procedimiento del calibrador real: varias lecturas consecutivas, imputación del
    valor suelo cuando el AP no se detecta, y descarte de los AP demasiado intermitentes.
    """
    observations: Dict[str, List[float]] = {ap.bssid: [] for ap in aps}

    for _ in range(samples):
        for ap in aps:
            value = ap.calculate_rssi(floor, position.x, position.y)
            # El AP solo entra en la lectura si supera la sensibilidad del receptor
            observations[ap.bssid].append(
                value if value > DETECTION_THRESHOLD_DBM else ABSENT_RSSI_DBM
            )

    means: Dict[str, float] = {}
    stds: Dict[str, float] = {}

    for bssid, values in observations.items():
        detections = sum(1 for v in values if v > ABSENT_RSSI_DBM)
        if detections / samples < MIN_DETECTION_RATE:
            continue
        means[bssid] = round(mean(values), 1)
        stds[bssid] = round(pstdev(values), 2) if len(values) > 1 else 0.0

    return means, stds


def generate_school_radio_map(
    output_path: str = DEFAULT_OUTPUT,
    seed: int = DEFAULT_SEED,
    samples: int = DEFAULT_SAMPLES,
):
    """Genera y guarda el dataset de calibración de 40 puntos de referencia."""
    # `SimulatedAP.calculate_rssi` usa el módulo `random`, así que la semilla se fija aquí para
    # que el dataset sea reproducible entre ejecuciones.
    random.seed(seed)

    graph, floors = create_default_school_graph()

    # Configuración de 12 Access Points distribuidos en los 4 pisos
    aps: List[SimulatedAP] = []
    for f in range(1, 5):
        aps.append(SimulatedAP(f"ap_p{f}_west", f"WIFI_COLEGIO_P{f}_W", floor=f, x=4.0, y=3.5))
        aps.append(SimulatedAP(f"ap_p{f}_east", f"WIFI_COLEGIO_P{f}_E", floor=f, x=16.0, y=3.5))
        aps.append(SimulatedAP(f"ap_p{f}_room02", f"AP_AULA_{f}02", floor=f, x=10.0, y=2.0))

    entries: List[RadioMapEntry] = []

    def add_entry(rp: ReferencePoint, floor: int, position: Point2D) -> None:
        means, stds = _calibrate_point(aps, floor, position, samples)
        entries.append(RadioMapEntry(
            reference_point=rp,
            rssi_means=means,
            rssi_std=stds,
            sample_count=samples
        ))

    # 1. Puntos de Referencia en Salones (Centro y Entrada de cada aula: 24 puntos)
    for floor_num, fl in floors.items():
        for r in fl.rooms:
            add_entry(
                ReferencePoint(
                    id=f"RP_{r.id}_Center",
                    floor_number=floor_num,
                    position=r.center,
                    label=f"Centro del {r.name}",
                    room_id=r.id
                ),
                floor_num, r.center
            )
            add_entry(
                ReferencePoint(
                    id=f"RP_{r.id}_Door",
                    floor_number=floor_num,
                    position=r.entrance,
                    label=f"Puerta de Acceso del {r.name}",
                    room_id=r.id
                ),
                floor_num, r.entrance
            )

    # 2. Puntos de Referencia en Pasillos (3 por piso: 12 puntos)
    for floor_num in range(1, 5):
        hallways = [
            (f"RP_P{floor_num}_Hall_W", Point2D(2.0, 5.0), f"Pasillo Oeste Piso {floor_num}"),
            (f"RP_P{floor_num}_Hall_C", Point2D(10.0, 5.0), f"Pasillo Central Piso {floor_num}"),
            (f"RP_P{floor_num}_Hall_E", Point2D(18.0, 5.0), f"Pasillo Este Piso {floor_num}")
        ]
        for rp_id, pos, label in hallways:
            add_entry(
                ReferencePoint(id=rp_id, floor_number=floor_num, position=pos, label=label),
                floor_num, pos
            )

    # 3. Puntos de Referencia en Escaleras (1 por piso: 4 puntos)
    for floor_num in range(1, 5):
        stair_pos = Point2D(10.0, 8.0)
        add_entry(
            ReferencePoint(
                id=f"RP_P{floor_num}_Stairs",
                floor_number=floor_num,
                position=stair_pos,
                label=f"Descanso de Escalera Piso {floor_num}"
            ),
            floor_num, stair_pos
        )

    # Guardar en archivo JSON
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    serialized = [entry.to_dict() for entry in entries]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)

    aps_per_rp = sum(len(e.rssi_means) for e in entries) / len(entries)
    print(f"✅ Radio-Mapa generado con {len(entries)} Puntos de Referencia en: {output_path}")
    print(f"   Semilla {seed} | {samples} muestras por punto | {aps_per_rp:.1f} APs por punto de media")
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Generador del radio-mapa sintético de calibración")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Ruta del fichero a generar")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Semilla de reproducibilidad")
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                        help="Lecturas por ráfaga de calibración en cada punto")
    args = parser.parse_args()
    generate_school_radio_map(args.output, args.seed, args.samples)


if __name__ == "__main__":
    enable_unicode_output()
    main()

"""
Generador de Radio-Mapa de Calibración para el Edificio Escolar (4 Pisos, 12 Salones).
Genera la base de datos de huellas de señal (Radio Map) con 40 Puntos de Referencia (RPs)
utilizando el modelo físico de propagación en interiores (RADAR / Horus).
"""
import os
import json
import math
from typing import List, Dict
from backend.domain.building import Point2D
from backend.domain.fingerprint import ReferencePoint, RadioMapEntry
from backend.domain.graph import create_default_school_graph
from mobile_app.virtual_sensor.virtual_scanner import SimulatedAP

def generate_school_radio_map(output_path: str = "data/radio_map.json"):
    """Genera y guarda el dataset de calibración de 40 puntos de referencia."""
    graph, floors = create_default_school_graph()

    # Configuración de 12 Access Points distribuidos en los 4 pisos
    aps: List[SimulatedAP] = []
    for f in range(1, 5):
        aps.append(SimulatedAP(f"ap_p{f}_west", f"WIFI_COLEGIO_P{f}_W", floor=f, x=4.0, y=3.5))
        aps.append(SimulatedAP(f"ap_p{f}_east", f"WIFI_COLEGIO_P{f}_E", floor=f, x=16.0, y=3.5))
        aps.append(SimulatedAP(f"ap_p{f}_room02", f"AP_AULA_{f}02", floor=f, x=10.0, y=2.0))

    entries: List[RadioMapEntry] = []

    # 1. Puntos de Referencia en Salones (Centro y Entrada de cada aula: 24 puntos)
    for floor_num, fl in floors.items():
        for r in fl.rooms:
            # RP Centro del Salón
            rp_center = ReferencePoint(
                id=f"RP_{r.id}_Center",
                floor_number=floor_num,
                position=r.center,
                label=f"Centro del {r.name}",
                room_id=r.id
            )
            rssi_center = {}
            for ap in aps:
                val = ap.calculate_rssi(floor_num, r.center.x, r.center.y)
                if val > -95.0:
                    rssi_center[ap.bssid] = val
            entries.append(RadioMapEntry(reference_point=rp_center, rssi_means=rssi_center, sample_count=15))

            # RP Entrada del Salón
            rp_entrance = ReferencePoint(
                id=f"RP_{r.id}_Door",
                floor_number=floor_num,
                position=r.entrance,
                label=f"Puerta de Acceso del {r.name}",
                room_id=r.id
            )
            rssi_entrance = {}
            for ap in aps:
                val = ap.calculate_rssi(floor_num, r.entrance.x, r.entrance.y)
                if val > -95.0:
                    rssi_entrance[ap.bssid] = val
            entries.append(RadioMapEntry(reference_point=rp_entrance, rssi_means=rssi_entrance, sample_count=15))

    # 2. Puntos de Referencia en Pasillos (3 por piso: 12 puntos)
    for floor_num in range(1, 5):
        hallways = [
            (f"RP_P{floor_num}_Hall_W", Point2D(2.0, 5.0), f"Pasillo Oeste Piso {floor_num}"),
            (f"RP_P{floor_num}_Hall_C", Point2D(10.0, 5.0), f"Pasillo Central Piso {floor_num}"),
            (f"RP_P{floor_num}_Hall_E", Point2D(18.0, 5.0), f"Pasillo Este Piso {floor_num}")
        ]
        for rp_id, pos, label in hallways:
            rp = ReferencePoint(id=rp_id, floor_number=floor_num, position=pos, label=label)
            rssi_map = {}
            for ap in aps:
                val = ap.calculate_rssi(floor_num, pos.x, pos.y)
                if val > -95.0:
                    rssi_map[ap.bssid] = val
            entries.append(RadioMapEntry(reference_point=rp, rssi_means=rssi_map, sample_count=15))

    # 3. Puntos de Referencia en Escaleras (1 por piso: 4 puntos)
    for floor_num in range(1, 5):
        stair_pos = Point2D(10.0, 8.0)
        rp = ReferencePoint(
            id=f"RP_P{floor_num}_Stairs",
            floor_number=floor_num,
            position=stair_pos,
            label=f"Descanso de Escalera Piso {floor_num}"
        )
        rssi_map = {}
        for ap in aps:
            val = ap.calculate_rssi(floor_num, stair_pos.x, stair_pos.y)
            if val > -95.0:
                rssi_map[ap.bssid] = val
        entries.append(RadioMapEntry(reference_point=rp, rssi_means=rssi_map, sample_count=15))

    # Guardar en archivo JSON
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    serialized = [entry.to_dict() for entry in entries]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)

    print(f"✅ Radio-Mapa generado exitosamente con {len(entries)} Puntos de Referencia en: {output_path}")
    return entries

if __name__ == "__main__":
    generate_school_radio_map()

"""
Herramienta de Calibración y Ajuste de Umbrales de Asistencia (FAR vs FRR).
Analiza la frontera de decisión entre estudiantes dentro del aula y peatones en el pasillo.
Audita la Tasa de Falsos Positivos (FAR) y Falsos Negativos (FRR).
"""
import numpy as np
from typing import Dict, List, Tuple
from backend.domain.building import Point2D
from backend.repositories.attendance_repo import InMemoryAttendanceRepository
from backend.services.attendance_tracker import AttendanceTrackerService
from backend.config import AttendanceConfig

def tune_attendance_thresholds():
    print("======================================================================")
    print(" AUDITORÍA Y CALIBRACIÓN DE UMBRALES DE ASISTENCIA (FAR vs FRR)")
    print("======================================================================")

    # 1. Conjunto de Evaluación 1: Estudiantes que entran a clase (Positivos reales)
    # Toman asiento en diferentes zonas del aula (x in [2..18], y in [1.5..3.5])
    true_attendees = [
        ("EST_POS_1", Point2D(10.0, 2.0), -45.0), # Centro
        ("EST_POS_2", Point2D(8.0, 2.5), -49.0),  # Fila izquierda
        ("EST_POS_3", Point2D(12.0, 1.8), -48.0), # Fila derecha
        ("EST_POS_4", Point2D(10.0, 3.2), -52.0), # Primera fila
    ]

    # 2. Conjunto de Evaluación 2: Peatones que solo caminan por el pasillo (Negativos reales)
    # Pasan frente a la puerta a 5m de distancia (y=5.0) y continúan caminando
    hallway_passers = [
        ("EST_NEG_1", Point2D(6.0, 5.0), -68.0),  # Aproximándose por pasillo
        ("EST_NEG_2", Point2D(10.0, 5.0), -58.0), # Frente a la puerta un instante
        ("EST_NEG_3", Point2D(14.0, 5.0), -69.0), # Alejándose por pasillo
    ]

    threshold_candidates = [-60.0, -55.0, -50.0]
    window_candidates = [1, 2, 3, 4]

    best_config = None
    min_total_error = float('inf')

    for thresh in threshold_candidates:
        for window in window_candidates:
            repo = InMemoryAttendanceRepository()
            cfg = AttendanceConfig(classroom_threshold_dbm=thresh, confirmation_window_scans=window)
            tracker = AttendanceTrackerService(repo, cfg)

            false_accepts = 0
            false_rejects = 0

            # Probar Peatones (Cada uno pasa frente al aula durante 2 escaneos rápidos y se va)
            for sid, pos, rssi in hallway_passers:
                for _ in range(2): # Solo 2 escaneos fugaces
                    rec, _, _ = tracker.process_student_presence(
                        sid, 3, pos, "S302", 3, Point2D(10.0, 2.0), strongest_rssi_to_room_ap=rssi
                    )
                if rec.status == "PRESENT_CONFIRMED":
                    false_accepts += 1

            # Probar Asistentes Reales (Permanecen 5 escaneos dentro)
            for sid, pos, rssi in true_attendees:
                for _ in range(5):
                    rec, _, _ = tracker.process_student_presence(
                        sid, 3, pos, "S302", 3, Point2D(10.0, 2.0), strongest_rssi_to_room_ap=rssi
                    )
                if rec.status != "PRESENT_CONFIRMED":
                    false_rejects += 1

            far = (false_accepts / len(hallway_passers)) * 100.0
            frr = (false_rejects / len(true_attendees)) * 100.0
            total_err = false_accepts + false_rejects

            print(f"• Umbral: {thresh} dBm | Ventana: {window} scans -> FAR: {far:4.1f}% | FRR: {frr:4.1f}% | Error Total: {total_err}")

            if total_err < min_total_error:
                min_total_error = total_err
                best_config = (thresh, window, far, frr)

    print("\n======================================================================")
    print(f" 🎯 CONFIGURACIÓN AUDITADA RECOMENDADA:")
    print(f"   Umbral RSSI de Aula:       {best_config[0]} dBm")
    print(f"   Ventana de Permanencia:    {best_config[1]} escaneos continuos")
    print(f"   Tasa de Falsos Positivos:  {best_config[2]:.1f}%")
    print(f"   Tasa de Falsos Negativos:  {best_config[3]:.1f}%")
    print("======================================================================")
    return best_config

if __name__ == "__main__":
    tune_attendance_thresholds()

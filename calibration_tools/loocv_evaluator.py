"""
Evaluador Científico de Calibración: Leave-One-Out Cross-Validation (LOOCV).
Audita rigurosamente el clasificador de piso y el algoritmo WKNN sobre el dataset escolar.
Evalúa la precisión de piso y el error medio de distancia para k in [1..5].
"""
import math
import numpy as np
from typing import List, Dict, Tuple
from backend.domain.fingerprint import FingerprintVector, RadioMapEntry
from backend.repositories.radio_map_repo import InMemoryRadioMapRepository
from backend.services.floor_classifier import FloorClassifierService
from backend.services.wknn_locator import WKNNPositioningService
from backend.config import WKNNConfig

def evaluate_loocv(radio_map_path: str = "data/radio_map.json", k_values: List[int] = [1, 2, 3, 4, 5]):
    full_repo = InMemoryRadioMapRepository(radio_map_path)
    all_entries = full_repo.get_all_entries()
    n_samples = len(all_entries)

    if n_samples == 0:
        print("❌ El radio mapa está vacío.")
        return

    print("======================================================================")
    print(f" INICIANDO AUDITORÍA LOOCV (Leave-One-Out Cross Validation) - {n_samples} PUNTOS")
    print("======================================================================")

    results = {}

    for k in k_values:
        floor_correct = 0
        distance_errors = []

        for i in range(n_samples):
            test_entry = all_entries[i]
            train_entries = all_entries[:i] + all_entries[i+1:]

            # Crear repositorio de entrenamiento temporal
            train_repo = InMemoryRadioMapRepository()
            for e in train_entries:
                train_repo.save_entry(e)

            floor_clf = FloorClassifierService(train_repo)
            wknn = WKNNPositioningService(train_repo, WKNNConfig(k=k))

            # Simular vector de prueba con ruido moderado
            online_readings = {}
            for bssid, mean_rssi in test_entry.rssi_means.items():
                noise = np.random.normal(0, 1.2)  # Fluctuación de señal típica en interiores
                online_readings[bssid] = mean_rssi + noise

            test_vector = FingerprintVector(
                timestamp=0.0,
                device_id="LOOCV_TEST",
                readings=online_readings
            )

            # 1. Evaluación de Piso
            est_floor, _ = floor_clf.classify_floor(test_vector)
            true_floor = test_entry.reference_point.floor_number
            if est_floor == true_floor:
                floor_correct += 1

            # 2. Evaluación 2D (utilizando el piso verdadero para evaluar pura precisión métrica)
            est_pos, _ = wknn.estimate_position(true_floor, test_vector)
            true_pos = test_entry.reference_point.position
            dist_err = est_pos.distance_to(true_pos)
            distance_errors.append(dist_err)

        floor_accuracy = (floor_correct / n_samples) * 100.0
        mean_err = np.mean(distance_errors)
        median_err = np.median(distance_errors)
        p90_err = np.percentile(distance_errors, 90)
        rmse = np.sqrt(np.mean(np.square(distance_errors)))

        results[k] = {
            "floor_accuracy": floor_accuracy,
            "mean_error": mean_err,
            "median_error": median_err,
            "p90_error": p90_err,
            "rmse": rmse
        }

        print(f"\n[Hiperparámetro k = {k}]")
        print(f"  • Precisión de Piso: {floor_accuracy:.1f}% ({floor_correct}/{n_samples})")
        print(f"  • Error Medio 2D:    {mean_err:.2f} m")
        print(f"  • Error Mediano 2D:  {median_err:.2f} m")
        print(f"  • Percentil 90:      {p90_err:.2f} m")
        print(f"  • RMSE:              {rmse:.2f} m")

    # Determinar mejor k
    best_k = min(results, key=lambda k: results[k]["mean_error"])
    print("\n======================================================================")
    print(f" 🏆 RESULTADO ÓPTIMO: k = {best_k} (Error Medio: {results[best_k]['mean_error']:.2f} m, Piso: {results[best_k]['floor_accuracy']:.1f}%)")
    print("======================================================================")
    return results, best_k

if __name__ == "__main__":
    evaluate_loocv()

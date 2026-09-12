"""
Evaluador Científico de Calibración: Leave-One-Out Cross-Validation (LOOCV).
Audita el clasificador de piso y el algoritmo WKNN sobre el dataset escolar.
Evalúa la precisión de piso y el error métrico 2D para k in [1..5].

Diseño experimental
-------------------
1. **Reproducibilidad.** El ruido gaussiano que simula la fluctuación del RSSI se extrae de un
   generador con semilla explícita (`--seed`, por defecto 42). Sin ella, dos ejecuciones sobre
   el mismo dataset producían métricas distintas y ninguna cifra publicada era verificable.

2. **Repeticiones.** Una sola pasada de LOOCV es una única realización del ruido. Se repite el
   experimento `--repeats` veces con semillas derivadas (`seed + r`) y se reporta **media ±
   desviación estándar**, que es lo que permite comparar contra un objetivo de diseño.

3. **Diseño pareado entre valores de k.** Dentro de cada repetición, todos los valores de k se
   evalúan sobre **el mismo** vector de prueba ruidoso. Así la comparación entre k no arrastra
   diferencias de ruido, solo del algoritmo.

4. **La precisión de piso no depende de k.** `FloorClassifierService` no usa el hiperparámetro k,
   de modo que se calcula una sola vez por repetición. Que en informes anteriores la precisión de
   piso variara con k era un artefacto del ruido sin semilla, no un efecto real.
"""
import argparse
from typing import Dict, List, Sequence, Tuple

import numpy as np

from backend.config import WKNNConfig
from backend.domain.fingerprint import FingerprintVector
from backend.repositories.radio_map_repo import InMemoryRadioMapRepository
from backend.services.floor_classifier import FloorClassifierService
from backend.services.wknn_locator import WKNNPositioningService
from calibration_tools.console import enable_unicode_output

DEFAULT_MAP = "data/radio_map.json"
DEFAULT_K_VALUES = [1, 2, 3, 4, 5]
DEFAULT_SEED = 42
DEFAULT_REPEATS = 30
DEFAULT_NOISE_SIGMA = 1.2  # Fluctuación de señal típica en interiores (dBm)


def evaluate_loocv(
    radio_map_path: str = DEFAULT_MAP,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
    seed: int = DEFAULT_SEED,
    repeats: int = DEFAULT_REPEATS,
    noise_sigma: float = DEFAULT_NOISE_SIGMA,
    verbose: bool = True,
) -> Tuple[Dict[int, dict], int]:
    """
    Ejecuta la validación cruzada dejando uno fuera sobre el radio-mapa indicado.

    Retorna:
        (results, best_k) donde results[k] contiene, para cada métrica, la media entre
        repeticiones y su desviación estándar con el sufijo `_std`.
    """
    full_repo = InMemoryRadioMapRepository(radio_map_path)
    all_entries = full_repo.get_all_entries()
    n_samples = len(all_entries)

    if n_samples == 0:
        print(f"❌ El radio mapa está vacío o no existe: {radio_map_path}")
        return {}, 0

    k_values = list(k_values)

    if verbose:
        print("======================================================================")
        print(f" AUDITORÍA LOOCV (Leave-One-Out Cross Validation) - {n_samples} PUNTOS")
        print(f" Semilla: {seed} | Repeticiones: {repeats} | Ruido: σ = {noise_sigma} dBm")
        print("======================================================================")

    floor_accuracy_runs: List[float] = []
    error_runs: Dict[int, Dict[str, List[float]]] = {
        k: {"mean": [], "median": [], "p90": [], "rmse": []} for k in k_values
    }

    for repetition in range(repeats):
        # Semilla derivada: cada repetición ve un ruido distinto, pero el conjunto de
        # repeticiones es idéntico entre ejecuciones.
        rng = np.random.default_rng(seed + repetition)

        floor_correct = 0
        errors_by_k: Dict[int, List[float]] = {k: [] for k in k_values}

        for i in range(n_samples):
            test_entry = all_entries[i]
            train_entries = all_entries[:i] + all_entries[i + 1:]

            # Repositorio de entrenamiento temporal (sin storage_path: nunca toca data/)
            train_repo = InMemoryRadioMapRepository()
            for entry in train_entries:
                train_repo.save_entry(entry)

            # Vector de prueba con ruido, compartido por todos los valores de k (diseño pareado)
            online_readings = {
                bssid: mean_rssi + rng.normal(0.0, noise_sigma)
                for bssid, mean_rssi in test_entry.rssi_means.items()
            }
            test_vector = FingerprintVector(
                timestamp=0.0,
                device_id="LOOCV_TEST",
                readings=online_readings
            )

            true_floor = test_entry.reference_point.floor_number
            true_pos = test_entry.reference_point.position

            # 1. Evaluación de Piso (independiente de k: se calcula una sola vez)
            est_floor, _ = FloorClassifierService(train_repo).classify_floor(test_vector)
            if est_floor == true_floor:
                floor_correct += 1

            # 2. Evaluación 2D (sobre el piso verdadero, para medir precisión métrica pura)
            for k in k_values:
                wknn = WKNNPositioningService(train_repo, WKNNConfig(k=k))
                est_pos, _ = wknn.estimate_position(true_floor, test_vector)
                errors_by_k[k].append(est_pos.distance_to(true_pos))

        floor_accuracy_runs.append(floor_correct / n_samples * 100.0)
        for k in k_values:
            errors = np.asarray(errors_by_k[k])
            error_runs[k]["mean"].append(float(np.mean(errors)))
            error_runs[k]["median"].append(float(np.median(errors)))
            error_runs[k]["p90"].append(float(np.percentile(errors, 90)))
            error_runs[k]["rmse"].append(float(np.sqrt(np.mean(np.square(errors)))))

    floor_accuracy = float(np.mean(floor_accuracy_runs))
    floor_accuracy_std = float(np.std(floor_accuracy_runs))

    results: Dict[int, dict] = {}
    for k in k_values:
        results[k] = {
            "floor_accuracy": floor_accuracy,
            "floor_accuracy_std": floor_accuracy_std,
            "floor_accuracy_min": float(np.min(floor_accuracy_runs)),
            "mean_error": float(np.mean(error_runs[k]["mean"])),
            "mean_error_std": float(np.std(error_runs[k]["mean"])),
            "median_error": float(np.mean(error_runs[k]["median"])),
            "median_error_std": float(np.std(error_runs[k]["median"])),
            "p90_error": float(np.mean(error_runs[k]["p90"])),
            "p90_error_std": float(np.std(error_runs[k]["p90"])),
            "rmse": float(np.mean(error_runs[k]["rmse"])),
            "rmse_std": float(np.std(error_runs[k]["rmse"])),
        }

        if verbose:
            r = results[k]
            print(f"\n[Hiperparámetro k = {k}]")
            print(f"  • Error Medio 2D:    {r['mean_error']:.2f} ± {r['mean_error_std']:.2f} m")
            print(f"  • Error Mediano 2D:  {r['median_error']:.2f} ± {r['median_error_std']:.2f} m")
            print(f"  • Percentil 90:      {r['p90_error']:.2f} ± {r['p90_error_std']:.2f} m")
            print(f"  • RMSE:              {r['rmse']:.2f} ± {r['rmse_std']:.2f} m")

    best_k = min(results, key=lambda k: results[k]["mean_error"])

    if verbose:
        print("\n----------------------------------------------------------------------")
        print(" PRECISIÓN DE PISO (independiente de k; el clasificador no usa ese hiperparámetro)")
        print(f"  • Media entre repeticiones: {floor_accuracy:.1f} ± {floor_accuracy_std:.1f}%")
        print(f"  • Peor repetición:          {results[best_k]['floor_accuracy_min']:.1f}%")
        print("======================================================================")
        print(f" 🏆 k ÓPTIMO: k = {best_k} "
              f"(Error Medio: {results[best_k]['mean_error']:.2f} ± "
              f"{results[best_k]['mean_error_std']:.2f} m)")
        print("======================================================================")

    return results, best_k


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoría LOOCV del radio-mapa y el motor WKNN")
    parser.add_argument("--map", default=DEFAULT_MAP, help="Ruta del radio-mapa a auditar")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Semilla del generador de ruido")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS, help="Repeticiones del experimento")
    parser.add_argument("--sigma", type=float, default=DEFAULT_NOISE_SIGMA, help="Desviación del ruido en dBm")
    parser.add_argument("--k", type=int, nargs="+", default=DEFAULT_K_VALUES, help="Valores de k a evaluar")
    args = parser.parse_args()

    evaluate_loocv(
        radio_map_path=args.map,
        k_values=args.k,
        seed=args.seed,
        repeats=args.repeats,
        noise_sigma=args.sigma,
    )



if __name__ == "__main__":
    enable_unicode_output()
    main()

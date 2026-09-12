"""
Herramienta de Calibración y Ajuste de Umbrales de Asistencia (FAR vs FRR).
Analiza la frontera de decisión entre estudiantes dentro del aula y peatones en el pasillo.

Modelo de evaluación
--------------------
La versión anterior evaluaba 3 peatones y 4 asistentes con posiciones y potencias fijas escritas
a mano. Con esa muestra la granularidad mínima del FAR era del 33%, así que un "FAR = 0.0%" no
respaldaba el objetivo de diseño de "≤5%". Además, el barrido de umbrales producía salidas
idénticas para -60, -55 y -50 dBm porque el criterio de decisión estaba cortocircuitado.

Ahora se generan poblaciones sintéticas con un generador sembrado, modelando las dos señales que
llegan al tracker como lo que son: **correlacionadas pero no idénticas**.

  • Potencia medida:    RSSI = pathloss(distancia_real) + N(0, sigma_rssi)
  • Posición estimada:  pos_WKNN = posicion_real + N(0, sigma_pos) por eje

Es el mecanismo real de falso positivo: un peatón del pasillo cuya posición estimada cae dentro
del radio del aula por error del WKNN, pero cuya potencia medida sigue siendo débil.
"""
import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from backend.config import AttendanceConfig
from backend.domain.attendance import AttendanceStatus
from backend.domain.building import Point2D
from backend.repositories.attendance_repo import InMemoryAttendanceRepository
from backend.services.attendance_tracker import AttendanceTrackerService

ROOM_ID = "S302"
ROOM_FLOOR = 3
ROOM_CENTER = Point2D(10.0, 2.0)

# Huella física asumida del aula. El modelo del edificio (`create_default_school_graph`) solo
# define el centro del aula y su puerta, no sus dimensiones, así que se derivan de la topología:
# los centros de aulas contiguas distan 8 m, la puerta está en y = 4.0.
ROOM_X_RANGE = (6.5, 13.5)   # 7 m de ancho útil, 1 m de muro entre aulas
ROOM_Y_RANGE = (0.5, 3.5)    # 3 m de fondo, hasta justo antes de la puerta
HALLWAY_X_RANGE = (4.0, 16.0)
HALLWAY_Y_RANGE = (4.4, 5.6)

DEFAULT_SEED = 42
DEFAULT_POPULATION = 40      # por clase (asistentes reales y peatones)
DEFAULT_SIGMA_RSSI = 3.0     # dispersión de la potencia medida, en dB
DEFAULT_SIGMA_POS = 1.2      # error del WKNN por eje, en metros

# Número de lecturas que aporta cada tipo de sujeto. Es el parámetro que da sentido a la ventana
# de permanencia: un alumno que asiste a clase escanea de forma sostenida durante toda la sesión,
# mientras que un peatón solo cruza el campo de visión del AP durante unos segundos. Con un
# escaneo cada 1.5 s, 20 lecturas son 30 segundos de permanencia.
DEFAULT_SCANS_ATTENDEE = 20
DEFAULT_SCANS_PASSER = 2


@dataclass
class Subject:
    """Un sujeto de evaluación con su verdad de campo y las señales que llegan al tracker."""
    subject_id: str
    is_true_attendee: bool
    estimated_positions: List[Point2D]
    measured_rssi: List[float]


def _path_loss_rssi(distance_meters: float) -> float:
    """Potencia esperada del AP del aula a una distancia dada (modelo log-distance)."""
    return -40.0 - 25.0 * (max(0.5, distance_meters) / 3.0)


def build_population(
    rng: np.random.Generator,
    population_size: int,
    sigma_rssi: float,
    sigma_pos: float,
    scans_attendee: int = DEFAULT_SCANS_ATTENDEE,
    scans_passer: int = DEFAULT_SCANS_PASSER
) -> List[Subject]:
    """
    Genera asistentes reales (sentados en el aula) y peatones (cruzando el pasillo).

    El aula ocupa y in [0.5, 3.4] y el pasillo y in [4.4, 5.6]; el centro del aula está en
    (10.0, 2.0). Los peatones nunca entran al aula: son negativos verdaderos por construcción.
    """
    subjects: List[Subject] = []

    for i in range(population_size):
        # Asistente real: sentado en algún pupitre del aula, uniformemente sobre su huella
        true_pos = Point2D(
            x=float(rng.uniform(*ROOM_X_RANGE)),
            y=float(rng.uniform(*ROOM_Y_RANGE))
        )
        subjects.append(_make_subject(
            f"POS_{i:02d}", True, true_pos, scans_attendee, rng, sigma_rssi, sigma_pos
        ))

    for i in range(population_size):
        # Peatón: recorre el pasillo frente a la puerta, sin entrar
        true_pos = Point2D(
            x=float(rng.uniform(*HALLWAY_X_RANGE)),
            y=float(rng.uniform(*HALLWAY_Y_RANGE))
        )
        subjects.append(_make_subject(
            f"NEG_{i:02d}", False, true_pos, scans_passer, rng, sigma_rssi, sigma_pos
        ))

    return subjects


def _make_subject(
    subject_id: str,
    is_attendee: bool,
    true_pos: Point2D,
    scans: int,
    rng: np.random.Generator,
    sigma_rssi: float,
    sigma_pos: float
) -> Subject:
    true_distance = true_pos.distance_to(ROOM_CENTER)
    estimated_positions = []
    measured_rssi = []

    for _ in range(scans):
        # Error del motor WKNN sobre la posición
        estimated_positions.append(Point2D(
            x=true_pos.x + float(rng.normal(0.0, sigma_pos)),
            y=true_pos.y + float(rng.normal(0.0, sigma_pos))
        ))
        # Ruido independiente sobre la potencia medida
        measured_rssi.append(_path_loss_rssi(true_distance) + float(rng.normal(0.0, sigma_rssi)))

    return Subject(subject_id, is_attendee, estimated_positions, measured_rssi)


def classroom_coverage(radius_meters: float, samples: int = 20000, seed: int = 0) -> float:
    """Porcentaje de la huella del aula que cubre un criterio circular de radio dado."""
    rng = np.random.default_rng(seed)
    inside = 0
    for _ in range(samples):
        point = Point2D(
            x=float(rng.uniform(*ROOM_X_RANGE)),
            y=float(rng.uniform(*ROOM_Y_RANGE))
        )
        if point.distance_to(ROOM_CENTER) <= radius_meters:
            inside += 1
    return inside / samples * 100.0


def evaluate_config(
    subjects: List[Subject],
    threshold_dbm: float,
    window_scans: int,
    radius_meters: float = AttendanceConfig().classroom_radius_meters
) -> Tuple[float, float, int, int]:
    """
    Evalúa una combinación (umbral, ventana, radio) sobre toda la población.

    Retorna:
        (FAR %, FRR %, falsos_aceptados, falsos_rechazados)
    """
    config = AttendanceConfig(
        classroom_threshold_dbm=threshold_dbm,
        confirmation_window_scans=window_scans,
        classroom_radius_meters=radius_meters
    )

    false_accepts = 0
    false_rejects = 0
    positives = sum(1 for s in subjects if s.is_true_attendee)
    negatives = len(subjects) - positives

    for subject in subjects:
        # Repositorio limpio por sujeto: los estados no deben arrastrarse entre sujetos
        repo = InMemoryAttendanceRepository()
        tracker = AttendanceTrackerService(repo, config)

        record = None
        for position, rssi in zip(subject.estimated_positions, subject.measured_rssi):
            record, _, _ = tracker.process_student_presence(
                subject.subject_id, ROOM_FLOOR, position, ROOM_ID, ROOM_FLOOR, ROOM_CENTER,
                strongest_rssi_to_room_ap=rssi
            )

        confirmed = record is not None and record.status == AttendanceStatus.PRESENT_CONFIRMED

        if confirmed and not subject.is_true_attendee:
            false_accepts += 1
        elif not confirmed and subject.is_true_attendee:
            false_rejects += 1

    far = (false_accepts / negatives * 100.0) if negatives else 0.0
    frr = (false_rejects / positives * 100.0) if positives else 0.0
    return far, frr, false_accepts, false_rejects


def tune_attendance_thresholds(
    seed: int = DEFAULT_SEED,
    population_size: int = DEFAULT_POPULATION,
    sigma_rssi: float = DEFAULT_SIGMA_RSSI,
    sigma_pos: float = DEFAULT_SIGMA_POS,
    thresholds: Optional[List[float]] = None,
    windows: Optional[List[int]] = None,
    scans_attendee: int = DEFAULT_SCANS_ATTENDEE,
    scans_passer: int = DEFAULT_SCANS_PASSER,
) -> Optional[tuple]:
    thresholds = thresholds if thresholds is not None else [-70.0, -65.0, -60.0, -55.0, -50.0]
    windows = windows if windows is not None else [1, 2, 3, 4]

    rng = np.random.default_rng(seed)
    subjects = build_population(
        rng, population_size, sigma_rssi, sigma_pos, scans_attendee, scans_passer
    )
    positives = sum(1 for s in subjects if s.is_true_attendee)
    negatives = len(subjects) - positives

    print("======================================================================")
    print(" CALIBRACION DE UMBRALES DE ASISTENCIA (FAR vs FRR)")
    print(f" Semilla: {seed} | Asistentes reales: {positives} | Peatones: {negatives}")
    print(f" sigma_RSSI = {sigma_rssi} dB | sigma_posicion_WKNN = {sigma_pos} m")
    print(f" Lecturas por asistente: {scans_attendee} | por peaton: {scans_passer}")
    print("======================================================================")
    print(f"{'Umbral':>9} {'Ventana':>8} {'FAR':>8} {'FRR':>8} {'Err.Total':>10}")
    print("-" * 47)

    best_config = None
    min_total_error = float("inf")

    for threshold in thresholds:
        for window in windows:
            far, frr, fa, fr = evaluate_config(subjects, threshold, window)
            total_err = fa + fr
            print(f"{threshold:>7.1f}dB {window:>8} {far:>7.1f}% {frr:>7.1f}% {total_err:>10}")

            if total_err < min_total_error:
                min_total_error = total_err
                best_config = (threshold, window, far, frr)
        print("-" * 47)

    # ------------------------------------------------------------------
    # Barrido del radio geométrico
    # ------------------------------------------------------------------
    # `classroom_radius_meters` es la ÚNICA definición de "dentro del aula" que existe en el
    # modelo, y un criterio circular no cubre un aula rectangular. Conviene auditarlo igual que
    # el umbral de potencia.
    default_radius = AttendanceConfig().classroom_radius_meters
    best_threshold, best_window = best_config[0], best_config[1]

    print()
    print("======================================================================")
    print(f" BARRIDO DEL RADIO DE AULA (umbral {best_threshold} dBm, ventana {best_window})")
    print("======================================================================")
    print(f"{'Radio':>8} {'Cobertura':>11} {'FAR':>8} {'FRR':>8} {'Err.Total':>10}")
    print("-" * 49)
    for radius in (3.0, 3.5, 4.0, 4.5, 5.0):
        far, frr, fa, fr = evaluate_config(subjects, best_threshold, best_window, radius)
        coverage = classroom_coverage(radius)
        marker = "  <- actual" if radius == default_radius else ""
        print(f"{radius:>7.1f}m {coverage:>10.1f}% {far:>7.1f}% {frr:>7.1f}% {fa + fr:>10}{marker}")

    print()
    print("======================================================================")
    print(" CONFIGURACION RECOMENDADA:")
    print(f"   Umbral RSSI de aula:      {best_config[0]} dBm")
    print(f"   Ventana de permanencia:   {best_config[1]} escaneos continuos")
    print(f"   Tasa de falsos positivos: {best_config[2]:.1f}%  (n = {negatives} peatones)")
    print(f"   Tasa de falsos negativos: {best_config[3]:.1f}%  (n = {positives} asistentes)")
    print("======================================================================")
    print()
    default_coverage = classroom_coverage(default_radius)
    corner_distance = Point2D(ROOM_X_RANGE[1], ROOM_Y_RANGE[1]).distance_to(ROOM_CENTER)
    if default_coverage < 99.9:
        print(f" AVISO: el radio configurado ({default_radius} m) cubre solo "
              f"{default_coverage:.1f}% de la huella del aula.")
        print(f" Un alumno sentado en la esquina mas lejana ({corner_distance:.2f} m del centro)")
        print(" no puede confirmar asistencia por mucho que permanezca en clase.")
    else:
        print(f" OK: el radio configurado ({default_radius} m) cubre el {default_coverage:.1f}% "
              f"de la huella del aula")
        print(f" (el pupitre mas lejano esta a {corner_distance:.2f} m del centro).")
    return best_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibración de umbrales de asistencia (FAR/FRR)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--population", type=int, default=DEFAULT_POPULATION,
                        help="Sujetos por clase (asistentes y peatones)")
    parser.add_argument("--sigma-rssi", type=float, default=DEFAULT_SIGMA_RSSI)
    parser.add_argument("--sigma-pos", type=float, default=DEFAULT_SIGMA_POS)
    parser.add_argument("--scans-attendee", type=int, default=DEFAULT_SCANS_ATTENDEE,
                        help="Lecturas que aporta un alumno que permanece en clase")
    parser.add_argument("--scans-passer", type=int, default=DEFAULT_SCANS_PASSER,
                        help="Lecturas que aporta un peaton que solo cruza el pasillo")
    args = parser.parse_args()

    tune_attendance_thresholds(
        seed=args.seed,
        population_size=args.population,
        sigma_rssi=args.sigma_rssi,
        sigma_pos=args.sigma_pos,
        scans_attendee=args.scans_attendee,
        scans_passer=args.scans_passer,
    )


if __name__ == "__main__":
    main()

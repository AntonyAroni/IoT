"""
Módulo de Configuración Central del Sistema IPS y Asistencia IoT.
Define hiperparámetros para WKNN, umbrales de proximidad de radiofrecuencia y ajustes de red.

Las rutas de datos se resuelven contra la raíz del proyecto, no contra el directorio de trabajo:
arrancar el servidor desde otro directorio cargaba silenciosamente 0 puntos de referencia y el
sistema aparentaba funcionar devolviendo siempre piso 1. Cada ruta admite además una variable de
entorno para despliegue.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

# backend/config.py -> backend/ -> raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_data_path(env_var: str, relative_path: str) -> str:
    """
    Resuelve una ruta de datos de forma independiente del directorio de trabajo.

    Prioridad: variable de entorno (si está definida) > ruta relativa a la raíz del proyecto.
    """
    override = os.environ.get(env_var)
    if override:
        return str(Path(override).expanduser().resolve())
    return str(PROJECT_ROOT / relative_path)


@dataclass(frozen=True)
class WKNNConfig:
    """
    Configuración para el algoritmo Weighted k-Nearest Neighbors.

    Elección de k
    -------------
    `k = 2` es el valor que minimiza el error medio (1.70 m frente a 2.03 m de k=3) y el RMSE
    en la validación LOOCV, y además acota mejor la cola del error, que es lo que importa para
    guiado paso a paso: percentil 90 de 2.74 m frente a 3.33 m. El valor anterior era 3, que
    contradecía sin explicación al "k=2 óptimo" que publicaba el propio reporte de validación.

    Salvedad: k=3 minimiza la *mediana* (1.82 m), es decir acierta más a menudo aunque falle
    peor cuando falla, y promediar más vecinos podría resultar más robusto frente al ruido real
    que el modelo sintético no reproduce. Si alguna vez se dispone de un radio-mapa de campo,
    conviene repetir el barrido antes de dar por buena esta elección.

    Reproducir: PYTHONPATH=. python calibration_tools/loocv_evaluator.py --seed 42 --repeats 30
    """
    k: int = 2
    epsilon: float = 1e-6
    default_absent_rssi: float = -105.0  # RSSI asignado cuando un AP no es detectado
    metric: str = "euclidean"  # 'euclidean' o 'manhattan'

    # Ponderación por varianza al estilo Horus (Youssef & Agrawala, 2005): cada término de la
    # distancia se divide por la desviación estándar del BSSID medida en calibración, de modo
    # que un AP inestable pesa menos que uno estable. Requiere que el radio-mapa traiga
    # `rssi_std`; sin ese dato la opción no tiene efecto.
    use_std_weighting: bool = False
    min_std_dbm: float = 1.0  # Suelo de la desviación, para no dividir por valores diminutos


@dataclass(frozen=True)
class AttendanceConfig:
    """
    Umbrales de proximidad y permanencia para la confirmación de asistencia.

    Coherencia entre umbral de potencia y radio geométrico
    -----------------------------------------------------
    Ambos criterios describen el mismo hecho físico —"el alumno está dentro del aula"— y por
    tanto deben ser equivalentes bajo el modelo de propagación del propio proyecto,
    `RSSI = -40 - 25 * (d / 3)`:

        -50 dBm -> 1.20 m      -65 dBm -> 3.00 m
        -55 dBm -> 1.80 m      -70 dBm -> 3.60 m
        -60 dBm -> 2.40 m      -75 dBm -> 4.20 m

    El valor anterior de -55 dBm equivalía a 1.80 m del centro, es decir solo el 44.9% de la
    huella del aula (7 x 3 m). Nunca fue coherente con "dentro del aula"; pasaba inadvertido
    porque la condición de distancia lo cortocircuitaba con un `or`.

    Los valores actuales (-70 dBm ~ 3.60 m, radio 4.00 m) cubren el aula completa, incluido el
    pupitre de la esquina más lejana, que está a 3.81 m del centro. Verificado con
    `calibration_tools/threshold_tuner.py`: FAR 0.0% y FRR 0.0% con N=3 sobre 40 asistentes y
    40 peatones.
    """
    approaching_threshold_dbm: float = -70.0  # Alumno en radio de detección (zona informativa)
    classroom_threshold_dbm: float = -70.0    # Equivale a 3.60 m bajo el modelo log-distance
    confirmation_window_scans: int = 3        # Muestras continuas requeridas sobre el umbral
    window_timeout_seconds: float = 15.0      # Tiempo máximo entre lecturas consecutivas

    # Permanencia mínima exigida, en segundos, medida entre la primera y la última lectura de la
    # racha. Complementa al recuento de muestras: `confirmation_window_scans` controla CUÁNTAS
    # veces se ha visto al alumno y este parámetro CUÁNTO TIEMPO lleva dentro.
    #
    # El valor 0.0 lo desactiva y deja el criterio en solo el recuento, que es el comportamiento
    # histórico. Con un escaneo cada 1.5 s, N=3 cubre unos 4.5 segundos: basta para descartar a
    # quien *pasa* por delante de la puerta, pero no a quien *se detiene* a conversar en el
    # umbral. Para eso hay que exigir permanencia explícita (por ejemplo 300.0 para cinco
    # minutos), y entonces conviene subir también `window_timeout_seconds`, porque una racha se
    # rompe si dos lecturas consecutivas se separan más de ese intervalo.
    minimum_dwell_seconds: float = 0.0

    # Radios geométricos de decisión, en metros, medidos desde el centro del aula.
    # Antes estaban incrustados como literales en AttendanceTrackerService.
    classroom_radius_meters: float = 4.0      # Cubre el 100% de la huella del aula
    approaching_radius_meters: float = 9.0


@dataclass(frozen=True)
class ServerConfig:
    """Configuración del servidor FastAPI y WebSockets."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    radio_map_file: str = field(
        default_factory=lambda: _resolve_data_path("IPS_RADIO_MAP_PATH", "data/radio_map.json")
    )
    attendance_log_file: str = field(
        default_factory=lambda: _resolve_data_path("IPS_ATTENDANCE_LOG_PATH", "data/attendance_log.json")
    )


@dataclass
class SystemConfig:
    wknn: WKNNConfig = field(default_factory=WKNNConfig)
    attendance: AttendanceConfig = field(default_factory=AttendanceConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


# Instancia global por defecto
config = SystemConfig()

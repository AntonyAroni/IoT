# Reporte de Validación: IPS Multi-Piso & Asistencia IoT

> **Proyecto:** Sistema de Localización en Interiores (IPS) y Asistencia Inteligente
> **Edificio modelado:** 4 pisos, 12 salones, pasillos centrales y núcleo de escaleras
> **Fecha de validación:** 2026-09-11
> **Naturaleza del experimento:** **simulación**, no medición de campo (ver §1)

---

## 1. Naturaleza y alcance del experimento

> ⚠️ **Este reporte NO contiene mediciones tomadas en un edificio real.**

Los 40 puntos de referencia evaluados son **sintéticos**: los genera
`calibration_tools/generate_synthetic_map.py` aplicando un modelo de propagación log-distance
(`SimulatedAP.calculate_rssi()`) con los siguientes parámetros:

| Parámetro del modelo | Valor |
| :--- | :---: |
| Potencia de referencia a 1 m | −42 dBm |
| Exponente de pérdidas (PLE) | 2.8 |
| Atenuación por losa de concreto | 14 dB por piso |
| Ruido gaussiano de generación | σ = 1.5 dB |
| Umbral de sensibilidad del receptor | −95 dBm |

La validación LOOCV toma esos mismos puntos, les añade ruido gaussiano adicional (σ = 1.2 dB) y
comprueba si los algoritmos recuperan la posición de origen. **Es una verificación funcional del
sistema de localización, no una medición de su precisión en un entorno real:** el modelo se está
validando contra sí mismo.

Lo que estas cifras **sí** demuestran: que el clasificador jerárquico de piso, el motor WKNN y la
cadena de datos completa funcionan correctamente y son consistentes bajo perturbación.

Lo que **no** demuestran: cuál será el error en un edificio real.

Las capturas Wi-Fi reales tomadas con el cliente Android se conservan aparte, en
`data/field_captures/`, y **no son utilizables como puntos de referencia** porque se guardaron sin
fijar sus coordenadas (ver el README de ese directorio).

### 1.1 Limitaciones conocidas del modelo

El modelo log-distance empleado **no reproduce** los fenómenos que dominan el error en
despliegues reales:

1. **Multicamino y desvanecimiento.** No hay reflexiones en muros, mobiliario metálico ni
   pizarras; el modelo es radialmente simétrico alrededor de cada AP.
2. **Atenuación por cuerpos humanos.** Un aula ocupada introduce 3–6 dB de pérdida adicional y
   variable. Aquí no existe.
3. **Deriva temporal del RSSI.** No se modela la variación entre la fase de calibración y la de
   operación (horas o días después), que es la principal fuente de degradación en fingerprinting.
4. **Heterogeneidad de dispositivos.** Todos los escaneos provienen del mismo modelo sintético.
   En la práctica, chipsets distintos reportan RSSI con desplazamientos de hasta 10 dB para la
   misma señal.
5. **Geometría idealizada.** Las paredes de los salones no atenúan: la única barrera modelada es
   la losa horizontal entre pisos, lo que favorece artificialmente el aislamiento de piso.
6. **Densidad de APs uniforme.** 3 APs por piso, perfectamente distribuidos. Una instalación real
   tiene cobertura irregular.

**Consecuencia:** los errores aquí reportados deben interpretarse como una **cota inferior
optimista**. La literatura sitúa el error típico de WKNN en despliegues reales en 3–5 m
(Bahl & Padmanabhan, 2000; Torres-Sospedra et al., 2014), frente a los 1.73 m de esta simulación.

---

## 2. Diseño experimental y reproducibilidad

| Aspecto | Configuración |
| :--- | :--- |
| Método | Leave-One-Out Cross-Validation sobre 40 RPs |
| Ruido añadido al vector de prueba | Gaussiano, σ = 1.2 dBm |
| **Semilla del generador** | **42** (`np.random.default_rng(seed + repetición)`) |
| **Repeticiones** | **30** |
| Estadístico reportado | Media ± desviación estándar entre repeticiones |
| Diseño entre valores de k | Pareado (mismo vector ruidoso para todos los k) |

Reproducir exactamente estas cifras:

```bash
PYTHONPATH=. python calibration_tools/loocv_evaluator.py --seed 42 --repeats 30
```

> **Nota sobre versiones anteriores de este reporte.** Las cifras publicadas hasta el 2026-09-11
> se obtuvieron **sin semilla fija**, por lo que no eran reproducibles: ejecuciones sucesivas
> sobre el mismo dataset arrojaban precisiones de piso entre 88.6% y 100%. Además el dataset
> auditado contenía 44 entradas en lugar de 40 (un artefacto de prueba y tres capturas de campo
> con coordenadas duplicadas), lo que degradaba la métrica de aislamiento de piso por debajo del
> objetivo de diseño. Ambos problemas están corregidos.

---

## 3. Resultados: precisión métrica (LOOCV)

```
 k  | Error Medio 2D  | Error Mediano   | Percentil 90    | RMSE
----+-----------------+-----------------+-----------------+-----------------
 1  | 1.90 ± 0.03 m   | 2.00 ± 0.00 m   | 3.00 ± 0.00 m   | 2.09 ± 0.03 m
 2  | 1.73 ± 0.05 m   | 1.98 ± 0.02 m   | 2.71 ± 0.02 m   | 2.16 ± 0.10 m   <- ÓPTIMO
 3  | 2.22 ± 0.02 m   | 1.79 ± 0.03 m   | 3.81 ± 0.08 m   | 2.57 ± 0.04 m
 4  | 2.65 ± 0.03 m   | 2.34 ± 0.05 m   | 4.31 ± 0.09 m   | 2.91 ± 0.02 m
 5  | 2.79 ± 0.04 m   | 2.55 ± 0.04 m   | 4.47 ± 0.07 m   | 3.09 ± 0.03 m
```

**Precisión de aislamiento de piso: 99.2 ± 1.2%** (peor repetición: 97.5%).

> Esta métrica **no depende de k**: `FloorClassifierService` no usa ese hiperparámetro. Que
> versiones anteriores del reporte mostraran la precisión de piso variando por fila era un
> artefacto del ruido sin semilla, no un efecto del algoritmo.

### 3.1 Contraste con los objetivos de diseño

| Métrica | Objetivo | Resultado (k=2) | Estado |
| :--- | :---: | :---: | :---: |
| Aislamiento de piso | ≥ 95.0% | 99.2 ± 1.2% (mín. 97.5%) | 🟢 CUMPLE |
| Error medio 2D | ≤ 2.50 m | 1.73 ± 0.05 m | 🟢 CUMPLE |
| Error mediano 2D | ≤ 2.20 m | 1.98 ± 0.02 m | 🟢 CUMPLE |
| Percentil 90 del error | ≤ 4.00 m | 2.71 ± 0.02 m | 🟢 CUMPLE |
| RMSE métrico | ≤ 3.00 m | 2.16 ± 0.10 m | 🟢 CUMPLE |

Todos los objetivos se cumplen **dentro del marco simulado descrito en §1**.

### 3.2 Conclusiones sobre el hiperparámetro k

1. **k = 2 minimiza el error medio** (1.73 m) con la densidad de referencia empleada
   (1 RP cada 3–8 m). El margen sobre k=1 (1.90 m) es pequeño pero consistente: la desviación
   entre repeticiones es de solo 0.03–0.05 m.
2. **k ≥ 4 incumple el objetivo de percentil 90** (4.31 m y 4.47 m frente al límite de 4.00 m):
   promediar demasiados vecinos arrastra la estimación hacia el centroide del piso.
3. **k = 3 minimiza la *mediana*** (1.79 m) pese a tener peor media que k=2. Es decir, k=3 acierta
   más a menudo pero falla peor cuando falla. Para guiado paso a paso interesa acotar la cola
   (percentil 90), lo que favorece a k=2.

> ⚠️ **Discrepancia pendiente con el código.** `backend/config.py` define `WKNNConfig.k = 3`,
> no el óptimo k=2 que arroja esta validación. Hay que alinear el valor por defecto o justificar
> explícitamente la elección.

---

## 4. Umbrales de asistencia (FAR / FRR)

### 4.1 Qué se corrigió antes de poder medir

La versión anterior de este reporte publicaba FAR = 0.0% y FRR = 0.0% sobre una muestra de **3
peatones y 4 asistentes**, con un barrido de umbrales que producía salidas **idénticas** para
−60, −55 y −50 dBm. Tres defectos lo invalidaban:

1. **Criterio cortocircuitado.** La condición de zona de aula era
   `rssi >= umbral **or** distancia <= 3.0`. El `or` permitía que la posición estimada
   confirmara por sí sola, volviendo decorativo el umbral de potencia.
2. **Ventana sin caducidad.** `window_timeout_seconds = 15.0` estaba declarado pero no se usaba
   en ninguna parte: el contador de muestras nunca expiraba, de modo que tres pasadas frente a
   la puerta en días distintos habrían confirmado la asistencia.
3. **Muestra sin poder estadístico.** Con n=3 negativos, la granularidad mínima del FAR es 33.3%;
   un "0.0%" no podía respaldar un objetivo de "≤5%".

### 4.2 Incoherencia física del umbral de −55 dBm

Bajo el modelo de propagación del propio proyecto, `RSSI = −40 − 25·(d/3)`:

| Umbral | Distancia equivalente | Cobertura del aula (7 × 3 m) |
| :---: | :---: | :---: |
| −50 dBm | 1.20 m | 20.5% |
| **−55 dBm** | **1.80 m** | **44.9%** |
| −60 dBm | 2.40 m | 66.1% |
| −65 dBm | 3.00 m | 82.2% |
| **−70 dBm** | **3.60 m** | **97.9%** |

El umbral de −55 dBm describía un círculo de 1.80 m alrededor del centro del aula: **menos de la
mitad de la superficie**. Nunca fue coherente con "el alumno está dentro del aula", pero pasaba
inadvertido porque el `or` lo cortocircuitaba.

El mismo análisis aplicado al radio geométrico: el valor de 3.0 m cubría el 82.2% de la huella,
dejando **estructuralmente fuera** al alumno sentado en la esquina más lejana, a 3.81 m del
centro, que no podía confirmar asistencia por mucho que permaneciera en clase.

### 4.3 Criterio de decisión adoptado

- **Zona de aula (gobierna la asistencia):** conjunción. Cuando el cliente envía una potencia
  medida, ésta y la geometría son señales **independientes** —correlacionadas, pero con ruidos
  distintos— y se exigen las dos. Es el criterio conservador que persigue el proyecto.
- **Zona de aproximación (alimenta el radar):** disyunción. Es informativa y no concede
  asistencia; un falso "aproximándose" no tiene coste. Exigir la conjunción dejaría el radar
  vacío, porque a 9 m el modelo predice −115 dBm, por debajo de la sensibilidad del receptor.
- **Sin potencia medida:** se decide solo por geometría, porque el RSSI se derivó de la distancia
  y no es una señal independiente. El registro queda marcado como estimado.

### 4.4 Resultados

Población sintética de 40 asistentes y 40 peatones, semilla 42. Las dos señales se modelan como
correlacionadas pero no idénticas: `RSSI = pathloss(d_real) + N(0, 3 dB)` y
`pos_WKNN = pos_real + N(0, 1.2 m)` por eje. Los asistentes aportan 20 lecturas (permanencia
sostenida) y los peatones 2 (cruce fugaz).

```
 Umbral   Ventana      FAR      FRR
--------------------------------------
-70.0 dB        1    35.0%     0.0%
-70.0 dB        2    12.5%     0.0%
-70.0 dB        3     0.0%     0.0%   <- configuración adoptada
-70.0 dB        4     0.0%     2.5%
-65.0 dB        3     0.0%    15.0%
-60.0 dB        3     0.0%    30.0%
-55.0 dB        3     0.0%    57.5%
```

Barrido del radio geométrico con umbral −70 dBm y N=3:

```
 Radio   Cobertura      FAR      FRR
--------------------------------------
 3.0 m       82.2%     0.0%    12.5%
 3.5 m       96.7%     0.0%     7.5%
 4.0 m      100.0%     0.0%     0.0%   <- configuración adoptada
```

| Métrica | Objetivo | Resultado | Estado |
| :--- | :---: | :---: | :---: |
| Tasa de falsos positivos (FAR) | ≤ 5.0% | **0.0%** (0/40 peatones) | 🟢 CUMPLE |
| Tasa de falsos negativos (FRR) | ≤ 5.0% | **0.0%** (0/40 asistentes) | 🟢 CUMPLE |

Reproducir:

```bash
PYTHONPATH=. python calibration_tools/threshold_tuner.py --seed 42
```

### 4.5 Lo que estos números sí y no sostienen

**Sí:** que la ventana de permanencia cumple su función. Con N=1 el FAR es del 35% —los peatones
cuya posición estimada cae dentro del aula por error del WKNN confirman asistencia— y baja a 0%
al exigir N=3. **La tesis central del proyecto queda respaldada**, ahora sí con un criterio en el
que el umbral de potencia interviene de verdad.

**No:** que el FAR real vaya a ser 0%. La población es sintética y hereda todas las limitaciones
de §1.1. En particular, el modelo asume que un peatón nunca se detiene frente a la puerta más de
2 lecturas; un alumno que conversa 30 segundos en el umbral sería indistinguible de uno sentado
en la última fila. Con un muestreo cada 1.5 s, N=3 cubre apenas 4.5 segundos de permanencia: es
inmunidad frente a quien *pasa*, no frente a quien *se detiene*.

> **Pendiente:** `window_timeout_seconds` ya tiene efecto, pero la ventana mide el hueco entre
> lecturas consecutivas, no una ventana deslizante sobre marcas de tiempo. Para permanencias
> largas (confirmar tras 5 minutos en el aula) haría falta lo segundo.

---

## 5. Auditoría de arquitectura de software (principios SOLID)

1. **Single Responsibility (SRP):** cada clase atiende una única preocupación — `BuildingGraph`
   modela la topología, `NavigationEngine` genera pistas, `WKNNPositioningService` computa
   coordenadas, `AttendanceTrackerService` gobierna los estados de presencia.
2. **Open/Closed (OCP):** los repositorios se definen como protocolos (`IRadioMapRepository`,
   `IAttendanceRepository`), lo que permite sustituir el almacenamiento JSON en memoria por
   SQLite o PostgreSQL sin tocar los servicios de negocio.
3. **Liskov / Interface Segregation (LSP / ISP):** protocolos acotados que no imponen métodos
   innecesarios a sus implementaciones.
4. **Dependency Inversion (DIP):** los servicios dependen de las abstracciones inyectadas en el
   constructor.

> **Salvedad honesta sobre el DIP.** La inversión de dependencias es completa en la capa de
> servicios, pero **no en la capa de API**: los routers y los manejadores de WebSocket resuelven
> sus dependencias con `from ..main import app_state` dentro de la propia función, un import
> diferido que evita un ciclo de importación. Es un localizador de servicios, no inyección de
> dependencias, y es la razón por la que las pruebas necesitan el `IsolatedAppStateMixin` de
> `backend/tests/helpers.py` para no escribir en `data/`.

---

## 6. Referencias

1. **Bahl, P., & Padmanabhan, V. N. (2000).** *RADAR: An in-building RF-based user location and
   tracking system.* IEEE INFOCOM 2000.
2. **Youssef, M., & Agrawala, A. (2005).** *The Horus WLAN location determination system.*
   ACM MobiSys 2005.
3. **Mostafa, S., Harras, K. A., & Youssef, M. (2024).** *A Survey of Indoor Localization Systems
   in Multi-Floor Environments.* IEEE Communications Surveys & Tutorials.
4. **Torres-Sospedra, J., et al. (2014).** *UJIIndoorLoc: A new multi-building and multi-floor
   database for WLAN fingerprint-based indoor localization problems.* IEEE IPIN.

> **Nota sobre la referencia a Horus.** El sistema persiste la desviación estándar por BSSID
> (`RadioMapEntry.rssi_std`) pero **no la utiliza**: `WKNNPositioningService` calcula una distancia
> euclidiana sin ponderación probabilística. El aporte de Horus —el modelado bayesiano de la
> incertidumbre del RSSI— está citado pero no implementado. Ver `PLAN_CORRECCIONES.md`, P2-4.

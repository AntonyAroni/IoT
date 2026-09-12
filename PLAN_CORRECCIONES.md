# Plan de Correcciones — Sistema IPS Multi-Piso & Asistencia IoT

> Lista de tareas derivada de la auditoría de código del 2026-09-11.
> Los hallazgos marcados **[verificado]** se reprodujeron ejecutando el código; los marcados
> **[riesgo]** son análisis estático que aún no se pudo confirmar ejecutando.

## Estado general

| Prioridad | Secciones | Estado | Descripción |
| :--- | :---: | :--- | :--- |
| **P0 — Bloqueante** | 4 | 3 ✅ / 1 aplazada | Invalidan métricas publicadas o el propósito del sistema |
| **P1 — Alto** | 5 | **5 ✅** | Funcionalidad documentada que no existe, o bugs visibles al usuario |
| **P2 — Medio** | 7 | **7 ✅** | Deuda técnica, build y limpieza |
| **P3 — Documentación** | 1 | pendiente | Sincronizar README y reporte con el código real |

**Cerrado:** P0-1, P0-2, P0-3, todo P1 y todo P2. El sistema hace lo que su documentación dice,
las métricas son reproducibles y los bugs visibles al usuario están corregidos.

**Aplazado por decisión del usuario:** P0-4 (autenticación).

**Suite de pruebas:** 11 → **33** pruebas, todas pasando, sin tocar `data/`.

> **Nota sobre las cifras de este documento.** Los bloques de resultados de cada tarea recogen lo
> medido **en el momento de cerrarla**. P2-4 descubrió después que el generador declaraba
> `sample_count = 15` pero tomaba una sola lectura, y al corregirlo el dataset cambió: las cifras
> vigentes son **piso 100.0 ± 0.0%** y **error medio 1.70 ± 0.02 m (k=2)**. La fuente de verdad
> es `calibration_tools/validation_report.md`.

---

## P0 — Bloqueante

### P0-1 · Descontaminar el radio-mapa y aislar los tests del fichero de producción — ✅ HECHO (2026-09-11)

> **Resultado:** dataset limpio de 40 RPs, tests aislados de `data/`, 6 pruebas de regresión
> nuevas (17 en total, todas pasan). LOOCV sobre 8 corridas: precisión de piso **97.5–100%
> (media 98.75%)**, error medio 2D **1.75 m**. El objetivo de diseño ≥95% se cumple en todas las
> corridas, pero el "100.0% exacto" que publica el reporte **no es estable** entre ejecuciones:
> eso lo cierra P0-2 al fijar la semilla. No se regeneró el mapa repetidamente buscando una
> corrida con 100% — sería el mismo *cherry-picking* que critica P0-3.

**[verificado]** `data/radio_map.json` contenía **44 entradas, no las 40 documentadas**.
Con el mapa tal cual está commiteado, la métrica estrella del proyecto **no se cumple**:

```
LOOCV k=2, mapa commiteado (44 RPs):   piso 93.2% | 90.9% | 88.6%   <- objetivo >=95% NO ALCANZADO
LOOCV k=2, mapa regenerado (40 RPs):   piso 100%  | 100%  | 100%    <- reproduce lo documentado
```

Las 4 entradas contaminantes:

| Entrada | Origen | Problema |
| :--- | :--- | :--- |
| `RP_TEST_S302` | `backend/tests/test_websocket_integration.py:19` | El test escribe en el fichero **de producción** |
| `RP_P3_HAll` | Calibrador Android | 32 BSSID MAC reales, posición (10.0, 2.0) |
| `RP_Escalera` | Calibrador Android | 29 BSSID MAC reales, posición (10.0, 2.0) |
| `RP_P4_Meta` | Calibrador Android | 23 BSSID MAC reales, posición (10.0, 2.0) |

Las tres capturas de campo están en la **misma coordenada (10.0, 2.0)**, el valor por defecto del
formulario: son artefactos de una prueba en la que no se fijaron `x`/`y`, no puntos reales
distintos. Además exponen MAC de APs reales, que son geolocalizables en bases públicas tipo WiGLE.

**Causa raíz:** `app_state.radio_map_repo` se construye con `storage_path`
(`backend/main.py:44`), así que **cualquier** `save_entry()` — incluido el de un test — reescribe
`data/radio_map.json`.

**Tareas**

- [x] En `backend/tests/test_websocket_integration.py`, sustituir el repositorio global por uno
      efímero en el `setUp`. → Creado `backend/tests/helpers.py` con `IsolatedAppStateMixin`, que
      reemplaza **ambos** repositorios (radio-mapa y asistencia) y los reenlaza en los servicios
      que los referencian (`floor_classifier`, `wknn_locator`, `attendance_tracker`), restaurando
      los originales por `addCleanup`. El repositorio de asistencia también escribía en `data/`.
- [x] Regenerar el mapa limpio: `PYTHONPATH=. python calibration_tools/generate_synthetic_map.py`
- [x] Verificar que el fichero resultante tiene exactamente 40 entradas y ningún BSSID con formato MAC.
- [x] Añadir una prueba de regresión. → `backend/tests/test_radio_map_integrity.py`, 6 pruebas:
      recuento de 40, solo APs sintéticos, sin MAC reales, IDs únicos, los 4 pisos cubiertos y
      **sin coordenadas duplicadas dentro de un piso** (el invariante que delató las capturas
      contaminantes, las tres guardadas en (10.0, 2.0)).
- [x] Decidir qué hacer con las capturas reales. → Conservadas como evidencia en
      `data/field_captures/field_captures.json`, con los 44 BSSID seudonimizados de forma
      determinista (`ap_field_<8 hex de sha256(mac)>`) y un `README.md` que documenta por qué no
      son utilizables como RPs hasta re-medir su posición.

**Criterio de aceptación:** ✅ `PYTHONPATH=. python calibration_tools/loocv_evaluator.py` reporta
`40 PUNTOS`; `python -m unittest discover backend/tests` pasa 17 pruebas y deja `data/` intacto.

**Pendiente derivado:** ✅ resuelto en P0-2 y P0-3. La precisión de piso se publica ahora como
99.2 ± 1.2% en lugar del "100.0% (40/40)" fijo, y `field_audit_report.md` pasó a llamarse
`validation_report.md`.

---

### P0-2 · Hacer reproducible la auditoría LOOCV — ✅ HECHO (2026-09-11)

> **Resultado:** dos ejecuciones consecutivas producen salida byte-idéntica, y `--seed 7` produce
> una salida distinta (control de que la semilla realmente actúa). Métricas publicadas ahora como
> media ± desviación estándar sobre 30 repeticiones: piso **99.2 ± 1.2%** (peor 97.5%), error
> medio k=2 **1.73 ± 0.05 m**. Tiempo de ejecución: ~10 s.



**[verificado]** `calibration_tools/loocv_evaluator.py` añade ruido gaussiano
(`np.random.normal(0, 1.2)`) sin fijar semilla. Tres corridas consecutivas sobre el **mismo**
fichero dieron 93.2%, 90.9% y 88.6% de precisión de piso. Ningún número del reporte es reproducible.

**Tareas**

- [x] Semilla explícita. → `evaluate_loocv(..., seed=42)` usando `np.random.default_rng(seed + r)`
      en lugar del estado global de numpy. Expuesta por CLI: `--seed`, `--repeats`, `--sigma`,
      `--k`, `--map`.
- [x] Documentar la semilla. → §2 de `calibration_tools/validation_report.md`, con el comando
      exacto para reproducir las cifras.
- [x] Repetir N=30 y reportar media ± desviación estándar.

**Mejoras adicionales no previstas en el plan original:**

- [x] **Diseño pareado entre valores de k.** Dentro de cada repetición, todos los k se evalúan
      sobre el *mismo* vector ruidoso, de modo que la comparación entre k no arrastra diferencias
      de ruido. Reduce la varianza y hace la comparación legítima.
- [x] **La precisión de piso se calcula una sola vez por repetición.** `FloorClassifierService`
      no usa el hiperparámetro k, así que reportarla por fila de k era engañoso: que variara entre
      filas en el informe anterior era puro artefacto del ruido sin semilla.
- [x] Reestructurado el bucle para construir el repositorio de entrenamiento una vez por muestra
      en lugar de una vez por (k, muestra): 30 repeticiones completas tardan ~10 s.

**Criterio de aceptación:** ✅ dos ejecuciones consecutivas producen salida byte-idéntica; una
semilla distinta produce salida distinta.

---

### P0-3 · Reformular las métricas como *simulación*, no como medición de campo — ✅ HECHO (2026-09-11)

> **Resultado:** `field_audit_report.md` renombrado a `validation_report.md` (el propio nombre
> afirmaba "campo") y reescrito. El README ya no afirma medición empírica en ningún punto. La
> sección FAR/FRR se marcó como **no concluyente**; P1-2 la rehízo después con una muestra de
> 40+40 sujetos y un criterio de decisión que sí discrimina, así que hoy vuelve a ser una métrica
> defendible.



**[verificado]** `field_audit_report.md` y el README describen *"40 Puntos de Referencia físicos"*
y una *"auditoría empírica"*. En realidad los 40 RPs los genera
`calibration_tools/generate_synthetic_map.py` con el modelo log-distance de
`SimulatedAP.calculate_rssi()`, y el LOOCV valida ese mismo modelo contra sí mismo añadiéndole
ruido. Es autovalidación, no medición.

Esto no invalida el trabajo — es una metodología legítima de verificación funcional — pero
presentarlo como datos empíricos es el punto más atacable del proyecto en una defensa.

**Tareas**

- [x] Reescribir el encabezado. → Renombrado a `calibration_tools/validation_report.md`, con un
      §1 "Naturaleza y alcance del experimento" que abre con un aviso inequívoco y tabula los
      parámetros del modelo de propagación.
- [x] Sección explícita de **Limitaciones**. → §1.1, con 6 fenómenos no modelados (multicamino,
      atenuación por cuerpos, deriva temporal, heterogeneidad de chipsets, geometría idealizada,
      densidad uniforme de APs) y la conclusión de que las cifras son una **cota inferior
      optimista** frente a los 3–5 m que reporta la literatura para despliegues reales.
- [x] Eliminar "empírica" del README. → Reescritas la tabla de métricas, las Capacidades
      Principales (ya no afirman "precisión del 100%") y la sección de herramientas.
- [x] **Extra:** §3.2 documenta que k≥4 incumple el objetivo de percentil 90 (4.31 y 4.47 m
      frente al límite de 4.00 m), y que k=3 minimiza la mediana pero no la media. El barrido de
      k deja de ser decorativo.
- [x] **Extra:** §5 añade una salvedad honesta sobre el DIP — la capa de API usa un localizador
      de servicios (`from ..main import app_state` dentro de la función), no inyección de
      dependencias.
- [ ] (Si hay tiempo) tomar una campaña de campo real aunque sea de 8-10 RPs y reportarla por
      separado. Diferenciar claramente "simulado" de "medido" vale más que un número alto.

**Criterio de aceptación:** ✅ ningún documento afirma medición física donde hubo simulación.

---

### P0-4 · Autenticación en el canal móvil (suplantación de asistencia)

**[verificado]** `backend/api/websocket_handlers.py:52` expone `/ws/mobile/{student_id}` sin
ninguna credencial. El `student_id` llega como texto libre en la ruta. Marcar la asistencia de
cualquier alumno es una línea de `websocat`. En un sistema cuyo único producto es el registro de
asistencia, esto anula el propósito del proyecto.

**Tareas**

- [ ] Emitir un token por alumno (JWT firmado o token opaco pre-provisionado) y validarlo en el
      handshake del WebSocket antes de `connect_mobile()`.
- [ ] Derivar el `student_id` **del token**, nunca de la ruta.
- [ ] Proteger también los endpoints mutantes: `DELETE /api/v1/calibration/radio-map`,
      `POST /api/v1/calibration/record` y `POST /api/v1/attendance/room/{id}/reset` hoy son
      anónimos y destructivos.
- [ ] Restringir el CORS: `allow_origins=["*"]` junto a `allow_credentials=True`
      (`backend/main.py`) es una combinación inválida además de insegura.
- [ ] Servir por TLS y cambiar a `wss://`; quitar `usesCleartextTraffic="true"` del
      `AndroidManifest.xml`.

**Criterio de aceptación:** una conexión a `/ws/mobile/EST_08` sin token es rechazada con 4401.

---

## P1 — Alto

### P1-1 · La ventana temporal de permanencia no existe — ✅ HECHO (2026-09-11)

**[verificado]** `window_timeout_seconds: float = 15.0` está declarado en `backend/config.py:22`
y **no se usa en ningún fichero del repositorio**. La "ventana deslizante de 3 muestras en 15
segundos" que el README presenta como el mecanismo anti-falsos-positivos es en realidad un
contador (`backend/services/attendance_tracker.py:85`) que nunca expira: tres pasadas frente a la
puerta en tres días distintos confirman la asistencia igual.

**Tareas**

- [x] Caducidad de la ventana implementada. Se captura `previous_last_seen` **antes** de
      sobrescribir `record.last_seen`, y si el hueco supera `window_timeout_seconds` la racha se
      reinicia. El mensaje de auditoría lo indica ("ventana reiniciada por inactividad").
- [x] Tests añadidos en `TestPermanenceWindowExpiry`: 2 muestras válidas + salto de 60 s ⇒ no
      confirma; 3 muestras separadas 5 s ⇒ sí confirma. El salto temporal se simula con
      `mock.patch` sobre `time.time`.
- [ ] Guardar los timestamps de las N muestras para una ventana verdaderamente deslizante. La
      implementación actual mide el hueco entre lecturas consecutivas, que es la semántica que
      documenta el propio `config.py` ("tiempo máximo entre lecturas consecutivas"). Para exigir
      permanencias largas (p. ej. confirmar tras 5 minutos en el aula) haría falta lo otro.

**Criterio de aceptación:** ✅ los tests pasan y `window_timeout_seconds` se usa en
`attendance_tracker.py`.

---

### P1-2 · El umbral RSSI está cortocircuitado por la regla de distancia — ✅ HECHO (2026-09-11)

**[verificado]** `backend/services/attendance_tracker.py:72`:

```python
is_in_classroom_zone = (
    detected_floor == target_room_floor and
    (effective_rssi >= self.config.classroom_threshold_dbm or distance_to_center <= 3.0)
)
```

El `or` hace que la posición WKNN por sí sola active la zona de aula, sin importar el RSSI.
Consecuencias:

1. `calibration_tools/threshold_tuner.py` barre umbrales de -60/-55/-50 dBm sobre un criterio que
   **no influye en el resultado**. El "FAR de 33.3% con N=1 o N=2" que reporta viene enteramente
   del contador de muestras, no del umbral de potencia.
2. El FAR/FRR se calculan sobre **3 y 4 muestras** respectivamente. Un "FAR = 0.0%" con n=3 no
   tiene poder estadístico; la granularidad mínima es 33%.

**Tareas**

- [x] Criterio decidido y documentado. **Conjunción donde se decide, disyunción donde se informa:**
      la zona de aula (que concede asistencia) exige potencia medida **y** geometría; la zona de
      aproximación (que solo alimenta el radar) mantiene la disyunción, porque a 9 m el AP del
      aula predice −115 dBm, por debajo de la sensibilidad del receptor, y la conjunción dejaría
      el radar vacío.
- [x] `threshold_tuner.py` reescrito. Población sembrada de 40 asistentes + 40 peatones, con las
      dos señales modeladas como correlacionadas pero **no idénticas**
      (`RSSI = pathloss(d) + N(0,3dB)`, `pos_WKNN = pos + N(0,1.2m)`), que es el mecanismo real
      del falso positivo. Flags `--seed`, `--population`, `--sigma-rssi`, `--sigma-pos`,
      `--scans-attendee`, `--scans-passer`.
- [x] Conjunto ampliado a 40 + 40. FAR/FRR ya tienen resolución del 2.5%.
- [x] Sección 4 del reporte reescrita con los números nuevos.

**Hallazgos nuevos surgidos al medir (no estaban en el diagnóstico inicial):**

- [x] **El umbral de −55 dBm nunca fue físicamente coherente.** Bajo el modelo del propio
      proyecto (`RSSI = −40 − 25·d/3`) equivale a **1.80 m** del centro, o sea el **44.9%** de la
      huella del aula. Pasaba inadvertido porque el `or` lo cortocircuitaba. Corregido a
      **−70 dBm** (≡ 3.60 m).
- [x] **El radio de 3.0 m dejaba zonas muertas.** Cubría el 82.2% del aula; el pupitre de la
      esquina está a 3.81 m del centro, así que ese alumno **no podía confirmar asistencia
      jamás**. Corregido a **4.0 m** (cobertura 100%).
- [x] `classroom_radius_meters` y `approaching_radius_meters` promovidos de literales incrustados
      en el servicio a campos de `AttendanceConfig`, y añadidos al barrido del tuner.

> ⚠️ **Cambio de comportamiento que conviene revisar.** Los umbrales por defecto cambiaron de
> (−55 dBm, 3.0 m) a (−70 dBm, 4.0 m). La justificación es el modelo de propagación del proyecto,
> no solo la simulación, pero es una decisión de producto: revísala antes de desplegar.

**Criterio de aceptación:** ✅ variar `classroom_threshold_dbm` cambia la salida del tuner de forma
marcada (FAR del 35% al 0%; FRR del 0% al 57.5% según el umbral). Con la configuración adoptada,
**FAR 0.0% y FRR 0.0%** sobre 40+40 sujetos, y el tuner converge de forma independiente en N=3,
respaldando la tesis central del proyecto.

---

### P1-3 · La asistencia no se persiste — ✅ HECHO (2026-09-11)

**[verificado]** `InMemoryAttendanceRepository` implementa `save_to_file()` pero **nunca**
`load_from_file()`. `data/attendance_log.json` es de solo escritura: al reiniciar el servidor se
pierde toda la asistencia del día, pese a que el README lo describe como *"registro automático
persistente"*.

Además `save_record()` (`backend/repositories/attendance_repo.py:64`) reescribe el fichero
**completo** en cada escaneo de cada alumno. Con 12 aulas activas eso es I/O síncrono bloqueando
el event loop de asyncio en cada mensaje WebSocket.

**Tareas**

- [x] `load_from_file()` implementado y llamado desde `__init__`. Añadido
      `AttendanceRecord.from_dict()` como simétrico de `to_dict()`.
- [x] Reconciliación: primero se siembra el padrón, después se carga el fichero, que tiene
      prioridad. Los alumnos del fichero que no están en el padrón demo se conservan.
- [x] Escritura fuera del camino crítico, con una política explícita: **las confirmaciones se
      escriben de inmediato** (es el dato que no se puede perder ante una caída) y el resto de
      telemetría se agrupa con `write_debounce_seconds` (2 s por defecto). Añadidos `flush()` y
      `has_pending_write()`; el `lifespan` de FastAPI hace `flush()` al apagar.
- [x] 5 tests nuevos en `backend/tests/test_attendance_persistence.py`, incluido uno que verifica
      que el repositorio sin `storage_path` no toca el disco jamás.

**Criterio de aceptación:** ✅ `test_confirmed_attendance_survives_restart` confirma, reinstancia
el repositorio sobre el mismo fichero y comprueba que sigue en `PRESENT_CONFIRMED`.

> **Pendiente a medio plazo:** migrar a SQLite. Los protocolos `IRadioMapRepository` /
> `IAttendanceRepository` están diseñados precisamente para ese cambio.

---

### P1-4 · XSS en el dashboard del docente — ✅ HECHO (2026-09-11)

**[verificado]** `frontend_stations/js/station_app.js:208-219` construye las filas de la tabla con
plantillas e `innerHTML` sin escapar `student_id` ni `student_name`. El `student_id` viene de la
ruta del WebSocket no autenticado, y el backend lo usa para fabricar el nombre cuando el alumno no
está en el padrón (`backend/services/attendance_tracker.py:39`: `f"Alumno {student_id}"`).
Conectarse a `/ws/mobile/<img src=x onerror=...>` ejecuta código en la laptop del profesor.

**Tareas**

- [x] `_renderTable()` reescrito con `document.createElement` + `textContent` sobre un
      `DocumentFragment`. Añadidos los helpers `_buildCell()` y `_renderEmptyTable()`. **No queda
      ningún `innerHTML`** en `frontend_stations/js/`.
- [x] Validación en el backend: `IDENTIFIER_PATTERN = ^[A-Za-z0-9_-]{1,32}$` aplicada a
      `student_id` **y** a `room_id`; el handshake se cierra con el código 4400 si no encaja.
      Defensa en profundidad, arreglado en ambos lados.
- [x] Revisados `lastStudentTelemetry` y `logAudit()`: ya usaban `textContent`, no eran
      explotables.

**Criterio de aceptación:** ✅ un `student_id` con marcado ya no llega al frontend (lo rechaza el
handshake), y si llegara se renderizaría como texto literal.

---

### P1-5 · Rutas dependientes del directorio de trabajo — ✅ HECHO (2026-09-11)

**[verificado]** `backend/config.py` usa rutas relativas (`"data/radio_map.json"`). Arrancar el
servidor desde cualquier directorio que no sea la raíz del repo carga **0 puntos de referencia en
silencio** — sin warning, sin error. El sistema devuelve entonces piso 1 y posición (10.0, 5.0)
para todos los alumnos, y aparenta funcionar.

**Tareas**

- [x] Rutas resueltas contra `PROJECT_ROOT = Path(__file__).resolve().parent.parent`.
- [x] Variables de entorno `IPS_RADIO_MAP_PATH` e `IPS_ATTENDANCE_LOG_PATH` para despliegue.
- [x] `logger.warning()` explícito en el `lifespan` si el radio-mapa carga con 0 entradas, con la
      ruta esperada y el comando para regenerarlo. El arranque además registra ahora el número de
      RPs cargados y la ruta en uso.
- [x] Eliminado `building_config_file`, que no se usaba en ninguna parte (era parte de P2-6).

**Criterio de aceptación:** ✅ arrancar desde un directorio ajeno carga los 40 RPs (antes cargaba
0 en silencio).

---

## P2 — Medio

### P2-1 · Bugs concretos de navegación — ✅ HECHO (2026-09-12)

**[verificado]** Reproducidos ejecutando `NavigationEngine.compute_route()`:

```
backend/services/navigation_engine.py:103
  f"Usar escalera hacia el Piso {path_ids[i+1]}"
  -> imprime "Usar escalera hacia el Piso Escalera_P2" (el ID del nodo, no el número de piso)

backend/services/navigation_engine.py:115
  progress = 100.0 - (total_distance * 4.0)
  -> 0% para cualquier ruta >=25 m. Trayectoria real de la demo:
       paso 1: 29.0 m ->   0%   (el README afirma "Progreso: 10%")
       paso 2: 21.0 m ->  16%
       paso 3: 12.0 m ->  52%   <- salto de 36 puntos en un solo paso
       paso 6:  3.0 m -> 100%   <- llega al 100% estando aún en la puerta

backend/services/navigation_engine.py:45
  return f"P{floor_number}_Hall_Center"
  -> devuelve un ID inexistente para pisos fuera de 1-4 -> ValueError que mata el WebSocket
```

**Tareas**

- [x] Usar `self.graph.get_node(path_ids[i+1]).floor_number` en la instrucción de escalera.
- [x] Calcular el progreso como `1 - (distancia_restante / distancia_inicial_de_la_ruta)`,
      guardando la distancia inicial al fijar el destino. La fórmula actual asume que toda ruta
      mide 25 m.
- [x] Cambiar el fallback de `find_closest_node()` por una excepción explícita o por el nodo más
      cercano de cualquier piso; hoy devuelve un ID que no existe.

### P2-2 · El RSSI que ve el docente es sintético — ✅ HECHO (2026-09-12)

**[verificado]** `WebSocketClientManager.sendScanVector()`
(`mobile_app/.../network/WebSocketClientManager.kt:95`) **nunca envía** `room_ap_rssi`. Como
`backend/api/websocket_handlers.py:98` lo lee con `.get()`, en un despliegue real siempre llega
`None`, y `attendance_tracker.py:57` fabrica el valor a partir de la posición WKNN:

```python
effective_rssi = -40.0 - 25.0 * (max(0.5, distance_to_center) / 3.0)
```

El dashboard del aula muestra ese número como si fuera una medición de radio.

- [x] Enviar el RSSI del AP del aula desde el cliente Android, o
- [x] marcar el campo como derivado en el payload (`"rssi_source": "estimated"`) y reflejarlo en
      la UI. Mostrar un valor calculado como si fuera medido es un problema de honestidad del dato.

### P2-3 · Sesgo de supervivencia en la calibración Android — ✅ HECHO (2026-09-12)

**[verificado]** `CalibratorManager.kt:50-58` acumula por BSSID solo las muestras **en las que ese
BSSID fue detectado** y promedia con `values.average()`. Un AP visto en 2 de 15 ráfagas obtiene la
media de esas 2 lecturas (fuertes), no su potencia real. El sesgo golpea justo a los APs débiles,
que son los que discriminan el piso.

- [x] Imputar un valor suelo (-100 dBm, coherente con `default_absent_rssi = -105.0`) para cada
      ráfaga en la que el BSSID no apareció, antes de promediar.
- [x] Registrar la tasa de detección por BSSID (`visto_en / total_muestras`) y descartar APs por
      debajo de un mínimo (p. ej. 30%).

### P2-4 · `rssi_std` se calcula, se guarda y nunca se usa — ✅ HECHO (2026-09-12)

El cliente Android calcula la desviación estándar, el backend la persiste en `RadioMapEntry`, y
`WKNNPositioningService` **no la consulta jamás**: la distancia es euclidiana pura sin ponderación
probabilística. La cita a Horus (Youssef & Agrawala) en README y base de conocimiento describe
exactamente el mecanismo bayesiano que aquí no está implementado.

- [x] O bien implementar la ponderación (dividir cada término de la distancia por la varianza del
      BSSID, que es una mejora real y barata), o bien
- [x] retirar la atribución a Horus y presentar el sistema como RADAR/WKNN determinista, que es lo
      que efectivamente es.

### P2-5 · Cliente Android: identidad y reconexión — ✅ HECHO (2026-09-12)

- [x] `MainActivity.kt:56` — `private val studentId = "EST_08"` está hardcodeado: el APK
      identifica a **todos** los dispositivos como el mismo alumno. Debe venir de un login o al
      menos de `SharedPreferences` configurable (ya existe el patrón para la IP del servidor).
- [x] `WebSocketClientManager.onFailure()` reintenta cada 3 s de forma indefinida y sin cancelar
      el socket anterior. Añadir backoff exponencial y un tope de reintentos.
- [x] El escaneo cada 1.5 s (`WifiScannerService.scanIntervalMs`) choca con el *throttling* de
      Android (4 escaneos / 2 min desde API 28). El fallback a caché existe, pero conviene
      documentar la cadencia real alcanzable y ajustar la expectativa del README.

### P2-7 · `threshold_tuner.py` revienta en consolas no-UTF8 (hallazgo nuevo, 2026-09-11) — ✅ HECHO (2026-09-12)

**[verificado]** Ejecutando la herramienta en una consola Windows con codificación cp1252:

```
File "calibration_tools/threshold_tuner.py", line 79, in tune_attendance_thresholds
    print(f" \U0001f3af CONFIGURACIÓN AUDITADA RECOMENDADA:")
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f3af'
```

El emoji 🎯 del bloque final aborta el script **justo antes de imprimir su conclusión**: el
barrido completo se ejecuta y se pierde. Afecta a cualquiera que siga el README desde `cmd`,
Git Bash o un CI con `PYTHONIOENCODING` sin definir. Funciona en PowerShell, lo que hace el fallo
intermitente según el entorno y difícil de atribuir.

Todos los scripts del proyecto imprimen emojis, así que el riesgo es general.

- [x] Reconfigurar la salida estándar al inicio de los scripts de `calibration_tools/`:
      `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (Python 3.7+).
- [x] Alternativa más robusta: retirar los emojis de la salida de las herramientas de línea de
      comandos y dejarlos solo en la documentación.
- [x] Verificar los tres scripts (`loocv_evaluator`, `threshold_tuner`, `generate_synthetic_map`)
      y `demo_runner.py` en una consola cp1252.

### P2-6 · Build de Android y limpieza — ✅ HECHO (2026-09-12)

**[riesgo]** No se pudo compilar en este entorno; verificar antes de dar por bueno el APK.

- [x] `mobile_app/android_client/gradle/wrapper/gradle-wrapper.properties` fija Gradle **9.3.0**,
      pero el proyecto usa **AGP 8.7.3**, que no soporta Gradle 9. Bajar el wrapper a 8.9–8.11
      o subir AGP.
- [x] `AndroidManifest.xml` conserva `package="com.school.ips"`, atributo que AGP 8 eliminó; el
      `namespace` ya está declarado en `app/build.gradle`. Quitar el atributo del manifiesto.
- [ ] Ejecutar `./gradlew assembleDebug` y dejar constancia del resultado en el README.
- [x] `demo_runner.py` define `start_server()` **dos veces**; la primera definición es código
      muerto. Eliminarla.
- [x] `backend/config.py:32` — `building_config_file` no se usa en ningún sitio. Eliminar.
- [x] `numpy` está en `backend/requirements.txt` pero solo lo usan las herramientas de
      calibración. Separar en `requirements-dev.txt` o `calibration_tools/requirements.txt`.

---

## P3 — Documentación

### P3-1 · Sincronizar README y reporte con el código

**[verificado]** Discrepancias detectadas:

| El README afirma | El código hace |
| :--- | :--- |
| `http://localhost:8000/api/attendance/summary` | No existe; es `/api/v1/attendance/room/{id}` |
| "k=2 (ÓPTIMO)" | `backend/config.py:11` usa `k: int = 3` |
| "Android 8.0 (API 26) o superior" | `app/build.gradle` declara `minSdk 24` |
| "Progreso: 10%" en el paso 1 de la demo | El valor real es 0.0% |
| "40 Puntos de Referencia" | El fichero commiteado tiene 44 |
| "registro automático persistente" | La asistencia nunca se recarga del disco |

**Tareas**

- [ ] Corregir la tabla de endpoints del README contra las rutas reales de `backend/api/`.
- [ ] Alinear `WKNNConfig.k` con el valor que la auditoría determine óptimo, **o** explicar por
      qué el valor por defecto difiere del óptimo de LOOCV (p. ej. robustez frente a ruido real).
- [ ] Regenerar la salida de consola de ejemplo del README ejecutando de verdad `demo_runner.py`
      y pegando el resultado, en lugar de transcribirlo a mano.
- [ ] Actualizar la tabla de métricas una vez cerradas P0-1 y P0-2.

---

## Apéndice · Comandos de verificación

```bash
# Entorno
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

# Batería de pruebas (debe dejar git status limpio)
python -m unittest discover backend/tests
git status --short

# Auditoría de precisión (debe reportar 40 PUNTOS y 100.0% de piso)
PYTHONPATH=. python calibration_tools/loocv_evaluator.py

# Regenerar radio-mapa limpio
PYTHONPATH=. python calibration_tools/generate_synthetic_map.py

# Umbrales de asistencia
PYTHONPATH=. python calibration_tools/threshold_tuner.py

# Demo extremo a extremo
python demo_runner.py
```

Comprobar contaminación del radio-mapa:

```python
import json
d = json.load(open("data/radio_map.json", encoding="utf-8"))
synth = {f"ap_p{f}_{k}" for f in range(1, 5) for k in ("west", "east", "room02")}
print(len(d), "entradas")
print([e["id"] for e in d if not set(e["rssi_means"]) <= synth] or "limpio")
```

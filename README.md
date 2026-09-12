# 📡 Sistema de Localización en Interiores (IPS) y Asistencia Inteligente IoT

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Android](https://img.shields.io/badge/Android-Kotlin-3DDC84.svg)](https://developer.android.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Sistema integral de mapeo, posicionamiento en interiores (Indoor Positioning System - IPS) multi-piso y registro automatizado de asistencia académica basado en *Wi-Fi Fingerprinting*, grafos topológicos y WebSockets en tiempo real.**

---

## 📋 Tabla de Contenidos
1. [Descripción General](#-descripción-general)
2. [Arquitectura del Sistema (Las 3 Divisiones)](#-arquitectura-del-sistema)
3. [Fundamento Teórico y Algoritmos](#-fundamento-teórico-y-algoritmos)
4. [Estructura del Proyecto](#-estructura-del-proyecto)
5. [Requisitos y Tecnologías](#-requisitos-y-tecnologías)
6. [Instalación y Configuración](#-instalación-y-configuración)
7. [Guía de Ejecución](#-guía-de-ejecución)
   - [Demostración Rápida Extremo a Extremo](#1-demostración-rápida-extremo-a-extremo)
   - [Ejecución del Servidor Backend](#2-ejecución-del-servidor-backend)
   - [Acceso al Frontend de Estaciones (Laptops de Salón)](#3-acceso-al-frontend-de-estaciones)
   - [Uso del Sensor Móvil Virtual](#4-uso-del-sensor-móvil-virtual)
   - [Cliente Android Nativo](#5-cliente-android-nativo)
8. [Herramientas de Calibración y Auditoría](#-herramientas-de-calibración-y-auditoría)
9. [Batería de Pruebas Unitarias](#-batería-de-pruebas-unitarias)
10. [Métricas y Resultados Obtenidos](#-métricas-y-resultados-obtenidos)

---

## 🔭 Descripción General

En entornos cerrados y edificios de múltiples niveles (como escuelas, universidades y hospitales), la señal satelital **GPS es atenuada por losas de concreto y techos**, volviéndose inútil para la localización precisa.

Este proyecto resuelve la localización en interiores utilizando la infraestructura existente de **puntos de acceso Wi-Fi (AP)** mediante la técnica de **Radio Fingerprinting**. El sistema modela un edificio de **4 pisos y 12 salones** (3 aulas por piso: `S101`-`S103`, `S201`-`S203`, `S301`-`S303`, `S401`-`S403`), pasillos centrales y núcleo de escaleras.

### Capacidades Principales
- 🏢 **Detección Jerárquica de Piso:** Identificación del nivel aprovechando la atenuación de losas de concreto (~14 dBm/piso); **99.2%** de acierto en validación simulada.
- 📍 **Posicionamiento 2D Continuo (WKNN):** Algoritmo *Weighted k-Nearest Neighbors* con error medio de **1.73 m** ($k=2$) en validación simulada — ver las limitaciones del modelo en `calibration_tools/validation_report.md`.
- 🧭 **Navegación Paso a Paso (*Turn-by-Turn*):** Grafo dirigido con algoritmo de Dijkstra que emite instrucciones dinámicas en tiempo real (*"Sube a la escalera al piso 3"*, *"Gira a la derecha hacia el Salón 302 a 4 m"*, *"¡Has llegado!"*).
- ⏱️ **Asistencia Inteligente sin Contacto:** Algoritmo con ventana temporal de permanencia ($N=3$ escaneos continuos que superen $-70\text{ dBm}$ **y** estén a $\le 4\text{ m}$ del centro del aula) que previene falsos positivos causados por alumnos que solo transitan por el pasillo frente a la puerta abierta.
- 💻 **Radar de Proximidad en Aulas:** Dashboard interactivo en tiempo real para las laptops docentes de cada aula con visualización de radar, notificaciones sonoras y registro automático persistente.

---

## 🏛 Arquitectura del Sistema

El proyecto está diseñado bajo una arquitectura desacoplada de 3 divisiones operativas:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DIVISIÓN 1: CLIENTE MÓVIL                             │
│  • App Nativa Android (Kotlin / WifiManager) para lectura real de BSSID & RSSI. │
│  • Modo Calibrador / Mapeo para levantamiento offline de radio-mapas.           │
│  • Interfaz de Guiado al estudiante con pistas paso a paso.                     │
│  • Simulador Python (VirtualMobileSensor) para pruebas y CI/CD automatizado.   │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ WebSocket / REST (JSON)
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│               DIVISIÓN 2: SERVIDOR CENTRAL Y CEREBRO IPS (BACKEND)              │
│  • FastAPI + Uvicorn con soporte asíncrono y WebSockets full-duplex.            │
│  • Clasificador Jerárquico de Piso (análisis energético por nivel).             │
│  • Motor de Fingerprinting WKNN (Métricas Euclidiana / Manhattan).              │
│  • Motor de Rutas y Navegación Topológica (Dijkstra sobre grafo del edificio).  │
│  • Tracker de Asistencia con máquina de estados de proximidad y permanencia.    │
│  • Repositorios de persistencia en JSON (`radio_map.json`, `attendance_log`).   │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Eventos de Proximidad por WebSocket
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                DIVISIÓN 3: ESTACIONES DE SALÓN (FRONTEND WEB)                   │
│  • Web Application moderna (HTML5, Vanilla JS, CSS3 con estética Cyberpunk).    │
│  • Visualizador Radar de proximidad en tiempo real (Canvas API).                │
│  • Notificaciones acústicas sintetizadas (Web Audio API) al confirmar presencia.│
│  • Tablero de asistencia dinámico filtrado por aula (`/estacion/?room=S302`).   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧠 Fundamento Teórico y Algoritmos

### 1. Detección Jerárquica de Piso
Dado un vector en línea de lecturas recibidas desde el móvil:
$$V_{\text{online}} = \{ (b_1, r_1), (b_2, r_2), \dots, (b_m, r_m) \}$$
donde $b_i$ representa el identificador físico BSSID y $r_i$ el nivel de señal RSSI en dBm.

El piso se calcula mediante correlación de máxima potencia sobre los puntos de acceso dominantes asignados a cada piso:
$$\text{Piso} = \arg\max_k \sum_{j \in \text{APs}_{Piso_k}} w_j \cdot r_j$$

### 2. Posicionamiento Métrico 2D: Weighted $k$-Nearest Neighbors (WKNN)
Dentro del piso clasificado, se calcula la distancia euclidiana entre el vector online y los vectores del radio-mapa offline:
$$d_i = \sqrt{\sum_{j=1}^{N} (r_{\text{online}, j} - r_{\text{offline}, i, j})^2}$$

Se ordenan los $k$ puntos de referencia con menor distancia y se pondera su posición en coordenadas $(x, y)$:
$$(x, y) = \frac{\sum_{i=1}^k \frac{1}{d_i + \epsilon} \cdot (x_i, y_i)}{\sum_{i=1}^k \frac{1}{d_i + \epsilon}}$$
*(donde $\epsilon = 10^{-6}$ evita divisiones por cero).*

### 3. Modelo de Navegación por Grafo y Dijkstra
El edificio se representa como un grafo dirigido $G = (V, E)$, donde cada nodo representa un punto notable (salón, pasillo, descansos de escalera) con coordenadas $(x, y, z)$. El motor calcula la ruta geodésica mínima y genera las pistas textuales en función de la posición actual del estudiante y su salón destino.

### 4. Lógica de Asistencia y Prevención de Falsos Positivos
- **Aproximación:** RSSI $\ge -70\text{ dBm}$ (el estudiante aparece en el radar del aula).
- **Dentro del Aula:** RSSI $\ge -70\text{ dBm}$ **y** distancia estimada $\le 4\text{ m}$ del centro del aula.
- **Confirmación de Asistencia:** Se exige una ventana de **3 muestras consecutivas** ($N=3$) que cumplan ambas condiciones, con un intervalo máximo de 15 segundos entre lecturas. Si se supera ese intervalo, la racha se rompe y el contador se reinicia.

> **Sobre la elección de los umbrales.** Ambos criterios describen el mismo hecho físico, así que deben ser equivalentes bajo el modelo de propagación del propio proyecto ($RSSI = -40 - 25 \cdot d/3$): $-70\text{ dBm}$ corresponde a $3.60\text{ m}$, y el radio de $4\text{ m}$ cubre el 100% de la huella del aula, incluido el pupitre más alejado (a $3.81\text{ m}$ del centro). El valor anterior de $-55\text{ dBm}$ equivalía a solo $1.80\text{ m}$, menos de la mitad del aula. Ver §4.2 de `calibration_tools/validation_report.md`.
>
> La conjunción se aplica **solo** a la zona de aula, que es la que concede asistencia. La zona de aproximación que alimenta el radar usa disyunción, porque es informativa y a $9\text{ m}$ el AP del aula ya no es legible.

---

## 📂 Estructura del Proyecto

```
.
├── BASE_DE_CONOCIMIENTO.md       # Documento técnico de referencia y estado del arte
├── demo_runner.py                # Script orquestador de demostración integral extremo a extremo
├── backend/                      # Servidor Central IPS (FastAPI + WebSockets)
│   ├── config.py                 # Configuración de hiperparámetros (WKNN, umbrales, puertos)
│   ├── main.py                   # Punto de entrada de la aplicación FastAPI y ruteo
│   ├── requirements.txt          # Dependencias de Python del proyecto
│   ├── api/                      # Controladores REST y WebSockets
│   │   ├── routes_attendance.py  # Endpoints de consulta y registro de asistencia
│   │   ├── routes_building.py    # Información topológica y aulas del edificio
│   │   ├── routes_calibration.py # Endpoints para calibración de mapas de radio
│   │   ├── routes_navigation.py  # Endpoints de cálculo de rutas y pistas
│   │   └── websocket_handlers.py # Manejadores de sockets para móviles y estaciones
│   ├── domain/                   # Modelos de dominio y entidades de negocio
│   │   ├── attendance.py         # Entidades de asistencia y estados
│   │   ├── building.py           # Modelos de piso, aula y coordenadas
│   │   ├── fingerprint.py        # Vectores de señal y mapa de radio
│   │   └── graph.py              # Estructura de grafo y nodos de navegación
│   ├── repositories/             # Capa de acceso a datos (Patrón Repository)
│   │   ├── attendance_repo.py    # Persistencia de registros de asistencia
│   │   └── radio_map_repo.py     # Carga y almacenamiento de huellas de señal
│   ├── services/                 # Lógica de negocio y motores matemáticos
│   │   ├── attendance_tracker.py # Máquina de estados de presencia y permanencia
│   │   ├── connection_manager.py # Gestión de conexiones WebSockets concurrentes
│   │   ├── floor_classifier.py   # Clasificación jerárquica de piso
│   │   ├── navigation_engine.py  # Algoritmo de rutas y generación de pistas
│   │   └── wknn_locator.py       # Motor de localización continua WKNN
│   └── tests/                    # Batería de pruebas unitarias automatizadas
│       ├── test_attendance_logic.py
│       ├── test_graph_navigation.py
│       ├── test_websocket_integration.py
│       └── test_wknn_positioning.py
├── calibration_tools/            # Herramientas de calibración, simulación y auditoría
│   ├── validation_report.md      # Reporte de validación LOOCV (simulación) y limitaciones
│   ├── generate_synthetic_map.py # Generador de radio-mapas bajo modelo log-distance
│   ├── loocv_evaluator.py        # Evaluador Leave-One-Out Cross-Validation
│   ├── synthetic_test_suite.py   # Suite de pruebas de estrés bajo diferentes escenarios
│   └── threshold_tuner.py        # Sintonizador de umbrales RSSI y ventana temporal
├── data/                         # Almacenamiento local de datos en formato JSON
│   ├── attendance_log.json       # Historial persistente de asistencias marcadas
│   └── radio_map.json            # Base de datos de huellas de señal (Fingerprints)
├── frontend_stations/            # Tablero Web para Laptops de Salón
│   ├── index.html                # Interfaz principal del aula
│   ├── css/
│   │   └── station.css           # Estilos visuales tipo radar / monitor
│   └── js/
│       ├── audio_service.js      # Notificaciones sonoras con Web Audio API
│       ├── radar_widget.js       # Widget de radar animado en Canvas
│       ├── station_app.js        # Lógica de actualización y renderizado UI
│       └── ws_client.js          # Cliente WebSocket para eventos en tiempo real
└── mobile_app/                   # Clientes móviles de escaneo y navegación
    ├── android_client/           # Proyecto nativo Android (Android Studio / Kotlin)
    │   ├── app/src/main/         # Código fuente Kotlin, layouts XML y manifiesto
    │   ├── build.gradle          # Configuración de compilación Gradle
    │   └── gradlew               # Wrapper de Gradle para construcción
    └── virtual_sensor/           # Sensor móvil virtual para simulación y pruebas
        └── virtual_scanner.py    # Emulador de escaneos Wi-Fi según trayectoria
```

---

## 🛠 Requisitos y Tecnologías

### Backend & Herramientas
- **Python 3.10 o superior**
- **FastAPI** (framework web asíncrono)
- **Uvicorn** (servidor ASGI de alto rendimiento)
- **WebSockets** (comunicación bidireccional en tiempo real)
- **NumPy** (cálculo matricial y distancias euclidianas)
- **Pydantic v2** (validación de datos y esquemas)

### Frontend
- Navegador web moderno con soporte para **WebSockets**, **HTML5 Canvas** y **Web Audio API** (Chrome, Firefox, Edge, Safari).

### Cliente Móvil Android (Opcional para dispositivo físico)
- **Android Studio Giraffe / Ladybug / Iguana** o superior
- **JDK 17**
- Dispositivo Android con **Android 8.0 (API 26) o superior** y soporte Wi-Fi.

---

## 🚀 Instalación y Configuración

### 1. Clonar el Repositorio
```bash
git clone https://github.com/AntonyAroni/IoT.git
cd IoT
```

### 2. Crear y Activar un Entorno Virtual de Python
```bash
# En Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# En Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Instalar Dependencias
```bash
pip install -r backend/requirements.txt
```

---

## 🕹 Guía de Ejecución

### 1. Demostración Rápida Extremo a Extremo
El proyecto incluye un script orquestador maestro (`demo_runner.py`) que levanta el servidor IPS, abre una estación de aula virtual para el **Salón 302**, y hace que un estudiante simulado recorra el edificio desde la entrada en el Piso 1 subiendo por las escaleras hasta ingresar al aula en el Piso 3:

```bash
python demo_runner.py
```

**Salida en consola:**
```text
================================================================================
 🚀 INICIANDO DEMOSTRACIÓN INTEGRAL DEL SISTEMA IPS & ASISTENCIA IOT
    • FASE 1: Cerebro Backend (Grafo 4 Pisos + WKNN + WebSockets)
    • FASE 2: Estación Laptop (Dashboard de Aula S302)
    • FASE 3: Sensor Móvil (Telemetría Wi-Fi + Navegación por Pistas)
    • FASE 4: Calibración y Auditoría en Campo
    • URL Servidor: http://127.0.0.1:8000
================================================================================

💻 [LAPTOP SALÓN 302]: Conectada exitosamente. Esperando alumnos...

[Paso 1/9] 📱 MÓVIL: Inicio en entrada principal - Piso 1
  📍 Ubicación Real: Piso 1 (2.0m, 5.0m)
  🧠 Estimación IPS: Piso 1 (2.0m, 5.0m)
  🗣️ Pista: "Avanza por el pasillo central hacia la escalera."
  📊 Progreso: 10% | Estado: NOT_REGISTERED
...
  💻 [LAPTOP SALÓN 302]: Radar detectó a 'Carlos Mendoza' | Estado: CONFIRMED | Distancia: 0.5m | RSSI: -48.2 dBm
```

---

### 2. Ejecución del Servidor Backend

Para ejecutar el servidor de manera independiente:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

- Documentación interactiva Swagger UI: **`http://localhost:8000/docs`**
- Verificación de estado de salud: **`http://localhost:8000/health`**
- Endpoints REST de asistencia: **`http://localhost:8000/api/attendance/summary`**

---

### 3. Acceso al Frontend de Estaciones

Cada laptop de aula puede abrir el panel interactivo especificando el identificador del salón en el parámetro URL:
- Salón 101: `http://localhost:8000/estacion/?room=S101`
- Salón 202: `http://localhost:8000/estacion/?room=S202`
- Salón 302: `http://localhost:8000/estacion/?room=S302`
- Salón 403: `http://localhost:8000/estacion/?room=S403`

El panel muestra:
- Radar visual en Canvas que proyecta a los estudiantes en un radio de 10 metros.
- Estado en vivo: *Fuera de rango*, *Aproximándose*, *En puerta*, *Asistencia Confirmada*.
- Efectos acústicos al validar la asistencia.
- Lista histórica y exportable de asistencias de la clase.

---

### 4. Uso del Sensor Móvil Virtual

Si deseas simular trayectorias personalizadas o emitir escaneos Wi-Fi programáticamente hacia el servidor:
```bash
PYTHONPATH=. python mobile_app/virtual_sensor/virtual_scanner.py
```

---

### 5. Cliente Android Nativo

La carpeta `mobile_app/android_client/` contiene el proyecto en Android Studio con las siguientes características:
- **`WifiScannerService.kt`**: Escanea puntos de acceso circundantes utilizando `WifiManager` con permisos `ACCESS_FINE_LOCATION`.
- **`WebSocketClientManager.kt`**: Establece conexión bidireccional de baja latencia con el servidor central.
- **`CalibratorManager.kt`**: Permite recolectar huellas (*Fingerprints*) en modo offline asociándolas a coordenadas $(x, y)$ de cada piso.
- **`MainActivity.kt`**: Muestra el piso actual estimado, la pista activa y la flecha direccional hacia el aula de destino.

**Para compilar desde terminal:**
```bash
cd mobile_app/android_client
./gradlew assembleDebug
```
El APK resultante se genera en `app/build/outputs/apk/debug/app-debug.apk`.

---

## 📊 Herramientas de Calibración y Auditoría

La carpeta `calibration_tools/` ofrece scripts científicos para validar la precisión del sistema:

### 1. Validación LOOCV (Leave-One-Out Cross-Validation)
Evalúa el error métrico y la precisión de piso ante diferentes valores del hiperparámetro $k$:
```bash
PYTHONPATH=. python calibration_tools/loocv_evaluator.py
```

El experimento es **reproducible**: el ruido se extrae de un generador con semilla fija y el
resultado se promedia sobre varias repeticiones. Opciones disponibles:

```bash
--seed 42        # Semilla del generador de ruido (por defecto 42)
--repeats 30     # Repeticiones del experimento; se reporta media ± desviación estándar
--sigma 1.2      # Desviación del ruido gaussiano añadido, en dBm
--k 1 2 3 4 5    # Valores del hiperparámetro a evaluar
--map <ruta>     # Radio-mapa alternativo a auditar
```

### 2. Sintonizador de Umbrales de Asistencia
Analiza las tasas de falsos positivos (FAR) y falsos negativos (FRR) variando el umbral de potencia ($RSSI_{th}$) y el tamaño de la ventana de escaneos:
```bash
PYTHONPATH=. python calibration_tools/threshold_tuner.py
```

Evalúa 40 asistentes reales y 40 peatones generados con un modelo sembrado, y barre además el
radio geométrico del aula. Opciones: `--seed`, `--population`, `--sigma-rssi`, `--sigma-pos`,
`--scans-attendee`, `--scans-passer`. Ver §4 de `calibration_tools/validation_report.md`.

### 3. Generador de Mapas de Radio Sintéticos
Permite regenerar el archivo `data/radio_map.json` modelando atenuación por distancia logarítmica y pérdidas por losas/muros:
```bash
PYTHONPATH=. python calibration_tools/generate_synthetic_map.py
```

---

## 🧪 Batería de Pruebas Unitarias

El proyecto cuenta con un conjunto completo de pruebas unitarias que validan la lógica de posicionamiento, navegación sobre grafos, integración por WebSockets y máquina de estados de asistencia:

```bash
python -m unittest discover backend/tests
```

**Resultado esperado:**
```text
...........
----------------------------------------------------------------------
Ran 11 tests in 0.062s

OK
```

---

## 📈 Métricas y Resultados de Validación

> ⚠️ **Estas cifras provienen de una simulación, no de mediciones en un edificio real.** Los 40
> puntos de referencia son sintéticos, generados con un modelo de propagación log-distance
> (PLE = 2.8, atenuación de losa 14 dB, σ = 1.5 dB) y validados por LOOCV contra ese mismo
> modelo. Constituyen una verificación funcional de los algoritmos, no una medida de su precisión
> en campo. El detalle completo, con las limitaciones del modelo, está en
> `calibration_tools/validation_report.md`.

Validación LOOCV sobre 40 RPs sintéticos, semilla 42, 30 repeticiones (media ± desviación estándar):

| Métrica | Objetivo de Diseño | Resultado Obtenido | Estado |
| :--- | :---: | :---: | :---: |
| **Aislamiento de Piso** | $\ge 95.0\%$ | **99.2 ± 1.2%** (mín. 97.5%) | 🟢 CUMPLE |
| **Error Medio 2D ($k=2$)** | $\le 2.50\text{ m}$ | **1.73 ± 0.05 m** | 🟢 CUMPLE |
| **Error Mediano 2D** | $\le 2.20\text{ m}$ | **1.98 ± 0.02 m** | 🟢 CUMPLE |
| **Percentil 90 del Error** | $\le 4.00\text{ m}$ | **2.71 ± 0.02 m** | 🟢 CUMPLE |
| **RMSE Métrico** | $\le 3.00\text{ m}$ | **2.16 ± 0.10 m** | 🟢 CUMPLE |
| **Tasa de Falsos Positivos (FAR)** | $\le 5.0\%$ | **0.0%** (0/40 peatones, $N=3$) | 🟢 CUMPLE |
| **Tasa de Falsos Negativos (FRR)** | $\le 5.0\%$ | **0.0%** (0/40 asistentes) | 🟢 CUMPLE |

Reproducir estas cifras exactamente:

```bash
PYTHONPATH=. python calibration_tools/loocv_evaluator.py --seed 42 --repeats 30
PYTHONPATH=. python calibration_tools/threshold_tuner.py --seed 42
```

**Sobre FAR/FRR:** con $N=1$ el FAR es del 35% (peatones cuya posición estimada cae dentro del
aula por error del WKNN) y baja a 0% al exigir $N=3$ lecturas sostenidas. Con un muestreo cada
1.5 s, $N=3$ cubre unos 4.5 segundos: es inmunidad frente a quien **pasa** por delante de la
puerta, no frente a quien **se detiene** a conversar en el umbral. Ver §4.5 del reporte de
validación.

---

## 📚 Referencias Científicas

1. **Bahl, P., & Padmanabhan, V. N. (2000).** *RADAR: An in-building RF-based user location and tracking system.* IEEE INFOCOM 2000.
2. **Youssef, M., & Agrawala, A. (2005).** *The Horus WLAN location determination system.* ACM MobiSys 2005.
3. **Mostafa, S., Harras, K. A., & Youssef, M. (2024).** *A Survey of Indoor Localization Systems in Multi-Floor Environments.* IEEE Communications Surveys & Tutorials.
4. **Torres-Sospedra, J., et al. (2014).** *UJIIndoorLoc: A new multi-building and multi-floor database for WLAN fingerprint-based indoor localization problems.* IEEE IPIN.

---

## 👨‍💻 Autor y Contacto

- **Antony Aroni**
- Universidad Nacional de San Agustín (UNSA)
- Correo: `aaronij@unsa.edu.pe`
- Repositorio GitHub: [https://github.com/AntonyAroni/IoT](https://github.com/AntonyAroni/IoT)

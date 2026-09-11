# Base de Conocimiento y Arquitectura de Sistema: Localización en Interiores y Asistencia IoT

> **Proyecto:** Sistema de Mapeo, Localización en Interiores (IPS) y Registro de Asistencia Inteligente en Edificio Escolar Multi-Piso.  
> **Escenario:** Edificio de 4 pisos, 3 salones por piso (12 salones en total) con conectividad Wi-Fi y laptops en cada aula.

---

## 1. Las 3 Divisiones del Proyecto

El sistema se estructura formalmente en **3 módulos o divisiones independientes y complementarias**:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DIVISIÓN 1: CLIENTE MÓVIL (APK)                       │
│  • Escaneo activo de señales Wi-Fi (BSSIDs y RSSI) con API WifiManager.         │
│  • Modo Mapeo / Calibrador para recolectar huellas de señal en la fase offline. │
│  • Interfaz de Navegación: Muestra ubicación actual, piso y pistas paso a paso  │
│    ("Sube al piso 3", "Gira a la derecha hacia el Salón 302").                 │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ WebSocket / REST (JSON)
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│               DIVISIÓN 2: SERVIDOR CENTRAL Y CEREBRO DE LOCALIZACIÓN            │
│  • Motor de Fingerprinting (Algoritmo WKNN / Scikit-Learn en Python).          │
│  • Clasificador Jerárquico: 1º Detección de Piso -> 2º Posición 2D / Salón.     │
│  • Motor de Rutas y Navegación (Grafo topológico del edificio + Dijkstra).     │
│  • Gestor de Base de Datos: Alumnos, horarios de clases, coordenadas y radio map.│
│  • Servidor WebSocket en tiempo real (FastAPI / Socket.io).                     │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Eventos WebSocket en tiempo real
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                DIVISIÓN 3: ESTACIONES DE SALÓN (WEB APP EN LAPTOPS)             │
│  • Aplicativo Web ligero ejecutado en el navegador de la laptop de cada salón.  │
│  • Identificación por aula (ej. /salon/101, /salon/202, etc.).                  │
│  • Panel de Detección de Proximidad: Muestra alertas cuando un alumno se acerca. │
│  • Módulo de Asistencia: Valida horario, confirma presencia y marca asistencia.  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Marco Teórico y Papers Académicos (Estado del Arte)

Para fundamentar la memoria técnica, tesis o reporte de investigación del proyecto, se detallan los artículos científicos de referencia:

### A. Fundamentos de Wi-Fi Fingerprinting
1. **RADAR: An In-Building RF-based User Location and Tracking System**
   * *Autores:* P. Bahl, V. N. Padmanabhan (Microsoft Research).
   * *Publicación:* **IEEE INFOCOM 2000**.
   * *Citas:* +13,000.
   * *Aporte clave:* Creó el paradigma de *Radio Fingerprinting*. Demostró que la propagación compleja de radiofrecuencia en interiores no necesita modelarse geométricamente con precisión si se crea una base de datos previa de intensidades de señal (RSS) y se compara con $k$-Nearest Neighbors ($k$-NN).

2. **Horus: A WLAN-Based Indoor Localization System**
   * *Autores:* M. Youssef, A. Agrawala.
   * *Publicación:* **ACM MobiSys 2005**.
   * *Aporte clave:* Introduce modelos probabilísticos bayesianos para manejar las fluctuaciones temporales y el ruido del RSSI causados por personas en movimiento y obstáculos físicos.

### B. Localización en Edificios de Varios Pisos (Multi-Floor)
3. **A Survey of Indoor Localization Systems in Multi-Floor Environments**
   * *Autores:* S. Mostafa, K. A. Harras, M. Youssef.
   * *Publicación:* **IEEE Communications Surveys & Tutorials (2024)**.
   * *Aporte clave:* Describe las metodologías para resolver el problema en 2.5D/3D. Destaca la importancia de una arquitectura en cascada: primero aislar el piso correcto (con precisión > 95% aprovechando la atenuación de 10–20 dBm por losa de concreto) antes de computar la coordenada 2D dentro del salón o pasillo.

4. **UJIIndoorLoc: A New Multi-Building and Multi-Floor Database for WLAN Fingerprint-Based Indoor Localization Problems**
   * *Autores:* J. Torres-Sospedra et al.
   * *Publicación:* **IPIN / IEEE (2014)**.
   * *Aporte clave:* El estándar internacional de datos abiertos para probar y validar algoritmos de detección de piso y salón usando teléfonos inteligentes comerciales.

5. **Wi-Fi RSS Fingerprinting-Based Indoor Localization in Large Multi-Floor Buildings**
   * *Publicación:* **Sensors (MDPI, 2024/2025)**.
   * *Aporte clave:* Evalúa algoritmos de Machine Learning modernos (Weighted k-NN, Random Forest, Multi-Layer Perceptrons) aplicados a campus educativos con múltiples plantas.

### C. Sistemas de Asistencia Inteligente (Smart Campus)
6. **Automated Attendance Management System Using Wi-Fi and Bluetooth Sensing in Smart Campus**
   * *Publicación:* **IEEE Internet of Things Journal / IEEE Access**.
   * *Aporte clave:* Lógica de validación de presencia por umbral de permanencia: un dispositivo solo se considera asistente si su RSSI supera el umbral del aula (ej. $\ge -55\text{ dBm}$) de manera estable durante un periodo mínimo continuo en la ventana horaria de la clase.

---

## 3. Principio Físico y Matemático del Algoritmo

### A. Detección Jerárquica de Piso
Dado un vector de lecturas en vivo recibido del móvil:
$$V_{\text{online}} = \{ (b_1, r_1), (b_2, r_2), \dots, (b_m, r_m) \}$$
donde $b_i$ es el BSSID y $r_i$ es el RSSI en dBm.

El piso se determina mediante el piso de máxima correlación energética o clasificador entrenado:
$$\text{Piso} = \arg\max_k \sum_{j \in \text{APs}_{Piso_k}} w_j \cdot r_j$$

### B. Weighted $k$-Nearest Neighbors (WKNN) en 2D
En el piso identificado, se compara el vector con la base de datos de huellas de ese piso:
$$d_i = \sqrt{\sum_{j=1}^{N} (r_{\text{online}, j} - r_{\text{offline}, i, j})^2}$$
Se seleccionan los $k$ puntos más cercanos (menor distancia Euclidiana $d_i$) y se pondera la posición:
$$(x, y) = \frac{\sum_{i=1}^k \frac{1}{d_i + \epsilon} \cdot (x_i, y_i)}{\sum_{i=1}^k \frac{1}{d_i + \epsilon}}$$

---

## 4. Modelado del Edificio para Guiado y Pistas (Grafo Topológico)

Para guiar al estudiante ("sube un piso", "gira a la derecha"), el edificio de 4 pisos y 12 salones se modela con un **Grafo Dirigido**:

* **Piso 1:**
  * Salones: `S101`, `S102`, `S103`
  * Pasillo Central: `P1_Pasillo`
  * Escalera: `Escalera_P1`
* **Piso 2:**
  * Salones: `S201`, `S202`, `S203`
  * Pasillo Central: `P2_Pasillo`
  * Escalera: `Escalera_P2`
* **Piso 3:**
  * Salones: `S301`, `S302`, `S303`
  * Pasillo Central: `P3_Pasillo`
  * Escalera: `Escalera_P3`
* **Piso 4:**
  * Salones: `S401`, `S402`, `S403`
  * Pasillo Central: `P4_Pasillo`
  * Escalera: `Escalera_P4`

### Lógica de Navegación:
1. El algoritmo de ruta más corta (**Dijkstra**) calcula el camino entre la ubicación actual estimada y el salón donde el alumno tiene clase según el horario.
2. Si $\text{Piso}_{\text{actual}} < \text{Piso}_{\text{destino}}$: Pista $\rightarrow$ *"Dirígete a la escalera y sube al Piso X"*.
3. Si $\text{Piso}_{\text{actual}} == \text{Piso}_{\text{destino}}$: Pista $\rightarrow$ *"Avanza hacia [Izquierda / Derecha] hacia el Salón XYZ (a N metros)"*.
4. Si $\text{Distancia al Salón} \le 2\text{ metros}$: Pista $\rightarrow$ *"¡Has llegado a tu salón!"*.

---

## 5. Decisiones de Despliegue y Conectividad

1. **¿Por qué una APK en lugar de Web pura en el móvil?**
   * Las políticas de seguridad de Chrome/Safari bloquean el escaneo de redes Wi-Fi (BSSID/RSSI) desde páginas web.
   * La APK Android usa `WifiManager` con permiso `ACCESS_FINE_LOCATION`, permitiendo lecturas precisas.
2. **¿Local o Nube para el Servidor?**
   * **Desarrollo / Pruebas:** Laptop local ejecutando Python FastAPI + túnel seguro con **ngrok** para evitar problemas de aislamiento de clientes (*Client Isolation*) del router escolar.
   * **Producción / Presentación Final:** Despliegue en la nube en **Render** (FastAPI + WebSockets persistentes) con base de datos en **Supabase**.
3. **¿Cómo se conectan las laptops de los salones?**
   * Cada laptop solo necesita abrir el navegador en la URL asignada a su aula: ej. `https://mi-servidor.onrender.com/dashboard/salon/201`.
   * Mantiene un WebSocket abierto recibiendo notificaciones en tiempo real cuando el alumno se aproxima.

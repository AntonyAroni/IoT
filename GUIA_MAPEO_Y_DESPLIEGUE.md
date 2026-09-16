# Guía Maestra de Mapeo, Despliegue Multi-Laptop y Pruebas en Entorno Real (IPS)

Esta guía detalla la metodología técnica y operativa para realizar pruebas de simulación y localización en un entorno real (un piso escolar con salones contiguos), resolver la conectividad multi-dispositivo y desplegar el sistema coordinando varias laptops y smartphones.

---

## 1. Análisis Técnico: ¿Vercel o Despliegue Local / Túnel?

> [!CAUTION]
> **¿Por qué Vercel NO es compatible con este proyecto?**
> 1. **Arquitectura Serverless Efímera:** Vercel está diseñado para sitios web y APIs *stateless* (funciones AWS Lambda que se apagan tras ejecutarse). En un sistema IPS en tiempo real, el Radio-Mapa, el Gestor de Conexiones WebSocket (`ConnectionManager`) y los estados de asistencia continua de los alumnos residen en memoria activa (`ApplicationState`). En Vercel, la memoria se destruye en cada petición o frío de función (*cold start*).
> 2. **WebSockets Incompatibles:** Las funciones serverless de Vercel terminan las conexiones TCP tras 15 a 30 segundos. No permiten mantener canales WebSocket bidireccionales continuos y persistentes a 10 Hz entre los sensores móviles y las laptops.
> 3. **Conclusión:** Intentar desplegar este backend en Vercel romperá la comunicación en vivo del radar, la telemetría continua y el tracking de presencia.

### Las 3 Soluciones Reales de Despliegue

```
                                    ┌────────────────────────────────────────────────────────┐
                                    │               LAPTOP 1: SERVIDOR MAESTRO               │
                                    │  • FastAPI + WebSockets Persistentes (:8000)           │
                                    │  • Base de datos en memoria (Radio Map + Asistencia)  │
                                    │  • Filtros Kalman 1D + Cinemático 2D                   │
                                    └──────────────────────────┬─────────────────────────────┘
                                                               │
                                  ┌────────────────────────────┴────────────────────────────┐
                                  │                                                         │
                MÉTODO A: Hotspot Wi-Fi Local                                MÉTODO B: Cloudflare Tunnel (Gratuito)
         (Recomendado: 0 ms lag, sin internet)                        (Recomendado si hay redes distintas / 4G)
       • La laptop crea Zona Wi-Fi móvil                            • Terminal: `cloudflared tunnel --url http://localhost:8000`
       • Todas las laptops y móviles se conectan                    • Genera: `https://mi-ips.trycloudflare.com`
       • Salta el Client Isolation escolar                          • Los móviles y laptops se conectan sin configurar IPs
```

| Método | Dónde corre el backend | Ventajas | Ideal para |
| :--- | :--- | :--- | :--- |
| **A. Red Local con Hotspot (Laptop Hub)** | En tu Laptop Maestra | Cero latencia ($< 5\text{ ms}$), no depende de que el Wi-Fi del colegio tenga internet, salta el aislamiento de clientes (*Client Isolation*). | El día de la presentación en el aula / auditorio. |
| **B. Local con Túnel Cloudflare (`cloudflared`)** | En tu Laptop Maestra con túnel | Gratis, da enlace HTTPS/WSS público (`https://xxx.trycloudflare.com`), los celulares pueden estar en datos móviles (4G/5G) y las laptops en Wi-Fi. | Pruebas cuando el router del colegio bloquea puertos o aisla dispositivos. |
| **C. Nube Persistente (Render / Railway / Fly.io)** | Contenedor Docker en la nube | Activo 24/7 en internet con soporte completo de WebSockets nativos de Python. | Producción final abierta al público. |

---

## 2. Arquitectura y Asignación de Roles para Varias Laptops (1 Piso)

Si dispones de varias laptops para mapear y probar 1 piso (ej. Piso 1 con Salones 101, 102 y 103):

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       PISO 1 (PLANTA DEL EDIFICIO)                                │
│                                                                                                   │
│  ┌──────────────────────┐        ┌──────────────────────┐        ┌──────────────────────┐         │
│  │      AULA S101       │        │      AULA S102       │        │      AULA S103       │         │
│  │   [ LAPTOP FIJA 2 ]  │        │   [ LAPTOP FIJA 3 ]  │        │   [ LAPTOP FIJA 4 ]  │         │
│  │ /estacion/?room=S101 │        │ /estacion/?room=S102 │        │ /estacion/?room=S103 │         │
│  └──────────┬───────────┘        └──────────┬───────────┘        └──────────┬───────────┘         │
│             │ Puerta S101                   │ Puerta S102                   │ Puerta S103         │
│  ═══════════╧═══════════════════════════════╧═══════════════════════════════╧═══════════════════  │
│                                    PASILLO CENTRAL DEL PISO 1                                     │
│     🚶‍♂️ Celular 1 (Alumno EST_01)           🚶‍♀️ Celular 2 (Alumno EST_02)                          │
│                                                                                                   │
│                                 [ LAPTOP 1: SERVIDOR MAESTRO ]                                    │
│                             (En sala de profesores, mesa de control)                              │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Laptop 1 (Servidor Maestro / Torre de Control):**
   - Ejecuta el backend Python: `python3 -m backend.main` o `uvicorn backend.main:app --host 0.0.0.0 --port 8000`.
   - Abre el navegador en `http://localhost:8000/estacion/` para monitorear el padrón general o telemetría global.
2. **Laptop 2 (Estación Fija en Salón 101):**
   - Se coloca físicamente en el escritorio del profesor del Salón 101.
   - Abre en Chrome: `http://<IP_LAPTOP_1>:8000/estacion/?room=S101`.
   - Muestra el Radar de Proximidad y reproduce alertas sonoras cuando el alumno asignado al 101 se aproxima por el pasillo.
3. **Laptop 3 (Estación Fija en Salón 102):**
   - En el Salón 102. Abre: `http://<IP_LAPTOP_1>:8000/estacion/?room=S102`.
4. **Laptop 4 (Estación Fija en Salón 103):**
   - En el Salón 103. Abre: `http://<IP_LAPTOP_1>:8000/estacion/?room=S103`.
5. **Teléfonos Celulares (Nodos Sensores Peatonales):**
   - Cada estudiante lleva su celular con la app Android instalada.
   - En la app, cada uno configura su usuario independiente (`EST_01`, `EST_02`, etc.) en el botón **"Cambiar Alumno"**. Esto evita colisiones de sesión y permite tracking simultáneo.

---

## 3. Protocolo Operativo: ¿Cómo Mapear el Piso Paso a Paso?

El mapeo en interiores (fase de calibración offline) consiste en construir el **Radio-Mapa**: una tabla que asocia coordenadas métricas físicas $(x, y)$ con las intensidades de señal de los Access Points del entorno.

### A. Preparación del Plano y Cuadrícula (Sistema de Coordenadas)

1. Define el punto origen $(0.00\text{ m}, 0.00\text{ m})$ en una esquina clara del piso (ejemplo: esquina inferior izquierda del pasillo).
2. Determina el eje $X$ (horizontal a lo largo del pasillo) y eje $Y$ (profundidad hacia adentro del aula).
3. **Medición métrica de aulas contiguas:**
   - Si las aulas están pegadas una al lado de la otra separadas por un muro de concreto:
     - **Aula 101:** Puerta en $(x = 4.00, y = 5.00)$, Centro en $(x = 4.00, y = 2.00)$.
     - **Aula 102:** Puerta en $(x = 10.00, y = 5.00)$, Centro en $(x = 10.00, y = 2.00)$.
     - **Aula 103:** Puerta en $(x = 16.00, y = 5.00)$, Centro en $(x = 16.00, y = 2.00)$.
   - En el pasillo, define puntos de referencia cada **1.5 a 2.0 metros**:
     - `RP_P1_Hall_1`: $(x = 2.00, y = 5.00)$
     - `RP_P1_Hall_2`: $(x = 4.00, y = 5.00)$ (Frente a S101)
     - `RP_P1_Hall_3`: $(x = 7.00, y = 5.00)$ (Entre S101 y S102)
     - `RP_P1_Hall_4`: $(x = 10.00, y = 5.00)$ (Frente a S102)
     - `RP_P1_Hall_5`: $(x = 13.00, y = 5.00)$ (Entre S102 y S103)
     - `RP_P1_Hall_6`: $(x = 16.00, y = 5.00)$ (Frente a S103)
     - `RP_P1_Hall_7`: $(x = 18.00, y = 5.00)$ (Acceso a Escaleras)

### B. Ajuste Clave en los Teléfonos Android (¡Imprescindible!)

> [!WARNING]
> Desde Android 9 (Pie) en adelante, el sistema operativo incluye **"Wi-Fi Scan Throttling"** para ahorrar batería, bloqueando escaneos a solo 4 cada 2 minutos.
> **Debes desactivarlo en cada teléfono antes de mapear o probar:**
> 1. Ve a *Ajustes* -> *Acerca del teléfono*.
> 2. Toca 7 veces seguidas en *Número de compilación* para activar *Opciones de Desarrollador*.
> 3. Entra a *Opciones de Desarrollador* -> busca **"Estrangulamiento de búsqueda de Wi-Fi"** (o *Wi-Fi scan throttling*) y **DESACTÍVALO**.
> Con esto, la app podrá escanear ráfagas en vivo cada 1.5 segundos sin bloqueos.

### C. Procedimiento de Muestreo Físico con la App Móvil

1. Abre la APK en el celular y asegúrate de que esté conectada al servidor (indicador verde `● Conectado`).
2. Toca el botón **"Modo Calibrador (Offline)"**.
3. Párate exactamente en el punto físico a calibrar (ej. puerta de S101).
4. Configura en pantalla:
   - **ID del Punto:** `RP_S101_Door`
   - **Piso:** Piso 1
   - **Coord X (m):** `4.00`
   - **Coord Y (m):** `5.00`
5. **Captura de Muestras (Criterio Científico de Atenuación Corporal):**
   - El cuerpo de una persona atenúa de $3\text{ a }6\text{ dBm}$ la señal Wi-Fi a 2.4/5 GHz si se interpone entre el router y el teléfono.
   - Sostén el celular a la altura del pecho.
   - Presiona **"Capturar Muestra RSSI"** (capturará 1 muestra).
   - Rota $90^\circ$ sobre tu propio eje y captura otra muestra.
   - Repite hasta completar **15 muestras** en las 4 orientaciones cardinales.
6. Presiona **"Enviar Huella al Servidor"**:
   - La app promediará los RSSI con 2 decimales y enviará la firma matemática al servidor central, guardándolo en `data/radio_map.json`.
7. Avanza al siguiente punto físico y repite el proceso.

---

## 4. Fundamentos Científicos de las Mejoras Implementadas (Papers)

Para respaldar tu proyecto ante jurados o en la memoria técnica, las mejoras añadidas implementan las siguientes contribuciones:

### 1. Filtro de Kalman 1D por BSSID (*Discrete Kalman Filter*)
* **Problema:** El canal inalámbrico interior sufre *multipath fading* (interferencias constructivas y destructivas por rebotes en paredes y pupitres), provocando que el RSSI fluctúe instantáneamente entre $\pm 8\text{ dBm}$ aun estando quieto.
* **Solución Implementada (`signal_filters.py`):** Un filtro estocástico que pondera la predicción teórica con la medición real según la covarianza de ruido ($Q=0.08, R=2.5$). Suprime el ruido impulsivo sin añadir retardo al caminar.

### 2. Diferencial de Fuerza de Señal (SSD / D-RSSI)
* **Referencia:** Torres-Sospedra et al., *UJIIndoorLoc Standard Benchmark*, IEEE IPIN.
* **Problema:** Un celular Xiaomi puede reportar $-58\text{ dBm}$ y un Samsung $-65\text{ dBm}$ exactamente en el mismo pupitre debido a ganancias de antena distintas ($G_{\text{Xiaomi}} \ne G_{\text{Samsung}}$).
* **Solución Implementada (`compute_differential_rssi`):** Al restar pares de Access Points:
  $$\Delta RSSI_{A,B} = RSSI_A - RSSI_B = (P_A + G) - (P_B + G) = P_A - P_B$$
  La ganancia de la antena $G$ se cancela algebraicamente, logrando inmunidad ante diferentes marcas de celular.

### 3. Filtro Cinemático de Trayectoria 2D (Anti-Teletransportación)
* **Problema:** Si dos aulas contiguas tienen huellas de radio similares, una lectura atípica podía hacer que la posición estimada saltara instantáneamente a través de la pared al aula vecina.
* **Solución Implementada (`TrajectoryKinematicFilter2D`):** Se establece la restricción física de velocidad peatonal máxima ($v_{\max} = 1.8\text{ m/s}$). Si la distancia Euclídea entre estimaciones consecutivas supera la distancia caminable admisible en ese intervalo $\Delta t$, el salto se acota y se aplica una media móvil exponencial suave (EMA).

### 4. Algoritmo WKNN Adaptativo
* **Problema:** Usar un $k=3$ fijo cuando el usuario está prácticamente encima de un punto de referencia calibrado ($d_{\text{signal}} < 3.5$) degrada la precisión al incorporar puntos más lejanos en el promedio ponderado.
* **Solución Implementada (`select_adaptive_k`):** Si la similitud del vecino más cercano es muy alta, el algoritmo contrae $k$ a 2 para anclarse firmemente al punto de calibración.

---

## 5. Checklist para el Día de la Prueba Real

- [ ] **Laptop Maestra:** Conectada a la corriente, backend corriendo en puerto 8000.
- [ ] **Red:** Zona Wi-Fi (Hotspot) activada o túnel Cloudflare ejecutándose.
- [ ] **Laptops de Salón:** Conectadas a la URL de su salón respectivo (ej. `/estacion/?room=S101`), volumen encendido para escuchar chimes de confirmación.
- [ ] **Celulares:** Wi-Fi Scan Throttling desactivado en *Opciones de Desarrollador*.
- [ ] **Identidad:** Cada alumno ingresó su ID (`EST_01`, `EST_02`) en la app antes de iniciar la caminata.
- [ ] **Prueba de Camino:** El alumno camina desde el pasillo hacia el salón; la estación del aula emite sonido sonar en el umbral y confirma la asistencia tras cumplir las muestras de permanencia.

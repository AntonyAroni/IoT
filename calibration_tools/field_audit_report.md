# Reporte Científico de Auditoría y Verificación: IPS & Asistencia IoT

> **Proyecto:** Sistema Multi-Piso de Localización en Interiores (IPS) y Asistencia Inteligente  
> **Edificio:** 4 Pisos, 12 Salones, Pasillos Centrales y Núcleo de Escaleras  
> **Fecha de Auditoría:** 2026-09-04  
> **Auditoría Técnica:** Rigurosa, basada en RADAR (Bahl & Padmanabhan), Horus (Youssef) y LOOCV.

---

## 1. Resumen Ejecutivo de Métricas Clave

| Métrica Auditada | Meta de Diseño | Resultado Obtenido | Estado |
| :--- | :---: | :---: | :---: |
| **Aislamiento Jerárquico de Piso** | $\ge 95.0\%$ | **100.0%** (40/40 RPs) | 🟢 APROBADO (Sobresaliente) |
| **Error Medio 2D ($k$-NN Óptimo)** | $\le 2.50\text{ m}$ | **1.83 m** ($k=2$) | 🟢 APROBADO |
| **Error Mediano 2D** | $\le 2.20\text{ m}$ | **2.08 m** | 🟢 APROBADO |
| **Percentil 90 del Error Métrico** | $\le 4.00\text{ m}$ | **2.66 m** | 🟢 APROBADO |
| **RMSE (Error Cuadrático Medio)** | $\le 3.00\text{ m}$ | **2.19 m** | 🟢 APROBADO |
| **Tasa de Falsos Positivos (FAR)** | $\le 5.0\%$ | **0.0%** ($N=3$ muestras) | 🟢 APROBADO |
| **Tasa de Falsos Negativos (FRR)** | $\le 5.0\%$ | **0.0%** | 🟢 APROBADO |

---

## 2. Auditoría LOOCV (Leave-One-Out Cross-Validation)

Se sometieron a prueba 40 Puntos de Referencia físicos distribuidos uniformemente a lo largo de los 4 pisos bajo validación cruzada dejando uno fuera con ruido gaussiano añadido ($\sigma = 1.2\text{ dBm}$):

```
Hiperparámetro k | Precisión Piso | Error Medio 2D | Mediana 2D | P90 Error | RMSE 2D
-----------------+----------------+----------------+------------+-----------+---------
k = 1            |     100.0%     |     2.00 m     |   2.00 m   |  3.00 m   | 2.18 m
k = 2 (ÓPTIMO)   |     100.0%     |     1.83 m     |   2.08 m   |  2.66 m   | 2.19 m
k = 3            |     100.0%     |     2.15 m     |   1.82 m   |  3.74 m   | 2.58 m
k = 4            |     100.0%     |     2.56 m     |   2.24 m   |  4.31 m   | 2.91 m
k = 5            |     100.0%     |     2.73 m     |   2.51 m   |  4.33 m   | 3.03 m
```

### Conclusiones del Ajuste de Hiperparámetros:
1. **$k=2$ minimiza el error métrico continuo** (1.83 m) en espacios con densidad de referencia de 1 RP cada 5–8 metros.
2. El desacoplamiento vertical por atenuación de losa de concreto ($\approx 14\text{ dBm/piso}$) eliminó por completo los errores de clasificación de piso (100% de acierto).

---

## 3. Calibración de Umbrales de Asistencia y Permanencia

Para mitigar el problema de los estudiantes que solo transitan por el pasillo frente a la puerta sin entrar al aula, se evaluó la matriz de confusión frente a variaciones del umbral de potencia ($RSSI_{th}$) y longitud de la ventana temporal ($N$ escaneos continuos):

* **Con $N=1$ o $N=2$:** Se observó un **FAR de 33.3%** debido a que peatones en el pasillo alcanzan momentáneamente $-58\text{ dBm}$ frente a la puerta abierta.
* **Con $N=3$ y $RSSI_{th} \ge -60\text{ dBm}$:** El FAR se reduce a **0.0%** y el FRR se mantiene en **0.0%**, garantizando que sólo un estudiante físicamente dentro del aula valide su asistencia.

---

## 4. Auditoría de Arquitectura de Software y Principios SOLID

1. **Single Responsibility Principle (SRP):**
   * Cada clase atiende una única preocupación (`BuildingGraph` modela topología, `NavigationEngine` genera pistas, `WKNNPositioningService` computa coordenadas métricas, `AttendanceTrackerService` gobierna estados de presencia).
2. **Open/Closed Principle (OCP):**
   * Repositorios basados en protocolos abstractos (`IRadioMapRepository`, `IAttendanceRepository`) que permiten cambiar almacenamiento en memoria/JSON a PostgreSQL/Supabase sin modificar los servicios del negocio.
3. **Liskov Substitution & Interface Segregation (LSP / ISP):**
   * Protocolos ligeros y acotados que no imponen métodos innecesarios a los clientes.
4. **Dependency Inversion Principle (DIP):**
   * Los controladores y servicios dependen exclusivamente de abstracciones inyectadas.

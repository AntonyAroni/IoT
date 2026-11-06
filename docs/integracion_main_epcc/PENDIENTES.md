# Pendientes

Orden recomendado. Responsable: **L** = Luis, **A** = AntonyAroni, **E** = todo el equipo.

## ¿Está listo para producción?

**No.** Hoy sirve como demo o prototipo. Para operar en la EPCC faltan, como mínimo:

| Bloqueante | Por qué | Dónde |
|---|---|---|
| Revisión de Antony pendiente | Las correcciones tocan su código. Las 118 pruebas ya pasan, también su `test_room_mapping.py` | Fase 1 |
| Endpoints que mueven aulas sin protección | Cualquiera en la red puede desplazar un aula y romper la asistencia | Fase 2 |
| Tráfico en claro | TLS sigue aparcado | Fase 2 |
| No hay radio-mapa real | `data/radio_map.json` tiene 1 punto. El de 40 es sintético y su LOOCV es circular | Fase 3 |
| Radio de asistencia no ajustado | 4 m no cubren el aula real (las esquinas quedan a 6,35 m del centro) | Fase 4 |
| Plano sin cerrar | 4 cotas por verificar; pisos 1 y 4 sin confirmar | Fase 3 |

**Ya está listo:** la integración de las dos ramas, el modelo EPCC, la corrección de los dos fallos de sincronización de aulas y las 118 pruebas, que pasan.

## 1. Antes de calibrar en campo (bloqueante)

- [x] **L** — Corregir que la app mueva el aula destino con cada punto calibrado (fallo 1). Hecho en el servidor con `resolve_rp_room_id`.
- [x] **L** — Corregir `infer_room_id` para que no asigne puntos de pasillo a aulas (fallo 2).
- [ ] **A** — Revisar las dos correcciones (`PARA_ANTONY.md`) y ejecutar su `test_room_mapping.py` en su equipo (aquí ya pasa).
- [ ] **A** — Opcional: que la app envíe `roomId` solo cuando el punto es del aula, para cerrar el caso de puntos de pasillo con nombre libre.

## 2. Cerrar la integración

- [x] **L** — Confirmar la fusión en `integracion/main-epcc` (`b339135`) y, aparte, las dos correcciones.
- [ ] **E** — Decidir cuándo se sube la rama y se abre el pull request hacia `main`.
- [ ] **E** — Decidir si `POST /calibration/record` y `PUT /building/room/{id}/position` vuelven a exigir el token de administrador.
- [x] **L** — Instalar `httpx2` y ejecutar los 7 módulos que no corrían: pasan las 118 pruebas, incluido `test_room_mapping.py`.
- [ ] **E** — Añadir `httpx2` a un `requirements` de desarrollo para que los demás puedan ejecutar las pruebas.
- [ ] **E** — Decidir cuándo se activa TLS (hoy aparcado) antes de desplegar en la red de la escuela.
- [ ] **E** — Decidir qué hacer con `RP_Centro_101` en (0, 0), que mueve S101 al arrancar.
- [ ] **L** — Recuperar o descartar el `attendance_log.json` guardado en `stash@{0}`.

## 3. Calibración de campo (Fase 8 del cronograma)

- [ ] **E** — Medir las 4 cotas marcadas como VERIFICAR en `data/planos/EPCC_nivel3.dwg`: baños (6,82 / 7,56), sala de estudios (8,81 / 9,30), vestíbulo (3,47 / 2,21) y fondo de la escalera este (4,58 / 4,85).
- [ ] **E** — Confirmar que los pisos 1 y 4 son iguales al 3.º (el 2.º ya se confirmó con su plano).
- [ ] **E** — Imprimir la cuadrícula: `PYTHONPATH=. python calibration_tools/print_mapping_grid.py --csv`.
- [ ] **E** — Arrancar el servidor con `IPS_BUILDING_MODEL=epcc`, `IPS_RADIO_MAP_PATH=data/radio_map_real.json` e `IPS_ADMIN_TOKEN=<token>`.
- [ ] **E** — En el móvil, desactivar la limitación de búsqueda de Wi-Fi (Opciones de desarrollador) y poner el token en el calibrador.
- [ ] **E** — Capturar 15 muestras en cada punto de la cuadrícula.

## Pruebas de campo del 29 y 30/10

- [ ] **A** — Revisar `resolve_rp_room_id`: el aula del ID manda sobre la declarada (`RP_S302_Door` con destino S303 movía la puerta de S303).
- [ ] **A** — Revisar el estado nuevo `LEFT_ROOM` («Salió del aula»): tras confirmar, 60 s seguidos fuera del aula (`exit_grace_seconds`). La asistencia se conserva y vuelve a «Presente» al regresar.
- [ ] **A** — App: coma decimal en las coordenadas, captura automática de 15 muestras y bloqueo del envío con menos.
- [x] **L** — Asistencia automática: `resolve_attendance_room` la evalúa en el aula de la credencial del móvil o en la asignada del padrón. El destino de la app solo guía la ruta y cuenta solo para alumnos sin aula (los autorregistrados quedan marcados con `auto_registered`). Pruebas: `test_attendance_room_resolution.py` (8).
- [ ] **E** — Cargar el padrón real: hoy son los 12 alumnos demo (EST_11 está en S402) y los dados de alta por `POST /attendance/students` no se guardan en disco, se pierden al reiniciar.
- [ ] **E** — `attendance_rate_percent` puede pasar del 100 %: `total_enrolled` cuenta solo los matriculados en el aula, pero los registros incluyen a quien la tenga como destino (visto con EST_11, matriculado en S402).
- [x] **L** — Calibración con varios móviles: el servidor guarda la huella de cada móvil por punto (`contributions`, por `device_id`) y combina las de todos, ponderando por muestras. Cada AP se promedia solo entre los móviles que lo vieron.
- [x] **L** — Recalibración. Reenviar un punto desde el mismo móvil sustituye su huella. La casilla «Recalibrar» de la app (`replace`) borra las de todos. `DELETE /calibration/point/{rp}/device/{id}` descarta un móvil concreto. Un ID con otro piso o a más de 0,5 m se rechaza con 409.
- [ ] **A** — Revisar lo anterior (`test_calibration_multi_device.py`, 12 pruebas).

Lo visto el 30/10, con 3 móviles (Redmi 2303ERA42L, Samsung SM-A107M y OPPO CPH2579). El radio-mapa `data/radio_map_real.json` tiene 13 puntos del 3.er piso: pasadizo, S302 y S303 (centro y sus dos puertas, medidas en sitio en x = 16,90 y 20,90).

- [ ] **L** — El WKNN compara la unión de redes e imputa −105 dBm a las que falten (`wknn_locator.py:37-44`). Cada móvil se «pega» a los puntos que calibró él mismo y a los que tienen muchas redes: el centro de S303 (7 redes) casi nunca gana a Hall_11 (43), y quien está dentro del aula sale en el pasadizo. Comparar solo las redes en común, o ponderar por ellas.
- [ ] **L** — Sustituir el círculo de 4 m por el rectángulo del aula. Estando en la puerta (y = 0), el alumno queda a 5 m del centro y nunca cuenta como presente (caso de Lucho_picks).
- [ ] **L** — Pedir varias lecturas seguidas dentro para pasar de «Salió del aula» a «Presente». Con una sola, el error de posición produce un vaivén cada 1–2 min.
- [ ] **L** — Rechazar en el servidor las huellas sin redes. El CPH2579, sin permiso de ubicación, envió dos veces Hall_10 con 0 redes y hubo que borrarlo a mano.
- [ ] **E** — En los móviles: ubicación activada, permiso de ubicación precisa y limitación de búsqueda Wi-Fi desactivada. Sin eso, Android devuelve escaneos vacíos y el servidor ubica al móvil en el piso 1.
- [ ] **E** — Un nombre de alumno por móvil: dos móviles como EST_08 mezclaban sus posiciones.
- [ ] **E** — El selector de piso de la app no se recuerda entre envíos. Un punto del 3.er piso llegó como piso 1.
- [ ] **E** — «Reiniciar» deja en el tablero a los alumnos de pruebas anteriores, como ausentes. Falta una forma de borrarlos.
- [ ] **E** — Faltan del 3.er piso: Hall_2–4, Hall_6, Hall_8–9, Hall_12, Hall_15, la S301 y las escaleras. Las puertas de S301 y S302 son estimaciones del plano (±0,5 m); la de S302 se calibró en el eje (x = 11,775) y conviene repetirla con «Recalibrar».

## 4. Después de la calibración

- [ ] **L** — Reajustar el radio de asistencia: el actual (4 m) no cubre el aula real de 7,85 × 9,98 m, cuyas esquinas quedan a 6,35 m del centro.
- [ ] **E** — Repetir el LOOCV con el radio-mapa medido y medir FAR/FRR con personas reales.
- [ ] **L** — Actualizar el informe y las diapositivas con las cifras de campo y con los cambios de esta integración (ubicación del radio-mapa y protección de los endpoints).

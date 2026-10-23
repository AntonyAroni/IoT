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

## 4. Después de la calibración

- [ ] **L** — Reajustar el radio de asistencia: el actual (4 m) no cubre el aula real de 7,85 × 9,98 m, cuyas esquinas quedan a 6,35 m del centro.
- [ ] **E** — Repetir el LOOCV con el radio-mapa medido y medir FAR/FRR con personas reales.
- [ ] **L** — Actualizar el informe y las diapositivas con las cifras de campo y con los cambios de esta integración (ubicación del radio-mapa y protección de los endpoints).

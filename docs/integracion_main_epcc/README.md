# Integración de `main` con el modelo real de la EPCC

Estado al 10/10/2026 de la rama **`integracion/main-epcc`**, que junta el trabajo de dos ramas:

| Origen | Autor | Contenido |
|---|---|---|
| `origin/main` — `4117dba` (21/09) | AntonyAroni | Mapeo dinámico de aulas desde el radio-mapa, `PUT /building/room/{id}/position`, borrado de puntos, restaurar baseline, modal de mapeo en el tablero, `roomId` desde la app |
| `fix/auditoria-p0-p1` — 4 commits (09/10) | Luis.C.L | Columna «Señal» del tablero, token de administrador y descarte de escaneos repetidos en la app, modelo real del pabellón (`IPS_BUILDING_MODEL=epcc`), planos del 3.er nivel |

**Criterio acordado:** cuando el código de AntonyAroni y el de Luis chocan, **manda el de AntonyAroni** y se adapta el otro. Los dos fallos de sincronización de aulas se corrigieron con el visto bueno de Luis y quedan pendientes de la revisión de AntonyAroni.

## Contenido de esta carpeta

| Archivo | Para qué |
|---|---|
| `README.md` | Este resumen: estado de la rama y cómo cerrarla |
| `PENDIENTES.md` | Lista de tareas, quién la hace y en qué orden |
| `PARA_ANTONY.md` | Mensaje para AntonyAroni: los dos fallos, cómo se corrigieron y qué queda por decidir |
| `reproducir_problemas.py` | Script que comprueba esos fallos sin tocar `data/` (hoy termina con «corregido») |

## Estado de la rama

- La fusión de `origin/main` está confirmada en el commit `b339135`.
- Había 4 conflictos, todos resueltos conservando las dos partes. En ninguno había que elegir entre una versión y otra:

  | Archivo | Resolución |
  |---|---|
  | `backend/main.py` | Imports de los dos lados: `create_building_graph` (selector de modelo) + `Point2D` e `infer_room_id` (sincronización de aulas) |
  | `frontend_stations/js/station_app.js` | El estado inicial muestra las coordenadas del aula (`room_position`) **y** pasa `msg.timestamp` para la columna «Señal» |
  | `mobile_app/.../MainActivity.kt` | La subida de calibración envía `roomId` **y** `adminToken` |
  | `.gitignore` | Se respeta que `main` quitó la línea duplicada de `data/devices.json`; se añaden las exclusiones del informe y de AutoCAD |

- Encima de la fusión, en un commit aparte, están las correcciones de los dos fallos de sincronización de aulas (ver más abajo). Fuera de eso, el código de AntonyAroni queda tal cual.
- Verificado: el JS y el Python compilan, la tabla del padrón tiene 6 cabeceras y 6 celdas, el servidor arranca con los dos modelos y pasan **las 118 pruebas**, incluidos los 7 módulos que usan el cliente HTTP de pruebas (entre ellos `test_room_mapping.py`, de AntonyAroni). Esos 7 necesitan `httpx2`, instalado en el venv el 10/10; no figura en ningún `requirements`.

## Commits de la rama

| Commit | Contenido |
|---|---|
| `b339135` | Fusión de `origin/main` con los 4 conflictos resueltos |
| `fix(mapeo): …` | Corrección de los dos fallos de sincronización de aulas y sus 10 pruebas |
| `docs: …` | Esta carpeta |

La rama **no está subida** a GitHub. Para subirla, cuando el equipo lo decida: `git push -u origin integracion/main-epcc`.

## Fallos corregidos (pendientes de revisión de AntonyAroni)

| Fallo | Antes | Después |
|---|---|---|
| 1. La app envía `roomId` = aula destino en todos los puntos | Calibrar un punto del pasadizo movía S302 a (−1,1, −0,965) | S302 no se mueve |
| 2. `infer_room_id` acepta cifras sueltas | 16 puntos de pasillo asignados a S101, S102 o S103 | 0 |

Comprobación: `PYTHONPATH=. python docs/integracion_main_epcc/reproducir_problemas.py` termina con «corregido». Detalle y límites en `PARA_ANTONY.md`.

## Otros datos a tener en cuenta

- **El radio-mapa por defecto cambió en `main`.** `data/radio_map.json` tiene ahora **1 punto real** (`RP_Centro_101`, 14 APs, en (0, 0)); los 40 puntos sintéticos se movieron a `data/radio_map_baseline.json`. Para reproducir las cifras del LOOCV:
  `PYTHONPATH=. python calibration_tools/loocv_evaluator.py --map data/radio_map_baseline.json`
- Al arrancar, `RP_Centro_101` mueve el aula **S101 a (0, 0)** con cualquiera de los dos modelos.
- El `data/attendance_log.json` local de `fix/auditoria-p0-p1` está guardado en **`stash@{0}`**. Para recuperarlo: `git switch fix/auditoria-p0-p1` y `git stash pop`.
- El informe de entrega (`trabajo_final_informe/`, fuera de git) dice que el radio-mapa de 40 puntos está en `data/radio_map.json` y que registrar huellas exige el token de administrador. Con esta integración **ninguna de las dos cosas es cierta**: hay que actualizar el informe o revertir esos cambios.

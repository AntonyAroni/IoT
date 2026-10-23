# Para AntonyAroni: dos correcciones en la sincronización de aulas

Hola Antony. Al integrar tu commit `4117dba` (mapeo dinámico de aulas) con el modelo real del
pabellón encontramos dos fallos que bloqueaban la calibración en campo. Los hemos corregido en la
rama **`integracion/main-epcc`**, tocando lo mínimo de tu código. **Revísalo antes
de que se suba la rama**: si prefieres otra solución, se cambia.

Comprobación rápida (no toca `data/`):

```bash
git switch integracion/main-epcc
PYTHONPATH=. python docs/integracion_main_epcc/reproducir_problemas.py   # debe decir "corregido"
PYTHONPATH=. python -m unittest backend.tests.test_room_sync_from_calibration
```

---

## Fallo 1 — la app movía el aula destino con CADA punto calibrado

**Causa:** `MainActivity.kt` envía `roomId = currentTargetRoomId` (por defecto **S302**) en todos los
puntos, también en los de pasillo y escalera, y `record_calibration_point` lo aceptaba siempre.
Cada punto calibrado movía el centro de S302 a su posición; al calibrar un punto del pasadizo,
S302 pasaba de `(11.775, 4.99)` a `(-1.1, -0.965)`.

**Corrección (solo en el servidor; no hace falta recompilar la app):** nueva función
`resolve_rp_room_id` en `backend/domain/graph.py`. Decide a qué aula pertenece un punto y la usan
tanto `record_calibration_point` como `sync_room_positions_from_radio_map` (al arrancar). Descarta:
- los puntos de circulación, si su ID o su etiqueta contienen *hall, pasillo, pasadizo, corredor,
  escalera, stairs, vestíbulo* o *ascensor*, aunque traigan un `room_id`;
- los puntos de un piso distinto al del aula.

**Se mantiene:** un punto con nombre libre tomado dentro del aula (por ejemplo `RP_Mesa_Profesor` con
`roomId=S302`) sigue moviendo esa aula, y la asignación manual desde el tablero
(`PUT /building/room/{id}/position` con `from_rp_id`) no cambia.

**Límite:** un punto de pasillo con un nombre que no contenga ninguna de esas palabras seguiría
moviendo el aula declarada. Para cerrarlo del todo, la app debería enviar `roomId` solo cuando el
punto es del aula (por ejemplo, con una casilla «este punto es del aula»). Eso es cosa tuya.

## Fallo 2 — `infer_room_id` asignaba puntos de pasillo a aulas, incluso de otro piso

**Causa:** el tercer patrón, `(?:P|PISO\s*)?([1-4])_?0?([1-3])`, aceptaba dos cifras sueltas. Leía
`RP_P3_Hall_12` como **S102**, y la coordenada `12.9m` de la etiqueta que genera la app también como
**S102**. Con la cuadrícula del edificio real, 16 puntos de pasillo se asignaban a S101, S102 o S103.

**Corrección:** `infer_room_id` solo reconoce un código de aula completo (`S303` o `303`) que no forme
parte de un número más largo, y lo descarta si su piso no coincide con el del punto.

**Se mantiene:** los 6 casos de tu `test_infer_room_id` dan el mismo resultado, y `RP_Centro_101`
sigue asignándose a S101.

---

## Pruebas

- Nuevo `backend/tests/test_room_sync_from_calibration.py` (10 pruebas): tus casos, los dos fallos y
  tu flujo de sincronización en caliente. No necesita `httpx2`.
- Tu `test_room_mapping.py` **pasa** con las correcciones, igual que el resto: 118 pruebas en total.
  Necesita `httpx2` (`pip install httpx2`). Aun así, **ejecútalo en tu equipo** para confirmarlo.

## Para decidir contigo (no lo hemos tocado)

- **`POST /calibration/record` ya no exige el token de administrador.** La app ya puede enviarlo
  (campo «Token de administrador» del calibrador). Como ese endpoint mueve aulas, cualquiera en la
  red podría desplazar una.
- **`PUT /building/room/{room_id}/position` no tiene protección** y también mueve aulas.
- **`RP_Centro_101` en (0, 0)** mueve S101 a esa posición al arrancar. ¿Se midió en el aula 101 real?
  ¿Con qué origen de coordenadas?

## Lo que te toca

En `PENDIENTES.md` están marcadas con **A**:
1. Revisar estas dos correcciones.
2. Ejecutar tu `test_room_mapping.py` en tu equipo (aquí ya pasa; necesita `httpx2`).
3. Opcional: que la app envíe `roomId` solo en los puntos del aula.

Ahí también está por qué **todavía no está listo para producción** (sección del principio).

Gracias. Cualquier cosa, lo vemos.

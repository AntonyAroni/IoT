"""
Reproduce los dos problemas de la sincronización de aulas al calibrar en campo.

Tras la corrección (resolve_rp_room_id e infer_room_id en backend/domain/graph.py) debe
terminar con "corregido". Sirve como comprobación rápida si se vuelve a tocar ese código.

No necesita httpx ni el servidor en marcha, y no modifica nada de `data/`: apunta el radio-mapa y
el registro de asistencia a archivos temporales antes de importar la aplicación.

Uso (desde la raíz del repo, con el venv activado):
    PYTHONPATH=. python docs/integracion_main_epcc/reproducir_problemas.py
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="ips_repro_")
os.environ["IPS_RADIO_MAP_PATH"] = os.path.join(_tmp, "radio_map.json")
os.environ["IPS_ATTENDANCE_LOG_PATH"] = os.path.join(_tmp, "attendance_log.json")
os.environ.setdefault("IPS_BUILDING_MODEL", "epcc")

from backend.api.routes_calibration import CalibrationUploadModel, record_calibration_point  # noqa: E402
from backend.domain.graph import infer_room_id  # noqa: E402
from backend.main import app_state  # noqa: E402
from calibration_tools.print_mapping_grid import build_grid  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def problema_1_inferencia() -> int:
    """infer_room_id asigna puntos de pasillo a aulas (por el ID o por las coordenadas de la etiqueta)."""
    print("PROBLEMA 1 — infer_room_id con la cuadrícula de mapeo y la etiqueta que genera la app")
    print("-" * 88)
    errores = 0
    for piso in (1, 2, 3, 4):
        for rp_id, pos, _ in build_grid(piso, "epcc"):
            # Formato de etiqueta que envía la app (MainActivity.kt)
            label = f"Punto Calibrado {rp_id} ({pos.x}m, {pos.y}m)"
            obtenido = infer_room_id(rp_id, piso, label)
            esperado = rp_id[3:7] if rp_id.startswith("RP_S") else None
            if obtenido != esperado:
                errores += 1
                print(f"  {rp_id:<24} x={pos.x:<6} -> {obtenido}   (debería ser {esperado})")
    print(f"  Total de puntos mal asignados: {errores}\n")
    return errores


def problema_2_room_id_de_la_app() -> bool:
    """La app envía como roomId el aula destino en TODOS los puntos, también en los de pasillo."""
    print("PROBLEMA 2 — la app envía roomId = aula destino (por defecto S302) en cada punto")
    print("-" * 88)
    antes = app_state.graph.get_node("S302").position
    print(f"  Centro de S302 antes de calibrar:  ({antes.x}, {antes.y})")

    # Lo que envía MainActivity.kt al calibrar un punto del pasadizo con el aula destino por defecto
    payload = CalibrationUploadModel(
        rp_id="RP_P3_Hall_A",
        floor_number=3,
        x=-1.1,
        y=-0.965,
        label="Punto Calibrado RP_P3_Hall_A (-1.1m, -0.965m)",
        room_id="S302",
        rssi_means={"aa:bb:cc:dd:ee:01": -60.0},
    )
    record_calibration_point(payload, repo=app_state.radio_map_repo)

    despues = app_state.graph.get_node("S302").position
    print(f"  Centro de S302 después de calibrar un punto del PASADIZO: ({despues.x}, {despues.y})")
    movida = (antes.x, antes.y) != (despues.x, despues.y)
    print(f"  ¿Se movió el aula? {'SÍ' if movida else 'no'}\n")
    return movida


if __name__ == "__main__":
    print(f"Modelo de edificio: {os.environ['IPS_BUILDING_MODEL']}  |  archivos temporales en {_tmp}\n")
    e1 = problema_1_inferencia()
    e2 = problema_2_room_id_de_la_app()
    if e1 or e2:
        print("RESULTADO: se reproduce", " y ".join(n for n, f in (("el problema 1", e1), ("el problema 2", e2)) if f))
    else:
        print("RESULTADO: corregido, no se reproduce ninguno de los dos problemas")

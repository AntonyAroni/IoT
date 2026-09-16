"""
Generador de la Cuadrícula de Mapeo a partir del Modelo del Edificio.

Emite la lista de puntos de referencia a levantar en campo —identificador y coordenadas— derivada
de `create_default_school_graph()`, que es la topología que realmente usan el motor de navegación
y el criterio de asistencia.

Existe porque transcribir las coordenadas a mano en la guía las desincronizó del código: la guía
situaba las aulas del piso 1 en x = 4, 10 y 16 mientras el modelo las tiene en x = 2, 10 y 18, y
llamaba "puerta" a y = 5.0, que en el modelo es el pasillo. Mapear con esas cifras deja cada
huella desplazada respecto al grafo, y el criterio de asistencia ("a 4 m o menos del centro del
aula") empieza a gastar parte de su margen en un error que no existe.

Uso:
    PYTHONPATH=. python calibration_tools/print_mapping_grid.py            # todos los pisos
    PYTHONPATH=. python calibration_tools/print_mapping_grid.py --floor 1  # solo el piso 1
    PYTHONPATH=. python calibration_tools/print_mapping_grid.py --csv      # para imprimir
"""
import argparse
from typing import List, Tuple

from backend.config import config
from backend.domain.building import Point2D
from backend.domain.graph import NodeType, create_default_school_graph
from calibration_tools.console import enable_unicode_output

# Separación entre puntos de referencia consecutivos en el pasillo, en metros.
HALLWAY_SPACING_M = 2.0


def build_grid(floor_number: int) -> List[Tuple[str, Point2D, str]]:
    """Devuelve (id_del_punto, coordenada, descripción) para un piso."""
    graph, floors = create_default_school_graph()
    floor = floors[floor_number]
    puntos: List[Tuple[str, Point2D, str]] = []

    for room in floor.rooms:
        puntos.append((f"RP_{room.id}_Center", room.center, f"Centro del {room.name}"))
        puntos.append((f"RP_{room.id}_Door", room.entrance, f"Puerta del {room.name}"))

    # Puntos de pasillo entre el extremo oeste y el este, a la altura del corredor
    hallway_nodes = [
        n for n in graph.nodes.values()
        if n.floor_number == floor_number and n.node_type == NodeType.HALLWAY
    ]
    if hallway_nodes:
        xs = [n.position.x for n in hallway_nodes]
        y = hallway_nodes[0].position.y
        x = min(xs)
        indice = 1
        while x <= max(xs) + 1e-6:
            puntos.append((
                f"RP_P{floor_number}_Hall_{indice}",
                Point2D(round(x, 2), y),
                f"Pasillo, {round(x, 2)} m desde el extremo oeste"
            ))
            x += HALLWAY_SPACING_M
            indice += 1

    for stair in floor.staircases:
        puntos.append((f"RP_P{floor_number}_Stairs", stair.position, "Descanso de escalera"))

    return puntos


def main() -> None:
    parser = argparse.ArgumentParser(description="Cuadrícula de mapeo derivada del modelo del edificio")
    parser.add_argument("--floor", type=int, help="Piso concreto (1-4). Por defecto, todos.")
    parser.add_argument("--csv", action="store_true", help="Salida en CSV para imprimir")
    args = parser.parse_args()

    _, floors = create_default_school_graph()
    pisos = [args.floor] if args.floor else sorted(floors)

    if args.csv:
        print("piso,rp_id,x,y,descripcion")
        for piso in pisos:
            for rp_id, pos, desc in build_grid(piso):
                print(f"{piso},{rp_id},{pos.x},{pos.y},{desc}")
        return

    radio = config.attendance.classroom_radius_meters
    print("=" * 74)
    print(" CUADRÍCULA DE MAPEO — derivada de create_default_school_graph()")
    print("=" * 74)
    print(" Estas son las coordenadas que usan la navegación y el criterio de asistencia.")
    print(" Si el edificio real no encaja con ellas, ajusta PRIMERO el modelo del grafo:")
    print(" mapear contra coordenadas que el sistema no comparte invalida las huellas.")
    print()

    total = 0
    for piso in pisos:
        puntos = build_grid(piso)
        total += len(puntos)
        print(f"--- Piso {piso} ({len(puntos)} puntos) ---")
        print(f"{'ID del punto':<22} {'X (m)':>7} {'Y (m)':>7}   Descripción")
        for rp_id, pos, desc in puntos:
            print(f"{rp_id:<22} {pos.x:>7.2f} {pos.y:>7.2f}   {desc}")
        print()

    print("=" * 74)
    print(f" Total: {total} puntos de referencia")
    print(f" 15 muestras por punto. Radio de aula configurado: {radio} m desde el centro.")
    print(" Protocolo completo: data/field_captures/PROTOCOLO_CAMPANA.md")
    print("=" * 74)


if __name__ == "__main__":
    enable_unicode_output()
    main()

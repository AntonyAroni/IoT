"""
Modelo Topológico Real del Pabellón de la EPCC (Tercer Nivel, replicado en los 4 pisos).

Geometría tomada del plano de señalización del tercer nivel (escala 1:100, en
`data/planos/`) y de las cotas medidas a mano sobre él; el dibujo esquemático está en
`data/planos/EPCC_nivel3.dwg`. El modelo sintético (`create_default_school_graph`) sigue
existiendo porque es el que generó el radio-mapa de `data/radio_map.json` y las cifras de
validación del informe: mezclar este modelo con ese radio-mapa pondría la posición estimada y
los centros de aula en sistemas de coordenadas distintos.

Sistema de coordenadas (metros):
- Origen en la esquina del Aula 1 junto al muro del pasadizo.
- X crece a lo largo del pasadizo, hacia el hall; Y crece desde el pasadizo hacia la fachada.

Supuestos que conviene declarar:
- Solo se dispone del plano del tercer nivel. El segundo se confirmó igual a la vista de su
  plano; el primero y el cuarto se suponen iguales SIN verificar.
- Cada aula tiene dos puertas al pasadizo; el modelo usa una sola entrada en el eje del aula.
- El ascensor no se modela como conexión vertical: la navegación solo propone escaleras.
- Cuatro cotas del plano no cuadran con el dibujo (baños, sala de estudios, vestíbulo y fondo
  de la escalera este) y siguen pendientes de medir; ninguna afecta a las aulas ni al pasadizo.
"""
from typing import Dict, List, Tuple

from .building import Floor, Point2D, Room, Staircase
from .graph import BuildingGraph, GraphNode, NodeType

# Aulas: (sufijo, x inicial, x final). Anchos medidos 7.85 / 7.85 / 7.76 m.
ROOM_SPANS: List[Tuple[str, float, float]] = [
    ("01", 0.00, 7.85),
    ("02", 7.85, 15.70),
    ("03", 15.70, 23.46),
]
# Fondo del aula desde el muro del pasadizo hasta la fachada (el Aula 3 tiene un quiebre a 8.40 m).
ROOM_DEPTH_M = 9.98
# Eje del pasadizo: el pasadizo mide 1.93 m de ancho, entre y = -1.93 e y = 0.
CORRIDOR_Y = -0.965

# Núcleos de escalera (centro de la caja de escalera).
WEST_STAIR = Point2D(-4.62, -1.97)   # caja de 4.82 x 4.82 m al oeste del pasadizo
EAST_STAIR = Point2D(35.19, 10.05)   # caja de 4.86 m de ancho al noreste del hall

# Penalización por cambio de piso, igual que en el modelo sintético.
VERTICAL_COST_M = 6.0


def _add(graph: BuildingGraph, node_id: str, label: str, floor_num: int, x: float, y: float,
         node_type: NodeType = NodeType.HALLWAY) -> str:
    graph.add_node(GraphNode(id=node_id, label=label, floor_number=floor_num,
                             position=Point2D(x, y), node_type=node_type))
    return node_id


def create_epcc_graph() -> Tuple[BuildingGraph, Dict[int, Floor]]:
    """
    Construye la topología real de la EPCC con 4 pisos idénticos al tercer nivel.

    Conserva los identificadores del modelo sintético para las aulas (S101 ... S403) y para los
    nodos de pasadizo frente a ellas (P{n}_Hall_West/Center/East), de modo que el padrón, la app
    y el tablero siguen funcionando sin cambios.
    """
    graph = BuildingGraph()
    floors: Dict[int, Floor] = {}

    for f in range(1, 5):
        # 1. Pasadizo: un nodo frente a cada aula, más el vestíbulo oeste
        hall_ids = []
        for (suffix, x0, x1), name in zip(ROOM_SPANS, ("West", "Center", "East")):
            cx = round((x0 + x1) / 2, 3)
            hall_ids.append(_add(graph, f"P{f}_Hall_{name}", f"Pasadizo frente al Aula {f}{suffix}",
                                 f, cx, CORRIDOR_Y))
        vestibule = _add(graph, f"P{f}_Vestibulo_Oeste", f"Vestíbulo Oeste Piso {f}", f, -1.10, CORRIDOR_Y)

        graph.add_edge(vestibule, hall_ids[0])
        graph.add_edge(hall_ids[0], hall_ids[1])
        graph.add_edge(hall_ids[1], hall_ids[2])

        # 2. Hall / estar y paso hacia la escalera este, rodeando el vacío por su lado este
        hall_estar = _add(graph, f"P{f}_Hall_Estar", f"Hall Piso {f}", f, 28.10, CORRIDOR_Y)
        hall_este = _add(graph, f"P{f}_Hall_Este", f"Hall Este Piso {f}", f, 31.55, 1.00)
        hall_noreste = _add(graph, f"P{f}_Hall_Noreste", f"Hall Noreste Piso {f}", f, 31.55, 6.30)
        zona_escalera = _add(graph, f"P{f}_Zona_Escalera_Este", f"Acceso a la Escalera Este Piso {f}",
                             f, 34.68, 6.30)

        graph.add_edge(hall_ids[2], hall_estar)
        graph.add_edge(hall_estar, hall_este)
        graph.add_edge(hall_este, hall_noreste)
        graph.add_edge(hall_noreste, zona_escalera)

        # 3. Escaleras oeste y este
        west_id = _add(graph, f"Escalera_Oeste_P{f}", "Escalera Oeste", f,
                       WEST_STAIR.x, WEST_STAIR.y, NodeType.STAIRCASE)
        east_id = _add(graph, f"Escalera_Este_P{f}", "Escalera Este", f,
                       EAST_STAIR.x, EAST_STAIR.y, NodeType.STAIRCASE)
        graph.add_edge(vestibule, west_id)
        graph.add_edge(zona_escalera, east_id)

        # 4. Aulas, con entrada en el muro del pasadizo
        rooms = []
        for (suffix, x0, x1), access_id in zip(ROOM_SPANS, hall_ids):
            room_id = f"S{f}{suffix}"
            cx = round((x0 + x1) / 2, 3)
            center = Point2D(cx, round(ROOM_DEPTH_M / 2, 3))
            _add(graph, room_id, f"Salón {f}{suffix}", f, center.x, center.y, NodeType.ROOM)
            graph.add_edge(room_id, access_id)
            rooms.append(Room(id=room_id, name=f"Aula {f}{suffix}", floor_number=f, center=center,
                              entrance=Point2D(cx, 0.0), access_node_id=access_id))

        stairs = [
            Staircase(id=stair_id, floor_number=f, position=pos,
                      connects_up=f"{prefix}_P{f + 1}" if f < 4 else None,
                      connects_down=f"{prefix}_P{f - 1}" if f > 1 else None)
            for stair_id, prefix, pos in (
                (west_id, "Escalera_Oeste", WEST_STAIR),
                (east_id, "Escalera_Este", EAST_STAIR),
            )
        ]

        floors[f] = Floor(floor_number=f, name=f"Piso {f}", height_meters=(f - 1) * 3.5,
                          rooms=rooms, staircases=stairs)

    # 5. Conexiones verticales de ambas escaleras
    for f in range(1, 4):
        for prefix in ("Escalera_Oeste", "Escalera_Este"):
            graph.add_edge(f"{prefix}_P{f}", f"{prefix}_P{f + 1}",
                           distance_meters=VERTICAL_COST_M, is_vertical=True)

    return graph, floors

"""
Módulo de Grafo Topológico y Enrutamiento (Dijkstra) del Edificio Escolar.
Modela nodos espaciales (salones, pasillos, escaleras) y conexiones ponderadas.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set
import heapq
import math
from .building import Point2D, Room, Staircase, Floor

class NodeType(str, Enum):
    ROOM = "ROOM"
    HALLWAY = "HALLWAY"
    STAIRCASE = "STAIRCASE"

@dataclass
class GraphNode:
    id: str
    label: str
    floor_number: int
    position: Point2D
    node_type: NodeType

@dataclass
class GraphEdge:
    target_id: str
    distance_meters: float
    is_vertical: bool = False  # Indica transición por escaleras entre pisos

class BuildingGraph:
    """Grafo dirigido/no-dirigido con pesos métricos para el edificio de 4 pisos."""

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.adjacency: Dict[str, List[GraphEdge]] = {}

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node
        if node.id not in self.adjacency:
            self.adjacency[node.id] = []

    def add_edge(self, from_id: str, to_id: str, distance_meters: Optional[float] = None, bidirectional: bool = True, is_vertical: bool = False) -> None:
        if from_id not in self.nodes or to_id not in self.nodes:
            raise ValueError(f"Nodos no válidos para la arista: {from_id} -> {to_id}")
        
        # Si no se especifica la distancia, calcularla euclidianamente
        if distance_meters is None:
            n1 = self.nodes[from_id]
            n2 = self.nodes[to_id]
            if is_vertical:
                # Penalización por cambio de piso vertical (equivalente a 6.0 metros de esfuerzo)
                distance_meters = 6.0
            else:
                distance_meters = n1.position.distance_to(n2.position)

        self.adjacency[from_id].append(GraphEdge(target_id=to_id, distance_meters=distance_meters, is_vertical=is_vertical))
        if bidirectional:
            self.adjacency[to_id].append(GraphEdge(target_id=from_id, distance_meters=distance_meters, is_vertical=is_vertical))

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)

    def find_shortest_path(self, start_id: str, goal_id: str) -> Tuple[List[str], float]:
        """
        Calcula la ruta más corta entre start_id y goal_id usando el algoritmo de Dijkstra.
        Retorna:
            (lista de IDs de nodos en orden de recorrido, distancia total acumulada)
        """
        if start_id not in self.nodes or goal_id not in self.nodes:
            raise ValueError(f"Nodo de inicio '{start_id}' o destino '{goal_id}' no existe en el grafo.")

        if start_id == goal_id:
            return ([start_id], 0.0)

        distances: Dict[str, float] = {node_id: float('inf') for node_id in self.nodes}
        previous: Dict[str, Optional[str]] = {node_id: None for node_id in self.nodes}
        distances[start_id] = 0.0

        # Cola de prioridad: (distancia_acumulada, nodo_id)
        pq: List[Tuple[float, str]] = [(0.0, start_id)]

        while pq:
            current_dist, current_id = heapq.heappop(pq)

            if current_dist > distances[current_id]:
                continue

            if current_id == goal_id:
                break

            for edge in self.adjacency.get(current_id, []):
                new_dist = current_dist + edge.distance_meters
                if new_dist < distances[edge.target_id]:
                    distances[edge.target_id] = new_dist
                    previous[edge.target_id] = current_id
                    heapq.heappush(pq, (new_dist, edge.target_id))

        if distances[goal_id] == float('inf'):
            return ([], float('inf'))  # No hay camino

        # Reconstruir camino hacia atrás
        path = []
        curr = goal_id
        while curr is not None:
            path.append(curr)
            curr = previous[curr]
        path.reverse()

        return (path, distances[goal_id])

def create_default_school_graph() -> Tuple[BuildingGraph, Dict[int, Floor]]:
    """
    Construye la topología canónica del edificio escolar de 4 pisos y 12 salones.
    Piso 1: S101, S102, S103
    Piso 2: S201, S202, S203
    Piso 3: S301, S302, S303
    Piso 4: S401, S402, S403
    """
    graph = BuildingGraph()
    floors: Dict[int, Floor] = {}

    for floor_num in range(1, 5):
        # 1. Crear Nodos del Pasillo Central
        hall_west = GraphNode(
            id=f"P{floor_num}_Hall_West",
            label=f"Pasillo Oeste Piso {floor_num}",
            floor_number=floor_num,
            position=Point2D(x=2.0, y=5.0),
            node_type=NodeType.HALLWAY
        )
        hall_center = GraphNode(
            id=f"P{floor_num}_Hall_Center",
            label=f"Pasillo Central Piso {floor_num}",
            floor_number=floor_num,
            position=Point2D(x=10.0, y=5.0),
            node_type=NodeType.HALLWAY
        )
        hall_east = GraphNode(
            id=f"P{floor_num}_Hall_East",
            label=f"Pasillo Este Piso {floor_num}",
            floor_number=floor_num,
            position=Point2D(x=18.0, y=5.0),
            node_type=NodeType.HALLWAY
        )

        graph.add_node(hall_west)
        graph.add_node(hall_center)
        graph.add_node(hall_east)

        # Conectar pasillos horizontalmente
        graph.add_edge(hall_west.id, hall_center.id)
        graph.add_edge(hall_center.id, hall_east.id)

        # 2. Crear Salones del Piso
        # Salón 1 (Oeste), Salón 2 (Centro), Salón 3 (Este)
        room_1_id = f"S{floor_num}01"
        room_2_id = f"S{floor_num}02"
        room_3_id = f"S{floor_num}03"

        r1_node = GraphNode(id=room_1_id, label=f"Salón {floor_num}01", floor_number=floor_num, position=Point2D(x=2.0, y=2.0), node_type=NodeType.ROOM)
        r2_node = GraphNode(id=room_2_id, label=f"Salón {floor_num}02", floor_number=floor_num, position=Point2D(x=10.0, y=2.0), node_type=NodeType.ROOM)
        r3_node = GraphNode(id=room_3_id, label=f"Salón {floor_num}03", floor_number=floor_num, position=Point2D(x=18.0, y=2.0), node_type=NodeType.ROOM)

        graph.add_node(r1_node)
        graph.add_node(r2_node)
        graph.add_node(r3_node)

        # Conectar salones al pasillo correspondiente
        graph.add_edge(room_1_id, hall_west.id)
        graph.add_edge(room_2_id, hall_center.id)
        graph.add_edge(room_3_id, hall_east.id)

        # 3. Crear Núcleo de Escalera
        stair_id = f"Escalera_P{floor_num}"
        stair_node = GraphNode(
            id=stair_id,
            label=f"Escalera Piso {floor_num}",
            floor_number=floor_num,
            position=Point2D(x=10.0, y=8.0),
            node_type=NodeType.STAIRCASE
        )
        graph.add_node(stair_node)
        graph.add_edge(hall_center.id, stair_id)

        # Crear objetos Room y Floor para el dominio
        r1 = Room(id=room_1_id, name=f"Aula {floor_num}01", floor_number=floor_num, center=Point2D(2.0, 2.0), entrance=Point2D(2.0, 4.0), access_node_id=hall_west.id)
        r2 = Room(id=room_2_id, name=f"Aula {floor_num}02", floor_number=floor_num, center=Point2D(10.0, 2.0), entrance=Point2D(10.0, 4.0), access_node_id=hall_center.id)
        r3 = Room(id=room_3_id, name=f"Aula {floor_num}03", floor_number=floor_num, center=Point2D(18.0, 2.0), entrance=Point2D(18.0, 4.0), access_node_id=hall_east.id)

        stair = Staircase(
            id=stair_id,
            floor_number=floor_num,
            position=Point2D(10.0, 8.0),
            connects_up=f"Escalera_P{floor_num+1}" if floor_num < 4 else None,
            connects_down=f"Escalera_P{floor_num-1}" if floor_num > 1 else None
        )

        floors[floor_num] = Floor(
            floor_number=floor_num,
            name=f"Piso {floor_num}",
            height_meters=(floor_num - 1) * 3.5,
            rooms=[r1, r2, r3],
            staircases=[stair]
        )

    # 4. Interconectar Escaleras verticalmente
    for f in range(1, 4):
        stair_from = f"Escalera_P{f}"
        stair_to = f"Escalera_P{f+1}"
        graph.add_edge(stair_from, stair_to, distance_meters=6.0, bidirectional=True, is_vertical=True)

    return graph, floors

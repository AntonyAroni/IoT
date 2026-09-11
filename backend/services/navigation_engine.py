"""
Motor de Navegación y Generador de Pistas de Guiado Paso a Paso.
Utiliza el Grafo Topológico del Edificio Escolar y Dijkstra para calcular
rutas óptimas y transformar coordenadas en instrucciones en lenguaje natural.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from ..domain.building import Point2D, Floor
from ..domain.graph import BuildingGraph, GraphNode, NodeType

@dataclass
class NavigationStep:
    node_id: str
    label: str
    floor_number: int
    instruction: str
    distance_to_next: float
    is_vertical: bool

@dataclass
class NavigationRoute:
    current_floor: int
    target_room_id: str
    target_floor: int
    total_distance_meters: float
    path_node_ids: List[str]
    steps: List[NavigationStep]
    active_clue: str             # Pista inmediata para mostrar en la pantalla del móvil
    progress_percentage: float  # Estimación del avance hacia la meta (0 a 100)
    has_arrived: bool

class NavigationEngine:
    def __init__(self, graph: BuildingGraph, floors: Dict[int, Floor]):
        self.graph = graph
        self.floors = floors

    def find_closest_node(self, floor_number: int, position: Point2D) -> str:
        """Encuentra el nodo del grafo más cercano a una posición estimada en un piso dado."""
        candidates = [
            node for node in self.graph.nodes.values()
            if node.floor_number == floor_number
        ]
        if not candidates:
            # Fallback a cualquier nodo del piso
            return f"P{floor_number}_Hall_Center"

        closest = min(candidates, key=lambda n: n.position.distance_to(position))
        return closest.id

    def compute_route(self, current_floor: int, current_pos: Point2D, target_room_id: str) -> NavigationRoute:
        """
        Calcula la ruta completa desde la ubicación estimada hasta el salón destino,
        generando pistas contextuales claras.
        """
        target_node = self.graph.get_node(target_room_id)
        if not target_node:
            raise ValueError(f"Salón objetivo '{target_room_id}' no encontrado en el edificio.")

        target_floor = target_node.floor_number

        # 1. Encontrar nodo de partida más cercano a la coordenada actual
        start_node_id = self.find_closest_node(current_floor, current_pos)
        start_node = self.graph.get_node(start_node_id)

        # 2. Ejecutar Dijkstra en el Grafo
        path_ids, total_distance = self.graph.find_shortest_path(start_node_id, target_room_id)

        # 3. Evaluar si ya está en el destino o umbral (< 2.5 metros)
        distance_to_room_center = current_pos.distance_to(target_node.position) if current_floor == target_floor else 999.0
        has_arrived = (current_floor == target_floor and distance_to_room_center <= 2.5)

        # 4. Generar Pistas Contextuales
        steps: List[NavigationStep] = []
        active_clue = ""

        if has_arrived:
            active_clue = f"🎉 ¡Has llegado al {target_node.label}! Registrando tu asistencia en la estación..."
        elif current_floor < target_floor:
            diff = target_floor - current_floor
            active_clue = f"🚶‍♂️ Estás en el Piso {current_floor}. Dirígete a la escalera central y sube {diff} nivel(es) al Piso {target_floor}."
        elif current_floor > target_floor:
            diff = current_floor - target_floor
            active_clue = f"🚶‍♂️ Estás en el Piso {current_floor}. Baja por la escalera {diff} nivel(es) al Piso {target_floor}."
        else:
            # Mismo piso, orientación horizontal
            dx = target_node.position.x - current_pos.x
            direction = "hacia tu derecha" if dx > 1.5 else ("hacia tu izquierda" if dx < -1.5 else "en línea recta")
            dist_str = f"{round(distance_to_room_center, 1)} m"
            active_clue = f"📍 Estás en el Piso {current_floor}. Avanza {direction} hacia el {target_node.label} ({dist_str})."

        for i, node_id in enumerate(path_ids):
            node = self.graph.get_node(node_id)
            dist_next = 0.0
            is_vert = False
            if i + 1 < len(path_ids):
                next_id = path_ids[i + 1]
                next_node = self.graph.get_node(next_id)
                dist_next = node.position.distance_to(next_node.position) if node.floor_number == next_node.floor_number else 6.0
                is_vert = (node.floor_number != next_node.floor_number)

            step_instr = f"Avanzar a {node.label}"
            if node.node_type == NodeType.STAIRCASE and is_vert:
                step_instr = f"Usar escalera hacia el Piso {path_ids[i+1]}"

            steps.append(NavigationStep(
                node_id=node.id,
                label=node.label,
                floor_number=node.floor_number,
                instruction=step_instr,
                distance_to_next=dist_next,
                is_vertical=is_vert
            ))

        # Cálculo de progreso aproximado
        progress = 100.0 if has_arrived else max(0.0, min(95.0, 100.0 - (total_distance * 4.0)))

        return NavigationRoute(
            current_floor=current_floor,
            target_room_id=target_room_id,
            target_floor=target_floor,
            total_distance_meters=round(total_distance, 1),
            path_node_ids=path_ids,
            steps=steps,
            active_clue=active_clue,
            progress_percentage=round(progress, 1),
            has_arrived=has_arrived
        )

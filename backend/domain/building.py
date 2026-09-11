"""
Entidades del Dominio: Modelado Físico y Topológico del Edificio Escolar.
Representa pisos, salones, pasillos, descansos de escalera y coordenadas 2D.
"""
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass(frozen=True)
class Point2D:
    """Coordenada bidimensional métrica en el plano del piso."""
    x: float
    y: float

    def distance_to(self, other: "Point2D") -> float:
        """Distancia euclidiana hacia otro punto 2D en metros."""
        import math
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

@dataclass(frozen=True)
class Room:
    """Representa un aula o salón del edificio."""
    id: str                 # Ej. "S101", "S202"
    name: str               # Ej. "Salón 101 - Matemáticas"
    floor_number: int       # 1 a 4
    center: Point2D         # Centro geométrico del aula
    entrance: Point2D       # Punto de entrada / puerta de acceso
    access_node_id: str     # ID del nodo en el grafo que da acceso al salón

@dataclass(frozen=True)
class Staircase:
    """Núcleo vertical de escaleras que interconecta los pisos."""
    id: str                 # Ej. "Escalera_P1", "Escalera_P2"
    floor_number: int
    position: Point2D
    connects_up: Optional[str] = None    # ID de escalera en piso superior
    connects_down: Optional[str] = None  # ID de escalera en piso inferior

@dataclass(frozen=True)
class Floor:
    """Representa una planta o nivel del edificio escolar."""
    floor_number: int
    name: str
    height_meters: float
    rooms: List[Room] = field(default_factory=list)
    staircases: List[Staircase] = field(default_factory=list)

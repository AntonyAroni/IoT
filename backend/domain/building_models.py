"""
Selección del Modelo del Edificio.

Hay dos topologías y cada una va con su radio-mapa:

- ``sintetico``: el edificio modelo de `create_default_school_graph`. Es el que generó el
  radio-mapa sintético (`data/radio_map.json`) y las cifras de validación del informe.
- ``epcc``: el pabellón real de la EPCC (`create_epcc_graph`), para la campaña de campo con un
  radio-mapa medido en el edificio.

Usar un modelo con el radio-mapa del otro pone la posición estimada y los centros de aula en
sistemas de coordenadas distintos, por eso la elección es explícita (`IPS_BUILDING_MODEL`).
"""
from typing import Callable, Dict, Tuple

from .building import Floor
from .epcc_building import create_epcc_graph
from .graph import BuildingGraph, create_default_school_graph

BUILDING_MODELS: Dict[str, Callable[[], Tuple[BuildingGraph, Dict[int, Floor]]]] = {
    "sintetico": create_default_school_graph,
    "epcc": create_epcc_graph,
}


def create_building_graph(model: str) -> Tuple[BuildingGraph, Dict[int, Floor]]:
    """Construye el grafo del modelo indicado; un nombre desconocido es un error, no un fallback."""
    try:
        factory = BUILDING_MODELS[model]
    except KeyError:
        raise ValueError(
            f"Modelo de edificio desconocido: {model!r}. Opciones: {', '.join(sorted(BUILDING_MODELS))}"
        ) from None
    return factory()

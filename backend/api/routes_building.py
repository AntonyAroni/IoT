"""
Controlador HTTP: Consulta del Modelo Físico y Topológico del Edificio.
Expone los pisos, salones, escaleras y coordenadas para clientes web y móviles.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from ..domain.graph import BuildingGraph, NodeType
from ..domain.building import Floor

router = APIRouter(prefix="/api/v1/building", tags=["Building"])

# Se inyectarán mediante FastAPI dependencies o estado de la app
def get_graph() -> BuildingGraph:
    from ..main import app_state
    return app_state.graph

def get_floors() -> Dict[int, Floor]:
    from ..main import app_state
    return app_state.floors

@router.get("/summary")
def get_building_summary(graph: BuildingGraph = Depends(get_graph), floors: Dict[int, Floor] = Depends(get_floors)) -> Dict[str, Any]:
    """Retorna un resumen de pisos, salones y nodos del grafo."""
    floor_summaries = []
    for f_num, fl in sorted(floors.items()):
        floor_summaries.append({
            "floor_number": f_num,
            "name": fl.name,
            "height_meters": fl.height_meters,
            "rooms": [{"id": r.id, "name": r.name, "center": {"x": r.center.x, "y": r.center.y}} for r in fl.rooms]
        })

    return {
        "building_name": "Pabellón Principal Escolar",
        "total_floors": len(floors),
        "total_rooms": sum(len(fl.rooms) for fl in floors.values()),
        "total_graph_nodes": len(graph.nodes),
        "floors": floor_summaries
    }

@router.get("/rooms")
def get_all_rooms(floors: Dict[int, Floor] = Depends(get_floors)) -> List[Dict[str, Any]]:
    """Lista todos los salones con sus coordenadas de centro y entrada."""
    rooms = []
    for fl in floors.values():
        for r in fl.rooms:
            rooms.append({
                "id": r.id,
                "name": r.name,
                "floor_number": r.floor_number,
                "center": {"x": r.center.x, "y": r.center.y},
                "entrance": {"x": r.entrance.x, "y": r.entrance.y},
                "access_node": r.access_node_id
            })
    return sorted(rooms, key=lambda x: x["id"])

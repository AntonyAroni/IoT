"""
Controlador HTTP: Consulta del Modelo Físico y Topológico del Edificio.
Expone los pisos, salones, escaleras y coordenadas para clientes web y móviles.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from ..domain.graph import BuildingGraph, NodeType
from ..domain.building import Floor, Point2D

router = APIRouter(prefix="/api/v1/building", tags=["Building"])

# Se inyectarán mediante FastAPI dependencies o estado de la app
def get_graph() -> BuildingGraph:
    from ..main import app_state
    return app_state.graph

def get_floors() -> Dict[int, Floor]:
    from ..main import app_state
    return app_state.floors

class RoomPositionUpdate(BaseModel):
    center_x: Optional[float] = Field(None, description="Coordenada X del centro / laptop")
    center_y: Optional[float] = Field(None, description="Coordenada Y del centro / laptop")
    entrance_x: Optional[float] = Field(None, description="Coordenada X de la puerta / entrada")
    entrance_y: Optional[float] = Field(None, description="Coordenada Y de la puerta / entrada")
    from_rp_id: Optional[str] = Field(None, description="ID de Punto de Referencia a vincular")
    rp_role: Optional[str] = Field("center", description="'center' o 'entrance'")

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

@router.get("/room/{room_id}")
def get_room_details(room_id: str, floors: Dict[int, Floor] = Depends(get_floors)) -> Dict[str, Any]:
    """Obtiene el detalle de coordenadas de un salón específico."""
    for fl in floors.values():
        for r in fl.rooms:
            if r.id == room_id:
                return {
                    "id": r.id,
                    "name": r.name,
                    "floor_number": r.floor_number,
                    "center": {"x": r.center.x, "y": r.center.y},
                    "entrance": {"x": r.entrance.x, "y": r.entrance.y},
                    "access_node": r.access_node_id
                }
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aula '{room_id}' no encontrada.")

@router.put("/room/{room_id}/position")
def update_room_position(
    room_id: str,
    payload: RoomPositionUpdate
) -> Dict[str, Any]:
    """Actualiza las coordenadas métricas del centro y/o puerta de un salón."""
    from ..main import app_state
    floors = app_state.floors
    radio_map_repo = app_state.radio_map_repo

    target_room = None
    for fl in floors.values():
        for r in fl.rooms:
            if r.id == room_id:
                target_room = r
                break
        if target_room:
            break

    if not target_room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aula '{room_id}' no encontrada.")

    new_center = None
    new_entrance = None

    # Si se solicitó asignar desde un RP existente
    if payload.from_rp_id:
        rp_entry = radio_map_repo.get_by_id(payload.from_rp_id)
        if not rp_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Punto de Referencia '{payload.from_rp_id}' no existe en el radio-mapa."
            )
        rp_pos = rp_entry.reference_point.position
        rp_entry.reference_point.room_id = room_id
        radio_map_repo.save_entry(rp_entry)

        if payload.rp_role == "entrance":
            new_entrance = rp_pos
        else:
            new_center = rp_pos

    if payload.center_x is not None and payload.center_y is not None:
        new_center = Point2D(x=payload.center_x, y=payload.center_y)

    if payload.entrance_x is not None and payload.entrance_y is not None:
        new_entrance = Point2D(x=payload.entrance_x, y=payload.entrance_y)

    app_state.sync_room_position(room_id, center=new_center, entrance=new_entrance)

    return {
        "status": "success",
        "message": f"Coordenadas de Aula '{room_id}' actualizadas correctamente.",
        "room": {
            "id": target_room.id,
            "name": target_room.name,
            "floor_number": target_room.floor_number,
            "center": {"x": target_room.center.x, "y": target_room.center.y},
            "entrance": {"x": target_room.entrance.x, "y": target_room.entrance.y}
        }
    }

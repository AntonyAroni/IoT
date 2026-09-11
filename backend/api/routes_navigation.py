"""
Controlador HTTP: Consulta de Ubicación y Rutas (Stateless / Fallback).
Permite inferir la posición mediante WKNN y solicitar una ruta a través de HTTP REST.
"""
import time
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, List
from ..domain.fingerprint import FingerprintVector
from ..domain.building import Point2D
from ..services.floor_classifier import FloorClassifierService
from ..services.wknn_locator import WKNNPositioningService
from ..services.navigation_engine import NavigationEngine

router = APIRouter(prefix="/api/v1/navigation", tags=["Navigation"])

def get_floor_classifier() -> FloorClassifierService:
    from ..main import app_state
    return app_state.floor_classifier

def get_wknn_locator() -> WKNNPositioningService:
    from ..main import app_state
    return app_state.wknn_locator

def get_navigation_engine() -> NavigationEngine:
    from ..main import app_state
    return app_state.navigation_engine

class LocateRequestModel(BaseModel):
    device_id: str = Field(..., description="ID del dispositivo o estudiante")
    readings: Dict[str, float] = Field(..., description="Mapeo BSSID -> RSSI en dBm")
    target_room_id: Optional[str] = Field(None, description="Salón objetivo para generar pistas")

@router.post("/locate")
def locate_and_route(
    req: LocateRequestModel,
    floor_clf: FloorClassifierService = Depends(get_floor_classifier),
    wknn: WKNNPositioningService = Depends(get_wknn_locator),
    nav_engine: NavigationEngine = Depends(get_navigation_engine)
) -> Dict[str, Any]:
    """Infiere el piso, calcula coordenada 2D con WKNN y genera pistas de navegación."""
    vector = FingerprintVector(
        timestamp=time.time(),
        device_id=req.device_id,
        readings={k.lower(): v for k, v in req.readings.items()}
    )

    # 1. Clasificación Jerárquica de Piso
    detected_floor, floor_confidence = floor_clf.classify_floor(vector)

    # 2. Localización 2D por WKNN en ese piso
    estimated_pos, neighbors = wknn.estimate_position(detected_floor, vector)

    response = {
        "device_id": req.device_id,
        "floor_number": detected_floor,
        "floor_confidence": round(floor_confidence, 2),
        "position": {"x": estimated_pos.x, "y": estimated_pos.y},
        "neighbors_used": len(neighbors)
    }

    # 3. Si se especifica salón destino, calcular la ruta y pista activa
    if req.target_room_id:
        try:
            route = nav_engine.compute_route(detected_floor, estimated_pos, req.target_room_id)
            response["navigation"] = {
                "target_room": req.target_room_id,
                "target_floor": route.target_floor,
                "distance_meters": route.total_distance_meters,
                "active_clue": route.active_clue,
                "progress_percentage": route.progress_percentage,
                "has_arrived": route.has_arrived,
                "path": route.path_node_ids
            }
        except Exception as e:
            response["navigation_error"] = str(e)

    return response

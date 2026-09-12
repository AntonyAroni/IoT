"""
Controlador HTTP: Modo Calibración y Gestión del Radio-Mapa (Fase Offline).
Permite que el sensor móvil o herramienta de calibración registre puntos de referencia (RPs).
"""
from fastapi import APIRouter, HTTPException, Depends
from .security import require_admin
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from ..domain.building import Point2D
from ..domain.fingerprint import ReferencePoint, RadioMapEntry
from ..repositories.base import IRadioMapRepository

router = APIRouter(prefix="/api/v1/calibration", tags=["Calibration"])

def get_radio_map_repo() -> IRadioMapRepository:
    from ..main import app_state
    return app_state.radio_map_repo

class CalibrationUploadModel(BaseModel):
    rp_id: str = Field(..., description="Identificador único del punto de referencia")
    floor_number: int = Field(..., ge=1, le=4, description="Piso donde se ubica el punto")
    x: float = Field(..., description="Coordenada X en metros")
    y: float = Field(..., description="Coordenada Y en metros")
    label: str = Field(..., description="Etiqueta amigable del punto")
    room_id: Optional[str] = Field(None, description="Salón asociado si aplica")
    rssi_means: Dict[str, float] = Field(..., description="Diccionario BSSID -> RSSI promedio")
    rssi_std: Optional[Dict[str, float]] = Field(default_factory=dict)
    sample_count: int = Field(15, ge=1)

@router.post("/record", dependencies=[Depends(require_admin)])
def record_calibration_point(
    payload: CalibrationUploadModel,
    repo: IRadioMapRepository = Depends(get_radio_map_repo)
) -> Dict[str, Any]:
    """Registra o actualiza una huella de calibración para un Punto de Referencia."""
    rp = ReferencePoint(
        id=payload.rp_id,
        floor_number=payload.floor_number,
        position=Point2D(x=payload.x, y=payload.y),
        label=payload.label,
        room_id=payload.room_id
    )
    entry = RadioMapEntry(
        reference_point=rp,
        rssi_means={k.lower(): v for k, v in payload.rssi_means.items()},
        rssi_std=payload.rssi_std or {},
        sample_count=payload.sample_count
    )
    repo.save_entry(entry)
    return {
        "status": "success",
        "message": f"Punto de Referencia '{payload.rp_id}' guardado correctamente.",
        "total_calibrated_points": len(repo.get_all_entries())
    }

@router.get("/radio-map")
def get_radio_map(repo: IRadioMapRepository = Depends(get_radio_map_repo)) -> List[Dict[str, Any]]:
    """Descarga el radio-mapa completo actual."""
    return [entry.to_dict() for entry in repo.get_all_entries()]

@router.delete("/radio-map", dependencies=[Depends(require_admin)])
def clear_radio_map(repo: IRadioMapRepository = Depends(get_radio_map_repo)) -> Dict[str, str]:
    """Limpia el radio-mapa en memoria y almacenamiento."""
    repo.clear()
    return {"status": "success", "message": "Radio-mapa reiniciado."}

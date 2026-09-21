"""
Controlador HTTP: Modo Calibración y Gestión del Radio-Mapa (Fase Offline).
Permite que el sensor móvil o herramienta de calibración registre puntos de referencia (RPs).
"""
import os
import shutil
from fastapi import APIRouter, HTTPException, Depends, status
from .security import require_admin
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from ..domain.building import Point2D
from ..domain.fingerprint import ReferencePoint, RadioMapEntry
from ..domain.graph import infer_room_id
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

@router.post("/record")
def record_calibration_point(
    payload: CalibrationUploadModel,
    repo: IRadioMapRepository = Depends(get_radio_map_repo)
) -> Dict[str, Any]:
    """Registra o actualiza una huella de calibración para un Punto de Referencia."""
    from ..main import app_state
    resolved_room_id = payload.room_id or infer_room_id(payload.rp_id, payload.floor_number, payload.label)

    rp = ReferencePoint(
        id=payload.rp_id,
        floor_number=payload.floor_number,
        position=Point2D(x=payload.x, y=payload.y),
        label=payload.label,
        room_id=resolved_room_id
    )
    entry = RadioMapEntry(
        reference_point=rp,
        rssi_means={k.lower(): v for k, v in payload.rssi_means.items()},
        rssi_std=payload.rssi_std or {},
        sample_count=payload.sample_count
    )
    repo.save_entry(entry)

    # Sincronizar en caliente la posición del aula si corresponde
    if resolved_room_id and resolved_room_id in app_state.graph.nodes:
        label_lower = (payload.label + " " + payload.rp_id).lower()
        is_door = "puerta" in label_lower or "door" in label_lower or "entrada" in label_lower
        if is_door:
            app_state.sync_room_position(resolved_room_id, entrance=Point2D(x=payload.x, y=payload.y))
        else:
            app_state.sync_room_position(resolved_room_id, center=Point2D(x=payload.x, y=payload.y))

    return {
        "status": "success",
        "message": f"Punto de Referencia '{payload.rp_id}' guardado correctamente.",
        "room_id": resolved_room_id,
        "total_calibrated_points": len(repo.get_all_entries())
    }

@router.get("/radio-map")
def get_radio_map(repo: IRadioMapRepository = Depends(get_radio_map_repo)) -> List[Dict[str, Any]]:
    """Descarga el radio-mapa completo actual."""
    return [entry.to_dict() for entry in repo.get_all_entries()]

@router.delete("/point/{rp_id}", dependencies=[Depends(require_admin)])
def delete_calibration_point(
    rp_id: str,
    repo: IRadioMapRepository = Depends(get_radio_map_repo)
) -> Dict[str, Any]:
    """Elimina un punto de referencia específico del radio-mapa."""
    from ..main import app_state
    if not repo.delete_entry(rp_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Punto de Referencia '{rp_id}' no encontrado en el radio-mapa."
        )
    app_state.sync_room_positions_from_radio_map()
    return {
        "status": "success",
        "message": f"Punto de Referencia '{rp_id}' eliminado correctamente.",
        "total_calibrated_points": len(repo.get_all_entries())
    }

@router.delete("/radio-map", dependencies=[Depends(require_admin)])
def clear_radio_map(repo: IRadioMapRepository = Depends(get_radio_map_repo)) -> Dict[str, Any]:
    """Limpia el radio-mapa en memoria y almacenamiento creando un respaldo preventivo."""
    from ..config import config
    if config.server.radio_map_file and os.path.exists(config.server.radio_map_file):
        backup_path = config.server.radio_map_file + ".backup"
        try:
            shutil.copyfile(config.server.radio_map_file, backup_path)
        except Exception:
            pass
    repo.clear()
    return {
        "status": "success",
        "message": "Radio-mapa vaciado completamente (0 puntos). Listo para nuevo mapeo.",
        "total_calibrated_points": 0
    }

@router.post("/restore-baseline", dependencies=[Depends(require_admin)])
def restore_baseline_radio_map(repo: IRadioMapRepository = Depends(get_radio_map_repo)) -> Dict[str, Any]:
    """Restaura el radio-mapa desde el archivo de respaldo o configuración original."""
    from ..config import config, PROJECT_ROOT
    from ..main import app_state

    baseline_path = str(PROJECT_ROOT / "data" / "radio_map_baseline.json")
    backup_path = config.server.radio_map_file + ".backup"

    source_path = None
    if os.path.exists(baseline_path):
        source_path = baseline_path
    elif os.path.exists(backup_path):
        source_path = backup_path

    if source_path:
        repo.load_from_file(source_path)
        repo.save_to_file(config.server.radio_map_file)
        app_state.sync_room_positions_from_radio_map()
        return {
            "status": "success",
            "message": f"Radio-mapa restaurado exitosamente ({len(repo.get_all_entries())} puntos).",
            "total_calibrated_points": len(repo.get_all_entries())
        }
    return {
        "status": "error",
        "message": "No se encontró copia de respaldo previa (.backup) ni archivo baseline."
    }



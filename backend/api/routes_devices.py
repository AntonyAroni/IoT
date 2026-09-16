"""
Controlador HTTP: Alta y Baja de Dispositivos.

El alta es una operación administrativa: la realiza quien despliega el sistema, no el alumno.
Por eso va protegida con `require_admin`, igual que las operaciones destructivas.

El token se devuelve **una sola vez**, en la respuesta del alta. El registro guarda solo su
huella, de modo que si el fichero se filtra no sirve para suplantar a ningún dispositivo. Si se
pierde el token, hay que dar de alta el dispositivo otra vez.
"""
import re
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..repositories.device_repo import DeviceRegistry
from .security import require_admin

router = APIRouter(prefix="/api/v1/devices", tags=["Devices"])

# Mismo alfabeto que exige el handshake del WebSocket.
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def get_device_registry() -> DeviceRegistry:
    from ..main import app_state
    return app_state.device_registry


class EnrollmentRequest(BaseModel):
    device_id: str = Field(..., description="Identificador del móvil, ej. MOVIL_AULA_302_01")
    student_id: str = Field(..., description="Alumno al que representa el dispositivo")
    student_name: str = Field("", description="Nombre visible en el tablero del aula")
    enrolled_room: str = Field(..., description="Aula asignada, ej. S302")


def _validate(field: str, value: str) -> None:
    if not IDENTIFIER_PATTERN.match(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{field}' solo admite [A-Za-z0-9_-] y hasta 32 caracteres.",
        )


@router.post("/enroll", dependencies=[Depends(require_admin)])
def enroll_device(
    payload: EnrollmentRequest,
    registry: DeviceRegistry = Depends(get_device_registry),
) -> Dict[str, Any]:
    """
    Da de alta un dispositivo y devuelve su token.

    Atención: dar de alta el **primer** dispositivo activa la exigencia de token en el canal
    móvil. A partir de ese momento, los clientes sin credencial dejan de ser aceptados.
    """
    for field in ("device_id", "student_id", "enrolled_room"):
        _validate(field, getattr(payload, field))

    era_permisivo = not registry.enforcement_enabled

    token = registry.enroll(
        device_id=payload.device_id,
        student_id=payload.student_id,
        student_name=payload.student_name or payload.student_id,
        enrolled_room=payload.enrolled_room,
    )

    respuesta: Dict[str, Any] = {
        "status": "success",
        "device_id": payload.device_id,
        "student_id": payload.student_id,
        "token": token,
        "aviso": (
            "Guarda este token ahora: el servidor solo conserva su huella y no puede volver a "
            "mostrarlo. Si se pierde, da de alta el dispositivo otra vez."
        ),
    }
    if era_permisivo:
        respuesta["cambio_de_modo"] = (
            "Era el primer dispositivo dado de alta. El canal /ws/mobile pasa a exigir token, "
            "y los clientes sin credencial (demostración, sensor virtual) dejarán de conectar."
        )
    return respuesta


@router.get("")
def list_devices(registry: DeviceRegistry = Depends(get_device_registry)) -> Dict[str, Any]:
    """Lista los dispositivos dados de alta. No expone huellas de token."""
    devices: List[Dict[str, Any]] = [d.to_public_dict() for d in registry.list_devices()]
    return {
        "total": len(devices),
        "token_requerido": registry.enforcement_enabled,
        "devices": sorted(devices, key=lambda d: d["device_id"]),
    }


@router.post("/{device_id}/revoke", dependencies=[Depends(require_admin)])
def revoke_device(
    device_id: str,
    registry: DeviceRegistry = Depends(get_device_registry),
) -> Dict[str, str]:
    """Revoca un dispositivo: su token deja de ser válido de inmediato."""
    if not registry.revoke(device_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay ningún dispositivo activo con id '{device_id}'.",
        )
    return {"status": "success", "message": f"Dispositivo '{device_id}' revocado."}

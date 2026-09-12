"""
Control de Acceso a las Operaciones Destructivas.

`DELETE /api/v1/calibration/radio-map` borra el radio-mapa completo,
`POST /api/v1/calibration/record` puede envenenarlo con huellas falsas y
`POST /api/v1/attendance/room/{id}/reset` descarta la asistencia de un aula. Las tres estaban
expuestas de forma anónima a toda la red local: una petición accidental durante una prueba
destruye la calibración del edificio.

Esto **no es autenticación de usuarios**. El sistema todavía no tiene padrón ni credenciales por
alumno, y esa tarea sigue pendiente (ver P0-4 en `PLAN_CORRECCIONES.md`). Lo que cubre es el
riesgo operativo, con dos modos:

- **Con `IPS_ADMIN_TOKEN` definido:** las operaciones exigen la cabecera `X-Admin-Token`.
- **Sin definir:** solo se aceptan desde la propia máquina. La demostración y el desarrollo
  siguen funcionando sin configurar nada, pero la red local queda cerrada.

El segundo modo es un valor por defecto deliberado: fallar cerrado del todo obligaría a
configurar un token para ejecutar `demo_runner.py`, y el resultado previsible sería que alguien
desactivara la comprobación entera.
"""
import logging
import secrets

from fastapi import Header, HTTPException, Request, status

from ..config import config

logger = logging.getLogger("ips.security")

ADMIN_TOKEN_HEADER = "X-Admin-Token"


def _client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def require_admin(
    request: Request,
    x_admin_token: str = Header(default="", alias=ADMIN_TOKEN_HEADER),
) -> None:
    """
    Dependencia de FastAPI que protege una operación destructiva.

    Lanza 401 si falta o no coincide el token, y 403 si la petición llega desde la red cuando no
    hay token configurado.
    """
    security = config.security

    if security.requires_token:
        # compare_digest evita filtrar información por el tiempo de comparación.
        if not x_admin_token or not secrets.compare_digest(x_admin_token, security.admin_token):
            logger.warning(
                f"Operación destructiva rechazada: token inválido o ausente "
                f"(origen {_client_host(request)}, ruta {request.url.path})"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Esta operación requiere la cabecera {ADMIN_TOKEN_HEADER}.",
            )
        return

    host = _client_host(request)
    if host not in security.loopback_hosts:
        logger.warning(
            f"Operación destructiva rechazada: petición remota desde {host} sin token "
            f"configurado (ruta {request.url.path})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Las operaciones destructivas solo se aceptan desde la máquina local. "
                "Define la variable de entorno IPS_ADMIN_TOKEN para permitirlas desde la red "
                f"enviando la cabecera {ADMIN_TOKEN_HEADER}."
            ),
        )

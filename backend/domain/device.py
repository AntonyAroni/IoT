"""
Entidades del Dominio: Credencial de Dispositivo.

El sistema identifica alumnos por el `student_id` que el móvil declara en la ruta del WebSocket,
sin comprobar nada: marcar la asistencia de otro es una línea de `websocat`. Esta entidad
sostiene el paso intermedio entre esa situación y un padrón completo de usuarios.

Lo que resuelve: que la identidad que envía un dispositivo sea **verificable** y no solo
declarada. Cada móvil se da de alta una vez, recibe un token y lo presenta al conectarse; el
`student_id` se deriva de la credencial, no del texto de la ruta.

Lo que NO resuelve, y conviene declararlo: atar la identidad al dispositivo no impide que un
alumno preste el móvil a otro. Le ocurre a cualquier sistema de asistencia por dispositivo y no
se corrige con criptografía, sino con controles fuera de banda.
"""
import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

# Longitud del token generado, en bytes de entropía antes de codificar.
TOKEN_ENTROPY_BYTES = 32


def generate_token() -> str:
    """Genera un token de dispositivo. Solo se muestra una vez, en el alta."""
    return secrets.token_urlsafe(TOKEN_ENTROPY_BYTES)


def hash_token(token: str) -> str:
    """
    Huella del token para almacenarlo.

    El servidor nunca guarda el token en claro: si el fichero del registro se filtra, no sirve
    para suplantar a ningún dispositivo.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class DeviceCredential:
    """Un dispositivo dado de alta y el alumno al que representa."""
    device_id: str
    token_hash: str
    student_id: str
    student_name: str
    enrolled_room: str
    enrolled_at: float
    revoked_at: Optional[float] = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def matches(self, token: str) -> bool:
        """Comprobación en tiempo constante, para no filtrar información por el tiempo de respuesta."""
        return secrets.compare_digest(self.token_hash, hash_token(token))

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "token_hash": self.token_hash,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "enrolled_room": self.enrolled_room,
            "enrolled_at": self.enrolled_at,
            "revoked_at": self.revoked_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceCredential":
        return cls(
            device_id=data["device_id"],
            token_hash=data["token_hash"],
            student_id=data["student_id"],
            student_name=data.get("student_name", data["student_id"]),
            enrolled_room=data["enrolled_room"],
            enrolled_at=data.get("enrolled_at", 0.0),
            revoked_at=data.get("revoked_at"),
        )

    def to_public_dict(self) -> dict:
        """Vista sin la huella del token, para listar dispositivos."""
        data = self.to_dict()
        data.pop("token_hash")
        data["active"] = self.is_active
        return data

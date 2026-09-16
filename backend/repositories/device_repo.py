"""
Registro de Dispositivos Dados de Alta.

Persiste las credenciales en JSON, con la misma política de escritura que el resto: se guarda al
instante, porque dar de alta o revocar un dispositivo es una operación puntual y no está en el
camino crítico de la telemetría.

Modo de transición
------------------
Mientras el registro esté **vacío**, el canal móvil sigue aceptando conexiones sin token. Es
deliberado: hay ocho consumidores que se conectan sin credencial (la demostración, el sensor
virtual, la suite sintética) y exigir token de golpe los rompería todos, con el resultado
previsible de que alguien acabara desactivando la comprobación entera.

En cuanto se da de alta el primer dispositivo, el token pasa a ser obligatorio.
"""
import json
import os
import time
from typing import Dict, List, Optional

from ..domain.device import DeviceCredential, generate_token, hash_token


class DeviceRegistry:
    def __init__(self, storage_path: Optional[str] = None):
        self._devices: Dict[str, DeviceCredential] = {}
        self.storage_path = storage_path
        if storage_path and os.path.exists(storage_path):
            self.load_from_file(storage_path)

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------

    @property
    def enforcement_enabled(self) -> bool:
        """
        True en cuanto se ha dado de alta algún dispositivo, aunque después se revoque.

        Deliberadamente NO es "hay algún dispositivo activo". Con esa definición, revocar el
        último dispositivo devolvía el canal móvil a modo permisivo: quien revocara un móvil
        comprometido estaría abriendo la puerta a cualquiera, justo en el momento en que menos
        lo quiere. La exigencia de token es un camino de ida.
        """
        return bool(self._devices)

    def get(self, device_id: str) -> Optional[DeviceCredential]:
        return self._devices.get(device_id)

    def list_devices(self) -> List[DeviceCredential]:
        return list(self._devices.values())

    def resolve_token(self, token: str) -> Optional[DeviceCredential]:
        """
        Devuelve la credencial activa que corresponde a un token, o None.

        Se compara contra la huella de todos los dispositivos en lugar de indexar por token,
        porque el token en claro no se almacena en ninguna parte.
        """
        if not token:
            return None
        objetivo = hash_token(token)
        for device in self._devices.values():
            if device.is_active and secrets_compare(device.token_hash, objetivo):
                return device
        return None

    # ------------------------------------------------------------------
    # Alta y baja
    # ------------------------------------------------------------------

    def enroll(
        self,
        device_id: str,
        student_id: str,
        student_name: str,
        enrolled_room: str,
    ) -> str:
        """
        Da de alta un dispositivo y devuelve su token **en claro**.

        Es la única vez que el token existe fuera del móvil: el registro solo guarda su huella.
        Si se pierde, hay que volver a dar de alta el dispositivo.
        """
        token = generate_token()
        self._devices[device_id] = DeviceCredential(
            device_id=device_id,
            token_hash=hash_token(token),
            student_id=student_id,
            student_name=student_name,
            enrolled_room=enrolled_room,
            enrolled_at=time.time(),
        )
        self._persist()
        return token

    def revoke(self, device_id: str) -> bool:
        device = self._devices.get(device_id)
        if not device or not device.is_active:
            return False
        device.revoked_at = time.time()
        self._persist()
        return True

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def load_from_file(self, filepath: str) -> None:
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._devices = {
            item["device_id"]: DeviceCredential.from_dict(item)
            for item in data
        }

    def save_to_file(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        data = [d.to_dict() for d in self._devices.values()]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _persist(self) -> None:
        if self.storage_path:
            self.save_to_file(self.storage_path)


def secrets_compare(a: str, b: str) -> bool:
    import secrets
    return secrets.compare_digest(a, b)

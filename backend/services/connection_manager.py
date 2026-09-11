"""
Gestor de Conexiones WebSocket en Tiempo Real.
Administra canales aislados para las laptops de cada salón, los dispositivos móviles
y el panel de control administrativo/auditoría.
"""
from typing import Dict, Set, Any
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger("ips.connection_manager")

class ConnectionManager:
    def __init__(self):
        # Laptops de estación: room_id -> Set[WebSocket]
        self._laptop_rooms: Dict[str, Set[WebSocket]] = {}
        # Clientes móviles de estudiantes: student_id -> Set[WebSocket]
        self._mobile_clients: Dict[str, Set[WebSocket]] = {}
        # Conexiones del panel administrativo global
        self._admin_subscribers: Set[WebSocket] = set()

    async def connect_laptop(self, websocket: WebSocket, room_id: str) -> None:
        await websocket.accept()
        if room_id not in self._laptop_rooms:
            self._laptop_rooms[room_id] = set()
        self._laptop_rooms[room_id].add(websocket)
        logger.info(f"Laptop conectada para el aula {room_id}. Conexiones activas en aula: {len(self._laptop_rooms[room_id])}")

    def disconnect_laptop(self, websocket: WebSocket, room_id: str) -> None:
        if room_id in self._laptop_rooms and websocket in self._laptop_rooms[room_id]:
            self._laptop_rooms[room_id].remove(websocket)
            if not self._laptop_rooms[room_id]:
                del self._laptop_rooms[room_id]
        logger.info(f"Laptop desconectada del aula {room_id}.")

    async def connect_mobile(self, websocket: WebSocket, student_id: str) -> None:
        await websocket.accept()
        if student_id not in self._mobile_clients:
            self._mobile_clients[student_id] = set()
        self._mobile_clients[student_id].add(websocket)
        logger.info(f"Sensor móvil conectado para estudiante {student_id}.")

    def disconnect_mobile(self, websocket: WebSocket, student_id: str) -> None:
        if student_id in self._mobile_clients and websocket in self._mobile_clients[student_id]:
            self._mobile_clients[student_id].remove(websocket)
            if not self._mobile_clients[student_id]:
                del self._mobile_clients[student_id]
        logger.info(f"Sensor móvil desconectado: {student_id}.")

    async def connect_admin(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._admin_subscribers.add(websocket)
        logger.info(f"Auditor/Admin conectado a telemetría global.")

    def disconnect_admin(self, websocket: WebSocket) -> None:
        self._admin_subscribers.discard(websocket)

    async def broadcast_to_room(self, room_id: str, message: dict) -> None:
        """Emite un evento a todas las laptops activas del salón especificado."""
        sockets = self._laptop_rooms.get(room_id, set()).copy()
        payload = json.dumps(message)
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.warning(f"Error enviando mensaje a laptop {room_id}: {e}")
                self.disconnect_laptop(ws, room_id)

    async def send_to_mobile(self, student_id: str, message: dict) -> None:
        """Envía pistas o actualización de posición al móvil del estudiante."""
        sockets = self._mobile_clients.get(student_id, set()).copy()
        payload = json.dumps(message)
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.warning(f"Error enviando mensaje a móvil {student_id}: {e}")
                self.disconnect_mobile(ws, student_id)

    async def broadcast_admin(self, message: dict) -> None:
        """Difunde telemetría y eventos al canal de administración global."""
        payload = json.dumps(message)
        for ws in list(self._admin_subscribers):
            try:
                await ws.send_text(payload)
            except Exception as e:
                self._admin_subscribers.discard(ws)

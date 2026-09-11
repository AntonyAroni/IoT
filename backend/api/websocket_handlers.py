"""
Controlador de WebSockets en Tiempo Real.
Orquesta el flujo bidireccional entre Sensores Móviles (Fase 3), Estaciones de Laptop (Fase 2)
y el Cerebro de Localización (Fase 1).
"""
import json
import time
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..domain.fingerprint import FingerprintVector
from ..domain.building import Point2D

logger = logging.getLogger("ips.websockets")
router = APIRouter(tags=["WebSockets"])

@router.websocket("/ws/laptop/{room_id}")
async def ws_laptop_station(websocket: WebSocket, room_id: str):
    """
    Canal de tiempo real para la laptop del aula (Fase 2).
    Recibe alertas instantáneas de alumnos aproximándose o confirmando asistencia.
    """
    from ..main import app_state
    manager = app_state.connection_manager
    attendance_repo = app_state.attendance_repo

    await manager.connect_laptop(websocket, room_id)
    try:
        # Enviar estado inicial del aula al conectarse
        records = attendance_repo.get_room_records(room_id)
        await websocket.send_text(json.dumps({
            "event": "initial_state",
            "room_id": room_id,
            "timestamp": time.time(),
            "records": [r.to_dict() for r in records]
        }))

        while True:
            # Mantener la conexión abierta y responder a keep-alives / comandos
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                if msg.get("action") == "ping":
                    await websocket.send_text(json.dumps({"event": "pong", "timestamp": time.time()}))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect_laptop(websocket, room_id)
    except Exception as e:
        logger.error(f"Error en websocket laptop {room_id}: {e}")
        manager.disconnect_laptop(websocket, room_id)

@router.websocket("/ws/mobile/{student_id}")
async def ws_mobile_sensor(websocket: WebSocket, student_id: str):
    """
    Canal de telemetría de alta frecuencia para el sensor móvil (Fase 3).
    Recibe lecturas Wi-Fi en vivo, computa posición + pistas y notifica a las estaciones de salón.
    """
    from ..main import app_state
    manager = app_state.connection_manager
    floor_clf = app_state.floor_classifier
    wknn = app_state.wknn_locator
    nav_engine = app_state.navigation_engine
    tracker = app_state.attendance_tracker
    graph = app_state.graph

    await manager.connect_mobile(websocket, student_id)
    try:
        while True:
            raw_text = await websocket.receive_text()
            payload = json.loads(raw_text)

            # Extraer vector de lecturas Wi-Fi
            readings = payload.get("readings", {})
            target_room_id = payload.get("target_room_id", "S302")  # Salón objetivo por defecto en demo
            timestamp = payload.get("timestamp", time.time())

            vector = FingerprintVector(
                timestamp=timestamp,
                device_id=student_id,
                readings={k.lower(): float(v) for k, v in readings.items()}
            )

            # 1. Clasificación Jerárquica de Piso
            detected_floor, floor_confidence = floor_clf.classify_floor(vector)

            # 2. Posicionamiento 2D mediante WKNN
            est_pos, neighbors = wknn.estimate_position(detected_floor, vector)

            # 3. Motor de Navegación y Pistas
            target_node = graph.get_node(target_room_id)
            target_floor = target_node.floor_number if target_node else 3
            target_center = target_node.position if target_node else Point2D(10.0, 2.0)

            route = nav_engine.compute_route(detected_floor, est_pos, target_room_id)

            # 4. Rastreo de Asistencia y Permanencia
            # Buscar si alguna de las lecturas corresponde al AP del aula meta
            room_ap_rssi = payload.get("room_ap_rssi")
            record, status_changed, audit_msg = tracker.process_student_presence(
                student_id=student_id,
                detected_floor=detected_floor,
                position=est_pos,
                target_room_id=target_room_id,
                target_room_floor=target_floor,
                target_room_center=target_center,
                strongest_rssi_to_room_ap=room_ap_rssi
            )

            # 5. Respuesta en tiempo real hacia el Móvil
            mobile_feedback = {
                "event": "location_update",
                "timestamp": timestamp,
                "floor_number": detected_floor,
                "floor_confidence": floor_confidence,
                "position": {"x": est_pos.x, "y": est_pos.y},
                "active_clue": route.active_clue,
                "progress_percentage": route.progress_percentage,
                "distance_meters": route.total_distance_meters,
                "has_arrived": route.has_arrived,
                "attendance_status": record.status.value
            }
            await websocket.send_text(json.dumps(mobile_feedback))

            # 6. Notificación reactiva a la Laptop del Salón si hubo cambio de estado o proximidad
            laptop_event = {
                "event": "student_proximity",
                "timestamp": timestamp,
                "student_id": student_id,
                "student_name": record.student_name,
                "status": record.status.value,
                "floor_number": detected_floor,
                "position": {"x": est_pos.x, "y": est_pos.y},
                "distance_to_classroom": round(est_pos.distance_to(target_center), 2) if detected_floor == target_floor else 99.0,
                "rssi": record.last_rssi,
                "samples_in_window": record.samples_in_window,
                "confirmed_at": record.confirmed_at,
                "audit_message": audit_msg
            }
            await manager.broadcast_to_room(target_room_id, laptop_event)

            # 7. Telemetría global para Administrador
            await manager.broadcast_admin({
                "type": "telemetry",
                "student_id": student_id,
                "floor": detected_floor,
                "pos": {"x": est_pos.x, "y": est_pos.y},
                "status": record.status.value,
                "active_clue": route.active_clue
            })

    except WebSocketDisconnect:
        manager.disconnect_mobile(websocket, student_id)
    except Exception as e:
        logger.error(f"Error en websocket móvil {student_id}: {e}")
        manager.disconnect_mobile(websocket, student_id)

@router.websocket("/ws/admin")
async def ws_admin_telemetry(websocket: WebSocket):
    """Canal para monitoreo global y auditoría del sistema."""
    from ..main import app_state
    manager = app_state.connection_manager
    await manager.connect_admin(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)

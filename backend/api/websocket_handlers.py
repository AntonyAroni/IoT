"""
Controlador de WebSockets en Tiempo Real.
Orquesta el flujo bidireccional entre Sensores Móviles (Fase 3), Estaciones de Laptop (Fase 2)
y el Cerebro de Localización (Fase 1).
"""
import json
import re
import time
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..domain.fingerprint import FingerprintVector
from ..domain.building import Point2D
from ..config import config

logger = logging.getLogger("ips.websockets")
router = APIRouter(tags=["WebSockets"])

# Los identificadores llegan como texto libre en la ruta del WebSocket y acaban propagándose al
# tablero del aula. Se restringen a un alfabeto seguro para que no puedan transportar marcado.
# Esto es defensa en profundidad: el frontend además escapa todo valor recibido.
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

# Código de cierre de aplicación para un identificador con formato inválido.
WS_CLOSE_INVALID_IDENTIFIER = 4400


def _is_valid_identifier(value: str) -> bool:
    return bool(IDENTIFIER_PATTERN.match(value))


async def _reject_identifier(websocket: WebSocket, field: str, value: str) -> None:
    """
    Rechaza el handshake informando al cliente del motivo.

    Hay que aceptar la conexión antes de cerrarla: cerrar sin aceptar hace que el servidor
    responda con un HTTP 403 al handshake, y el código de cierre de aplicación nunca llega al
    cliente. Aceptando primero, el móvil recibe el 4400 y sabe que reintentar con el mismo
    identificador no puede funcionar.
    """
    logger.warning(f"Rechazada conexión con {field} inválido: {value!r}")
    await websocket.accept()
    await websocket.close(code=WS_CLOSE_INVALID_IDENTIFIER, reason=f"{field} inválido")

@router.websocket("/ws/laptop/{room_id}")
async def ws_laptop_station(websocket: WebSocket, room_id: str):
    """
    Canal de tiempo real para la laptop del aula (Fase 2).
    Recibe alertas instantáneas de alumnos aproximándose o confirmando asistencia.
    """
    from ..main import app_state
    manager = app_state.connection_manager
    attendance_repo = app_state.attendance_repo

    if not _is_valid_identifier(room_id):
        await _reject_identifier(websocket, "room_id", room_id)
        return

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
    attendance_repo = app_state.attendance_repo

    from ..services.signal_filters import MultiBSSIDKalmanFilter, TrajectoryKinematicFilter2D
    from ..domain.attendance import Student

    # La validación va ANTES de reservar nada: los filtros se guardan en diccionarios del
    # estado global indexados por `student_id`, y la rama de rechazo retorna sin pasar por la
    # limpieza del `finally`. Reservarlos primero dejaba dos objetos colgados por cada intento
    # rechazado, con claves que elige quien se conecta, de modo que repetir conexiones con
    # identificadores aleatorios hacía crecer la memoria sin límite.
    if not _is_valid_identifier(student_id):
        await _reject_identifier(websocket, "student_id", student_id)
        return

    if student_id not in app_state.mobile_kalman_filters:
        app_state.mobile_kalman_filters[student_id] = MultiBSSIDKalmanFilter()
    kalman_filter = app_state.mobile_kalman_filters[student_id]

    if student_id not in app_state.mobile_trajectory_filters:
        app_state.mobile_trajectory_filters[student_id] = TrajectoryKinematicFilter2D()
    trajectory_filter = app_state.mobile_trajectory_filters[student_id]

    await manager.connect_mobile(websocket, student_id)

    # Distancia de la ruta cuando el alumno empezó a navegar hacia cada destino. El motor de
    # navegación no guarda estado entre llamadas, así que la sesión la mantiene aquí para poder
    # expresar el progreso como fracción del trayecto ya recorrido.
    route_origin_distance: dict = {}

    try:
        while True:
            raw_text = await websocket.receive_text()
            payload = json.loads(raw_text)

            # Extraer vector de lecturas Wi-Fi
            readings = payload.get("readings", {})
            target_room_id = payload.get("target_room_id", "S302")
            timestamp = payload.get("timestamp", time.time())

            # Validación o autoregistro de usuario para permitir múltiples dispositivos
            student_obj = attendance_repo.get_student(student_id)
            if not student_obj:
                student_name = payload.get("student_name", f"Alumno {student_id}")
                student_obj = Student(id=student_id, name=student_name, enrolled_room=target_room_id)
                attendance_repo.register_student(student_obj)

            # 0. Filtrado de Kalman 1D por BSSID para atenuar fluctuaciones por multi-trayecto.
            # `enable_kalman_filter` estaba declarado en la configuración pero no se consultaba
            # en ninguna parte, de modo que el filtro se aplicaba siempre y el interruptor no
            # hacía nada.
            raw_readings = {k.lower(): float(v) for k, v in readings.items()}
            if config.wknn.enable_kalman_filter:
                filtered_readings = kalman_filter.filter_readings(raw_readings, timestamp)
            else:
                filtered_readings = raw_readings

            vector = FingerprintVector(
                timestamp=timestamp,
                device_id=student_id,
                readings=filtered_readings
            )

            # 1. Clasificación Jerárquica de Piso
            detected_floor, floor_confidence = floor_clf.classify_floor(vector)

            # 2. Posicionamiento 2D mediante WKNN
            raw_est_pos, neighbors = wknn.estimate_position(detected_floor, vector)

            # 2.1 Suavizado Cinemático de Trayectoria (Anti-Teletransportación entre aulas contiguas)
            est_pos = trajectory_filter.filter_position(raw_est_pos, timestamp)

            # 3. Motor de Navegación y Pistas
            target_node = graph.get_node(target_room_id)
            target_floor = target_node.floor_number if target_node else 3
            target_center = target_node.position if target_node else Point2D(10.0, 2.0)

            known_origin = route_origin_distance.get(target_room_id)
            route = nav_engine.compute_route(
                detected_floor, est_pos, target_room_id,
                initial_distance_meters=known_origin
            )

            # La primera ruta hacia este destino fija el origen del progreso. Si el alumno se
            # aleja y la ruta se alarga más allá del punto de partida, se reancla, de modo que
            # el progreso no quede clavado en 0% durante el resto de la sesión.
            if known_origin is None or route.total_distance_meters > known_origin:
                route_origin_distance[target_room_id] = route.total_distance_meters

            if known_origin is None and not route.has_arrived:
                # En la primera lectura el alumno está en el punto de partida por definición,
                # así que el progreso es 0% y no un valor indeterminado.
                route.progress_percentage = 0.0

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

            # 5. Respuesta en tiempo real hacia el Móvil con alta resolución métrica
            mobile_feedback = {
                "event": "location_update",
                "timestamp": timestamp,
                "student_id": student_id,
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
            dist_to_room = round(est_pos.distance_to(target_center), 2) if detected_floor == target_floor else 99.0
            laptop_event = {
                "event": "student_proximity",
                "timestamp": timestamp,
                "student_id": student_id,
                "student_name": record.student_name,
                "status": record.status.value,
                "floor_number": detected_floor,
                "position": {"x": est_pos.x, "y": est_pos.y},
                "distance_to_classroom": dist_to_room,
                "rssi": record.last_rssi,
                "rssi_is_measured": record.rssi_is_measured,
                "samples_in_window": record.samples_in_window,
                "confirmed_at": record.confirmed_at,
                "audit_message": audit_msg
            }
            await manager.broadcast_to_room(target_room_id, laptop_event)

            # 7. Telemetría global para Administrador
            await manager.broadcast_admin({
                "type": "telemetry",
                "student_id": student_id,
                "student_name": record.student_name,
                "floor": detected_floor,
                "pos": {"x": est_pos.x, "y": est_pos.y},
                "status": record.status.value,
                "active_clue": route.active_clue
            })

    except WebSocketDisconnect:
        manager.disconnect_mobile(websocket, student_id)
        if student_id not in manager._mobile_clients:
            app_state.mobile_kalman_filters.pop(student_id, None)
            app_state.mobile_trajectory_filters.pop(student_id, None)
    except Exception as e:
        logger.error(f"Error en websocket móvil {student_id}: {e}")
        manager.disconnect_mobile(websocket, student_id)
        if student_id not in manager._mobile_clients:
            app_state.mobile_kalman_filters.pop(student_id, None)
            app_state.mobile_trajectory_filters.pop(student_id, None)

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

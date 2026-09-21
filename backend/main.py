"""
Punto de Entrada Principal del Backend: Sistema Multi-Piso de Localización en Interiores (IPS).
Configura la aplicación FastAPI, inyección de dependencias, CORS, rutas y archivos estáticos.
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse

from .config import config
from .domain.building import Point2D
from .domain.graph import create_default_school_graph, infer_room_id
from .repositories.radio_map_repo import InMemoryRadioMapRepository
from .repositories.attendance_repo import InMemoryAttendanceRepository
from .repositories.device_repo import DeviceRegistry
from .services.floor_classifier import FloorClassifierService
from .services.wknn_locator import WKNNPositioningService
from .services.navigation_engine import NavigationEngine
from .services.attendance_tracker import AttendanceTrackerService
from .services.connection_manager import ConnectionManager
from .api import (
    building_router,
    calibration_router,
    navigation_router,
    attendance_router,
    network_router,
    devices_router,
    websocket_router
)
from .services.signal_filters import MultiBSSIDKalmanFilter, TrajectoryKinematicFilter2D

# Configurar Logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ips.main")

class ApplicationState:
    """Contenedor de estado e inyección de dependencias."""
    def __init__(self):
        # 1. Topología del Edificio y Grafo de 4 pisos
        self.graph, self.floors = create_default_school_graph()

        # 2. Repositorios de Persistencia
        self.radio_map_repo = InMemoryRadioMapRepository(config.server.radio_map_file)
        self.attendance_repo = InMemoryAttendanceRepository(config.server.attendance_log_file)
        self.device_registry = DeviceRegistry(config.server.device_registry_file)

        # 3. Servicios del Negocio
        self.floor_classifier = FloorClassifierService(self.radio_map_repo)
        self.wknn_locator = WKNNPositioningService(self.radio_map_repo, config.wknn)
        self.navigation_engine = NavigationEngine(self.graph, self.floors)
        self.attendance_tracker = AttendanceTrackerService(self.attendance_repo, config.attendance)
        self.connection_manager = ConnectionManager()

        # 4. Filtros Híbridos por Cliente Móvil (Kalman 1D para RSSI y Cinemático 2D para Trayectoria)
        self.mobile_kalman_filters: dict = {}
        self.mobile_trajectory_filters: dict = {}

    def sync_room_position(self, room_id: str, center: Point2D = None, entrance: Point2D = None) -> bool:
        """Actualiza las coordenadas de un salón en el grafo topológico y en la jerarquía de pisos."""
        updated = False
        if center is not None:
            if self.graph.update_node_position(room_id, center):
                updated = True

        for fl in self.floors.values():
            for r in fl.rooms:
                if r.id == room_id:
                    if center is not None:
                        r.center = center
                        updated = True
                    if entrance is not None:
                        r.entrance = entrance
                        updated = True
        return updated

    def sync_room_positions_from_radio_map(self) -> int:
        """Sincroniza las coordenadas de salones con los puntos de referencia calibrados en el radio-mapa."""
        entries = self.radio_map_repo.get_all_entries()
        synced_count = 0
        modified_entries = False
        for entry in entries:
            rp = entry.reference_point
            r_id = rp.room_id or infer_room_id(rp.id, rp.floor_number, rp.label)
            if not r_id or r_id not in self.graph.nodes:
                continue

            if rp.room_id is None:
                rp.room_id = r_id
                modified_entries = True

            label_lower = (rp.label + " " + rp.id).lower()
            is_door = "puerta" in label_lower or "door" in label_lower or "entrada" in label_lower

            if is_door:
                self.sync_room_position(r_id, entrance=rp.position)
            else:
                self.sync_room_position(r_id, center=rp.position)
            synced_count += 1

        if modified_entries and hasattr(self.radio_map_repo, "save_to_file") and getattr(self.radio_map_repo, "storage_path", None):
            self.radio_map_repo.save_to_file(self.radio_map_repo.storage_path)

        return synced_count

# Instancia global del estado de la aplicación
app_state = ApplicationState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    calibrated_points = len(app_state.radio_map_repo.get_all_entries())
    synced_rooms = app_state.sync_room_positions_from_radio_map()

    logger.info("=======================================================")
    logger.info(" INICIANDO CEREBRO IPS (4 PISOS, 12 SALONES, WEBSOCKETS)")
    logger.info(f" Nodos en Grafo: {len(app_state.graph.nodes)}")
    logger.info(f" Salones Registrados: {sum(len(f.rooms) for f in app_state.floors.values())}")
    logger.info(f" Puntos de Referencia Calibrados: {calibrated_points}")
    if synced_rooms > 0:
        logger.info(f" Salones Sincronizados con Radio-Mapa: {synced_rooms}")
    logger.info(f" Radio-Mapa: {config.server.radio_map_file}")
    if config.security.requires_token:
        logger.info(" Operaciones destructivas: requieren cabecera X-Admin-Token")
    else:
        logger.info(" Operaciones destructivas: solo desde la máquina local")
        logger.info("   (define IPS_ADMIN_TOKEN para permitirlas desde la red)")
    origins = config.server.allowed_origins
    logger.info(f" CORS: {', '.join(origins) if origins else 'solo mismo origen'}")

    registry = app_state.device_registry
    activos = sum(1 for d in registry.list_devices() if d.is_active)
    if registry.enforcement_enabled:
        logger.info(f" Canal móvil: requiere token de dispositivo ({activos} activos)")
    else:
        logger.info(" Canal móvil: ABIERTO, cualquier identificador es aceptado")
        logger.info("   (da de alta un dispositivo en POST /api/v1/devices/enroll para exigir token)")
    logger.info("=======================================================")

    # Un IPS sin radio-mapa no falla: devuelve piso 1 y una posición por defecto para todos,
    # aparentando funcionar. Hay que avisar ruidosamente en lugar de degradar en silencio.
    if calibrated_points == 0:
        logger.warning("=======================================================")
        logger.warning(" ⚠️  RADIO-MAPA VACÍO: el posicionamiento NO es fiable.")
        logger.warning(f"    Ruta esperada: {config.server.radio_map_file}")
        logger.warning("    Genéralo con:  PYTHONPATH=. python calibration_tools/generate_synthetic_map.py")
        logger.warning("    O apunta a otro fichero con la variable IPS_RADIO_MAP_PATH.")
        logger.warning("=======================================================")

    yield

    # Volcar a disco lo que quede pendiente por el debounce de escritura.
    app_state.attendance_repo.flush()
    logger.info("Apagando servidor IPS...")

app = FastAPI(
    title="Sistema IPS & Asistencia Inteligente Multi-Piso",
    description="Backend central con Grafo 4 Pisos, WKNN y WebSockets para guiado y confirmación de asistencia",
    version="1.0.0",
    lifespan=lifespan
)

# CORS restringido.
#
# La configuración anterior combinaba `allow_origins=["*"]` con `allow_credentials=True`.
# Starlette resuelve esa combinación reflejando el Origin de quien pregunta, de modo que no
# fallaba de forma visible: simplemente concedía acceso con credenciales a cualquier sitio web.
#
# El tablero de aula no necesita CORS en absoluto. Se sirve desde este mismo servidor bajo
# `/estacion`, pide la API con rutas relativas y construye la URL del WebSocket a partir de
# `window.location`, así que todas sus peticiones son del mismo origen. Los clientes Android
# tampoco lo necesitan: CORS es una política de navegadores.
#
# Por eso la lista por defecto está vacía. Solo hay que rellenar `IPS_ALLOWED_ORIGINS` si el
# frontend llega a desplegarse en otro dominio.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)

# Registrar Routers de la API y WebSockets
app.include_router(building_router)
app.include_router(calibration_router)
app.include_router(navigation_router)
app.include_router(attendance_router)
app.include_router(network_router)
app.include_router(devices_router)
app.include_router(websocket_router)

# Montar Frontend de Estaciones de Salón si existe el directorio
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend_stations"))
if os.path.exists(frontend_dir):
    app.mount("/estacion", StaticFiles(directory=frontend_dir, html=True), name="station_frontend")

@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "system": "IPS Multi-Floor Core",
        "floors": len(app_state.floors),
        "calibrated_points": len(app_state.radio_map_repo.get_all_entries())
    }

@app.get("/apk", tags=["Mobile Client"])
@app.get("/download/apk", tags=["Mobile Client"])
def download_apk():
    apk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app-debug.apk"))
    if not os.path.exists(apk_path):
        apk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mobile_app", "android_client", "app", "build", "outputs", "apk", "debug", "app-debug.apk"))
    if os.path.exists(apk_path):
        return FileResponse(apk_path, media_type="application/vnd.android.package-archive", filename="app-debug.apk")
    return {"error": "APK not found. Build it with ./gradlew assembleDebug"}

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/estacion/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=config.server.host, port=config.server.port, reload=config.server.debug)

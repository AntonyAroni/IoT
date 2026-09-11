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
from fastapi.responses import RedirectResponse

from .config import config
from .domain.graph import create_default_school_graph
from .repositories.radio_map_repo import InMemoryRadioMapRepository
from .repositories.attendance_repo import InMemoryAttendanceRepository
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
    websocket_router
)

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

        # 3. Servicios del Negocio
        self.floor_classifier = FloorClassifierService(self.radio_map_repo)
        self.wknn_locator = WKNNPositioningService(self.radio_map_repo, config.wknn)
        self.navigation_engine = NavigationEngine(self.graph, self.floors)
        self.attendance_tracker = AttendanceTrackerService(self.attendance_repo, config.attendance)
        self.connection_manager = ConnectionManager()

# Instancia global del estado de la aplicación
app_state = ApplicationState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=======================================================")
    logger.info(" INICIANDO CEREBRO IPS (4 PISOS, 12 SALONES, WEBSOCKETS)")
    logger.info(f" Nodos en Grafo: {len(app_state.graph.nodes)}")
    logger.info(f" Salones Registrados: {sum(len(f.rooms) for f in app_state.floors.values())}")
    logger.info("=======================================================")
    yield
    logger.info("Apagando servidor IPS...")

app = FastAPI(
    title="Sistema IPS & Asistencia Inteligente Multi-Piso",
    description="Backend central con Grafo 4 Pisos, WKNN y WebSockets para guiado y confirmación de asistencia",
    version="1.0.0",
    lifespan=lifespan
)

# Habilitar CORS para permitir conexión desde cualquier laptop o smartphone en la red local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar Routers de la API y WebSockets
app.include_router(building_router)
app.include_router(calibration_router)
app.include_router(navigation_router)
app.include_router(attendance_router)
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

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/estacion/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=config.server.host, port=config.server.port, reload=config.server.debug)

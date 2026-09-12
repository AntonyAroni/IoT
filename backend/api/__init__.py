from .routes_building import router as building_router
from .routes_calibration import router as calibration_router
from .routes_navigation import router as navigation_router
from .routes_attendance import router as attendance_router
from .routes_network import router as network_router
from .websocket_handlers import router as websocket_router

__all__ = [
    "building_router",
    "calibration_router",
    "navigation_router",
    "attendance_router",
    "network_router",
    "websocket_router"
]

"""
Controlador HTTP: Diagnóstico y Descubrimiento Dinámico de Red.
Permite a las estaciones de salón mostrar al docente la dirección a la que debe conectarse el
móvil, sin obligarle a averiguar la IP de la laptop a mano.

Alcance de lo que se publica
----------------------------
El único consumidor es el tablero de aula, que se sirve desde este mismo servidor. La enumeración
completa de interfaces —Wi-Fi, Ethernet, hotspot, redes internas de Docker— es útil para quien
opera el servidor, pero para el resto de la red local es sólo reconocimiento gratuito.

Por eso la respuesta se reduce según el origen: desde la propia máquina se devuelve el detalle
completo; desde la red, únicamente la dirección con la que conectarse. El tablero necesita esto
último, así que no se rompe abriéndolo desde otra laptop.
"""
import logging
import platform
import socket
import subprocess
from typing import Any, Dict, List

from fastapi import APIRouter, Request

from ..config import config

logger = logging.getLogger("ips.network")
router = APIRouter(prefix="/api/v1/network", tags=["Network"])

# `hostname -I` lista las direcciones IPv4 en Linux, pero en Windows el mismo binario interpreta
# el argumento como el nuevo nombre del equipo e intenta cambiarlo:
#
#     sethostname: use el applet del Panel de control para establecer el nombre del host.
#
# Falla sin privilegios y la excepción se captura, pero lanzaba un subproceso en cada petición y
# ensuciaba la salida de error. Solo se invoca donde tiene el significado esperado.
_HOSTNAME_FLAG_IS_SUPPORTED = platform.system() != "Windows"


def _label_for(ip: str) -> str:
    """Etiqueta legible para orientar a quien configura el móvil."""
    if ip.startswith("10.42."):
        return "Zona Wi-Fi (Hotspot de tu Laptop)"
    if ip.startswith("192.168.43.") or ip.startswith("192.168.137."):
        return "Zona Wi-Fi (Hotspot Móvil)"
    if ip.startswith(("172.17.", "172.18.", "172.19.")):
        return "Red Interna Docker (No usar)"
    if ip.startswith("192.168.") or ip.startswith("10."):
        return "Red Wi-Fi / LAN"
    return "Red Local / LAN"


def get_primary_local_ip() -> str:
    """Obtiene la IP local primaria orientada a la salida de red."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No envía paquetes reales, solo consulta la tabla de ruteo del kernel
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_all_host_ips() -> List[Dict[str, str]]:
    """Detecta todas las IPs IPv4 activas en las interfaces locales (Wi-Fi, Hotspot, Ethernet)."""
    ip_list: List[Dict[str, str]] = []
    seen = set()

    def add(raw_ip: str) -> None:
        clean = raw_ip.strip()
        if clean and not clean.startswith("127.") and clean not in seen:
            seen.add(clean)
            ip_list.append({"ip": clean, "type": _label_for(clean)})

    # Método 1: enumeración por socket. Funciona en cualquier sistema y no lanza procesos.
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except Exception:
        pass

    # Método 2: `hostname -I`, solo donde ese argumento significa "listar direcciones".
    # En Linux detecta interfaces que la resolución del nombre puede omitir, como un hotspot.
    if _HOSTNAME_FLAG_IS_SUPPORTED:
        try:
            output = subprocess.check_output(["hostname", "-I"], text=True, timeout=1.0)
            for ip in output.strip().split():
                add(ip)
        except Exception:
            pass

    # Fallback si no se detectó nada
    primary = get_primary_local_ip()
    if primary not in seen and primary != "127.0.0.1":
        ip_list.append({"ip": primary, "type": "Red Wi-Fi / LAN"})
        seen.add(primary)

    if not ip_list:
        ip_list.append({"ip": "127.0.0.1", "type": "Loopback Local"})

    return ip_list


def determine_best_client_ip(all_ips: List[Dict[str, str]]) -> str:
    """Selecciona la mejor IP para que los celulares se conecten."""
    # 1. Prioridad: Hotspot (10.42.0.1, 192.168.43.1 o 192.168.137.1)
    for item in all_ips:
        ip = item["ip"]
        if ip.startswith("10.42.") or ip.startswith("192.168.43.") or ip.startswith("192.168.137."):
            return ip

    # 2. Prioridad: Wi-Fi / LAN, evitando las redes internas de Docker
    for item in all_ips:
        ip = item["ip"]
        if not ip.startswith(("172.17.", "172.18.", "127.")):
            return ip

    # 3. Fallback
    return all_ips[0]["ip"] if all_ips else "127.0.0.1"


@router.get("/info")
def get_network_info(request: Request) -> Dict[str, Any]:
    """
    Retorna la dirección a la que deben conectarse los clientes.

    Desde la propia máquina se incluye además el detalle de todas las interfaces, que sirve para
    diagnosticar. Desde la red se omite: enumerar interfaces y señalar cuáles son de Docker es
    reconocimiento que no necesita quien solo va a abrir el tablero.
    """
    all_ips = get_all_host_ips()
    primary_ip = determine_best_client_ip(all_ips)
    port = config.server.port

    client_host = request.client.host if request.client else ""
    is_local = client_host in config.security.loopback_hosts

    response: Dict[str, Any] = {
        "status": "online",
        "server_port": port,
        "primary_ip": primary_ip,
        "connection_helpers": {
            "web_dashboard": f"http://{primary_ip}:{port}/estacion/",
            "api_base": f"http://{primary_ip}:{port}",
            "websocket_mobile_template": f"ws://{primary_ip}:{port}/ws/mobile/{{student_id}}",
            "websocket_laptop_template": f"ws://{primary_ip}:{port}/ws/laptop/{{room_id}}"
        },
        "tips": [
            "Si tu laptop creó el Hotspot en Linux, la IP para el celular SIEMPRE es: 10.42.0.1:8000",
            "NUNCA ingreses 127.0.0.1 en el celular porque 127.0.0.1 es solo para la propia laptop.",
            "Para conectar dispositivos sin configurar IPs, usa un túnel con: cloudflared tunnel --url http://localhost:8000"
        ]
    }

    if is_local:
        response["available_ips"] = all_ips
    else:
        # Se informa de que hay más, para que quien diagnostica sepa dónde mirar.
        response["available_ips"] = [{"ip": primary_ip, "type": _label_for(primary_ip)}]
        response["detail_restricted"] = (
            "El detalle de interfaces solo se publica a peticiones desde la propia máquina."
        )

    return response

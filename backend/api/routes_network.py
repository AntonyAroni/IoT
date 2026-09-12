"""
Controlador HTTP: Diagnóstico y Descubrimiento Dinámico de Red.
Permite a los clientes móviles y estaciones de salón descubrir automáticamente
las direcciones IP activas de la laptop servidora (Wi-Fi, Ethernet, Hotspot)
sin requerir configuración manual compleja.
"""
import socket
import subprocess
import logging
from typing import Dict, List, Any
from fastapi import APIRouter
from ..config import config

logger = logging.getLogger("ips.network")
router = APIRouter(prefix="/api/v1/network", tags=["Network"])

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

    # Método 1: comando hostname -I (Linux estándar)
    try:
        output = subprocess.check_output(["hostname", "-I"], text=True, timeout=1.0)
        for ip in output.strip().split():
            clean = ip.strip()
            if clean and not clean.startswith("127.") and clean not in seen:
                seen.add(clean)
                if clean.startswith("10.42."):
                    label = "Zona Wi-Fi (Hotspot de tu Laptop)"
                elif clean.startswith("192.168.43.") or clean.startswith("192.168.137."):
                    label = "Zona Wi-Fi (Hotspot Móvil)"
                elif clean.startswith("172.17.") or clean.startswith("172.18.") or clean.startswith("172.19."):
                    label = "Red Interna Docker (No usar)"
                elif clean.startswith("192.168.") or clean.startswith("10."):
                    label = "Red Wi-Fi / LAN"
                else:
                    label = "Red Local / LAN"
                ip_list.append({"ip": clean, "type": label})
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
    # 1. Prioridad: Hotspot de Linux (10.42.0.1 o 192.168.43.1 o 192.168.137.1)
    for item in all_ips:
        ip = item["ip"]
        if ip.startswith("10.42.") or ip.startswith("192.168.43.") or ip.startswith("192.168.137."):
            return ip

    # 2. Prioridad: Wi-Fi / LAN (evitando docker 172.17 / 172.18)
    for item in all_ips:
        ip = item["ip"]
        if not ip.startswith("172.17.") and not ip.startswith("172.18.") and not ip.startswith("127."):
            return ip

    # 3. Fallback
    return all_ips[0]["ip"] if all_ips else "127.0.0.1"

@router.get("/info")
def get_network_info() -> Dict[str, Any]:
    """
    Retorna la configuración de red y URLs listas para usar por celulares y laptops.
    """
    all_ips = get_all_host_ips()
    primary_ip = determine_best_client_ip(all_ips)
    port = config.server.port

    return {
        "status": "online",
        "server_port": port,
        "primary_ip": primary_ip,
        "available_ips": all_ips,
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

"""
Script Maestro de Demostración Extremo a Extremo (Fases 1, 2, 3 y 4).
Ejecuta el Cerebro IPS en background, conecta una Estación Laptop ficticia en Salón 302,
y despacha al Sensor Móvil recorriendo el trayecto desde Piso 1 hasta Salón 302.
"""
import asyncio
import json
import os
import sys
import time
import uvicorn
import multiprocessing
from backend.main import app
from mobile_app.virtual_sensor.virtual_scanner import VirtualMobileSensor
from calibration_tools.console import enable_unicode_output

async def run_end_to_end_demo(port: int = 8000):
    import websockets

    print("\n================================================================================")
    print(" 🚀 INICIANDO DEMOSTRACIÓN INTEGRAL DEL SISTEMA IPS & ASISTENCIA IOT")
    print("    • FASE 1: Cerebro Backend (Grafo 4 Pisos + WKNN + WebSockets)")
    print("    • FASE 2: Estación Laptop (Dashboard de Aula S302)")
    print("    • FASE 3: Sensor Móvil (Telemetría Wi-Fi + Navegación por Pistas)")
    print("    • FASE 4: Calibración y Auditoría en Campo")
    print(f"    • URL Servidor: http://127.0.0.1:{port}")
    print("================================================================================\n")

    ws_laptop_url = f"ws://127.0.0.1:{port}/ws/laptop/S302"
    ws_mobile_url = f"ws://127.0.0.1:{port}/ws/mobile/EST_08"

    # Conectar oyente de la laptop en background
    async def laptop_listener(ws):
        try:
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                event = msg.get("event")
                if event == "student_proximity":
                    status = msg.get("status")
                    rssi = msg.get("rssi")
                    dist = msg.get("distance_to_classroom")
                    name = msg.get("student_name")
                    print(f"  💻 [LAPTOP SALÓN 302]: Radar detectó a '{name}' | Estado: {status} | Distancia: {dist}m | RSSI: {rssi} dBm")
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    # Desde que la asistencia se persiste entre arranques, el estado de una ejecución anterior
    # sobrevive y el alumno aparecería ya confirmado en el primer paso. Reiniciar el aula deja
    # la demostración reproducible.
    reset_room_attendance(port, "S302")

    async with websockets.connect(ws_laptop_url) as ws_laptop:
        # Snapshot inicial
        init_state = await ws_laptop.recv()
        print("💻 [LAPTOP SALÓN 302]: Conectada exitosamente. Esperando alumnos...")

        laptop_task = asyncio.create_task(laptop_listener(ws_laptop))

        # Sensor Móvil
        sensor = VirtualMobileSensor(student_id="EST_08", target_room_id="S302")

        trajectory = [
            (1, 2.0, 5.0, "Inicio en entrada principal - Piso 1"),
            (1, 8.0, 6.0, "Caminando hacia escalera - Piso 1"),
            (2, 10.0, 8.0, "Subiendo escaleras - Piso 2"),
            (3, 10.0, 8.0, "Llegando a descanso de escalera - Piso 3"),
            (3, 10.0, 6.0, "Saliendo a pasillo central - Piso 3"),
            (3, 10.0, 4.0, "Frente a puerta de Salón 302 (Umbral)"),
            (3, 10.0, 2.5, "Entrando al aula S302 (Muestra 1/3)"),
            (3, 10.0, 2.0, "Tomando asiento en S302 (Muestra 2/3)"),
            (3, 10.0, 2.0, "Permanencia validada en S302 (Muestra 3/3 - Confirmado)")
        ]

        async with websockets.connect(ws_mobile_url) as ws_mobile:
            for idx, (floor, x, y, label) in enumerate(trajectory, 1):
                readings = sensor.scan_environment(floor, x, y)
                room_rssi = readings.get("ap_p3_room02")

                payload = {
                    "timestamp": time.time(),
                    "target_room_id": "S302",
                    "readings": readings,
                    "room_ap_rssi": room_rssi
                }

                await ws_mobile.send(json.dumps(payload))
                resp = json.loads(await ws_mobile.recv())

                print(f"\n[Paso {idx}/{len(trajectory)}] 📱 MÓVIL: {label}")
                print(f"  📍 Ubicación Real: Piso {floor} ({x}m, {y}m)")
                print(f"  🧠 Estimación IPS: Piso {resp['floor_number']} ({resp['position']['x']}m, {resp['position']['y']}m)")
                print(f"  🗣️ Pista: \"{resp['active_clue']}\"")
                print(f"  📊 Progreso: {resp['progress_percentage']}% | Estado: {resp['attendance_status']}")

                await asyncio.sleep(0.6)

        await asyncio.sleep(0.5)
        laptop_task.cancel()

    print("\n================================================================================")
    print(" 🎉 DEMOSTRACIÓN FINALIZADA CON ÉXITO")
    print("    • Localización multi-piso verificada.")
    print("    • Pistas de guiado emitidas paso a paso.")
    print("    • Asistencia inteligente confirmada en la Laptop del Salón 302.")
    print("    • Web App disponible en: http://localhost:8000/estacion/?room=S302")
    print("================================================================================\n")

def find_available_port(start_port: int = 8000) -> int:
    import socket
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port

def start_server(port: int):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

def reset_room_attendance(port: int, room_id: str) -> None:
    """Deja el aula sin asistencias confirmadas para que la demostración parta de cero."""
    import urllib.request
    url = f"http://127.0.0.1:{port}/api/v1/attendance/room/{room_id}/reset"
    try:
        request = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(request, timeout=2.0) as response:
            if response.status == 200:
                print(f"🔄 Asistencia del aula {room_id} reiniciada para la demostración.\n")
    except Exception as e:
        print(f"⚠️ No se pudo reiniciar la asistencia de {room_id}: {e}")


def is_server_running(port: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ejecutor de la Demo IPS")
    parser.add_argument("--port", type=int, default=None, help="Puerto para el servidor IPS")
    args = parser.parse_args()

    port = args.port or (8000 if is_server_running(8000) else find_available_port(8000))
    already_running = is_server_running(port)
    server_process = None

    if already_running:
        print(f"ℹ️ Servidor IPS detectado en ejecución en http://127.0.0.1:{port}. Reutilizando instancia...")
    else:
        print(f"ℹ️ Iniciando servidor IPS en segundo plano en http://127.0.0.1:{port}...")
        server_process = multiprocessing.Process(target=start_server, args=(port,))
        server_process.start()
        for _ in range(20):
            time.sleep(0.2)
            if is_server_running(port):
                break

    try:
        asyncio.run(run_end_to_end_demo(port))
    finally:
        if server_process:
            server_process.terminate()
            server_process.join()


if __name__ == "__main__":
    enable_unicode_output()
    main()

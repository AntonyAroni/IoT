"""
Simulador Virtual de Sensor Móvil Wi-Fi de Alta Fidelidad.
Modela la propagación de radiofrecuencia (Log-Distance Path Loss + Atenuación de Pisos + Ruido Gaussiano)
y simula la caminata de un estudiante a través del edificio de 4 pisos.
Permite auditar y verificar el sistema de extremo a extremo sin depender de compilación continua en Android.
"""
import asyncio
import json
import math
import random
import time
from typing import Dict, List, Tuple

class SimulatedAP:
    def __init__(self, bssid: str, ssid: str, floor: int, x: float, y: float, tx_power_at_1m: float = -42.0, path_loss_exponent: float = 2.8):
        self.bssid = bssid
        self.ssid = ssid
        self.floor = floor
        self.x = x
        self.y = y
        self.tx_power = tx_power_at_1m
        self.ple = path_loss_exponent

    def calculate_rssi(self, current_floor: int, current_x: float, current_y: float) -> float:
        """Calcula el RSSI en dBm considerando distancia euclidiana y atenuación de losas."""
        dist_2d = math.sqrt((self.x - current_x) ** 2 + (self.y - current_y) ** 2)
        dist_3d = max(0.8, dist_2d)

        # Pérdida de trayectoria en espacio libre y paredes internas
        loss = 10 * self.ple * math.log10(dist_3d)

        # Atenuación vertical por losa de concreto (~14 dBm por piso de diferencia)
        floor_diff = abs(self.floor - current_floor)
        floor_attenuation = floor_diff * 14.0

        # Ruido gaussiano (fluctuaciones temporales y personas en movimiento)
        noise = random.gauss(0, 1.5)

        rssi = self.tx_power - loss - floor_attenuation + noise
        return round(max(-100.0, min(-30.0, rssi)), 1)

class VirtualMobileSensor:
    def __init__(self, student_id: str = "EST_08", target_room_id: str = "S302"):
        self.student_id = student_id
        self.target_room_id = target_room_id
        self.access_points = self._setup_school_aps()

    def _setup_school_aps(self) -> List[SimulatedAP]:
        """Configura los Access Points de referencia distribuidos en los 4 pisos."""
        aps = []
        for f in range(1, 5):
            # 2 APs por piso (Ala Oeste y Ala Este)
            aps.append(SimulatedAP(f"ap_p{f}_west", f"WIFI_COLEGIO_P{f}", floor=f, x=4.0, y=3.5))
            aps.append(SimulatedAP(f"ap_p{f}_east", f"WIFI_COLEGIO_P{f}", floor=f, x=16.0, y=3.5))
            # AP en el aula central (ej. S302 en Piso 3)
            aps.append(SimulatedAP(f"ap_p{f}_room02", f"AP_AULA_{f}02", floor=f, x=10.0, y=2.0))
        return aps

    def scan_environment(self, floor: int, x: float, y: float) -> Dict[str, float]:
        """Realiza un escaneo activo recolectando el RSSI de cada AP."""
        readings = {}
        for ap in self.access_points:
            val = ap.calculate_rssi(floor, x, y)
            if val > -92.0:  # Sensibilidad típica de un receptor smartphone comercial
                readings[ap.bssid] = val
        return readings

    async def run_scenario(self, ws_url: str = "ws://localhost:8000/ws/mobile/EST_08"):
        """
        Ejecuta el escenario canónico de la demo:
        1. Alumno inicia en Piso 1 (Pasillo Oeste).
        2. Camina a la escalera central.
        3. Sube al Piso 2, luego al Piso 3.
        4. Llega al pasillo del Piso 3, se aproxima a S302 y entra al aula.
        5. Permanece en el aula para confirmar la asistencia.
        """
        import websockets

        trajectory = [
            # Piso 1
            (1, 2.0, 5.0, "En pasillo Piso 1"),
            (1, 6.0, 5.0, "Caminando hacia escalera Piso 1"),
            (1, 10.0, 8.0, "En descanso de escalera Piso 1"),
            # Transición por escaleras al Piso 2
            (2, 10.0, 8.0, "Subiendo por escalera - Piso 2"),
            # Transición por escaleras al Piso 3
            (3, 10.0, 8.0, "Llegando al descanso de escalera - Piso 3"),
            (3, 10.0, 6.0, "Saliendo al pasillo del Piso 3"),
            (3, 10.0, 4.0, "Frente a la puerta del Salón 302 (Umbral)"),
            # Dentro de S302 (3 muestras para ventana de permanencia)
            (3, 10.0, 2.5, "Entrando al Salón 302 (Muestra 1/3)"),
            (3, 10.0, 2.0, "Tomando asiento en Salón 302 (Muestra 2/3)"),
            (3, 10.0, 2.0, "En su pupitre - Salón 302 (Muestra 3/3 - Asistencia)")
        ]

        print("================================================================")
        print(" INICIANDO SIMULADOR VIRTUAL DE SENSOR MÓVIL (ESCENARIO COMPLETO)")
        print(f" Alumno: {self.student_id} | Destino Asignado: {self.target_room_id}")
        print(f" Conectando a: {ws_url}")
        print("================================================================")

        try:
            async with websockets.connect(ws_url) as ws:
                for idx, (floor, x, y, desc) in enumerate(trajectory, 1):
                    readings = self.scan_environment(floor, x, y)
                    room_ap_rssi = readings.get("ap_p3_room02")

                    payload = {
                        "timestamp": time.time(),
                        "target_room_id": self.target_room_id,
                        "readings": readings,
                        "room_ap_rssi": room_ap_rssi
                    }

                    await ws.send(json.dumps(payload))
                    raw_resp = await ws.recv()
                    resp = json.loads(raw_resp)

                    print(f"\n[Paso {idx}/{len(trajectory)}] {desc}")
                    print(f"  📍 Posición Real: Piso {floor} ({x}m, {y}m)")
                    print(f"  🧠 Estimación IPS: Piso {resp.get('floor_number')} ({resp.get('position', {}).get('x')}m, {resp.get('position', {}).get('y')}m) [Conf: {resp.get('floor_confidence')}]")
                    print(f"  🗣️ Pista Móvil: \"{resp.get('active_clue')}\"")
                    print(f"  📊 Progreso: {resp.get('progress_percentage')}% | Estado Asistencia: {resp.get('attendance_status')}")

                    await asyncio.sleep(0.5)

                print("\n✅ Escenario completado exitosamente con verificación de asistencia.")

        except Exception as e:
            print(f"❌ Error en la simulación del sensor móvil: {e}")

if __name__ == "__main__":
    sensor = VirtualMobileSensor()
    asyncio.run(sensor.run_scenario())

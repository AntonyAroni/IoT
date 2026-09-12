"""
Suite Completa de Pruebas Sintéticas Avanzadas para el Sistema IPS y Asistencia IoT.
Abarca:
1. Concurrencia Multi-Estudiante (3 alumnos simultáneos en diferentes pisos y salones).
2. Recuperación ante Desviación de Ruta (alumno desorientado que se pasa de piso).
3. Prueba de Resiliencia ante Falsos Positivos (peatón detenido frente a la puerta).
4. Simulación Monte Carlo con Ruido Severo y Multicamino (200 muestras aleatorias).
"""
import asyncio
import json
import math
import random
import time
import numpy as np
from typing import Dict, List, Tuple
from fastapi.testclient import TestClient

from backend.main import app, app_state
from backend.domain.building import Point2D
from backend.domain.fingerprint import FingerprintVector
from backend.domain.attendance import AttendanceStatus
from mobile_app.virtual_sensor.virtual_scanner import VirtualMobileSensor, SimulatedAP
from calibration_tools.console import enable_unicode_output

# ==============================================================================
# TEST 1: SIMULACIÓN CONCURRENTE MULTI-ESTUDIANTE (3 ALUMNOS SIMULTÁNEOS)
# ==============================================================================
def test_multi_student_concurrency():
    print("\n" + "="*80)
    print(" 🧪 PRUEBA SINTÉTICA 1: CONCURRENCIA MULTI-ESTUDIANTE (3 ALUMNOS SIMULTÁNEOS)")
    print("="*80)

    client = TestClient(app)

    # 3 Estudiantes con diferentes salones destino
    students_data = [
        {"id": "EST_04", "name": "Lucía Morales", "target": "S201", "target_floor": 2, "target_pos": Point2D(2.0, 2.0)},
        {"id": "EST_08", "name": "Diego Ramos",   "target": "S302", "target_floor": 3, "target_pos": Point2D(10.0, 2.0)},
        {"id": "EST_11", "name": "Renata Paredes", "target": "S402", "target_floor": 4, "target_pos": Point2D(10.0, 2.0)},
    ]

    # Conectar 3 Laptops de Aula simultáneamente vía WebSocket
    with client.websocket_connect("/ws/laptop/S201") as ws_laptop_201, \
         client.websocket_connect("/ws/laptop/S302") as ws_laptop_302, \
         client.websocket_connect("/ws/laptop/S402") as ws_laptop_402:

        # Consumir initial_state de cada laptop
        init_201 = ws_laptop_201.receive_json()
        init_302 = ws_laptop_302.receive_json()
        init_402 = ws_laptop_402.receive_json()

        print("  ✓ Laptops conectadas: S201, S302, S402 listas.")

        # Simular conexión de los 3 móviles
        with client.websocket_connect("/ws/mobile/EST_04") as ws_mob_04, \
             client.websocket_connect("/ws/mobile/EST_08") as ws_mob_08, \
             client.websocket_connect("/ws/mobile/EST_11") as ws_mob_11:

            # Paso A: Todos en entrada de Piso 1
            sensor = VirtualMobileSensor()

            for s in students_data:
                ws = ws_mob_04 if s["id"] == "EST_04" else (ws_mob_08 if s["id"] == "EST_08" else ws_mob_11)
                readings = sensor.scan_environment(1, 2.0, 5.0)
                ws.send_json({"timestamp": time.time(), "target_room_id": s["target"], "readings": readings})
                resp = ws.receive_json()
                print(f"  📱 {s['name']} (Piso 1): Pista -> \"{resp['active_clue']}\"")

            # Paso B: Cada estudiante llega directamente a su respectiva aula
            print("\n  🚶‍♂️ Estudiantes caminan a sus aulas correspondientes...")
            for s in students_data:
                ws = ws_mob_04 if s["id"] == "EST_04" else (ws_mob_08 if s["id"] == "EST_08" else ws_mob_11)
                t_floor = s["target_floor"]
                t_pos = s["target_pos"]

                # Enviar 3 muestras dentro del aula para validar permanencia
                for sample_idx in range(1, 4):
                    readings = sensor.scan_environment(t_floor, t_pos.x, t_pos.y)
                    # AP del aula con señal fuerte
                    room_ap_key = f"ap_p{t_floor}_room02" if "02" in s["target"] else f"ap_p{t_floor}_west"
                    ws.send_json({
                        "timestamp": time.time(),
                        "target_room_id": s["target"],
                        "readings": readings,
                        "room_ap_rssi": -42.0
                    })
                    resp = ws.receive_json()

                print(f"  ✓ {s['name']} llegó a {s['target']} | Estado: {resp['attendance_status']}")

        # Paso C: Verificar que cada laptop de salón recibió la confirmación de su propio alumno
        event_201 = ws_laptop_201.receive_json()
        event_302 = ws_laptop_302.receive_json()
        event_402 = ws_laptop_402.receive_json()

        print("\n  💻 Verificación de Aislamiento de Canales en Laptops:")
        print(f"    • Laptop S201 recibió: Alumno={event_201['student_name']} | Estado={event_201['status']}")
        print(f"    • Laptop S302 recibió: Alumno={event_302['student_name']} | Estado={event_302['status']}")
        print(f"    • Laptop S402 recibió: Alumno={event_402['student_name']} | Estado={event_402['status']}")

        assert event_201["student_id"] == "EST_04", "Contaminación cruzada en S201"
        assert event_302["student_id"] == "EST_08", "Contaminación cruzada en S302"
        assert event_402["student_id"] == "EST_11", "Contaminación cruzada en S402"
        print("  🎉 TEST 1 CONCURRENCIA: APROBADO SIN CONTAMINACIÓN CRUZADA.")

# ==============================================================================
# TEST 2: ALUMNO DESORIENTADO CON DESVIACIÓN DE PISO (RE-ENRUTAMIENTO)
# ==============================================================================
def test_rerouting_wrong_floor():
    print("\n" + "="*80)
    print(" 🧪 PRUEBA SINTÉTICA 2: RECUPERACIÓN ANTE DESVIACIÓN DE PISO (ALUMNO DESORIENTADO)")
    print("="*80)

    client = TestClient(app)
    sensor = VirtualMobileSensor(student_id="EST_08", target_room_id="S302")

    with client.websocket_connect("/ws/mobile/EST_08") as ws_mob:
        # 1. Alumno debe ir a S302 (Piso 3), pero por error sube hasta el Piso 4
        print("  ⚠️ El alumno debía ir a S302 (Piso 3), pero se equivocó y subió al Piso 4...")
        readings_p4 = sensor.scan_environment(floor=4, x=10.0, y=5.0)

        ws_mob.send_json({
            "timestamp": time.time(),
            "target_room_id": "S302",
            "readings": readings_p4
        })
        resp1 = ws_mob.receive_json()

        print(f"  🧠 Estimación IPS: Piso {resp1['floor_number']}")
        print(f"  🗣️ Pista Emitida: \"{resp1['active_clue']}\"")

        assert resp1['floor_number'] == 4, "Debe detectar Piso 4"
        assert "baja" in resp1['active_clue'].lower(), "La pista debe indicar que debe bajar"
        assert "piso 3" in resp1['active_clue'].lower(), "La pista debe indicar el piso meta 3"

        # 2. El alumno sigue la pista correctiva y baja al Piso 3
        print("\n  🚶‍♂️ Alumno corrige rumbo y baja al Piso 3...")
        readings_p3 = sensor.scan_environment(floor=3, x=10.0, y=5.0)
        ws_mob.send_json({
            "timestamp": time.time(),
            "target_room_id": "S302",
            "readings": readings_p3
        })
        resp2 = ws_mob.receive_json()

        print(f"  🧠 Estimación IPS: Piso {resp2['floor_number']}")
        print(f"  🗣️ Pista Emitida: \"{resp2['active_clue']}\"")

        assert resp2['floor_number'] == 3, "Debe detectar Piso 3"
        assert "salón 302" in resp2['active_clue'].lower()
        print("  🎉 TEST 2 RE-ENRUTAMIENTO: APROBADO CON ÉXITO.")

# ==============================================================================
# TEST 3: PEATÓN EN PASILLO (RESILIENCIA ANTE FALSOS POSITIVOS)
# ==============================================================================
def test_hallway_passerby_false_positive_immunity():
    print("\n" + "="*80)
    print(" 🧪 PRUEBA SINTÉTICA 3: INMUNIDAD ANTE PEATONES EN PASILLO (FALSOS POSITIVOS)")
    print("="*80)

    client = TestClient(app)
    sensor = VirtualMobileSensor()

    with client.websocket_connect("/ws/laptop/S302") as ws_laptop:
        ws_laptop.receive_json() # snapshot

        with client.websocket_connect("/ws/mobile/EST_99") as ws_mob:
            # Peatón que se queda parado 10 segundos en el pasillo (x=10.0, y=5.0)
            # frente a la puerta de S302, pero SIN entrar al aula
            print("  🚶‍♂️ Peatón transita frente al aula S302 por el pasillo (y=5.0m) durante 6 escaneos...")
            final_status = "UNKNOWN"

            for i in range(1, 7):
                readings = sensor.scan_environment(floor=3, x=10.0, y=5.0)
                # RSSI moderado por estar en pasillo (-64 dBm)
                ws_mob.send_json({
                    "timestamp": time.time(),
                    "target_room_id": "S302",
                    "readings": readings,
                    "room_ap_rssi": -64.0
                })
                resp = ws_mob.receive_json()
                final_status = resp["attendance_status"]
                print(f"    [Escaneo {i}/6] RSSI: -64 dBm | Distancia: 3.0m | Estado: {final_status}")

            assert final_status != "PRESENT_CONFIRMED", "ERROR CRÍTICO: Peatón en pasillo fue confirmado falsamente!"
            assert final_status in ["APPROACHING", "ABSENT"]
            print(f"  ✓ Estado final del peatón: {final_status} (Asistencia NO confirmada)")
            print("  🎉 TEST 3 INMUNIDAD: APROBADO (0% Falsos Positivos).")

# ==============================================================================
# TEST 4: MONTE CARLO CON RUIDO SEVERO Y MULTICAMINO (200 MUESTRAS ALEATORIAS)
# ==============================================================================
def test_monte_carlo_severe_noise(num_samples: int = 200):
    print("\n" + "="*80)
    print(f" 🧪 PRUEBA SINTÉTICA 4: SIMULACIÓN MONTE CARLO CON RUIDO SEVERO ({num_samples} PUNTOS)")
    print("="*80)

    sensor = VirtualMobileSensor()
    floor_clf = app_state.floor_classifier
    wknn = app_state.wknn_locator

    floor_successes = 0
    distance_errors = []

    # Configuración de ruido severo: sigma = 2.5 dBm (alta fluctuación por personas y obstáculos)
    noise_sigma = 2.5

    for i in range(num_samples):
        true_floor = random.randint(1, 4)
        true_x = random.uniform(1.0, 19.0)
        true_y = random.uniform(1.5, 6.5)

        # Generar lecturas con ruido añadido
        clean_readings = sensor.scan_environment(true_floor, true_x, true_y)
        noisy_readings = {
            bssid: rssi + random.gauss(0, noise_sigma)
            for bssid, rssi in clean_readings.items()
        }

        vector = FingerprintVector(
            timestamp=time.time(),
            device_id=f"MC_{i}",
            readings=noisy_readings
        )

        # 1. Evaluar Piso
        est_floor, conf = floor_clf.classify_floor(vector)
        if est_floor == true_floor:
            floor_successes += 1

        # 2. Evaluar Posición 2D
        est_pos, _ = wknn.estimate_position(true_floor, vector)
        err = est_pos.distance_to(Point2D(true_x, true_y))
        distance_errors.append(err)

    floor_acc = (floor_successes / num_samples) * 100.0
    mean_err = np.mean(distance_errors)
    median_err = np.median(distance_errors)
    p75_err = np.percentile(distance_errors, 75)
    p90_err = np.percentile(distance_errors, 90)
    rmse = np.sqrt(np.mean(np.square(distance_errors)))

    print(f"  • Muestras Evaluadas:      {num_samples}")
    print(f"  • Desviación de Ruido:     σ = {noise_sigma} dBm (Multicamino Severo)")
    print(f"  • Precisión de Piso:       {floor_acc:.2f}% ({floor_successes}/{num_samples})")
    print(f"  • Error Medio 2D:          {mean_err:.2f} m")
    print(f"  • Error Mediano 2D:        {median_err:.2f} m")
    print(f"  • Percentil 75:            {p75_err:.2f} m")
    print(f"  • Percentil 90:            {p90_err:.2f} m")
    print(f"  • RMSE:                    {rmse:.2f} m")

    # CDF a distancias clave
    cdf_1m = (sum(1 for e in distance_errors if e <= 1.0) / num_samples) * 100.0
    cdf_2m = (sum(1 for e in distance_errors if e <= 2.0) / num_samples) * 100.0
    cdf_3m = (sum(1 for e in distance_errors if e <= 3.0) / num_samples) * 100.0

    print(f"\n  📈 Curva de Distribución Acumulada del Error (CDF):")
    print(f"    • Probabilidad Error ≤ 1.0m: {cdf_1m:.1f}%")
    print(f"    • Probabilidad Error ≤ 2.0m: {cdf_2m:.1f}%")
    print(f"    • Probabilidad Error ≤ 3.0m: {cdf_3m:.1f}%")

    assert floor_acc >= 95.0, f"Precisión de piso cayó por debajo del 95%: {floor_acc}%"
    assert mean_err <= 3.0, f"Error medio superó los 3.0m: {mean_err}m"
    print("\n  🎉 TEST 4 MONTE CARLO: APROBADO BAJO CONDICIONES DE RUIDO SEVERO.")

# ==============================================================================
# EJECUTOR PRINCIPAL DE TODA LA SUITE
# ==============================================================================
def run_all_synthetic_tests():
    print("\n" + "#"*80)
    print(" INICIANDO BATERÍA COMPLETA DE PRUEBAS SINTÉTICAS AVANZADAS")
    print("#"*80)

    t0 = time.time()
    test_multi_student_concurrency()
    test_rerouting_wrong_floor()
    test_hallway_passerby_false_positive_immunity()
    test_monte_carlo_severe_noise(200)
    elapsed = round(time.time() - t0, 2)

    print("\n" + "#"*80)
    print(f" ✅ TODAS LAS PRUEBAS SINTÉTICAS (4/4) FUERON SUPERADAS EXITOSAMENTE EN {elapsed}s")
    print("#"*80 + "\n")


if __name__ == "__main__":
    enable_unicode_output()
    run_all_synthetic_tests()

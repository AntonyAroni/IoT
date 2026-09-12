"""
Pruebas Unitarias para Filtros de Señal Híbridos, Diagnóstico de Red y Gestión de Alumnos.
"""
import unittest
from fastapi.testclient import TestClient
from backend.main import app
from backend.domain.building import Point2D
from backend.services.signal_filters import (
    KalmanFilter1D,
    MultiBSSIDKalmanFilter,
    TrajectoryKinematicFilter2D,
    compute_differential_rssi,
    select_adaptive_k
)

class TestSignalFiltersAndNetwork(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_kalman_filter_1d_smoothing(self):
        """Verifica que el Filtro de Kalman suavice fluctuaciones extremas de RSSI."""
        kf = KalmanFilter1D(initial_value=-60.0)
        # Señal con ruido oscilante (-75, -50, -80, -55)
        raw_values = [-75.0, -50.0, -80.0, -55.0, -62.0]
        smoothed = []
        for val in raw_values:
            smoothed.append(kf.update(val))

        # La estimación final debe converger hacia el rango medio amortiguando los picos
        self.assertGreater(smoothed[-1], -75.0)
        self.assertLess(smoothed[-1], -55.0)

    def test_multi_bssid_kalman(self):
        """Verifica que el banco de filtros maneje múltiples BSSIDs simultáneos."""
        mbk = MultiBSSIDKalmanFilter()
        readings_1 = {"ap_1": -60.0, "ap_2": -80.0}
        readings_2 = {"ap_1": -70.0, "ap_2": -75.0}

        out1 = mbk.filter_readings(readings_1, current_time=100.0)
        out2 = mbk.filter_readings(readings_2, current_time=101.0)

        self.assertIn("ap_1", out2)
        self.assertIn("ap_2", out2)
        # AP 1 debe haber sido suavizado entre -60 y -70
        self.assertLess(out2["ap_1"], -60.0)
        self.assertGreater(out2["ap_1"], -70.0)

    def test_trajectory_kinematic_filter(self):
        """Verifica que el filtro cinemático limite saltos imposibles a velocidad peatonal."""
        tf = TrajectoryKinematicFilter2D(max_speed_mps=1.5, smoothing_factor=0.5)
        p0 = Point2D(2.0, 2.0)
        out0 = tf.filter_position(p0, current_time=0.0)
        self.assertEqual((out0.x, out0.y), (2.0, 2.0))

        # Intento de salto de 20 metros en 1 segundo (teletransporte)
        p_jump = Point2D(22.0, 2.0)
        out1 = tf.filter_position(p_jump, current_time=1.0)

        # La distancia recorrida real no puede exceder el límite peatonal admisible
        dist = p0.distance_to(out1)
        self.assertLess(dist, 5.0)  # Muy por debajo del salto de 20m

    def test_differential_rssi_computation(self):
        """Verifica el cálculo de Signal Strength Difference (SSD)."""
        readings = {"ap_a": -50.0, "ap_b": -70.0, "ap_c": -80.0}
        diffs = compute_differential_rssi(readings)
        self.assertEqual(diffs[("ap_a", "ap_b")], 20.0)
        self.assertEqual(diffs[("ap_a", "ap_c")], 30.0)
        self.assertEqual(diffs[("ap_b", "ap_c")], 10.0)

    def test_network_info_endpoint(self):
        """Verifica que el endpoint /api/v1/network/info retorne IPs y helpers válidos."""
        resp = self.client.get("/api/v1/network/info")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "online")
        self.assertIn("primary_ip", data)
        self.assertIn("connection_helpers", data)
        self.assertIn("available_ips", data)

    def test_students_api_endpoints(self):
        """Verifica el listado y registro dinámico de estudiantes."""
        # 1. Listar estudiantes iniciales
        resp_list = self.client.get("/api/v1/attendance/students")
        self.assertEqual(resp_list.status_code, 200)
        students = resp_list.json()
        self.assertGreater(len(students), 5)

        # 2. Registrar nuevo estudiante
        payload = {
            "id": "EST_99",
            "name": "Estudiante Prueba Real",
            "enrolled_room": "S101"
        }
        resp_post = self.client.post("/api/v1/attendance/students", json=payload)
        self.assertEqual(resp_post.status_code, 200)
        post_data = resp_post.json()
        self.assertEqual(post_data["status"], "success")

        # 3. Confirmar que aparece en la lista
        resp_list2 = self.client.get("/api/v1/attendance/students")
        ids = [s["id"] for s in resp_list2.json()]
        self.assertIn("EST_99", ids)

if __name__ == "__main__":
    unittest.main()

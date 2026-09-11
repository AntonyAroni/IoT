"""
Pruebas Unitarias de Verificación: Algoritmo WKNN y Aislamiento de Piso.
Audita la precisión del posicionamiento en 2D y la robustez del clasificador jerárquico.
"""
import unittest
import time
from backend.domain.building import Point2D
from backend.domain.fingerprint import ReferencePoint, RadioMapEntry, FingerprintVector
from backend.repositories.radio_map_repo import InMemoryRadioMapRepository
from backend.services.floor_classifier import FloorClassifierService
from backend.services.wknn_locator import WKNNPositioningService
from backend.config import WKNNConfig

class TestWKNNPositioning(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRadioMapRepository()
        self.config = WKNNConfig(k=3, epsilon=1e-5)
        self.floor_clf = FloorClassifierService(self.repo)
        self.wknn = WKNNPositioningService(self.repo, self.config)

        # Crear Puntos de Referencia Sintéticos calibrados
        # Piso 1: 3 puntos en pasillo
        self._add_rp("RP_P1_01", floor=1, x=2.0, y=5.0, rssi={"ap_p1_a": -45.0, "ap_p1_b": -60.0, "ap_p2_a": -80.0})
        self._add_rp("RP_P1_02", floor=1, x=10.0, y=5.0, rssi={"ap_p1_a": -60.0, "ap_p1_b": -45.0, "ap_p2_a": -75.0})
        self._add_rp("RP_P1_03", floor=1, x=18.0, y=5.0, rssi={"ap_p1_a": -75.0, "ap_p1_b": -55.0, "ap_p2_a": -85.0})

        # Piso 3: 3 puntos (Salón 302 y alrededores)
        self._add_rp("RP_P3_S301", floor=3, x=2.0, y=2.0, rssi={"ap_p3_a": -42.0, "ap_p3_b": -70.0, "ap_p1_a": -95.0})
        self._add_rp("RP_P3_S302", floor=3, x=10.0, y=2.0, rssi={"ap_p3_a": -65.0, "ap_p3_b": -40.0, "ap_p1_a": -98.0})
        self._add_rp("RP_P3_S303", floor=3, x=18.0, y=2.0, rssi={"ap_p3_a": -80.0, "ap_p3_b": -55.0, "ap_p1_a": -100.0})

    def _add_rp(self, rp_id: str, floor: int, x: float, y: float, rssi: dict):
        rp = ReferencePoint(id=rp_id, floor_number=floor, position=Point2D(x=x, y=y), label=rp_id)
        entry = RadioMapEntry(reference_point=rp, rssi_means=rssi, sample_count=15)
        self.repo.save_entry(entry)

    def test_floor_isolation_accuracy(self):
        """Verifica que el clasificador jerárquico aísle el piso correcto (Piso 3 vs Piso 1)."""
        # Vector tomado en piso 3 (fuerte señal de APs del piso 3)
        vector_p3 = FingerprintVector(
            timestamp=time.time(),
            device_id="TEST_DEV",
            readings={"ap_p3_b": -42.0, "ap_p3_a": -64.0, "ap_p1_a": -95.0}
        )
        detected_floor, confidence = self.floor_clf.classify_floor(vector_p3)
        self.assertEqual(detected_floor, 3)
        self.assertGreaterEqual(confidence, 0.5)

    def test_wknn_coordinate_estimation(self):
        """
        Verifica que WKNN aproxime con precisión la coordenada (x, y).
        Vector de prueba muy similar a RP_P3_S302 (x=10.0, y=2.0).
        """
        vector_s302 = FingerprintVector(
            timestamp=time.time(),
            device_id="TEST_DEV",
            readings={"ap_p3_a": -64.5, "ap_p3_b": -41.0, "ap_p1_a": -97.0}
        )
        est_pos, neighbors = self.wknn.estimate_position(floor_number=3, vector=vector_s302)
        
        # El error respecto a (10.0, 2.0) debe ser menor a 1.5 metros
        true_pos = Point2D(x=10.0, y=2.0)
        error_distance = est_pos.distance_to(true_pos)
        self.assertLess(error_distance, 1.5, f"Error de distancia ({error_distance}m) superó el umbral de 1.5m")

if __name__ == "__main__":
    unittest.main()

"""
Pruebas de Mapeo Dinámico de Aulas y Sincronización con Puntos de Calibración.
"""
import unittest
from fastapi.testclient import TestClient
from backend.main import app, app_state
from backend.domain.building import Point2D
from backend.domain.graph import infer_room_id
from backend.tests.helpers import IsolatedAppStateMixin


class TestRoomMapping(IsolatedAppStateMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app, client=("127.0.0.1", 50000))

    def test_infer_room_id(self):
        """Verifica la inferencia de IDs de aula desde etiquetas o nombres de RPs."""
        self.assertEqual(infer_room_id("RP_P3_303", 3), "S303")
        self.assertEqual(infer_room_id("RP_S302_Center", 3), "S302")
        self.assertEqual(infer_room_id("RP_P1_101", 1), "S101")
        self.assertEqual(infer_room_id("303", 3), "S303")
        self.assertEqual(infer_room_id("Punto Calibrado RP_P3_303 (0.1m, 0.1m)", 3), "S303")
        self.assertEqual(infer_room_id("RP_PASILLO_1", 1), None)

    def test_get_and_update_room_position(self):
        """Verifica la consulta y actualización de coordenadas de un aula."""
        # 1. Obtener detalles iniciales
        res = self.client.get("/api/v1/building/room/S303")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], "S303")
        self.assertEqual(data["floor_number"], 3)

        # 2. Actualizar posición del centro / laptop
        update_payload = {
            "center_x": 0.1,
            "center_y": 0.1,
            "entrance_x": 0.5,
            "entrance_y": 0.5
        }
        res_put = self.client.put("/api/v1/building/room/S303/position", json=update_payload)
        self.assertEqual(res_put.status_code, 200)
        res_data = res_put.json()
        self.assertEqual(res_data["room"]["center"], {"x": 0.1, "y": 0.1})
        self.assertEqual(res_data["room"]["entrance"], {"x": 0.5, "y": 0.5})

        # 3. Comprobar que el grafo topológico refleja la nueva coordenada
        node = app_state.graph.get_node("S303")
        self.assertIsNotNone(node)
        self.assertEqual(node.position, Point2D(0.1, 0.1))

    def test_calibration_record_auto_syncs_room_position(self):
        """Al subir una huella de calibración asociada a un aula, el aula se sincroniza en caliente."""
        payload = {
            "rp_id": "RP_P3_303",
            "floor_number": 3,
            "x": 0.15,
            "y": 0.15,
            "label": "Punto Calibrado RP_P3_303 (0.15m, 0.15m)",
            "rssi_means": {"ap_01": -45.0},
            "sample_count": 15
        }
        res = self.client.post("/api/v1/calibration/record", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["room_id"], "S303")

        # Verificar que el nodo en el grafo y el aula en el piso tienen (0.15, 0.15)
        node = app_state.graph.get_node("S303")
        self.assertEqual(node.position.x, 0.15)
        self.assertEqual(node.position.y, 0.15)

    def test_assign_room_position_from_existing_rp(self):
        """Permite asignar las coordenadas de un RP existente como centro del aula."""
        # 1. Grabar un RP
        self.client.post("/api/v1/calibration/record", json={
            "rp_id": "RP_MESA_PROFESOR",
            "floor_number": 3,
            "x": 1.25,
            "y": 2.50,
            "label": "Mesa Laptop Profesor",
            "rssi_means": {"ap_01": -50.0},
        })

        # 2. Vincularlo al aula S303
        res = self.client.put("/api/v1/building/room/S303/position", json={
            "from_rp_id": "RP_MESA_PROFESOR",
            "rp_role": "center"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["room"]["center"], {"x": 1.25, "y": 2.50})

        # El RP ahora debe tener room_id = S303
        entry = app_state.radio_map_repo.get_entry("RP_MESA_PROFESOR")
        self.assertEqual(entry.reference_point.room_id, "S303")


if __name__ == "__main__":
    unittest.main()

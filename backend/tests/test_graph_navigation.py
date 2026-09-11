"""
Pruebas Unitarias de Verificación: Grafo Topológico de 4 Pisos y Dijkstra.
Audita la navegación vertical por escaleras y la generación de pistas.
"""
import unittest
from backend.domain.building import Point2D
from backend.domain.graph import create_default_school_graph
from backend.services.navigation_engine import NavigationEngine

class TestBuildingGraphNavigation(unittest.TestCase):
    def setUp(self):
        self.graph, self.floors = create_default_school_graph()
        self.engine = NavigationEngine(self.graph, self.floors)

    def test_building_structure(self):
        """Verifica que el edificio tenga 4 pisos y 12 salones creados correctamente."""
        self.assertEqual(len(self.floors), 4)
        total_rooms = sum(len(f.rooms) for f in self.floors.values())
        self.assertEqual(total_rooms, 12)

        # Verificar presencia de nodos de escalera
        for floor_num in range(1, 5):
            stair_node = self.graph.get_node(f"Escalera_P{floor_num}")
            self.assertIsNotNone(stair_node)

    def test_same_floor_path(self):
        """Verifica la ruta entre salones del mismo piso (S101 -> S103)."""
        path, distance = self.graph.find_shortest_path("S101", "S103")
        expected_path = ["S101", "P1_Hall_West", "P1_Hall_Center", "P1_Hall_East", "S103"]
        self.assertEqual(path, expected_path)
        self.assertGreater(distance, 0.0)

    def test_multi_floor_navigation_p1_to_p3(self):
        """
        Audita el tránsito vertical obligatorio por escaleras:
        Origen: Salón 101 (Piso 1) -> Destino: Salón 302 (Piso 3).
        Debe obligatoriamente cruzar Escalera_P1, Escalera_P2 y Escalera_P3.
        """
        path, distance = self.graph.find_shortest_path("S101", "S302")
        self.assertIn("Escalera_P1", path)
        self.assertIn("Escalera_P2", path)
        self.assertIn("Escalera_P3", path)
        self.assertEqual(path[-1], "S302")

    def test_clue_generation_different_floors(self):
        """Verifica que la pista activa instruya subir escaleras si está en un piso inferior."""
        current_pos = Point2D(x=2.0, y=5.0)  # Cerca a P1_Hall_West
        route = self.engine.compute_route(current_floor=1, current_pos=current_pos, target_room_id="S302")
        
        self.assertEqual(route.current_floor, 1)
        self.assertEqual(route.target_floor, 3)
        self.assertFalse(route.has_arrived)
        self.assertIn("sube", route.active_clue.lower())
        self.assertIn("piso 3", route.active_clue.lower())

    def test_clue_generation_arrival(self):
        """Verifica que al estar a menos de 2.5m del salón meta, se active la pista de llegada."""
        target_pos = Point2D(x=10.0, y=2.0)  # Centro de S302
        route = self.engine.compute_route(current_floor=3, current_pos=target_pos, target_room_id="S302")
        
        self.assertTrue(route.has_arrived)
        self.assertEqual(route.progress_percentage, 100.0)
        self.assertIn("has llegado", route.active_clue.lower())

if __name__ == "__main__":
    unittest.main()

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

    def test_staircase_instruction_names_the_floor(self):
        """
        La instrucción de escalera debe nombrar el piso destino, no el ID del nodo.

        Antes interpolaba `path_ids[i+1]`, produciendo "Usar escalera hacia el Piso Escalera_P2".
        """
        route = self.engine.compute_route(1, Point2D(2.0, 5.0), "S302")
        stair_steps = [s for s in route.steps if s.is_vertical]

        self.assertTrue(stair_steps, "La ruta de P1 a P3 debe incluir tramos verticales")
        for step in stair_steps:
            self.assertNotIn(
                "Escalera_P", step.instruction,
                f"La instrucción filtra el ID del nodo: {step.instruction!r}"
            )
            self.assertRegex(step.instruction, r"Piso \d+$")

        self.assertEqual(stair_steps[0].instruction, "Subir por la escalera al Piso 2")
        self.assertEqual(stair_steps[1].instruction, "Subir por la escalera al Piso 3")

    def test_descending_staircase_instruction(self):
        """Bajar de piso debe decir 'Bajar', no 'Subir'."""
        route = self.engine.compute_route(4, Point2D(10.0, 8.0), "S102")
        stair_steps = [s for s in route.steps if s.is_vertical]
        self.assertTrue(stair_steps)
        for step in stair_steps:
            self.assertTrue(
                step.instruction.startswith("Bajar"),
                f"Se esperaba una instrucción de bajada: {step.instruction!r}"
            )

    def test_progress_is_undefined_without_an_origin(self):
        """
        Sin distancia de partida el progreso es None, no un número inventado.

        La fórmula anterior (`100 - distancia * 4`) asumía que toda ruta medía 25 m y devolvía
        0% para el primer paso del recorrido de la demo, que son 29 m.
        """
        route = self.engine.compute_route(1, Point2D(2.0, 5.0), "S302")
        self.assertIsNone(route.progress_percentage)
        self.assertGreater(route.total_distance_meters, 25.0)

    def test_progress_advances_monotonically_along_the_route(self):
        """Con distancia de partida conocida, el progreso crece de forma monótona."""
        trajectory = [
            (1, Point2D(2.0, 5.0)),
            (1, Point2D(8.0, 6.0)),
            (2, Point2D(10.0, 8.0)),
            (3, Point2D(10.0, 8.0)),
            (3, Point2D(10.0, 6.0)),
        ]

        origin = self.engine.compute_route(1, trajectory[0][1], "S302").total_distance_meters
        progresses = [
            self.engine.compute_route(floor, pos, "S302", initial_distance_meters=origin).progress_percentage
            for floor, pos in trajectory
        ]

        self.assertEqual(progresses[0], 0.0, "En el punto de partida el progreso debe ser 0%")
        for previous, current in zip(progresses, progresses[1:]):
            self.assertGreaterEqual(current, previous, f"El progreso retrocedió: {progresses}")
        self.assertLessEqual(max(progresses), 99.0, "Sin llegar, el progreso no debe alcanzar 100%")

    def test_closest_node_falls_back_to_an_existing_node(self):
        """
        Un piso inexistente no debe producir un ID fabricado.

        El fallback anterior devolvía `P{n}_Hall_Center`, que para un piso fuera de rango no
        existe en el grafo y hacía que Dijkstra lanzara ValueError, cerrando el WebSocket.
        """
        node_id = self.engine.find_closest_node(9, Point2D(10.0, 5.0))
        self.assertIn(node_id, self.graph.nodes, f"'{node_id}' no existe en el grafo")

        # Y la ruta completa debe poder calcularse sin reventar
        route = self.engine.compute_route(9, Point2D(10.0, 5.0), "S302")
        self.assertEqual(route.path_node_ids[-1], "S302")

if __name__ == "__main__":
    unittest.main()

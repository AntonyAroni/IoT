"""
Pruebas del Modelo Real del Pabellón de la EPCC y de la Selección de Modelo.

El modelo real convive con el sintético: cada uno va con su radio-mapa. Estas pruebas fijan la
geometría medida en el plano y que la navegación elija bien entre las dos escaleras.
"""
import unittest

from backend.domain.building import Point2D
from backend.domain.building_models import create_building_graph
from backend.domain.graph import NodeType, create_default_school_graph
from backend.services.navigation_engine import NavigationEngine


class TestEpccBuilding(unittest.TestCase):
    def setUp(self):
        self.graph, self.floors = create_building_graph("epcc")
        self.engine = NavigationEngine(self.graph, self.floors)

    def test_keeps_the_room_ids_of_the_roster(self):
        """El padrón, la app y el tablero usan S101..S403: el modelo real no puede cambiarlos."""
        ids = sorted(r.id for f in self.floors.values() for r in f.rooms)
        expected = sorted(f"S{p}{n}" for p in range(1, 5) for n in ("01", "02", "03"))
        self.assertEqual(ids, expected)

    def test_room_centers_match_the_measured_plan(self):
        """Aulas de 7.85 / 7.85 / 7.76 m de ancho y 9.98 m de fondo, en fila desde el origen."""
        centers = {r.id: r.center for r in self.floors[3].rooms}
        self.assertAlmostEqual(centers["S301"].x, 3.925, places=3)
        self.assertAlmostEqual(centers["S302"].x, 11.775, places=3)
        self.assertAlmostEqual(centers["S303"].x, 19.58, places=3)
        for center in centers.values():
            self.assertAlmostEqual(center.y, 4.99, places=3)

    def test_every_floor_has_two_staircases_connected_vertically(self):
        for f in range(1, 5):
            stairs = [n for n in self.graph.nodes.values()
                      if n.floor_number == f and n.node_type == NodeType.STAIRCASE]
            self.assertEqual(len(stairs), 2, f"El piso {f} debe tener escalera oeste y este")
        path, _ = self.graph.find_shortest_path("S101", "S302")
        self.assertEqual(path[-1], "S302")
        self.assertTrue(any(node_id.startswith("Escalera_") for node_id in path))

    def test_route_uses_the_nearest_staircase(self):
        """Desde el Aula 1 (extremo oeste) la ruta sube por la escalera oeste, no por la este."""
        path, _ = self.graph.find_shortest_path("S101", "S301")
        self.assertIn("Escalera_Oeste_P1", path)
        self.assertNotIn("Escalera_Este_P1", path)

    def test_clue_names_the_staircase_when_there_are_two(self):
        """Con dos escaleras, "escalera central" mandaría al alumno en la dirección equivocada."""
        route = self.engine.compute_route(1, Point2D(3.9, -0.965), "S302")
        self.assertIn("escalera oeste", route.active_clue.lower())
        self.assertNotIn("central", route.active_clue.lower())

    def test_arrival_at_the_real_room_center(self):
        route = self.engine.compute_route(3, Point2D(11.775, 4.99), "S302")
        self.assertTrue(route.has_arrived)


class TestBuildingModelSelection(unittest.TestCase):
    def test_synthetic_model_is_unchanged(self):
        """El modelo sintético respalda el radio-mapa y las cifras del informe: no debe moverse."""
        graph, _ = create_building_graph("sintetico")
        reference, _ = create_default_school_graph()
        self.assertEqual(
            {k: (n.position.x, n.position.y) for k, n in graph.nodes.items()},
            {k: (n.position.x, n.position.y) for k, n in reference.nodes.items()},
        )

    def test_synthetic_clue_still_says_central_staircase(self):
        graph, floors = create_building_graph("sintetico")
        route = NavigationEngine(graph, floors).compute_route(1, Point2D(2.0, 5.0), "S302")
        self.assertIn("escalera central", route.active_clue)

    def test_unknown_model_is_an_error(self):
        with self.assertRaises(ValueError):
            create_building_graph("edificio_inexistente")


if __name__ == "__main__":
    unittest.main()

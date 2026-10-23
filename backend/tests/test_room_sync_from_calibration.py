"""
Pruebas de la Asociación entre Puntos de Calibración y Aulas.

Al calibrar, el servidor mueve el centro (o la puerta) del aula a la posición del punto. Estas
pruebas fijan qué puntos pueden hacerlo y cuáles no, sin necesitar el cliente HTTP de pruebas:
llaman directamente al endpoint y a la sincronización de arranque.
"""
import unittest

from backend.api.routes_calibration import CalibrationUploadModel, record_calibration_point
from backend.domain.building_models import create_building_graph
from backend.domain.graph import infer_room_id, resolve_rp_room_id
from backend.tests.helpers import IsolatedAppStateMixin
from calibration_tools.print_mapping_grid import build_grid


class TestInferRoomId(unittest.TestCase):
    def test_original_cases_still_hold(self):
        """Los casos de test_room_mapping.test_infer_room_id deben seguir igual."""
        self.assertEqual(infer_room_id("RP_P3_303", 3), "S303")
        self.assertEqual(infer_room_id("RP_S302_Center", 3), "S302")
        self.assertEqual(infer_room_id("RP_P1_101", 1), "S101")
        self.assertEqual(infer_room_id("303", 3), "S303")
        self.assertEqual(infer_room_id("Punto Calibrado RP_P3_303 (0.1m, 0.1m)", 3), "S303")
        self.assertEqual(infer_room_id("RP_PASILLO_1", 1), None)
        self.assertEqual(infer_room_id("RP_Centro_101", 1), "S101")

    def test_loose_digits_are_not_a_room(self):
        """El índice del punto o una coordenada de la etiqueta no son un código de aula."""
        self.assertIsNone(infer_room_id("RP_P3_Hall_12", 3))
        self.assertIsNone(infer_room_id("RP_P3_Hall_8", 3, "Punto Calibrado RP_P3_Hall_8 (12.9m, -0.965m)"))

    def test_code_of_another_floor_is_discarded(self):
        self.assertIsNone(infer_room_id("RP_S101_Center", 3))


class TestResolveRpRoomId(unittest.TestCase):
    def test_declared_room_is_ignored_for_circulation_points(self):
        """La app declara el aula destino en todos los puntos: en los de pasillo no cuenta."""
        for rp_id in ("RP_P3_Hall_A", "RP_Escalera_Este_P3", "RP_P3_Stairs", "RP_PASILLO_1"):
            self.assertIsNone(resolve_rp_room_id(rp_id, 3, f"Punto Calibrado {rp_id}", "S302"), rp_id)

    def test_declared_room_of_another_floor_is_ignored(self):
        self.assertIsNone(resolve_rp_room_id("RP_Mesa", 1, "Mesa", "S302"))

    def test_declared_room_is_kept_for_a_room_point(self):
        """Un punto con nombre libre tomado dentro del aula sí representa al aula declarada."""
        self.assertEqual(resolve_rp_room_id("RP_Mesa_Profesor", 3, "Mesa", "S302"), "S302")

    def test_no_point_of_the_epcc_grid_is_misassigned(self):
        """Con la etiqueta que genera la app, cada punto de la cuadrícula va a su aula o a ninguna."""
        for floor in (1, 2, 3, 4):
            for rp_id, pos, _ in build_grid(floor, "epcc"):
                label = f"Punto Calibrado {rp_id} ({pos.x}m, {pos.y}m)"
                expected = rp_id[3:7] if rp_id.startswith("RP_S") else None
                self.assertEqual(resolve_rp_room_id(rp_id, floor, label), expected, rp_id)


class TestCalibrationMovesOnlyItsRoom(IsolatedAppStateMixin, unittest.TestCase):
    """El endpoint de calibración y la sincronización de arranque, sobre un grafo propio."""

    def setUp(self):
        super().setUp()
        original = (self.app_state.graph, self.app_state.floors)
        self.app_state.graph, self.app_state.floors = create_building_graph("epcc")
        self.addCleanup(self._restore_graph, *original)

    def _restore_graph(self, graph, floors):
        self.app_state.graph, self.app_state.floors = graph, floors

    def _record(self, rp_id, floor, x, y, room_id=None):
        payload = CalibrationUploadModel(
            rp_id=rp_id, floor_number=floor, x=x, y=y,
            label=f"Punto Calibrado {rp_id} ({x}m, {y}m)", room_id=room_id,
            rssi_means={"aa:bb:cc:dd:ee:01": -60.0},
        )
        return record_calibration_point(payload, repo=self.radio_map_repo)

    def _center(self, room_id):
        pos = self.app_state.graph.get_node(room_id).position
        return (pos.x, pos.y)

    def test_hallway_point_with_declared_room_does_not_move_it(self):
        """Fallo 1: un punto del pasadizo con roomId=S302 (lo que envía la app) no mueve S302."""
        before = self._center("S302")
        response = self._record("RP_P3_Hall_A", 3, -1.1, -0.965, room_id="S302")
        self.assertIsNone(response["room_id"])
        self.assertEqual(self._center("S302"), before)

    def test_room_point_still_moves_its_room(self):
        """El flujo previsto se mantiene: un punto del aula la sincroniza en caliente."""
        response = self._record("RP_P3_303", 3, 0.15, 0.15)
        self.assertEqual(response["room_id"], "S303")
        self.assertEqual(self._center("S303"), (0.15, 0.15))

    def test_startup_sync_ignores_hallway_points(self):
        """Un punto de pasillo guardado con un room_id antiguo no mueve el aula al arrancar."""
        before = self._center("S102")
        self._record("RP_P1_Hall_12", 1, 20.9, -0.965)
        entry = self.radio_map_repo.get_by_id("RP_P1_Hall_12")
        entry.reference_point.room_id = "S102"  # como lo habría guardado la versión anterior
        self.app_state.sync_room_positions_from_radio_map()
        self.assertEqual(self._center("S102"), before)


if __name__ == "__main__":
    unittest.main()

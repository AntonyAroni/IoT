"""
Pruebas de la Calibración con Varios Móviles y de la Recalibración.

Cada móvil aporta su huella al punto y el radio-mapa guarda la combinación. Reenviar desde el
mismo móvil sustituye su huella; `replace` descarta las de todos.
"""
import unittest

from fastapi import HTTPException

from backend.api.routes_calibration import (
    CalibrationUploadModel,
    delete_device_contribution,
    record_calibration_point,
)
from backend.domain.building_models import create_building_graph
from backend.domain.fingerprint import LEGACY_DEVICE_ID, RadioMapEntry, merge_contributions
from backend.tests.helpers import IsolatedAppStateMixin

AP1, AP2, AP3 = "aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02", "aa:bb:cc:dd:ee:03"


class TestMergeContributions(unittest.TestCase):
    def test_weighted_by_sample_count(self):
        means, _, total = merge_contributions({
            "A": {"rssi_means": {AP1: -60.0}, "rssi_std": {}, "sample_count": 15},
            "B": {"rssi_means": {AP1: -70.0}, "rssi_std": {}, "sample_count": 5},
        })
        self.assertEqual(means[AP1], -62.5)
        self.assertEqual(total, 20)

    def test_ap_seen_by_one_phone_is_not_penalized(self):
        """Un AP que el otro móvil no detecta conserva su media: no se le imputan -105 dBm."""
        means, _, _ = merge_contributions({
            "A": {"rssi_means": {AP1: -60.0, AP2: -80.0}, "rssi_std": {}, "sample_count": 15},
            "B": {"rssi_means": {AP1: -64.0}, "rssi_std": {}, "sample_count": 15},
        })
        self.assertEqual(means[AP2], -80.0)
        self.assertEqual(means[AP1], -62.0)

    def test_std_includes_the_spread_between_phones(self):
        _, stds, _ = merge_contributions({
            "A": {"rssi_means": {AP1: -60.0}, "rssi_std": {AP1: 0.0}, "sample_count": 10},
            "B": {"rssi_means": {AP1: -70.0}, "rssi_std": {AP1: 0.0}, "sample_count": 10},
        })
        self.assertEqual(stds[AP1], 5.0)


class TestRadioMapEntryContributions(unittest.TestCase):
    def test_legacy_entry_keeps_its_fingerprint_as_a_contribution(self):
        """Los puntos guardados antes del cambio no se pierden al llegar un segundo móvil."""
        entry = RadioMapEntry.from_dict({
            "id": "RP_S302_Center", "floor_number": 3, "x": 11.775, "y": 4.99, "label": "c",
            "rssi_means": {AP1: -60.0}, "sample_count": 15,
        })
        entry.add_contribution("B", {AP1: -70.0}, {}, 15, 1.0)
        self.assertEqual(set(entry.contributions), {LEGACY_DEVICE_ID, "B"})
        self.assertEqual(entry.rssi_means[AP1], -65.0)

    def test_round_trip_keeps_contributions(self):
        entry = RadioMapEntry.from_dict({
            "id": "RP_X", "floor_number": 3, "x": 0, "y": 0, "label": "x", "rssi_means": {},
        })
        entry.add_contribution("A", {AP1: -60.0}, {AP1: 2.0}, 15, 1.0)
        restored = RadioMapEntry.from_dict(entry.to_dict())
        self.assertEqual(restored.contributions, entry.contributions)
        self.assertEqual(restored.rssi_means, entry.rssi_means)


class TestRecordEndpoint(IsolatedAppStateMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        original = (self.app_state.graph, self.app_state.floors)
        self.app_state.graph, self.app_state.floors = create_building_graph("epcc")
        self.addCleanup(self._restore_graph, *original)

    def _restore_graph(self, graph, floors):
        self.app_state.graph, self.app_state.floors = graph, floors

    def _record(self, device_id, rssi, floor=3, x=6.9, y=-0.965, replace=False, samples=15):
        payload = CalibrationUploadModel(
            rp_id="RP_P3_Hall_5", floor_number=floor, x=x, y=y, label="Punto Calibrado RP_P3_Hall_5",
            rssi_means=rssi, sample_count=samples, device_id=device_id, replace=replace,
        )
        return record_calibration_point(payload, repo=self.radio_map_repo)

    def _entry(self):
        return self.radio_map_repo.get_by_id("RP_P3_Hall_5")

    def test_two_phones_are_merged(self):
        self._record("A", {AP1: -60.0, AP2: -75.0})
        response = self._record("B", {AP1: -70.0, AP3: -80.0})
        self.assertEqual(response["devices"], ["A", "B"])
        self.assertEqual(self._entry().rssi_means, {AP1: -65.0, AP2: -75.0, AP3: -80.0})
        self.assertEqual(self._entry().sample_count, 30)

    def test_same_phone_again_replaces_only_its_fingerprint(self):
        self._record("A", {AP1: -60.0})
        self._record("B", {AP1: -70.0})
        self._record("A", {AP1: -50.0})
        self.assertEqual(self._entry().rssi_means[AP1], -60.0)
        self.assertEqual(sorted(self._entry().contributions), ["A", "B"])

    def test_replace_starts_the_point_from_scratch(self):
        self._record("A", {AP1: -60.0})
        self._record("B", {AP1: -70.0})
        response = self._record("C", {AP2: -55.0}, x=7.2, replace=True)
        self.assertEqual(response["devices"], ["C"])
        self.assertEqual(self._entry().rssi_means, {AP2: -55.0})
        self.assertEqual(self._entry().reference_point.position.x, 7.2)

    def test_different_floor_or_position_is_rejected(self):
        """Caso de campo: el móvil B envió como piso 1 un punto del 3.º."""
        self._record("A", {AP1: -60.0})
        for kwargs in ({"floor": 1}, {"x": 10.9}):
            with self.assertRaises(HTTPException) as ctx:
                self._record("B", {AP1: -70.0}, **kwargs)
            self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(list(self._entry().contributions), ["A"])

    def test_small_position_difference_is_the_same_point(self):
        self._record("A", {AP1: -60.0})
        self._record("B", {AP1: -70.0}, x=7.1)
        self.assertEqual(len(self._entry().contributions), 2)

    def test_delete_one_phone_recombines_the_rest(self):
        self._record("A", {AP1: -60.0})
        self._record("B", {AP1: -70.0})
        delete_device_contribution("RP_P3_Hall_5", "B", repo=self.radio_map_repo)
        self.assertEqual(self._entry().rssi_means, {AP1: -60.0})
        delete_device_contribution("RP_P3_Hall_5", "A", repo=self.radio_map_repo)
        self.assertIsNone(self._entry())

    def test_delete_unknown_phone_is_404(self):
        self._record("A", {AP1: -60.0})
        with self.assertRaises(HTTPException) as ctx:
            delete_device_contribution("RP_P3_Hall_5", "Z", repo=self.radio_map_repo)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

"""
Pruebas de Integridad del Dataset de Calibración (`data/radio_map.json`).

Regresión frente a la contaminación detectada en la auditoría: el fichero llegó a tener 44
entradas en lugar de 40 (un artefacto de prueba, `RP_TEST_S302`, más tres capturas reales de
campo con direcciones MAC y coordenadas duplicadas). Con ese dataset la precisión de aislamiento
de piso medida por LOOCV caía a 88.6–93.2%, por debajo del objetivo de diseño de ≥95%.

Si alguna de estas pruebas falla, regenerar el radio-mapa:

    PYTHONPATH=. python calibration_tools/generate_synthetic_map.py
"""
import json
import re
import unittest
from collections import Counter
from pathlib import Path

# backend/tests/test_x.py -> backend/tests -> backend -> raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RADIO_MAP_PATH = PROJECT_ROOT / "data" / "radio_map.json"

EXPECTED_ENTRY_COUNT = 40
EXPECTED_FLOORS = {1, 2, 3, 4}

# Conjunto canónico de APs sintéticos generado por calibration_tools/generate_synthetic_map.py:
# 3 APs por piso (ala oeste, ala este y aula central) en 4 pisos.
SYNTHETIC_APS = {
    f"ap_p{floor}_{wing}"
    for floor in range(1, 5)
    for wing in ("west", "east", "room02")
}

MAC_PATTERN = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", re.IGNORECASE)

REGENERATE_HINT = (
    "Regenera el dataset con: "
    "PYTHONPATH=. python calibration_tools/generate_synthetic_map.py"
)


class TestRadioMapIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RADIO_MAP_PATH.exists():
            raise unittest.SkipTest(f"No existe {RADIO_MAP_PATH}. {REGENERATE_HINT}")
        with open(RADIO_MAP_PATH, encoding="utf-8") as f:
            cls.entries = json.load(f)

    def test_entry_count_matches_documented_dataset(self):
        """El dataset debe tener exactamente los 40 RPs que documentan README y reporte de auditoría."""
        self.assertEqual(
            len(self.entries),
            EXPECTED_ENTRY_COUNT,
            f"Se esperaban {EXPECTED_ENTRY_COUNT} puntos de referencia y hay {len(self.entries)}. "
            f"Las métricas publicadas (100% de aislamiento de piso) solo se reproducen con el "
            f"dataset limpio. {REGENERATE_HINT}"
        )

    def test_only_synthetic_access_points_present(self):
        """
        Ningún BSSID ajeno al conjunto sintético.

        Detecta tanto artefactos de prueba (p. ej. 'ap_test_s302' escrito por un test que usaba
        el repositorio de producción) como capturas de campo mezcladas con el dataset.
        """
        offenders = {}
        for entry in self.entries:
            intruders = set(entry["rssi_means"]) - SYNTHETIC_APS
            if intruders:
                offenders[entry["id"]] = sorted(intruders)

        self.assertEqual(
            offenders,
            {},
            f"Entradas con BSSID ajenos al dataset sintético: {offenders}. {REGENERATE_HINT}"
        )

    def test_no_real_mac_addresses_leaked(self):
        """
        Ninguna dirección MAC real en el dataset.

        Las MAC de puntos de acceso son geolocalizables en bases públicas de wardriving; las
        capturas reales viven seudonimizadas en data/field_captures/.
        """
        leaked = sorted({
            bssid
            for entry in self.entries
            for bssid in entry["rssi_means"]
            if MAC_PATTERN.match(bssid)
        })

        self.assertEqual(
            leaked,
            [],
            f"Direcciones MAC reales filtradas en el radio-mapa: {leaked}. "
            f"Muévelas a data/field_captures/ seudonimizadas."
        )

    def test_reference_point_ids_are_unique(self):
        """Un ID duplicado sobreescribe silenciosamente al anterior en el repositorio."""
        duplicates = [rp_id for rp_id, count in Counter(e["id"] for e in self.entries).items() if count > 1]
        self.assertEqual(duplicates, [], f"IDs de punto de referencia duplicados: {duplicates}")

    def test_floors_are_evenly_covered(self):
        """Los 4 pisos deben estar representados; un piso vacío degrada el clasificador jerárquico."""
        per_floor = Counter(e["floor_number"] for e in self.entries)
        self.assertEqual(
            set(per_floor),
            EXPECTED_FLOORS,
            f"Cobertura de pisos inesperada: {dict(per_floor)}"
        )

    def test_calibration_statistics_are_actually_sampled(self):
        """
        `sample_count` debe corresponder a un muestreo real, con su desviación estándar.

        El generador declaraba `sample_count=15` pero tomaba **una sola** lectura por AP, así que
        la "media" era un único valor ruidoso y `rssi_std` quedaba vacío en las 40 entradas. La
        ponderación probabilística que cita el proyecto (Horus) no tenía datos sobre los que
        operar.
        """
        without_std = [e["id"] for e in self.entries if not e.get("rssi_std")]
        self.assertEqual(
            without_std, [],
            f"Entradas sin desviación estándar: {without_std}. {REGENERATE_HINT}"
        )

        for entry in self.entries:
            self.assertGreater(
                entry["sample_count"], 1,
                f"{entry['id']} declara {entry['sample_count']} muestras"
            )
            self.assertEqual(
                set(entry["rssi_std"]), set(entry["rssi_means"]),
                f"{entry['id']}: media y desviación cubren BSSIDs distintos"
            )

    def test_no_duplicate_positions_within_a_floor(self):
        """
        Dos RPs del mismo piso no pueden compartir coordenada.

        Esta fue la señal que delató las capturas de campo contaminantes: tres puntos
        físicamente distintos guardados todos en (10.0, 2.0), el valor por defecto del
        formulario del calibrador.
        """
        seen = {}
        collisions = {}
        for entry in self.entries:
            key = (entry["floor_number"], entry["position"]["x"], entry["position"]["y"])
            if key in seen:
                collisions.setdefault(key, [seen[key]]).append(entry["id"])
            else:
                seen[key] = entry["id"]

        self.assertEqual(
            collisions,
            {},
            f"Puntos de referencia superpuestos (piso, x, y) -> IDs: {collisions}"
        )


if __name__ == "__main__":
    unittest.main()

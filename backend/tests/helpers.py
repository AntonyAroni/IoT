"""
Utilidades de Aislamiento para la Batería de Pruebas.

Los repositorios del `app_state` global se construyen con `storage_path` apuntando a `data/`
(ver `backend/main.py`), por lo que cualquier `save_entry()` o `save_record()` ejecutado durante
una prueba reescribe los ficheros de datos reales del proyecto. Esto contaminó en el pasado
`data/radio_map.json` con el punto de referencia sintético `RP_TEST_S302`, degradando la métrica
de aislamiento de piso auditada por LOOCV.

`IsolatedAppStateMixin` sustituye esos repositorios por instancias en memoria sin persistencia
mientras dura cada prueba, y los restaura al terminar.
"""
from backend.repositories.attendance_repo import InMemoryAttendanceRepository
from backend.repositories.radio_map_repo import InMemoryRadioMapRepository


class IsolatedAppStateMixin:
    """
    Aísla los repositorios del estado global de la aplicación durante una prueba.

    Expone `self.radio_map_repo` y `self.attendance_repo` como repositorios efímeros, ya
    enlazados tanto en `app_state` como en los servicios que mantienen una referencia directa
    a ellos (clasificador de piso, localizador WKNN y tracker de asistencia).

    Uso:
        class MiPrueba(IsolatedAppStateMixin, unittest.TestCase):
            ...
    """

    def setUp(self):
        super().setUp()
        # Importación diferida: `backend.main` construye el `app_state` global al importarse.
        from backend.main import app_state

        self.app_state = app_state
        original_radio_map_repo = app_state.radio_map_repo
        original_attendance_repo = app_state.attendance_repo

        # Repositorios efímeros: sin `storage_path` nunca escriben en `data/`.
        self.radio_map_repo = InMemoryRadioMapRepository()
        self.attendance_repo = InMemoryAttendanceRepository()

        self._bind_repositories(self.radio_map_repo, self.attendance_repo)
        self.addCleanup(
            self._bind_repositories,
            original_radio_map_repo,
            original_attendance_repo
        )

    def _bind_repositories(self, radio_map_repo, attendance_repo) -> None:
        """Reconecta los repositorios en el estado global y en los servicios que los referencian."""
        self.app_state.radio_map_repo = radio_map_repo
        self.app_state.floor_classifier.radio_map_repo = radio_map_repo
        self.app_state.wknn_locator.radio_map_repo = radio_map_repo

        self.app_state.attendance_repo = attendance_repo
        self.app_state.attendance_tracker.attendance_repo = attendance_repo

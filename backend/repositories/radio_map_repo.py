"""
Implementación del Repositorio de Radio-Mapa en Memoria con persistencia JSON.
Cumple con la interfaz IRadioMapRepository.
"""
import json
import os
from typing import List, Dict, Optional
from ..domain.fingerprint import RadioMapEntry
from .base import IRadioMapRepository

class InMemoryRadioMapRepository(IRadioMapRepository):
    def __init__(self, storage_path: Optional[str] = None):
        self._entries: Dict[str, RadioMapEntry] = {}
        self.storage_path = storage_path
        if storage_path and os.path.exists(storage_path):
            self.load_from_file(storage_path)

    def save_entry(self, entry: RadioMapEntry) -> None:
        self._entries[entry.reference_point.id] = entry
        if self.storage_path:
            self.save_to_file(self.storage_path)

    def get_all_entries(self) -> List[RadioMapEntry]:
        return list(self._entries.values())

    def get_entries_by_floor(self, floor_number: int) -> List[RadioMapEntry]:
        return [
            entry for entry in self._entries.values()
            if entry.reference_point.floor_number == floor_number
        ]

    def get_by_id(self, rp_id: str) -> Optional[RadioMapEntry]:
        return self._entries.get(rp_id)

    get_entry = get_by_id

    def delete_entry(self, rp_id: str) -> bool:
        if rp_id in self._entries:
            del self._entries[rp_id]
            if self.storage_path:
                self.save_to_file(self.storage_path)
            return True
        return False

    def clear(self) -> None:
        self._entries.clear()
        if self.storage_path:
            self.save_to_file(self.storage_path)

    def load_from_file(self, filepath: str) -> None:
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            self._entries = {
                item["id"]: RadioMapEntry.from_dict(item)
                for item in data
            }

    def save_to_file(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        data = [entry.to_dict() for entry in self._entries.values()]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

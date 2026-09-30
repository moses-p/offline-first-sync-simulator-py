"""
Storage adapters for the offline queue's persisted state.

MemoryStorage is used in tests, where each test should start from an
empty, isolated state. FileStorage persists to a local JSON file and
stands in for a device-local store (e.g. SQLite/IndexedDB on a real
client), so queued records survive an application restart.
"""

import json
import os


class MemoryStorage:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value

    def clear(self):
        self._data = {}


class FileStorage:
    def __init__(self, path):
        self.path = path

    def _read(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get(self, key):
        return self._read().get(key)

    def set(self, key, value):
        data = self._read()
        data[key] = value
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def clear(self):
        if os.path.exists(self.path):
            os.remove(self.path)

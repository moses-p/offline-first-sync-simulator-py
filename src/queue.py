"""
Durable local queue for submissions captured while offline.

Each pending item is stored in an envelope {queue_id, record, attempts}
so retry bookkeeping never mutates the original payload. Duplicate
submissions are intercepted at enqueue time by submission_uuid
(first write wins); later copies are dropped and logged.
"""


def _empty_state():
    return {
        "next_id": 1,
        "pending": [],
        "seen_uuids": [],
        "dropped": [],
        "quarantined": [],
    }


class OfflineQueue:
    def __init__(self, storage, key="offline_queue"):
        self.storage = storage
        self.key = key

    def _load(self):
        return self.storage.get(self.key) or _empty_state()

    def _save(self, state):
        self.storage.set(self.key, state)

    def enqueue(self, record):
        """Add a record to the queue, or drop it if the UUID was already seen."""
        state = self._load()
        uuid_value = record.get("submission_uuid") if isinstance(record, dict) else None

        if uuid_value is not None and uuid_value in state["seen_uuids"]:
            state["dropped"].append({"submission_uuid": uuid_value, "reason": "duplicate_submission"})
            self._save(state)
            return {"status": "dropped_duplicate", "submission_uuid": uuid_value}

        if uuid_value is not None:
            state["seen_uuids"].append(uuid_value)

        queue_id = state["next_id"]
        state["next_id"] += 1
        state["pending"].append({"queue_id": queue_id, "record": record, "attempts": 0})
        self._save(state)
        return {"status": "queued", "queue_id": queue_id, "submission_uuid": uuid_value}

    def pending(self):
        return self._load()["pending"]

    def dropped(self):
        return self._load()["dropped"]

    def quarantined(self):
        return self._load()["quarantined"]

    def ack(self, queue_id):
        """Remove an item once the server has confirmed receipt."""
        state = self._load()
        state["pending"] = [item for item in state["pending"] if item["queue_id"] != queue_id]
        self._save(state)

    def quarantine(self, queue_id, errors):
        """Move a failed-validation item out of the retry path, with its errors."""
        state = self._load()
        item = next((i for i in state["pending"] if i["queue_id"] == queue_id), None)
        if item is None:
            return
        state["pending"] = [i for i in state["pending"] if i["queue_id"] != queue_id]
        state["quarantined"].append({**item, "errors": errors})
        self._save(state)

    def mark_attempt(self, queue_id):
        """Record a failed send attempt; the item remains queued for retry."""
        state = self._load()
        for item in state["pending"]:
            if item["queue_id"] == queue_id:
                item["attempts"] += 1
        self._save(state)

"""
End-to-end demo: offline capture, app restart, and sync on reconnect.

Run with:
    python -m src.main
"""

import json
import os

from .storage import FileStorage
from .queue import OfflineQueue
from .remote import MockRemoteStore
from .sync import SyncEngine
from .validate import validate_record

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD_PATH = os.path.join(HERE, "..", "data", "payload.json")
STATE_PATH = os.path.join(HERE, "..", ".sync-state.json")


def short(uuid_value):
    return uuid_value[:8]


def main():
    with open(PAYLOAD_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)

    storage = FileStorage(STATE_PATH)
    storage.clear()  # start this run from a clean device state

    online = {"value": False}
    remote = MockRemoteStore()

    # 1. Offline: submissions are captured into the local queue.
    print("== 1. Device is OFFLINE: 4 records are submitted ==")
    queue = OfflineQueue(storage)
    for record in payload:
        outcome = queue.enqueue(record)
        label = "queued" if outcome["status"] == "queued" else "DROPPED (duplicate submission_uuid)"
        print(f"  {short(record['submission_uuid'])}  {record['urban_council']:<27} -> {label}")
    print(f"  pending in local queue: {len(queue.pending())}")

    offline_engine = SyncEngine(queue, remote, validate_record, is_online=lambda: online["value"])
    attempt = offline_engine.flush()
    print(f"  flush attempt while offline -> {attempt['status']}, nothing sent")

    # 2. App restart: queue state is reloaded from persisted storage.
    print("\n== 2. App restarts: queue reloaded from local storage ==")
    restored_queue = OfflineQueue(storage)
    print(f"  recovered {len(restored_queue.pending())} pending record(s)")

    # 3. Connectivity restored: validate and commit.
    print("\n== 3. Connectivity restored: sync ==")
    online["value"] = True
    engine = SyncEngine(restored_queue, remote, validate_record, is_online=lambda: online["value"])
    result = engine.flush()

    for c in result["committed"]:
        print(f"  committed {short(c['submission_uuid'])}  {c['urban_council']}")
    for r in result["rejected"]:
        print(f"  rejected  {r['record']['submission_uuid']}: {'; '.join(r['errors'])}")
    for f in result["failed"]:
        print(f"  failed    {short(f['submission_uuid'])}: {f['error']} (will retry)")

    print("\n== Summary ==")
    print(f"  records received      : {len(payload)}")
    print(f"  duplicates dropped    : {len(restored_queue.dropped())}")
    print(f"  committed to server   : {len(remote.all())}")
    print(f"  still pending / failed: {len(restored_queue.pending())}")


if __name__ == "__main__":
    main()

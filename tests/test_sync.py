"""Automated tests for the offline queue, validation, and sync engine."""

import json
import os
import unittest

from src.storage import MemoryStorage
from src.queue import OfflineQueue
from src.remote import MockRemoteStore
from src.sync import SyncEngine
from src.validate import validate_record

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "..", "data", "payload.json"), "r", encoding="utf-8") as f:
    PAYLOAD = json.load(f)

MUKONO, ENTEBBE, MUKONO_DUPLICATE, GULU = PAYLOAD


def make_system(online=True, fail_first_n_commits=0):
    """Build a fresh queue + remote + engine, wired together, for one test."""
    storage = MemoryStorage()
    queue = OfflineQueue(storage)
    remote = MockRemoteStore(fail_first_n_commits=fail_first_n_commits)
    state = {"online": online}
    engine = SyncEngine(queue, remote, validate_record, is_online=lambda: state["online"])
    return storage, queue, remote, engine, state


class ValidationTests(unittest.TestCase):
    def test_accepts_the_three_unique_records(self):
        for record in (MUKONO, ENTEBBE, GULU):
            result = validate_record(record)
            self.assertEqual(result, {"valid": True, "errors": []})

    def test_rejects_malformed_records(self):
        bad_records = [
            {**MUKONO, "submission_uuid": "not-a-uuid"},
            {**MUKONO, "urban_council": "   "},
            {**MUKONO, "pdp_status": "Unknown"},
            {**MUKONO, "expiry_year": None},        # Active needs a year
            {**MUKONO, "expiry_year": "2032"},      # must be a number, not text
            {**GULU, "expiry_year": 2030},          # Missing must have null year
            {**MUKONO, "field_officer_timestamp": "yesterday"},
            None,
        ]
        for record in bad_records:
            self.assertFalse(validate_record(record)["valid"], msg=record)


class QueueTests(unittest.TestCase):
    def test_intercepts_the_duplicate_mukono_submission(self):
        _, queue, _, _, _ = make_system()
        statuses = [queue.enqueue(r)["status"] for r in PAYLOAD]
        self.assertEqual(statuses, ["queued", "queued", "dropped_duplicate", "queued"])
        self.assertEqual(len(queue.pending()), 3)
        self.assertEqual(len(queue.dropped()), 1)
        self.assertEqual(queue.dropped()[0]["submission_uuid"], MUKONO["submission_uuid"])

    def test_queued_records_survive_an_app_restart(self):
        storage, queue, _, _, _ = make_system()
        for record in PAYLOAD:
            queue.enqueue(record)

        # A new OfflineQueue instance backed by the same storage simulates
        # an application restart.
        restored_queue = OfflineQueue(storage)
        self.assertEqual(len(restored_queue.pending()), 3)
        self.assertEqual(len(restored_queue.dropped()), 1)


class SyncTests(unittest.TestCase):
    def test_commits_exactly_the_three_unique_validated_records(self):
        _, queue, remote, engine, _ = make_system()
        for record in PAYLOAD:
            queue.enqueue(record)

        result = engine.flush()

        self.assertEqual(len(result["committed"]), 3)
        self.assertEqual(len(remote.all()), 3)
        self.assertEqual(
            sorted(r["urban_council"] for r in remote.all()),
            ["Entebbe Municipal Council", "Gulu City Council", "Mukono Municipality"],
        )
        self.assertEqual(len(queue.pending()), 0)

    def test_while_offline_nothing_is_sent(self):
        _, queue, remote, engine, state = make_system(online=False)
        for record in PAYLOAD:
            queue.enqueue(record)

        result = engine.flush()
        self.assertEqual(result["status"], "offline")
        self.assertEqual(len(remote.all()), 0)
        self.assertEqual(len(queue.pending()), 3)

        state["online"] = True
        engine.flush()
        self.assertEqual(len(remote.all()), 3)

    def test_a_failed_commit_is_retried_and_never_duplicated(self):
        _, queue, remote, engine, _ = make_system(fail_first_n_commits=1)
        for record in PAYLOAD:
            queue.enqueue(record)

        first = engine.flush()
        self.assertEqual(len(first["failed"]), 1)
        self.assertEqual(len(first["committed"]), 2)
        self.assertEqual(len(queue.pending()), 1)
        self.assertEqual(queue.pending()[0]["attempts"], 1)

        second = engine.flush()
        self.assertEqual(len(second["committed"]), 1)
        self.assertEqual(len(remote.all()), 3)
        self.assertEqual(len(queue.pending()), 0)

    def test_invalid_records_are_quarantined_not_committed(self):
        _, queue, remote, engine, _ = make_system()
        queue.enqueue(MUKONO)
        queue.enqueue({**ENTEBBE, "submission_uuid": "bad-id"})

        result = engine.flush()

        self.assertEqual(len(result["committed"]), 1)
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(len(remote.all()), 1)
        self.assertEqual(len(queue.quarantined()), 1)
        self.assertEqual(len(queue.pending()), 0)

    def test_resubmitting_an_already_committed_uuid_is_dropped(self):
        _, queue, _, engine, _ = make_system()
        queue.enqueue(MUKONO)
        engine.flush()

        self.assertEqual(queue.enqueue(MUKONO_DUPLICATE)["status"], "dropped_duplicate")
        self.assertEqual(len(queue.pending()), 0)

    def test_server_side_commit_is_idempotent_even_if_queue_guard_bypassed(self):
        remote = MockRemoteStore()
        self.assertEqual(remote.commit(MUKONO), "committed")
        self.assertEqual(remote.commit(MUKONO_DUPLICATE), "already_committed")
        self.assertEqual(len(remote.all()), 1)


if __name__ == "__main__":
    unittest.main()

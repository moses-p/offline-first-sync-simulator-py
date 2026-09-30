"""
Sync engine: drains the offline queue when connectivity is available.

For each queued item:
  1. Validate. Invalid records are quarantined, not retried.
  2. Commit. Success acknowledges (removes) the item; failure leaves it
     queued for the next flush().
"""

from .remote import NetworkError


class SyncEngine:
    def __init__(self, queue, remote, validate, is_online=lambda: True):
        self.queue = queue
        self.remote = remote
        self.validate = validate
        self.is_online = is_online

    def flush(self):
        result = {"status": "online", "committed": [], "rejected": [], "failed": []}

        if not self.is_online():
            result["status"] = "offline"
            return result

        # Iterate over a snapshot; ack()/quarantine() mutate the queue in place.
        for item in list(self.queue.pending()):
            record = item["record"]
            outcome = self.validate(record)

            if not outcome["valid"]:
                self.queue.quarantine(item["queue_id"], outcome["errors"])
                result["rejected"].append({"record": record, "errors": outcome["errors"]})
                continue

            try:
                commit_outcome = self.remote.commit(record)
                self.queue.ack(item["queue_id"])
                result["committed"].append({
                    "submission_uuid": record["submission_uuid"],
                    "urban_council": record["urban_council"],
                    "outcome": commit_outcome,
                })
            except NetworkError as err:
                self.queue.mark_attempt(item["queue_id"])
                result["failed"].append({
                    "submission_uuid": record["submission_uuid"],
                    "error": str(err),
                })

        return result

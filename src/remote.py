"""
In-memory mock of the remote server, used to run and test the sync
engine without a live backend.

commit() is idempotent: committing the same submission_uuid twice
stores it once. This is the server-side safety net that makes retries
safe even if the client-side duplicate check is ever bypassed.
"""


class NetworkError(Exception):
    """Raised to simulate a failed network call."""


class MockRemoteStore:
    def __init__(self, fail_first_n_commits=0):
        self._records = {}
        self.remaining_failures = fail_first_n_commits

    def commit(self, record):
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise NetworkError("Network error (simulated)")

        uuid_value = record["submission_uuid"]
        if uuid_value in self._records:
            return "already_committed"

        self._records[uuid_value] = dict(record)
        return "committed"

    def all(self):
        return list(self._records.values())

# Offline-First Sync Simulator (Python)

A small, dependency-free Python simulation of how a field tool should behave in low-connectivity areas: **cache submissions locally, drop duplicates, validate, and commit only clean records when the connection returns.**

## Run it

Requires Python 3.10 or newer. Nothing to install (standard library only).

```bash
python -m src.main       # runs the demo against data/payload.json
python -m unittest -v    # runs the 10 automated tests
```

Expected demo result: 4 records received, **1 duplicate dropped, 3 committed**.

## How it works

```
field officer -> enqueue() -> [durable local queue] -> flush() -> validate -> commit -> server
                    |                                     |            |
             drops duplicate                      offline? do nothing   invalid? quarantine
             submission_uuid                      commit fails? retry
```

| File | Responsibility |
|---|---|
| `src/queue.py` | Durable queue. **Intercepts duplicates** by `submission_uuid` (first write wins) and logs each drop. |
| `src/validate.py` | Pure validation function returning `{valid, errors}`. |
| `src/sync.py` | `SyncEngine.flush()` — validates, commits, acknowledges, retries. |
| `src/remote.py` | Mock server with an **idempotent** `commit()`. |
| `src/storage.py` | Storage adapters (file-backed for the demo, in-memory for tests). |

## Design decisions

- **Two layers of de-duplication.** The queue drops duplicates at capture time (saves bandwidth), and the server commit is idempotent (safe if a retry re-sends a record whose acknowledgement was lost). Retries can never create duplicates.
- **Durable queue.** State is written to a JSON file, so pending records survive an app restart (demonstrated in step 2 of the demo). A real device would use SQLite instead of a JSON file; the interface (`get`/`set`/`clear`) would stay the same.
- **Retry vs. reject.** A network failure keeps the record in the queue for the next flush. An *invalid* record is moved to a quarantine list instead — retrying it would never succeed.
- **Idempotency key = `submission_uuid`.** It is generated on the device at capture time, so it stays stable across retries.

## Validation rules

- `submission_uuid`: valid UUID
- `urban_council`: non-empty string
- `pdp_status`: one of `Active`, `Expiring`, `Missing`
- `expiry_year`: whole number 2000–2100 when status is `Active`/`Expiring`; **must be `null` when `Missing`** (this is why the Gulu record is valid)
- `field_officer_timestamp`: parseable ISO-8601 timestamp

## Assumptions

- "Validated" means passing the rules above; all 3 unique records in the sample pass.
- Duplicate policy is *first write wins*. If two records shared a UUID but had different contents, a production system should flag a conflict rather than silently drop — noted below.

## What I would add next

- Real device storage: SQLite with a `UNIQUE` constraint on `submission_uuid` as a second safety net.
- If this became a live API: FastAPI for the commit endpoint, since Python is already the language here.
- Exponential backoff with a max-attempts limit, then quarantine.
- Conflict detection for same-UUID / different-payload submissions.
- Ordering commits by `field_officer_timestamp`.

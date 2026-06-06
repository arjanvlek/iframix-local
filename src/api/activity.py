"""Asynchronous per-device activity tracking.

Display/controller devices only re-run the login flow occasionally, so a
presence indicator based on ``last_login`` goes stale. This module records a
``last_active`` timestamp for a device on every API request
that can be attributed to it, written off the request thread so request
latency is unaffected.

Public API:

* ``record_activity(device_uuid)`` — cheap, non-blocking, never raises.
  Schedules an async ``last_active`` write for the device, throttled so a
  given device is written at most once per ``WRITE_INTERVAL`` seconds.
* ``flush(timeout=...)`` — block until every queued write has been applied
  (test helper).
* ``reset_for_tests()`` — clear the throttle map (test helper).

The actual DB write resolves the connection through ``src.api.persistence``
at write time and never caches one, so the fresh-import-per-test pattern
(which repoints the SQLite path per test via ``src.db.set_db_path``) works.
"""

import logging
import queue
import threading
import time

logger = logging.getLogger(__name__)

# Minimum seconds between persisted writes for a single device. Repeated
# record_activity() calls inside this window are dropped, so a chatty device
# costs at most one write per interval.
WRITE_INTERVAL = 30

# Throttle map: uuid -> unix timestamp of the last write we scheduled.
_last_written = {}
_throttle_lock = threading.Lock()

# Lazily-started worker. The queue + worker are created on first use (guarded
# by _worker_lock) so merely importing this module never spawns a thread.
_queue = None
_worker = None
_worker_lock = threading.Lock()


def _ensure_worker():
    """Start the daemon worker thread on first use."""
    global _queue, _worker
    if _worker is not None:
        return
    with _worker_lock:
        if _worker is not None:
            return
        _queue = queue.Queue()
        _worker = threading.Thread(
            target=_worker_loop, name="activity-writer", daemon=True)
        _worker.start()


def _worker_loop():
    while True:
        device_uuid = _queue.get()
        try:
            # Resolve persistence lazily at write time so tests that repoint
            # the SQLite path per test still hit the right database.
            from src.api import persistence
            persistence.touch_session_last_active(
                device_uuid, int(time.time()))
        except Exception:  # noqa: BLE001 - never let a write break the worker
            logger.debug(
                "[ACTIVITY] write failed for %s", device_uuid, exc_info=True)
        finally:
            _queue.task_done()


def record_activity(device_uuid):
    """Record that ``device_uuid`` was just active. Cheap and never raises.

    Enqueues an async ``last_active`` write at most once per WRITE_INTERVAL
    seconds per device. Safe to call on the request hot path.
    """
    try:
        if not device_uuid:
            return
        now = time.time()
        with _throttle_lock:
            last = _last_written.get(device_uuid, 0)
            if now - last < WRITE_INTERVAL:
                return
            _last_written[device_uuid] = now
        _ensure_worker()
        _queue.put(device_uuid)
    except Exception:  # noqa: BLE001 - activity tracking is best-effort
        logger.debug(
            "[ACTIVITY] record_activity failed for %s",
            device_uuid, exc_info=True)


def flush(timeout=None):
    """Block until all queued writes have been applied (test helper).

    Returns immediately if the worker has never started (nothing queued).
    """
    if _queue is None:
        return
    if timeout is None:
        _queue.join()
        return
    # queue.join() has no timeout, so poll unfinished_tasks instead.
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _queue.all_tasks_done:
            if _queue.unfinished_tasks == 0:
                return
        time.sleep(0.01)


def reset_for_tests():
    """Clear the throttle map so a fresh-imported test sees no prior writes."""
    with _throttle_lock:
        _last_written.clear()

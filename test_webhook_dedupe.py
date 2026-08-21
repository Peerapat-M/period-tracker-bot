import threading
import time
from unittest.mock import MagicMock

from handlers import _IN_PROGRESS_EVENT_IDS, _PROCESSED_EVENT_IDS, _dedupe_webhook_event


def _event(event_id):
    event = MagicMock()
    event.webhook_event_id = event_id
    return event


def _reset():
    _PROCESSED_EVENT_IDS.clear()
    _IN_PROGRESS_EVENT_IDS.clear()


def test_dedupe_skips_a_repeated_event_after_a_successful_run():
    _reset()
    calls = []

    @_dedupe_webhook_event
    def handler(event):
        calls.append(event.webhook_event_id)

    handler(_event("evt-1"))
    handler(_event("evt-1"))

    assert calls == ["evt-1"]


def test_dedupe_still_retries_after_a_failed_attempt():
    _reset()
    calls = []
    attempt_count = 0

    @_dedupe_webhook_event
    def handler(event):
        nonlocal attempt_count
        attempt_count += 1
        calls.append(event.webhook_event_id)
        if attempt_count == 1:
            raise RuntimeError("boom")

    try:
        handler(_event("evt-2"))
    except RuntimeError:
        pass
    handler(_event("evt-2"))

    assert calls == ["evt-2", "evt-2"]


def test_dedupe_still_retries_after_a_non_exception_base_exception():
    # A plain `except Exception` would miss this and leave the event stuck
    # in _IN_PROGRESS_EVENT_IDS forever, silently dropping every future
    # retry of the same webhook event.
    _reset()
    calls = []
    attempt_count = 0

    @_dedupe_webhook_event
    def handler(event):
        nonlocal attempt_count
        attempt_count += 1
        calls.append(event.webhook_event_id)
        if attempt_count == 1:
            raise SystemExit("worker recycled mid-handler")

    try:
        handler(_event("evt-base-exc"))
    except SystemExit:
        pass
    handler(_event("evt-base-exc"))

    assert calls == ["evt-base-exc", "evt-base-exc"]
    assert "evt-base-exc" not in _IN_PROGRESS_EVENT_IDS


def test_dedupe_treats_different_event_ids_independently():
    _reset()
    calls = []

    @_dedupe_webhook_event
    def handler(event):
        calls.append(event.webhook_event_id)

    handler(_event("evt-3"))
    handler(_event("evt-4"))

    assert calls == ["evt-3", "evt-4"]


def test_dedupe_claims_before_processing_so_a_concurrent_retry_is_skipped():
    # Reproduces the race a gthread worker makes possible: a retry of the
    # same webhook event arrives on a second thread while the original is
    # still mid-flight on the first. Without claiming the event up front
    # (before running the handler), both threads would see "not yet done"
    # and process it twice.
    _reset()
    calls = []
    started = threading.Event()

    @_dedupe_webhook_event
    def handler(event):
        started.set()
        time.sleep(0.05)
        calls.append(event.webhook_event_id)

    event = _event("evt-race")
    first = threading.Thread(target=handler, args=(event,))
    first.start()
    started.wait(timeout=1)

    handler(event)  # the "retry", racing the still-running first attempt
    first.join(timeout=1)

    assert calls == ["evt-race"]

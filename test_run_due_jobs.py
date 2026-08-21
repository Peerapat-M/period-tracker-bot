from unittest.mock import MagicMock, patch

import scheduler as scheduler_module


class _FakeJob:
    def __init__(self, job_id, func):
        self.id = job_id
        self.func = func
        self.args = ()
        self.kwargs = {}


def _run_with_due_jobs(due_jobs):
    fake_store = MagicMock()
    fake_store.get_due_jobs.return_value = due_jobs
    with patch.object(scheduler_module, "SQLAlchemyJobStore", return_value=fake_store):
        fired = scheduler_module.run_due_jobs()
    return fired, fake_store


def test_a_job_that_runs_without_raising_is_removed():
    job = _FakeJob("ok", lambda: None)
    fired, fake_store = _run_with_due_jobs([job])
    assert fired == 1
    fake_store.remove_job.assert_called_once_with("ok")
    fake_store.shutdown.assert_called_once()


def test_a_job_that_raises_is_left_in_place_for_the_next_poll():
    def boom():
        raise RuntimeError("push failed")

    job = _FakeJob("fail", boom)
    fired, fake_store = _run_with_due_jobs([job])
    assert fired == 0
    fake_store.remove_job.assert_not_called()
    fake_store.shutdown.assert_called_once()


def test_one_failing_job_does_not_block_the_others_in_the_same_poll():
    def boom():
        raise RuntimeError("push failed")

    failing = _FakeJob("fail", boom)
    ok = _FakeJob("ok", lambda: None)
    fired, fake_store = _run_with_due_jobs([failing, ok])
    assert fired == 1
    fake_store.remove_job.assert_called_once_with("ok")

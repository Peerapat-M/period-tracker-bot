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


def test_a_job_that_ran_but_could_not_be_removed_still_counts_the_rest_of_the_batch():
    fake_store = MagicMock()
    fake_store.remove_job.side_effect = [Exception("row already gone"), None]
    fake_store.get_due_jobs.return_value = [_FakeJob("a", lambda: None), _FakeJob("b", lambda: None)]
    with patch.object(scheduler_module, "SQLAlchemyJobStore", return_value=fake_store):
        fired = scheduler_module.run_due_jobs()
    # "a" ran but its remove_job failed; "b" still ran and was removed --
    # one bad removal doesn't abort the rest of the poll's batch.
    assert fired == 1
    assert fake_store.remove_job.call_count == 2


def test_an_overlapping_call_is_skipped_instead_of_double_firing():
    fake_store = MagicMock()
    with patch.object(scheduler_module, "SQLAlchemyJobStore", return_value=fake_store):
        scheduler_module._RUN_DUE_JOBS_LOCK.acquire()
        try:
            fired = scheduler_module.run_due_jobs()
        finally:
            scheduler_module._RUN_DUE_JOBS_LOCK.release()
    assert fired == 0
    fake_store.get_due_jobs.assert_not_called()

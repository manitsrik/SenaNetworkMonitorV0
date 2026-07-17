import async_runtime
from task_scheduler import TaskScheduler


class FakeJobDatabase:
    def __init__(self):
        self.started = []
        self.completed = []
        self.errors = []

    def log_job_start(self, job_id, job_name):
        self.started.append((job_id, job_name))
        return len(self.started)

    def log_job_complete(self, history_id, summary):
        self.completed.append((history_id, summary))

    def log_job_error(self, history_id, message):
        self.errors.append((history_id, message))

    def get_job_history(self, **_kwargs):
        return []


def test_cooperative_scheduler_dispatches_and_reports_live_heartbeat():
    db = FakeJobDatabase()
    runs = []
    scheduler = TaskScheduler(db)
    scheduler.add_task('probe', 'Probe', lambda: runs.append('ran'),
                       trigger='interval', seconds=1)

    scheduler.start()
    try:
        async_runtime.sleep(1.2)
        health = scheduler.get_health()
        assert runs == ['ran']
        assert health['running'] is True
        assert health['heartbeat_ok'] is True
        assert health['activity_age_seconds'] < 3
        assert db.errors == []
    finally:
        scheduler.shutdown()


def test_scheduler_pause_resume_and_manual_run_do_not_use_scheduler_locks():
    db = FakeJobDatabase()
    runs = []
    scheduler = TaskScheduler(db)
    scheduler.add_task('probe', 'Probe', lambda: runs.append('ran'),
                       trigger='interval', seconds=60)
    scheduler.start()
    try:
        assert scheduler.pause_task('probe')['success'] is True
        assert scheduler.get_tasks()[0]['status'] == 'paused'
        assert scheduler.resume_task('probe')['success'] is True
        assert scheduler.run_now('probe')['success'] is True
        async_runtime.sleep(0.05)
        assert runs == ['ran']
        assert scheduler.get_tasks()[0]['status'] == 'scheduled'
    finally:
        scheduler.shutdown()

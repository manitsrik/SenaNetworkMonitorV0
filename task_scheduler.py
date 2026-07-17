"""Cooperative background task scheduler for the Eventlet web runtime.

APScheduler's blocking/background schedulers rely on threading conditions.
Those conditions are replaced by Eventlet in production and have previously
stopped dispatching while the web process stayed healthy.  This small
scheduler uses the application's cooperative clock directly, so there is no
cross-runtime condition or scheduler lock that can silently deadlock.
"""
from datetime import datetime, timedelta
import traceback

import async_runtime


class TaskScheduler:
    """Schedule interval and daily cron jobs as isolated greenlets."""

    def __init__(self, db):
        self.db = db
        self.tasks = {}
        self._running = False
        self._scheduler_greenlet = None
        self._started_at = None
        self._last_scheduler_activity = None

    @staticmethod
    def _interval_seconds(trigger, trigger_args):
        if trigger != 'interval':
            return None
        return max(1, int(trigger_args.get('seconds', 0) or 0) +
                   int(trigger_args.get('minutes', 0) or 0) * 60 +
                   int(trigger_args.get('hours', 0) or 0) * 3600)

    @staticmethod
    def _next_cron_run(now, trigger_args):
        hour = int(trigger_args.get('hour', 0))
        minute = int(trigger_args.get('minute', 0))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    def _calculate_next_run(self, meta, now=None):
        now = now or datetime.now()
        if meta['trigger'] == 'interval':
            return now + timedelta(seconds=self._interval_seconds(meta['trigger'], meta['trigger_args']))
        if meta['trigger'] == 'cron':
            return self._next_cron_run(now, meta['trigger_args'])
        raise ValueError(f"Unsupported trigger: {meta['trigger']}")

    def add_task(self, job_id, name, func, trigger, **trigger_args):
        meta = {
            'name': name,
            'func': func,
            'trigger': trigger,
            'trigger_args': trigger_args,
            'created_at': datetime.now(),
            'next_run': None,
            'paused': False,
            'running': False,
        }
        meta['next_run'] = self._calculate_next_run(meta)
        self.tasks[job_id] = meta

    def start(self):
        if self._running:
            return
        self._running = True
        self._started_at = datetime.now()
        self._last_scheduler_activity = self._started_at
        for meta in self.tasks.values():
            meta['next_run'] = self._calculate_next_run(meta, self._started_at)
        self._scheduler_greenlet = async_runtime.spawn(self._run_loop)
        print(f"[TaskScheduler] Started with {len(self.tasks)} tasks (cooperative eventlet loop)")

    def _run_loop(self):
        while self._running:
            try:
                now = datetime.now()
                self._last_scheduler_activity = now
                for job_id, meta in list(self.tasks.items()):
                    if meta['paused'] or not meta['next_run'] or meta['next_run'] > now:
                        continue

                    # Coalesce missed runs and never overlap the same job.
                    meta['next_run'] = self._calculate_next_run(meta, now)
                    if meta['running']:
                        continue

                    meta['running'] = True
                    async_runtime.spawn(self._execute_job, job_id, meta)
            except Exception as exc:
                # One metadata error must never kill dispatch for every job.
                print(f"[TaskScheduler] Dispatch loop error: {exc}")
                traceback.print_exc()
            async_runtime.sleep(1)

    def _execute_job(self, job_id, meta):
        try:
            self._wrap_job(job_id, meta['name'], meta['func'])()
        finally:
            meta['running'] = False
            self._last_scheduler_activity = datetime.now()

    def is_running(self):
        greenlet = self._scheduler_greenlet
        return bool(self._running and greenlet is not None and not greenlet.dead)

    def get_health(self):
        now = datetime.now()
        last_activity = self._last_scheduler_activity
        activity_age = (now - last_activity).total_seconds() if last_activity else None
        heartbeat_ok = activity_age is not None and activity_age <= 180
        return {
            'running': self.is_running(),
            'heartbeat_ok': heartbeat_ok,
            'last_activity': last_activity.isoformat() if last_activity else None,
            'activity_age_seconds': round(activity_age, 1) if activity_age is not None else None,
        }

    def shutdown(self):
        self._running = False
        if self._scheduler_greenlet is not None and not self._scheduler_greenlet.dead:
            self._scheduler_greenlet.kill()
        print("[TaskScheduler] Shut down")

    def pause_task(self, job_id):
        meta = self.tasks.get(job_id)
        if not meta:
            return {'success': False, 'error': f'Unknown task: {job_id}'}
        meta['paused'] = True
        meta['next_run'] = None
        return {'success': True, 'message': f'Task {job_id} paused'}

    def resume_task(self, job_id):
        meta = self.tasks.get(job_id)
        if not meta:
            return {'success': False, 'error': f'Unknown task: {job_id}'}
        meta['paused'] = False
        meta['next_run'] = self._calculate_next_run(meta)
        return {'success': True, 'message': f'Task {job_id} resumed'}

    def run_now(self, job_id):
        meta = self.tasks.get(job_id)
        if not meta:
            return {'success': False, 'error': f'Unknown task: {job_id}'}
        if meta['running']:
            return {'success': False, 'error': f'Task {job_id} is already running'}
        meta['running'] = True
        async_runtime.spawn(self._execute_job, job_id, meta)
        return {'success': True, 'message': f'Task {job_id} triggered'}

    def reschedule(self, job_id, trigger, **trigger_args):
        meta = self.tasks.get(job_id)
        if not meta:
            return {'success': False, 'error': f'Unknown task: {job_id}'}
        try:
            meta['trigger'] = trigger
            meta['trigger_args'] = trigger_args
            meta['next_run'] = self._calculate_next_run(meta)
            return {'success': True, 'message': f'Task {job_id} rescheduled'}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    def get_tasks(self):
        result = []
        for job_id, meta in self.tasks.items():
            args = meta.get('trigger_args', {})
            trigger_desc = meta['trigger']
            if meta['trigger'] == 'interval':
                seconds = self._interval_seconds(meta['trigger'], args)
                trigger_desc = f'every {seconds}s'
            elif meta['trigger'] == 'cron':
                trigger_desc = f"cron {int(args.get('hour', 0)):02d}:{int(args.get('minute', 0)):02d}"
            result.append({
                'job_id': job_id,
                'name': meta['name'],
                'trigger': trigger_desc,
                'status': 'running' if meta['running'] else ('paused' if meta['paused'] else 'scheduled'),
                'next_run': meta['next_run'].isoformat() if meta['next_run'] else None,
            })
        return result

    def get_history(self, job_id=None, limit=50):
        return self.db.get_job_history(job_id=job_id, limit=limit)

    def _wrap_job(self, job_id, job_name, func):
        db = self.db

        def wrapper():
            timeout_sec = 300
            timer = async_runtime.Timeout(timeout_sec)
            history_id = db.log_job_start(job_id, job_name)
            try:
                result = func()
                summary = None
                if isinstance(result, list):
                    summary = f"{len(result)} items processed"
                elif isinstance(result, dict):
                    summary = str(result)[:200]
                elif result is not None:
                    summary = str(result)[:200]
                db.log_job_complete(history_id, summary)
            except async_runtime.TimeoutError:
                db.log_job_error(history_id, f"Job timed out after {timeout_sec}s")
                print(f"[TaskScheduler] Job {job_id} TIMED OUT after {timeout_sec}s")
            except Exception as exc:
                db.log_job_error(history_id, f"{type(exc).__name__}: {str(exc)}")
                print(f"[TaskScheduler] Job {job_id} failed: {exc}")
                traceback.print_exc()
            finally:
                timer.cancel()

        wrapper.__name__ = f"wrapped_{job_id}"
        return wrapper

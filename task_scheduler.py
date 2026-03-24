"""
Enhanced Task Scheduler for Network Monitor
Wraps APScheduler with job management, history tracking, and admin API support
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime
import traceback
import eventlet


class TaskScheduler:
    """Enhanced scheduler with job management and execution history"""
    
    def __init__(self, db):
        # Use BlockingScheduler with a single-thread executor to ensure all jobs
        # run within the same greenlet context, avoiding thread-switching errors
        executors = {
            'default': ThreadPoolExecutor(2)
        }
        job_defaults = {
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 60
        }
        self.scheduler = BlockingScheduler(executors=executors, job_defaults=job_defaults)
        self.db = db
        self.tasks = {}  # job_id -> task metadata
    
    def add_task(self, job_id, name, func, trigger, **trigger_args):
        """
        Register and schedule a task
        
        Args:
            job_id: Unique identifier (e.g., 'monitor_job')
            name: Human-readable name (e.g., 'Device Monitoring')
            func: The function to execute
            trigger: APScheduler trigger type ('interval', 'cron')
            **trigger_args: Arguments for the trigger (e.g., seconds=30, hour=8)
        """
        # Store metadata
        self.tasks[job_id] = {
            'name': name,
            'func': func,
            'trigger': trigger,
            'trigger_args': trigger_args,
            'created_at': datetime.now(),
        }
        
        # Wrap function with history logging
        wrapped = self._wrap_job(job_id, name, func)
        
        # Add to APScheduler
        self.scheduler.add_job(
            func=wrapped,
            trigger=trigger,
            id=job_id,
            max_instances=1 if job_id == 'monitor_job' else 2,
            misfire_grace_time=30,
            **trigger_args
        )
    
    def start(self):
        """Start the scheduler in a dedicated greenlet"""
        eventlet.spawn(self.scheduler.start)
        print(f"[TaskScheduler] Started with {len(self.tasks)} tasks (eventlet context)")
    
    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()
        print("[TaskScheduler] Shut down")
    
    def pause_task(self, job_id):
        """Pause a scheduled task"""
        if job_id not in self.tasks:
            return {'success': False, 'error': f'Unknown task: {job_id}'}
        try:
            self.scheduler.pause_job(job_id)
            return {'success': True, 'message': f'Task {job_id} paused'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def resume_task(self, job_id):
        """Resume a paused task"""
        if job_id not in self.tasks:
            return {'success': False, 'error': f'Unknown task: {job_id}'}
        try:
            self.scheduler.resume_job(job_id)
            return {'success': True, 'message': f'Task {job_id} resumed'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def run_now(self, job_id):
        """Run a task immediately (one-shot)"""
        if job_id not in self.tasks:
            return {'success': False, 'error': f'Unknown task: {job_id}'}
        try:
            task = self.tasks[job_id]
            wrapped = self._wrap_job(job_id, task['name'], task['func'])
            # Add a one-shot job
            self.scheduler.add_job(
                func=wrapped,
                trigger='date',
                id=f'{job_id}_manual',
                replace_existing=True
            )
            return {'success': True, 'message': f'Task {job_id} triggered'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def reschedule(self, job_id, trigger, **trigger_args):
        """Change task schedule"""
        if job_id not in self.tasks:
            return {'success': False, 'error': f'Unknown task: {job_id}'}
        try:
            self.scheduler.reschedule_job(job_id, trigger=trigger, **trigger_args)
            self.tasks[job_id]['trigger'] = trigger
            self.tasks[job_id]['trigger_args'] = trigger_args
            return {'success': True, 'message': f'Task {job_id} rescheduled'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_tasks(self):
        """Get all tasks with their current status and next run time"""
        result = []
        for job_id, meta in self.tasks.items():
            job = self.scheduler.get_job(job_id)
            
            next_run = None
            status = 'unknown'
            if job:
                next_run = job.next_run_time.isoformat() if job.next_run_time else None
                status = 'paused' if job.next_run_time is None else 'scheduled'
            else:
                status = 'removed'
            
            # Build trigger description
            trigger_desc = meta['trigger']
            args = meta.get('trigger_args', {})
            if meta['trigger'] == 'interval' and 'seconds' in args:
                trigger_desc = f"every {args['seconds']}s"
            elif meta['trigger'] == 'cron':
                parts = []
                if 'hour' in args:
                    parts.append(f"{args['hour']:02d}:{args.get('minute', 0):02d}")
                trigger_desc = f"cron {' '.join(parts)}" if parts else 'cron'
            
            result.append({
                'job_id': job_id,
                'name': meta['name'],
                'trigger': trigger_desc,
                'status': status,
                'next_run': next_run,
            })
        
        return result
    
    def get_history(self, job_id=None, limit=50):
        """Get job execution history from database"""
        return self.db.get_job_history(job_id=job_id, limit=limit)
    
    def _wrap_job(self, job_id, job_name, func):
        """Wrap a job function with history logging"""
        db = self.db
        
        def wrapper():
            # Mandatory timeout for ALL background jobs to prevent global stall
            # monitor_job has a 30s interval, give it 120s max. Others 300s.
            timeout_sec = 300 if job_id == 'monitor_job' else 300
            
            import eventlet.timeout
            timer = eventlet.timeout.Timeout(timeout_sec)
            
            history_id = db.log_job_start(job_id, job_name)
            try:
                result = func()
                # Generate summary from result
                summary = None
                if isinstance(result, list):
                    summary = f"{len(result)} items processed"
                elif isinstance(result, dict):
                    summary = str(result)[:200]
                elif result is not None:
                    summary = str(result)[:200]
                
                db.log_job_complete(history_id, summary)
            except eventlet.timeout.Timeout:
                db.log_job_error(history_id, f"Job timed out after {timeout_sec}s")
                print(f"[TaskScheduler] Job {job_id} TIMED OUT after {timeout_sec}s")
            except Exception as e:
                db.log_job_error(history_id, f"{type(e).__name__}: {str(e)}")
                print(f"[TaskScheduler] Job {job_id} failed: {e}")
                traceback.print_exc()
            finally:
                timer.cancel()
        
        wrapper.__name__ = f"wrapped_{job_id}"
        return wrapper

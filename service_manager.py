"""
Service Manager for Network Monitor
Centralized lifecycle management for all background services
"""
from datetime import datetime


class ServiceManager:
    """Manages lifecycle of all background services"""
    
    def __init__(self):
        self.services = {}
        self._start_time = datetime.now()
    
    def register(self, name, service, start_fn=None, stop_fn=None):
        """
        Register a background service
        
        Args:
            name: Unique service name (e.g., 'monitor', 'telegram')
            service: The service object instance
            start_fn: Method name to call on start (string) or callable
            stop_fn: Method name to call on stop (string) or callable
        """
        self.services[name] = {
            'service': service,
            'start_fn': start_fn,
            'stop_fn': stop_fn,
            'status': 'registered',
            'started_at': None,
            'error': None,
        }
    
    def start(self, name):
        """Start a single service by name"""
        if name not in self.services:
            print(f"[ServiceManager] Unknown service: {name}")
            return False
        
        info = self.services[name]
        try:
            fn = info['start_fn']
            if fn:
                if callable(fn):
                    fn()
                else:
                    getattr(info['service'], fn)()
            info['status'] = 'running'
            info['started_at'] = datetime.now()
            info['error'] = None
            print(f"[ServiceManager] Started: {name}")
            return True
        except Exception as e:
            info['status'] = 'error'
            info['error'] = str(e)
            print(f"[ServiceManager] Failed to start {name}: {e}")
            return False
    
    def stop(self, name):
        """Stop a single service by name"""
        if name not in self.services:
            return False
        
        info = self.services[name]
        try:
            fn = info['stop_fn']
            if fn:
                if callable(fn):
                    fn()
                else:
                    getattr(info['service'], fn)()
            info['status'] = 'stopped'
            print(f"[ServiceManager] Stopped: {name}")
            return True
        except Exception as e:
            info['status'] = 'error'
            info['error'] = str(e)
            print(f"[ServiceManager] Error stopping {name}: {e}")
            return False
    
    def start_all(self):
        """Start all registered services"""
        print(f"[ServiceManager] Starting {len(self.services)} services...")
        for name in self.services:
            self.start(name)
    
    def stop_all(self):
        """Gracefully stop all services (reverse order)"""
        print(f"[ServiceManager] Stopping all services...")
        for name in reversed(list(self.services.keys())):
            self.stop(name)
    
    def restart(self, name):
        """Restart a specific service"""
        self.stop(name)
        return self.start(name)
    
    def get_status(self):
        """Get status of all services"""
        uptime = (datetime.now() - self._start_time).total_seconds()
        
        services_status = []
        for name, info in self.services.items():
            svc_uptime = None
            if info['started_at']:
                svc_uptime = (datetime.now() - info['started_at']).total_seconds()
            
            services_status.append({
                'name': name,
                'status': info['status'],
                'started_at': info['started_at'].isoformat() if info['started_at'] else None,
                'uptime_seconds': round(svc_uptime) if svc_uptime else None,
                'error': info['error'],
            })
        
        return {
            'server_uptime_seconds': round(uptime),
            'total_services': len(self.services),
            'running': sum(1 for s in services_status if s['status'] == 'running'),
            'services': services_status,
        }

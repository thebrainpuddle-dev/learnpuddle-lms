"""Gunicorn production configuration for LearnPuddle LMS."""
import multiprocessing
import os

# Server socket
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
backlog = 2048

# Worker processes
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", 4))
worker_connections = 1000
timeout = int(os.getenv("GUNICORN_TIMEOUT", 30))
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "learnpuddle"

# Security
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Graceful restart
graceful_timeout = 30
preload_app = True

# SSL (handled by nginx, but available if needed)
# keyfile = None
# certfile = None

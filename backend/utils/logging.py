# utils/logging.py
"""
Structured JSON logging configuration with contextual fields.

This module provides:
1. JSON-formatted log output for easy parsing by log aggregators
2. Automatic inclusion of request context (request_id, tenant_id, user_id)
3. Thread-local storage for passing context through the call stack

Usage in views/services:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("User action", extra={"action": "login", "success": True})

The JSON output will include:
    {
        "timestamp": "2024-01-15T10:30:00.123456Z",
        "level": "INFO",
        "logger": "apps.users.views",
        "message": "User action",
        "request_id": "abc-123",
        "tenant_id": "def-456",
        "user_id": "ghi-789",
        "action": "login",
        "success": true
    }
"""

import logging
import threading
from datetime import datetime, timezone
from pythonjsonlogger import jsonlogger


# Thread-local storage for request context
_request_context = threading.local()


def set_request_context(request_id=None, tenant_id=None, user_id=None):
    """
    Set the current request context for logging.
    Called by middleware at the start of each request.
    """
    _request_context.request_id = request_id
    _request_context.tenant_id = tenant_id
    _request_context.user_id = user_id


def clear_request_context():
    """
    Clear the request context after request completes.
    Called by middleware at the end of each request.
    """
    _request_context.request_id = None
    _request_context.tenant_id = None
    _request_context.user_id = None


def get_request_context():
    """Get the current request context."""
    return {
        'request_id': getattr(_request_context, 'request_id', None),
        'tenant_id': getattr(_request_context, 'tenant_id', None),
        'user_id': getattr(_request_context, 'user_id', None),
    }


class ContextualJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter that automatically includes request context.
    
    Output format:
    {
        "timestamp": "ISO8601 timestamp",
        "level": "INFO|WARNING|ERROR|...",
        "logger": "module.name",
        "message": "Log message",
        "request_id": "uuid or None",
        "tenant_id": "uuid or None", 
        "user_id": "uuid or None",
        ... any extra fields ...
    }
    """
    
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp in ISO 8601 format
        log_record['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        # Add standard fields
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        
        # Add request context from thread-local storage
        context = get_request_context()
        log_record['request_id'] = context['request_id']
        log_record['tenant_id'] = context['tenant_id']
        log_record['user_id'] = context['user_id']
        
        # Add exception info if present
        if record.exc_info:
            log_record['exc_info'] = self.formatException(record.exc_info)
        
        # Move message to consistent position
        if 'message' not in log_record:
            log_record['message'] = record.getMessage()


def get_logging_config(log_level='INFO', use_json=True):
    """
    Generate Django LOGGING configuration.
    
    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_json: Whether to use JSON format (True for production, False for dev)
    
    Returns:
        dict: Django LOGGING configuration
    """
    if use_json:
        formatter_class = 'utils.logging.ContextualJsonFormatter'
        formatter_config = {
            '()': formatter_class,
        }
    else:
        # Simple format for local development
        formatter_config = {
            'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        }
    
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'json': formatter_config,
            'simple': {
                'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S',
            },
        },
        'filters': {
            'require_debug_false': {
                '()': 'django.utils.log.RequireDebugFalse',
            },
            'require_debug_true': {
                '()': 'django.utils.log.RequireDebugTrue',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'json' if use_json else 'simple',
            },
            'console_debug': {
                'class': 'logging.StreamHandler',
                'formatter': 'simple',
                'filters': ['require_debug_true'],
            },
        },
        'root': {
            'handlers': ['console'],
            'level': log_level,
        },
        'loggers': {
            'django': {
                'handlers': ['console'],
                'level': log_level,
                'propagate': False,
            },
            'django.request': {
                'handlers': ['console'],
                'level': 'WARNING',  # Reduce noise from request logs
                'propagate': False,
            },
            'django.db.backends': {
                'handlers': ['console'],
                'level': 'WARNING',  # Reduce SQL noise
                'propagate': False,
            },
            'celery': {
                'handlers': ['console'],
                'level': log_level,
                'propagate': False,
            },
            'apps': {
                'handlers': ['console'],
                'level': log_level,
                'propagate': False,
            },
            'utils': {
                'handlers': ['console'],
                'level': log_level,
                'propagate': False,
            },
        },
    }

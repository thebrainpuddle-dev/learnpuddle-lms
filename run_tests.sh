#!/bin/bash
# Test runner script - uses venv pytest
export DJANGO_SETTINGS_MODULE=config.settings
cd /Users/rakeshreddy/LMS/backend
/Users/rakeshreddy/LMS/backend/venv/bin/pytest "$@"

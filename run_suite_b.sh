#!/bin/bash
export PYTHONPATH=/Users/rakeshreddy/LMS/backend/venv/lib/python3.13/site-packages:/Users/rakeshreddy/LMS/backend
export DJANGO_SETTINGS_MODULE=config.settings
cd /Users/rakeshreddy/LMS/backend
/usr/local/bin/python3 -m pytest apps/users/tests_scim_cross_tenant.py -v --tb=short 2>&1 | tail -100

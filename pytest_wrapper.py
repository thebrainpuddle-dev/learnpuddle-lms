"""Pytest wrapper that adds venv to sys.path before running tests."""
import sys
import os

# Add venv site-packages to path
sys.path.insert(0, '/Users/rakeshreddy/LMS/backend/venv/lib/python3.13/site-packages')
sys.path.insert(0, '/Users/rakeshreddy/LMS/backend')

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Change to backend directory
os.chdir('/Users/rakeshreddy/LMS/backend')

import pytest
sys.exit(pytest.main(sys.argv[1:]))

"""Concrete PDF parsing adapters.

Importing this package triggers @register_adapter on every adapter
module. Mineru cloud is the only Phase 10 first-cut provider.
"""
from . import mineru_cloud  # noqa: F401  - side-effect: register_adapter

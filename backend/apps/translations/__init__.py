"""TASK-058 — Auto-Translation Service.

App provides admin-triggered stored translations of Course/Module/Content
translatable fields into allowlisted target languages. Provider abstraction
(OpenRouter LLM → Azure Translator → deterministic stub) is in
``providers.py``.
"""

default_app_config = "apps.translations.apps.TranslationsConfig"

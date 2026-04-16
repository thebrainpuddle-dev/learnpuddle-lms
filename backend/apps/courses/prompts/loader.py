"""Load + cache prompt template files.

Templates live as .md files in this directory and are loaded once per process.
"""
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Load a prompt file by name (without extension). Cached.

    Example: load_prompt('agent_profiles') -> content of agent_profiles.md
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")

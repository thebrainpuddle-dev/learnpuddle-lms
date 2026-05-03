"""Conversation/peer/whiteboard summarizers for the director + agent prompts.

Mirrors upstream `lib/orchestration/summarizers/`. Each module is a small,
pure helper that compresses a slice of OrchestratorState into a string
suitable for prompt injection.

Modules:
    conversation_summary — render the last N user/assistant turns
                           (MAIC-109).
"""
from apps.maic.orchestration.summarizers.conversation_summary import (
    summarize_conversation,
)

__all__ = ["summarize_conversation"]

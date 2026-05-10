"""Concrete media-generation adapters.

Importing this package triggers registration of every adapter module
listed below — each adapter file uses the @register_adapter decorator
at module bottom, so importing the module is what populates
apps.maic.media.providers._REGISTRY.

To register all shipped adapters from elsewhere, just do:

    from apps.maic.media import adapters  # noqa: F401

Phase 9 ships one reference adapter (OpenAI image, MAIC-903) and 10
sibling adapters (MAIC-904 → MAIC-913) that copy its shape.
"""
from . import openai_image  # noqa: F401  - side-effect: register_adapter
from . import qwen_image    # noqa: F401  - side-effect: register_adapter (MAIC-904)
from . import grok_image    # noqa: F401  - side-effect: register_adapter (MAIC-905)
from . import minimax_image # noqa: F401  - side-effect: register_adapter (MAIC-906)
from . import nano_banana   # noqa: F401  - side-effect: register_adapter (MAIC-907)
from . import seedream      # noqa: F401  - side-effect: register_adapter (MAIC-908)
from . import stability     # noqa: F401  - side-effect: register_adapter (MAIC-909)
from . import veo           # noqa: F401  - side-effect: register_adapter (MAIC-910)
from . import kling         # noqa: F401  - side-effect: register_adapter (MAIC-911)
from . import minimax_video # noqa: F401  - side-effect: register_adapter (MAIC-912)

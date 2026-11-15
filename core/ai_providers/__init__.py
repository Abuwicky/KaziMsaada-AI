"""Built-in, opt-in AI provider adapters."""

from __future__ import annotations

from ..ai_client import register_ai_provider
from .google_ai_studio import GoogleAIStudioProvider


def register_builtin_providers() -> None:
    """Register bundled adapters without contacting any provider.

    An adapter registered by an approved integration before this point is left
    in place, so custom deployments can replace the bundled default explicitly.
    """

    try:
        register_ai_provider("GoogleAiStudio", GoogleAIStudioProvider)
    except ValueError:
        # A matching adapter was already registered by the application.
        pass


__all__ = ["GoogleAIStudioProvider", "register_builtin_providers"]

"""Provider-neutral AI feedback configuration and adapter boundary.

Provider adapters register here. The built-in Google AI Studio adapter is
available only when secure application secrets configure it; ordinary
Streamlit reruns never call the network. Credentials are read only from
Streamlit application secrets and are never included in messages, logs, or
object representations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


class AIError(Exception):
    """Base class for AI configuration and request failures."""


class AIProviderNotConfigured(AIError):
    """Raised when no AI provider is selected or no adapter is installed."""


class AIProviderError(AIError):
    """Raised when an approved provider cannot produce usable output."""


@dataclass(frozen=True)
class FeedbackRequest:
    """The minimum context sent to an AI provider for answer feedback."""

    target_role: str
    category: str
    difficulty: str
    question: str
    answer: str


@dataclass(frozen=True)
class QuestionRequest:
    """The minimum context sent to an AI provider for a follow-up question."""

    target_role: str
    category: str
    difficulty: str
    previous_questions: tuple[str, ...]


@dataclass(frozen=True)
class ModelAnswerRequest:
    """The minimum context sent to an AI provider for a model answer."""

    target_role: str
    category: str
    difficulty: str
    question: str


class AIProvider(Protocol):
    """Minimal interface an approved provider adapter must implement."""

    name: str

    def generate_feedback(
        self,
        request: FeedbackRequest,
    ) -> Mapping[str, Any]:
        """Return feedback containing relevance, clarity, structure and examples."""


class AIQuestionProvider(Protocol):
    """Optional interface for providers that can generate follow-up questions."""

    name: str

    def generate_question(
        self,
        request: QuestionRequest,
    ) -> Mapping[str, Any]:
        """Return one new practice question with assessment and structure notes."""


class AIModelAnswerProvider(Protocol):
    """Optional interface for providers that can draft a model answer."""

    name: str

    def generate_model_answer(
        self,
        request: ModelAnswerRequest,
    ) -> Mapping[str, Any]:
        """Return one practice model answer with STAR notes and tips."""


@dataclass(frozen=True)
class AISettings:
    provider: str | None = None
    model: str | None = None
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 20.0
    max_output_chars: int = 4000

    @property
    def configured(self) -> bool:
        return bool(str(self.provider or "").strip())


@dataclass(frozen=True)
class AIAvailability:
    configured: bool
    available: bool
    message: str


ProviderFactory = Callable[[AISettings], AIProvider]

_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {}
_BUILTIN_PROVIDERS_REGISTERED = False


def _provider_key(provider_name: str) -> str:
    """Normalise provider names so spelling and separators do not matter."""

    return "".join(
        character
        for character in str(provider_name or "").casefold()
        if character.isalnum()
    )


def _ensure_builtin_providers() -> None:
    """Register bundled adapters once, without making any network request."""

    global _BUILTIN_PROVIDERS_REGISTERED
    if _BUILTIN_PROVIDERS_REGISTERED:
        return

    try:
        from .ai_providers import register_builtin_providers

        register_builtin_providers()
    except Exception:
        # Optional adapters must never prevent local practice from working.
        _BUILTIN_PROVIDERS_REGISTERED = True
        return

    _BUILTIN_PROVIDERS_REGISTERED = True


def _section_from_secrets(secrets: Any) -> Mapping[str, Any]:
    try:
        section = secrets.get("ai", {})
    except Exception:
        return {}
    return section if isinstance(section, Mapping) else {}


def _streamlit_secrets() -> Any:
    try:
        import streamlit as st

        return st.secrets
    except Exception:
        return {}


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def load_ai_settings(secrets: Mapping[str, Any] | None = None) -> AISettings:
    """Load AI settings from secure application configuration.

    The ``secrets`` argument exists for tests and approved integrations. In the
    application, Streamlit's ``st.secrets`` is used. Missing configuration is a
    normal state, not an error.
    """

    section = _section_from_secrets(
        _streamlit_secrets() if secrets is None else secrets
    )
    provider = str(section.get("provider", "") or "").strip() or None
    model = str(section.get("model", "") or "").strip() or None
    api_key = str(section.get("api_key", "") or "").strip() or None

    return AISettings(
        provider=provider,
        model=model,
        api_key=api_key,
        timeout_seconds=_clamp_float(
            section.get("timeout_seconds"), 20.0, 5.0, 60.0
        ),
        max_output_chars=_clamp_int(
            section.get("max_output_chars"), 4000, 500, 8000
        ),
    )


def register_ai_provider(
    provider_name: str,
    factory: ProviderFactory,
    *,
    replace: bool = False,
) -> None:
    """Register an approved adapter without changing the interview UI."""

    name = str(provider_name or "").strip()
    key = _provider_key(name)
    if not key:
        raise ValueError("A provider name is required.")
    if key in _PROVIDER_FACTORIES and not replace:
        raise ValueError("That AI provider adapter is already registered.")
    _PROVIDER_FACTORIES[key] = factory


def get_ai_provider(settings: AISettings | None = None) -> AIProvider | None:
    """Return an approved provider adapter, or ``None`` when not configured."""

    _ensure_builtin_providers()
    settings = settings or load_ai_settings()
    if not settings.configured:
        return None

    factory = _PROVIDER_FACTORIES.get(_provider_key(str(settings.provider)))
    if factory is None:
        raise AIProviderNotConfigured(
            "An AI provider is configured, but no approved adapter is installed."
        )

    try:
        provider = factory(settings)
    except Exception as error:
        raise AIProviderError("The AI provider adapter could not start.") from error

    if not callable(getattr(provider, "generate_feedback", None)):
        raise AIProviderError("The AI provider adapter does not implement feedback.")
    return provider


def ai_status(settings: AISettings | None = None) -> AIAvailability:
    """Describe availability without exposing credentials or provider details."""

    settings = settings or load_ai_settings()
    if not settings.configured:
        return AIAvailability(
            configured=False,
            available=False,
            message=(
                "AI practice features are not configured yet. Practice, saved "
                "sessions, manual STAR review and local question-bank guidance are "
                "still available."
            ),
        )

    try:
        provider = get_ai_provider(settings)
    except AIProviderNotConfigured:
        return AIAvailability(
            configured=True,
            available=False,
            message=(
                "An AI provider is configured, but no approved adapter is installed. "
                "Local question-bank guidance and manual STAR practice will be used."
            ),
        )
    except AIProviderError:
        return AIAvailability(
            configured=True,
            available=False,
            message=(
                "AI settings are present, but the provider is not ready. Local "
                "question-bank guidance and manual STAR practice will be used. "
                "Check the model and API key in .streamlit/secrets.toml."
            ),
        )

    if provider is None:
        return AIAvailability(
            configured=False,
            available=False,
            message=(
                "AI practice features are not configured yet. Local question-bank "
                "guidance and manual STAR practice will be used."
            ),
        )
    return AIAvailability(
        configured=True,
        available=True,
        message="AI-assisted interview practice is configured for this workspace.",
    )

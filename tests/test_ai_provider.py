"""Tests for the optional Google AI Studio adapter.

No test in this module contacts Google or uses a real credential. HTTP calls are
replaced with local fakes so request shape and error handling can be checked
deterministically.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ai_client import (  # noqa: E402
    AIProviderError,
    AISettings,
    FeedbackRequest,
    ai_status,
    get_ai_provider,
    load_ai_settings,
)
from core.ai_providers.google_ai_studio import (  # noqa: E402
    GoogleAIStudioProvider,
)


class FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._raw if size < 0 else self._raw[:size]


def test_settings(
    *,
    provider: str = "GoogleAiStudio",
    model: str = "gemini-2.5-flash",
    api_key: str = "test-key-not-a-real-credential",
    timeout_seconds: float = 12.5,
) -> AISettings:
    return load_ai_settings(
        {
            "ai": {
                "provider": provider,
                "model": model,
                "api_key": api_key,
                "timeout_seconds": timeout_seconds,
                "max_output_chars": 4000,
            }
        }
    )


def sample_feedback() -> dict:
    return {
        "relevance": "The answer connects the example to the target role.",
        "clarity": "The answer is easy to follow.",
        "structure": "The result could be stated more clearly.",
        "examples": "The answer includes a concrete attachment example.",
        "suggestions": [
            "State the result in one sentence.",
            "Link the example back to the role.",
        ],
        "summary": "A useful practice answer with a clear example.",
    }


class GoogleProviderRegistrationTests(unittest.TestCase):
    def test_provider_is_registered_and_status_does_not_use_network(self) -> None:
        for provider_name in (
            "GoogleAiStudio",
            "google_ai_studio",
            "Google AI Studio",
        ):
            with self.subTest(provider_name=provider_name):
                settings = test_settings(provider=provider_name)
                with patch(
                    "core.ai_providers.google_ai_studio.urlopen",
                    side_effect=AssertionError("status must not call the network"),
                ):
                    status = ai_status(settings)
                    provider = get_ai_provider(settings)

                self.assertTrue(status.configured)
                self.assertTrue(status.available)
                self.assertIsInstance(provider, GoogleAIStudioProvider)
                self.assertEqual(provider.name, "Google AI Studio")

    def test_incomplete_settings_are_reported_without_crashing(self) -> None:
        missing_key = test_settings(api_key="")
        status = ai_status(missing_key)
        self.assertTrue(status.configured)
        self.assertFalse(status.available)
        self.assertIn("not ready", status.message)
        with self.assertRaises(AIProviderError):
            GoogleAIStudioProvider(missing_key)

        missing_model = test_settings(model="")
        status = ai_status(missing_model)
        self.assertTrue(status.configured)
        self.assertFalse(status.available)
        with self.assertRaises(AIProviderError):
            GoogleAIStudioProvider(missing_model)

    def test_unknown_provider_remains_unavailable(self) -> None:
        settings = test_settings(
            provider="NotRegistered",
            model="some-model",
            api_key="some-key",
        )
        status = ai_status(settings)
        self.assertTrue(status.configured)
        self.assertFalse(status.available)
        self.assertIn("no approved adapter", status.message)


class GoogleProviderRequestTests(unittest.TestCase):
    def test_request_contains_only_minimum_context_and_parses_feedback(self) -> None:
        provider = GoogleAIStudioProvider(test_settings())
        request = FeedbackRequest(
            target_role="ICT support officer",
            category="Experience",
            difficulty="intermediate",
            question="Walk me through a project you are proud of.",
            answer=(
                "During my attachment I restored a staff laptop's network "
                "connection and documented the fix."
            ),
        )
        captured: dict = {}

        def fake_urlopen(http_request, timeout):
            captured["url"] = http_request.full_url
            captured["headers"] = {
                key.casefold(): value
                for key, value in http_request.header_items()
            }
            captured["body"] = json.loads(http_request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeHttpResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": json.dumps(sample_feedback())}
                                ]
                            }
                        }
                    ]
                }
            )

        with patch(
            "core.ai_providers.google_ai_studio.urlopen",
            side_effect=fake_urlopen,
        ):
            result = provider.generate_feedback(request)

        self.assertEqual(result["suggestions"], sample_feedback()["suggestions"])
        self.assertEqual(
            captured["url"],
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent",
        )
        self.assertNotIn("test-key-not-a-real-credential", captured["url"])
        self.assertEqual(
            captured["headers"]["x-goog-api-key"],
            "test-key-not-a-real-credential",
        )
        self.assertEqual(captured["timeout"], 12.5)

        body = captured["body"]
        prompt = body["contents"][0]["parts"][0]["text"]
        self.assertIn("ICT support officer", prompt)
        self.assertIn("Experience", prompt)
        self.assertIn("intermediate", prompt)
        self.assertIn(request.question, prompt)
        self.assertIn(request.answer, prompt)
        self.assertEqual(
            body["generationConfig"]["responseMimeType"],
            "application/json",
        )
        self.assertIn("responseSchema", body["generationConfig"])
        self.assertNotIn("education", prompt.casefold())
        self.assertNotIn("profile name", prompt.casefold())

    def test_code_fenced_json_is_accepted(self) -> None:
        provider = GoogleAIStudioProvider(test_settings())
        request = FeedbackRequest(
            target_role="Customer service assistant",
            category="Customer service",
            difficulty="beginner",
            question="How do you keep records accurate?",
            answer="I read details back and check them before saving.",
        )
        fenced = "```json\n" + json.dumps(sample_feedback()) + "\n```"
        response = FakeHttpResponse(
            {
                "candidates": [
                    {"content": {"parts": [{"text": fenced}]}}
                ]
            }
        )

        with patch(
            "core.ai_providers.google_ai_studio.urlopen",
            return_value=response,
        ):
            result = provider.generate_feedback(request)

        self.assertEqual(result["summary"], sample_feedback()["summary"])

    def test_rate_limit_error_is_safe_and_actionable(self) -> None:
        provider = GoogleAIStudioProvider(test_settings())
        request = FeedbackRequest(
            target_role="ICT support officer",
            category="Experience",
            difficulty="intermediate",
            question="Tell me about a project.",
            answer="I completed a project and documented the result.",
        )

        def fake_urlopen(http_request, timeout):
            raise HTTPError(
                http_request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b""),
            )

        with patch(
            "core.ai_providers.google_ai_studio.urlopen",
            side_effect=fake_urlopen,
        ):
            with self.assertRaises(AIProviderError) as caught:
                provider.generate_feedback(request)

        message = str(caught.exception)
        self.assertIn("rate limit", message.casefold())
        self.assertNotIn("test-key-not-a-real-credential", message)

    def test_malformed_provider_responses_are_rejected(self) -> None:
        provider = GoogleAIStudioProvider(test_settings())
        request = FeedbackRequest(
            target_role="Graduate trainee",
            category="Graduate",
            difficulty="beginner",
            question="What did you learn from your studies?",
            answer="I learned to plan work and check details.",
        )

        responses = (
            {"candidates": []},
            {
                "candidates": [
                    {"content": {"parts": [{"text": "not-json"}]}}
                ]
            },
            {"unexpected": "shape"},
        )
        for payload in responses:
            with self.subTest(payload=payload):
                with patch(
                    "core.ai_providers.google_ai_studio.urlopen",
                    return_value=FakeHttpResponse(payload),
                ):
                    with self.assertRaises(AIProviderError):
                        provider.generate_feedback(request)


if __name__ == "__main__":
    unittest.main()

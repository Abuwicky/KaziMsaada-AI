"""Authentication gate and owner-identity tests.

These tests never start Streamlit and never call an identity provider. They
exercise the configuration decisions that decide whether personal data may be
loaded at all.
"""

from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from core.auth import auth_configured, auth_required
from core.workspace import owner_id_from_identity


def _sections(values):
    return lambda name: values.get(name, {})


class AuthGateTests(unittest.TestCase):
    def test_cloud_without_auth_configuration_fails_closed(self) -> None:
        with patch("core.auth._secret_section", side_effect=_sections({})), patch(
            "core.auth.is_cloud_deployment", return_value=True
        ):
            self.assertTrue(auth_required())
            self.assertFalse(auth_configured())

    def test_auth_section_requires_sign_in_even_on_a_local_host(self) -> None:
        with patch(
            "core.auth._secret_section",
            side_effect=_sections({"auth": {"client_id": "test-client"}}),
        ), patch("core.auth.is_cloud_deployment", return_value=False):
            self.assertTrue(auth_configured())
            self.assertTrue(auth_required())

    def test_explicit_require_auth_true_requires_sign_in(self) -> None:
        with patch(
            "core.auth._secret_section",
            side_effect=_sections({"app": {"require_auth": True}}),
        ), patch("core.auth.is_cloud_deployment", return_value=False):
            self.assertTrue(auth_required())

    def test_explicit_require_auth_false_wins_even_on_cloud(self) -> None:
        with patch(
            "core.auth._secret_section",
            side_effect=_sections({"app": {"require_auth": False}}),
        ), patch("core.auth.is_cloud_deployment", return_value=True):
            self.assertFalse(auth_required())

    def test_owner_identity_is_stable_opaque_and_account_specific(self) -> None:
        first = owner_id_from_identity("person@example.com")
        again = owner_id_from_identity("person@example.com")
        other = owner_id_from_identity("other@example.com")

        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertNotIn("person", first)
        self.assertNotIn("example.com", first)
        self.assertTrue(re.fullmatch(r"[a-f0-9]{32}", first))


if __name__ == "__main__":
    unittest.main()

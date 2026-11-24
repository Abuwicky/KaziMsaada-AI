"""Sign-in gating and truthful workspace messaging.

The app supports two modes:

* authenticated mode, using Streamlit's OpenID Connect integration
  (``st.login`` / ``st.user``); and
* local mode for the original single-user desktop/CLI workflow.

Signed-in users share one SQLite database but every personal row is filtered by
an opaque owner ID. The mentor directory remains intentionally shared.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from .workspace import (
    clear_current_owner_id,
    get_current_owner_id,
    owner_id_from_identity,
    set_current_owner_id,
    set_strict_owner_mode,
)

_CLOUD_ENV_VARS = (
    "STREAMLIT_SHARING_MODE",
    "STREAMLIT_CLOUD",
    "IS_STREAMLIT_CLOUD",
    "KAZIMSAADA_CLOUD",
)


def _secret_section(name: str):
    try:
        section = st.secrets.get(name, {})
    except Exception:
        return {}
    return section if hasattr(section, "get") else {}


def auth_configured() -> bool:
    return bool(_secret_section("auth"))


def _running_from_cloud_mount() -> bool:
    """Streamlit Community Cloud runs apps from /mount/src/<repo>."""

    try:
        return Path(__file__).resolve().as_posix().startswith("/mount/src/")
    except OSError:
        return False


def is_cloud_deployment() -> bool:
    if any(os.getenv(name) for name in _CLOUD_ENV_VARS):
        return True
    if _running_from_cloud_mount():
        return True
    app_section = _secret_section("app")
    return str(app_section.get("environment", "")).strip().lower() == "cloud"


def auth_required() -> bool:
    """Return whether this deployment must require a signed-in user.

    An explicit ``[app] require_auth`` setting wins. Otherwise authentication is
    required when it is configured, or when a Streamlit Cloud environment is
    detected. A plain local run keeps the original no-login experience.
    """

    app_section = _secret_section("app")
    explicit = app_section.get("require_auth")
    if explicit is not None:
        return bool(explicit)
    return auth_configured() or is_cloud_deployment()


def _user_proxy():
    try:
        if getattr(st.user, "is_logged_in", False):
            return st.user
    except Exception:
        pass
    return None


def _user_value(user, key: str):
    if user is None:
        return None
    try:
        value = user.get(key)
    except Exception:
        value = None
    if value:
        return value
    try:
        return getattr(user, key, None)
    except Exception:
        return None


def current_user():
    return _user_proxy()


def is_authenticated() -> bool:
    return _user_proxy() is not None


def current_user_name() -> str:
    user = _user_proxy()
    if user is None:
        return ""
    for key in ("name", "email", "preferred_username"):
        value = _user_value(user, key)
        if value:
            return str(value)
    return "Signed-in user"


def _identity_value() -> str:
    user = _user_proxy()
    if user is None:
        return ""
    for key in ("sub", "email", "preferred_username"):
        value = _user_value(user, key)
        if value:
            return str(value)
    return ""


def current_owner_id() -> str:
    return get_current_owner_id()


def _render_login() -> None:
    st.markdown(
        """
        <div class="km-page-head">
          <div class="km-eyebrow">KaziMsaada AI</div>
          <h1>Sign in to your workspace</h1>
          <p>Your profiles, CV drafts, practice history and mentor bookings are
          kept separate from other signed-in users.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info(
        "Sign-in is required on this deployment. The app does not show saved "
        "profiles before you sign in."
    )
    if st.button("Sign in", type="primary", key="workspace_sign_in"):
        try:
            st.login()
        except Exception as error:
            st.error(
                "Sign-in could not start. The deployment's authentication "
                "settings need to be checked."
            )
            with st.expander("Technical details"):
                st.code(f"{type(error).__name__}: {error}", language=None)
    st.caption(
        "Authentication uses your organisation's OpenID Connect provider. "
        "KaziMsaada AI receives an opaque account identifier and your display "
        "name; it does not receive your password."
    )


def _render_auth_setup_required() -> None:
    st.markdown(
        """
        <div class="km-page-head">
          <div class="km-eyebrow">KaziMsaada AI</div>
          <h1>Private workspace setup required</h1>
          <p>This deployment is configured to require sign-in, but no OpenID
          Connect provider is configured yet.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.warning(
        "Saved profiles are not loaded until authentication is configured. "
        "Do not remove this guard on a public deployment."
    )
    st.markdown("Add an `[auth]` section to Streamlit secrets. Example:")
    st.code(
        """[auth]
redirect_uri = "https://your-app.example.com/oauth2callback"
cookie_secret = "replace-with-a-long-random-secret"
client_id = "your-oidc-client-id"
client_secret = "your-oidc-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[app]
require_auth = true""",
        language="toml",
    )
    st.caption(
        "The redirect URI must be the deployed app URL followed by "
        "`/oauth2callback`. Restart or reboot the app after saving secrets."
    )


def require_workspace_owner() -> str:
    """Set and return the owner for this run, rendering a gate when required.

    Fail-closed: whenever sign-in is required, strict owner mode is switched on
    and any stale owner from a previous rerun is cleared first, so personal data
    is unreachable until a signed-in identity has been resolved.
    """

    clear_current_owner_id()

    if not auth_required():
        set_strict_owner_mode(False)
        return set_current_owner_id("local")

    set_strict_owner_mode(True)

    if not auth_configured():
        _render_auth_setup_required()
        st.stop()
        return ""

    user = _user_proxy()
    if user is None:
        _render_login()
        st.stop()
        return ""

    identity = _identity_value()
    if not identity:
        st.error(
            "Sign-in succeeded, but the provider did not return a stable account "
            "identifier. Please sign out and try again, or contact the app owner."
        )
        if st.button("Sign out", key="workspace_sign_out_missing_identity"):
            st.logout()
        st.stop()
        return ""

    return set_current_owner_id(owner_id_from_identity(identity))


def workspace_label() -> str:
    return "Account workspace" if is_authenticated() else "Local workspace"


def privacy_summary() -> str:
    if is_authenticated():
        return (
            "Your profiles and work are stored in this app's shared database and "
            "scoped to your signed-in account."
        )
    return "Profiles and CVs are stored in this local workspace."


def persistence_note() -> str:
    if is_cloud_deployment():
        return (
            "Streamlit Community Cloud can reset local files when the app restarts "
            "or is redeployed. Download a full export from Settings regularly."
        )
    if is_authenticated():
        return (
            "Saved profiles are separated by account. Download a full export from "
            "Settings before moving the app to another server."
        )
    return (
        "This workspace is stored on this computer. Download a backup from "
        "Settings before moving or reinstalling the app."
    )


__all__ = [
    "auth_configured",
    "auth_required",
    "current_owner_id",
    "current_user",
    "current_user_name",
    "is_authenticated",
    "is_cloud_deployment",
    "persistence_note",
    "privacy_summary",
    "require_workspace_owner",
    "workspace_label",
]

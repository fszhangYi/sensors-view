"""Cookie session auth for sensors-view (cookie-session-auth port)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
USERS_PATH = ROOT / "config" / "users.json"
AUTH_BOOTSTRAP_PATH = ROOT / "config" / ".auth.json"
COOKIE_NAME = "sensors_view_session"
SESSION_TTL_SEC = 7 * 24 * 3600
PBKDF2_ITERATIONS = 120_000

PUBLIC_API_PATHS = frozenset(
    {
        "/api/auth/status",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/health",
    }
)

_lock = threading.RLock()
_sessions: dict[str, dict[str, Any]] = {}
_state: dict[str, Any] = {
    "enabled": True,
    "username": "sensors",
    "password_hash": "",
}


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _pbkdf2_hash(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    stored = (stored or "").strip()
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iters_s, salt_hex, digest_hex = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters_s)
            )
            return secrets.compare_digest(digest.hex(), digest_hex)
        except Exception:
            return False
    return secrets.compare_digest(password, stored)


def _write_users(username: str, password_hash: str) -> None:
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "users": [
            {
                "username": username,
                "role": "admin",
                "enabled": True,
                "password_hash": password_hash,
            }
        ]
    }
    USERS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(USERS_PATH, 0o600)
    except OSError:
        pass


def _load_primary_user() -> tuple[str, str]:
    if USERS_PATH.is_file():
        data = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        users = data.get("users") if isinstance(data, dict) else None
        if isinstance(users, list) and users:
            u = users[0]
            return str(u.get("username") or "sensors"), str(u.get("password_hash") or "")
    return "sensors", ""


def init_auth() -> dict[str, Any]:
    with _lock:
        if _env_truthy("SENSORS_VIEW_AUTH_DISABLED"):
            _state.update(enabled=False, username="", password_hash="")
            return {"enabled": False, "username": None, "source": "disabled"}

        user = (os.environ.get("SENSORS_VIEW_AUTH_USER") or "").strip() or "sensors"
        password = (os.environ.get("SENSORS_VIEW_AUTH_PASSWORD") or "").strip()
        source = "users.json"

        existing_user, existing_hash = _load_primary_user()
        if existing_hash:
            if password:
                # env password upserts primary admin
                ph = _pbkdf2_hash(password)
                _write_users(user, ph)
                _state.update(enabled=True, username=user, password_hash=ph)
                source = "env"
            else:
                _state.update(enabled=True, username=existing_user, password_hash=existing_hash)
            return {"enabled": True, "username": _state["username"], "source": source}

        if not password:
            password = secrets.token_urlsafe(12)
            source = "bootstrap"
        ph = _pbkdf2_hash(password)
        _write_users(user, ph)
        AUTH_BOOTSTRAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUTH_BOOTSTRAP_PATH.write_text(
            json.dumps(
                {
                    "username": user,
                    "password": password,
                    "password_hash": ph,
                    "note": "Bootstrap only. Prefer SENSORS_VIEW_AUTH_PASSWORD. Do not commit.",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(AUTH_BOOTSTRAP_PATH, 0o600)
        except OSError:
            pass
        print(
            f"[auth] created admin in config/users.json (user={user} password={password})",
            flush=True,
        )
        _state.update(enabled=True, username=user, password_hash=ph)
        return {"enabled": True, "username": user, "source": source}


def auth_enabled() -> bool:
    return bool(_state.get("enabled"))


def public_status() -> dict[str, Any]:
    return {
        "ok": True,
        "authRequired": auth_enabled(),
        "usernameHint": _state.get("username") if auth_enabled() else None,
        "loginPath": "/login",
    }


def parse_session_cookie(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return None
    morsel = jar.get(COOKIE_NAME)
    if not morsel:
        return None
    token = (morsel.value or "").strip()
    return token or None


def _purge_expired() -> None:
    now = time.time()
    dead = [k for k, v in _sessions.items() if float(v.get("expires", 0)) < now]
    for k in dead:
        _sessions.pop(k, None)


def session_profile(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with _lock:
        _purge_expired()
        row = _sessions.get(token)
        if not row:
            return None
        if float(row.get("expires", 0)) < time.time():
            _sessions.pop(token, None)
            return None
        row["expires"] = time.time() + SESSION_TTL_SEC
        return {
            "username": str(row.get("username") or ""),
            "role": str(row.get("role") or "admin"),
        }


def create_session(username: str, role: str = "admin") -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = {
            "username": username,
            "role": role,
            "expires": time.time() + SESSION_TTL_SEC,
            "created": time.time(),
        }
    return token


def destroy_session(token: str | None) -> None:
    if not token:
        return
    with _lock:
        _sessions.pop(token, None)


def cookie_header_set(token: str) -> str:
    return f"{COOKIE_NAME}={token}; HttpOnly; Path=/; SameSite=Lax"


def cookie_header_clear() -> str:
    return f"{COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"


def is_authenticated(cookie_header: str | None) -> bool:
    if not auth_enabled():
        return True
    return session_profile(parse_session_cookie(cookie_header)) is not None


def path_requires_auth(path: str) -> bool:
    if not auth_enabled():
        return False
    if path in PUBLIC_API_PATHS:
        return False
    if path.startswith("/api/"):
        return True
    return False


def try_login(username: str, password: str) -> dict[str, Any]:
    if not auth_enabled():
        return {
            "ok": True,
            "authRequired": False,
            "authenticated": True,
            "user": None,
        }
    user = (username or "").strip()
    primary, ph = _state.get("username", ""), _state.get("password_hash", "")
    # reload hash in case file changed
    file_user, file_hash = _load_primary_user()
    if file_hash:
        primary, ph = file_user, file_hash
        _state.update(username=primary, password_hash=ph)

    if not user or not _verify_password(password, ph) or user != primary:
        return {"ok": False, "error": "invalid credentials", "authRequired": True}

    token = create_session(primary, "admin")
    return {
        "ok": True,
        "authRequired": True,
        "authenticated": True,
        "user": {"username": primary, "role": "admin"},
        "_set_cookie": cookie_header_set(token),
    }


def auth_me(cookie_header: str | None) -> dict[str, Any]:
    if not auth_enabled():
        return {
            "ok": True,
            "authRequired": False,
            "authenticated": True,
            "user": None,
        }
    prof = session_profile(parse_session_cookie(cookie_header))
    if not prof:
        return {
            "ok": True,
            "authRequired": True,
            "authenticated": False,
            "user": None,
            "loginPath": "/login",
        }
    return {
        "ok": True,
        "authRequired": True,
        "authenticated": True,
        "user": {"username": prof["username"], "role": prof["role"]},
    }


def auth_logout(cookie_header: str | None) -> dict[str, Any]:
    destroy_session(parse_session_cookie(cookie_header))
    return {"ok": True, "authRequired": auth_enabled(), "_clear_cookie": cookie_header_clear()}

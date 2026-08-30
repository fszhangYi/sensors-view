"""Cookie session auth for sensors-view (multi-user + password change)."""

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
VALID_ROLES = frozenset({"admin", "user"})

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
_users: list[dict[str, Any]] = []
_state: dict[str, Any] = {"enabled": True, "username_hint": "sensors"}


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


def _normalize_role(role: str) -> str:
    r = (role or "user").strip().lower()
    return r if r in VALID_ROLES else "user"


def _save_users_unlocked() -> None:
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "users": _users}
    USERS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(USERS_PATH, 0o600)
    except OSError:
        pass


def _load_users_file() -> list[dict[str, Any]]:
    if not USERS_PATH.is_file():
        return []
    raw = json.loads(USERS_PATH.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("users"), list):
        return [u for u in raw["users"] if isinstance(u, dict)]
    if isinstance(raw, list):
        return [u for u in raw if isinstance(u, dict)]
    return []


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(row.get("username") or ""),
        "role": _normalize_role(str(row.get("role") or "user")),
        "enabled": bool(row.get("enabled", True)),
    }


def find_user(username: str) -> dict[str, Any] | None:
    u = (username or "").strip()
    if not u:
        return None
    with _lock:
        for row in _users:
            if str(row.get("username") or "") == u:
                return dict(row)
    return None


def list_users_public() -> list[dict[str, Any]]:
    with _lock:
        return [_public_row(u) for u in _users]


def is_admin(username: str | None) -> bool:
    row = find_user(username or "")
    return bool(row and row.get("enabled", True) and str(row.get("role")) == "admin")


def create_user(username: str, password: str, role: str = "user") -> dict[str, Any]:
    u = (username or "").strip()
    if not u:
        raise ValueError("username required")
    if not password:
        raise ValueError("password required")
    if len(u) > 64:
        raise ValueError("username too long")
    if len(password) < 4:
        raise ValueError("password too short")
    with _lock:
        if any(str(r.get("username") or "") == u for r in _users):
            raise ValueError("username already exists")
        row = {
            "username": u,
            "role": _normalize_role(role),
            "enabled": True,
            "password_hash": _pbkdf2_hash(password),
        }
        _users.append(row)
        _save_users_unlocked()
        return _public_row(row)


def update_user(
    username: str,
    *,
    role: str | None = None,
    enabled: bool | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    u = (username or "").strip()
    with _lock:
        for i, row in enumerate(_users):
            if str(row.get("username") or "") != u:
                continue
            if role is not None:
                row["role"] = _normalize_role(role)
            if enabled is not None:
                # keep at least one enabled admin
                if not enabled and str(row.get("role")) == "admin":
                    admins = [
                        r
                        for r in _users
                        if str(r.get("role")) == "admin" and bool(r.get("enabled", True))
                    ]
                    if len(admins) <= 1:
                        raise ValueError("cannot disable last admin")
                row["enabled"] = bool(enabled)
            if password is not None and password != "":
                if len(password) < 4:
                    raise ValueError("password too short")
                row["password_hash"] = _pbkdf2_hash(password)
            _users[i] = row
            _save_users_unlocked()
            return _public_row(row)
    raise ValueError("user not found")


def delete_user(username: str, *, actor: str | None = None) -> None:
    u = (username or "").strip()
    if actor and actor == u:
        raise ValueError("cannot delete yourself")
    with _lock:
        before = len(_users)
        target = next((r for r in _users if str(r.get("username") or "") == u), None)
        if not target:
            raise ValueError("user not found")
        if str(target.get("role")) == "admin":
            admins = [r for r in _users if str(r.get("role")) == "admin"]
            if len(admins) <= 1:
                raise ValueError("cannot delete last admin")
        _users[:] = [r for r in _users if str(r.get("username") or "") != u]
        if len(_users) == before:
            raise ValueError("user not found")
        if not _users:
            raise ValueError("cannot delete last user")
        _save_users_unlocked()


def change_own_password(username: str, current_password: str, new_password: str) -> None:
    row = find_user(username)
    if not row or not row.get("enabled", True):
        raise ValueError("user not found")
    if not _verify_password(current_password or "", str(row.get("password_hash") or "")):
        raise ValueError("current password incorrect")
    if not new_password or len(new_password) < 4:
        raise ValueError("password too short")
    update_user(username, password=new_password)


def init_auth() -> dict[str, Any]:
    global _users
    with _lock:
        if _env_truthy("SENSORS_VIEW_AUTH_DISABLED"):
            _users = []
            _state.update(enabled=False, username_hint="")
            return {"enabled": False, "username": None, "source": "disabled"}

        user = (os.environ.get("SENSORS_VIEW_AUTH_USER") or "").strip() or "sensors"
        password = (os.environ.get("SENSORS_VIEW_AUTH_PASSWORD") or "").strip()
        _users = _load_users_file()
        source = "users.json"

        if not _users:
            if not password:
                password = secrets.token_urlsafe(12)
                source = "bootstrap"
            else:
                source = "env"
            row = {
                "username": user,
                "role": "admin",
                "enabled": True,
                "password_hash": _pbkdf2_hash(password),
            }
            _users = [row]
            _save_users_unlocked()
            if source == "bootstrap":
                AUTH_BOOTSTRAP_PATH.parent.mkdir(parents=True, exist_ok=True)
                AUTH_BOOTSTRAP_PATH.write_text(
                    json.dumps(
                        {
                            "username": user,
                            "password": password,
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
            else:
                print(f"[auth] created admin via env (user={user})", flush=True)
        elif password:
            # upsert env user password / ensure admin exists without wiping others
            existing = next((r for r in _users if str(r.get("username") or "") == user), None)
            if existing:
                existing["password_hash"] = _pbkdf2_hash(password)
                existing["role"] = "admin"
                existing["enabled"] = True
            else:
                _users.append(
                    {
                        "username": user,
                        "role": "admin",
                        "enabled": True,
                        "password_hash": _pbkdf2_hash(password),
                    }
                )
            _save_users_unlocked()
            source = "env-upsert"

        hint = next(
            (str(u.get("username")) for u in _users if str(u.get("role")) == "admin"),
            str(_users[0].get("username") or user) if _users else user,
        )
        _state.update(enabled=True, username_hint=hint)
        return {"enabled": True, "username": hint, "source": source, "count": len(_users)}


def auth_enabled() -> bool:
    return bool(_state.get("enabled"))


def public_status() -> dict[str, Any]:
    return {
        "ok": True,
        "authRequired": auth_enabled(),
        "usernameHint": _state.get("username_hint") if auth_enabled() else None,
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
            "role": str(row.get("role") or "user"),
        }


def create_session(username: str, role: str = "user") -> str:
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


def destroy_sessions_for_user(username: str) -> None:
    u = (username or "").strip()
    with _lock:
        dead = [k for k, v in _sessions.items() if str(v.get("username") or "") == u]
        for k in dead:
            _sessions.pop(k, None)


def cookie_header_set(token: str) -> str:
    return f"{COOKIE_NAME}={token}; HttpOnly; Path=/; SameSite=Lax"


def cookie_header_clear() -> str:
    return f"{COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"


def is_authenticated(cookie_header: str | None) -> bool:
    if not auth_enabled():
        return True
    return session_profile(parse_session_cookie(cookie_header)) is not None


def current_user(cookie_header: str | None) -> dict[str, Any] | None:
    if not auth_enabled():
        return {"username": "anonymous", "role": "admin"}
    return session_profile(parse_session_cookie(cookie_header))


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
        return {"ok": True, "authRequired": False, "authenticated": True, "user": None}
    user = (username or "").strip()
    row = find_user(user)
    if (
        not row
        or not row.get("enabled", True)
        or not _verify_password(password or "", str(row.get("password_hash") or ""))
    ):
        return {"ok": False, "error": "invalid credentials", "authRequired": True}
    role = _normalize_role(str(row.get("role") or "user"))
    token = create_session(user, role)
    return {
        "ok": True,
        "authRequired": True,
        "authenticated": True,
        "user": {"username": user, "role": role},
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

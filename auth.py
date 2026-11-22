import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from threading import Lock

import persistence
from catalog import DEFAULT_PROFILE


PASSWORD_ITERATIONS = 600_000
SESSION_LIFETIME = timedelta(hours=12)
SESSION_COOKIE = "inclutalent_session"
LOGIN_ATTEMPT_WINDOW = 600
LOGIN_ATTEMPT_LIMIT = 8
LOGIN_ATTEMPTS = {}
LOGIN_ATTEMPTS_LOCK = Lock()

DUMMY_PASSWORD_SALT = b"inclutalent-mvp-dummy-salt"


def _password_digest(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    ).hex()


DUMMY_PASSWORD_HASH = _password_digest("unavailable-password", DUMMY_PASSWORD_SALT)


def _normalize_email(email):
    if not isinstance(email, str):
        raise ValueError("Escribe un correo electronico valido.")
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Escribe un correo electronico valido.")
    return email


def _auth_rate_key(email):
    return _normalize_email(email)


def _check_auth_rate_limit(email):
    now = datetime.now(timezone.utc).timestamp()
    with LOGIN_ATTEMPTS_LOCK:
        recent = [
            item for item in LOGIN_ATTEMPTS.get(email, [])
            if now - item < LOGIN_ATTEMPT_WINDOW
        ]
        if recent:
            LOGIN_ATTEMPTS[email] = recent
        else:
            LOGIN_ATTEMPTS.pop(email, None)
        return len(recent) >= LOGIN_ATTEMPT_LIMIT


def _record_failed_auth(email):
    now = datetime.now(timezone.utc).timestamp()
    with LOGIN_ATTEMPTS_LOCK:
        recent = [
            item for item in LOGIN_ATTEMPTS.get(email, [])
            if now - item < LOGIN_ATTEMPT_WINDOW
        ]
        recent.append(now)
        LOGIN_ATTEMPTS[email] = recent


def _clear_auth_rate_limit(email):
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.pop(email, None)


def _new_auth_session(data, user_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    data["auth_sessions"][token_hash] = {
        "user_id": user_id,
        "expires_at": (datetime.now(timezone.utc) + SESSION_LIFETIME).timestamp(),
    }
    return token


def register_user(payload):
    email = _normalize_email(payload.get("email"))
    password = payload.get("password")
    name = payload.get("name")
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise ValueError("La contrasena debe tener entre 10 y 128 caracteres.")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError("Escribe un nombre de entre 1 y 80 caracteres.")
    salt = secrets.token_bytes(16)
    user_id = uuid.uuid4().hex
    profile = dict(DEFAULT_PROFILE)
    profile["skills"] = []
    profile["accommodations"] = []
    profile["name"] = name.strip()
    user = {
        "email": email,
        "password_salt": salt.hex(),
        "password_hash": _password_digest(password, salt),
        "profile": profile,
        "sessions": [],
    }
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        if any(existing.get("email") == email for existing in data["users"].values()):
            raise ValueError("No se pudo crear la cuenta. Revisa los datos o inicia sesion.")
        data["users"][user_id] = user
        token = _new_auth_session(data, user_id)
        persistence._write_store(data)
    return {"token": token, "user": {"email": email, "profile": profile}}


def login_user(payload):
    email = _normalize_email(payload.get("email"))
    password = payload.get("password")
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise ValueError("Correo o contrasena incorrectos.")
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        user_id = next(
            (key for key, user in data["users"].items() if user.get("email") == email),
            None,
        )
        user = data["users"].get(user_id) if user_id else None
        if user:
            salt = bytes.fromhex(user["password_salt"])
            expected = user["password_hash"]
        else:
            salt = DUMMY_PASSWORD_SALT
            expected = DUMMY_PASSWORD_HASH
    actual = _password_digest(password, salt)
    if not user or not hmac.compare_digest(actual, expected):
        raise ValueError("Correo o contrasena incorrectos.")
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        if user_id not in data["users"]:
            raise ValueError("Correo o contrasena incorrectos.")
        user = data["users"][user_id]
        now = datetime.now(timezone.utc).timestamp()
        data["auth_sessions"] = {
            key: value for key, value in data["auth_sessions"].items()
            if value.get("expires_at", 0) > now
        }
        token = _new_auth_session(data, user_id)
        persistence._write_store(data)
    return {"token": token, "user": {"email": email, "profile": user["profile"]}}


def authenticate_token(token):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        session = data["auth_sessions"].get(token_hash)
        if not session or session.get("expires_at", 0) <= datetime.now(timezone.utc).timestamp():
            return None
        if session.get("user_id") not in data["users"]:
            return None
        return session["user_id"]


def revoke_token(token):
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        if data["auth_sessions"].pop(token_hash, None) is not None:
            persistence._write_store(data)

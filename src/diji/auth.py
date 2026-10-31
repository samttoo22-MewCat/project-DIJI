"""DIJI account sessions plus optional Google and OpenRouter connections."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import os
import json
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from pydantic import BaseModel


SESSION_COOKIE = "diji_session"
SESSION_DAYS = 30
OAUTH_STATE_MINUTES = 10
OPENROUTER_AUTHORIZE_URL = "https://openrouter.ai/auth"
OPENROUTER_EXCHANGE_URL = "https://openrouter.ai/api/v1/auth/keys"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class AuthenticatedUser(BaseModel):
    id: str
    login_provider: str = "openrouter"
    display_name: str | None = None
    openrouter_user_id: str | None = None


@dataclass(frozen=True)
class AuthSettings:
    required: bool
    callback_url: str
    encryption_key: str | None
    google_callback_url: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None

    @classmethod
    def from_environment(cls) -> "AuthSettings":
        callback_url = os.getenv("DIJI_OPENROUTER_OAUTH_CALLBACK_URL", "http://127.0.0.1:8080/api/auth/openrouter/callback")
        return cls(
            required=os.getenv("DIJI_AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"},
            callback_url=callback_url,
            encryption_key=os.getenv("DIJI_CREDENTIAL_ENCRYPTION_KEY"),
            google_callback_url=os.getenv("DIJI_GOOGLE_OAUTH_CALLBACK_URL"),
            google_client_id=os.getenv("DIJI_GOOGLE_CLIENT_ID"),
            google_client_secret=os.getenv("DIJI_GOOGLE_CLIENT_SECRET"),
        )

    @property
    def secure_cookie(self) -> bool:
        return (self.google_callback_url or self.callback_url).startswith("https://")

    @property
    def google_login_available(self) -> bool:
        return bool(self.google_callback_url and self.google_client_id and self.google_client_secret)


class OpenRouterOAuthClient:
    """Exchange a short-lived PKCE authorization code without exposing a key to JS."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def exchange(self, code: str, verifier: str) -> tuple[str, str]:
        async with httpx.AsyncClient(timeout=20.0, transport=self.transport) as client:
            response = await client.post(
                OPENROUTER_EXCHANGE_URL,
                json={"code": code, "code_verifier": verifier, "code_challenge_method": "S256"},
            )
        response.raise_for_status()
        raw = response.json()
        payload = raw.get("data", raw) if isinstance(raw, dict) else {}
        key = payload.get("key")
        user_id = payload.get("user_id") or (sha256(key.encode()).hexdigest() if isinstance(key, str) else None)
        if not isinstance(key, str) or not isinstance(user_id, str) or not key or not user_id:
            raise ValueError("OpenRouter 授權回應缺少 key 或 user_id")
        return user_id, key


class GoogleOAuthClient:
    """Exchange Google OAuth codes on the server and read the OIDC user profile."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def exchange(self, code: str, callback_url: str, client_id: str, client_secret: str) -> tuple[str, str, str]:
        async with httpx.AsyncClient(timeout=20.0, transport=self.transport) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": callback_url,
                    "grant_type": "authorization_code",
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("Google 授權回應缺少 access token")
            profile_response = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        profile_response.raise_for_status()
        profile = profile_response.json()
        subject, name, email = profile.get("sub"), profile.get("name"), profile.get("email")
        if not isinstance(subject, str) or not subject:
            raise ValueError("Google 授權回應缺少使用者識別")
        return subject, str(name or "Google 使用者"), str(email or "")


class AccountStore:
    """SQLite is the account/session source of truth for a single DIJI server."""

    def __init__(self, path: Path, encryption_key: str | None) -> None:
        self.path = path
        self.cipher = Fernet(encryption_key.encode("utf-8")) if encryption_key else None
        self._initialize()

    def _connection(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        connection = sqlite3.connect(self.path)
        self.path.chmod(0o600)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    openrouter_user_id TEXT NOT NULL UNIQUE,
                    encrypted_openrouter_key BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    verifier TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS google_users (
                    id TEXT PRIMARY KEY,
                    google_subject TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS google_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES google_users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS google_oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_connections (
                    user_id TEXT PRIMARY KEY,
                    encrypted_key BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS additional_provider_keys (
                    user_id TEXT NOT NULL, provider TEXT NOT NULL, encrypted_key BLOB NOT NULL,
                    PRIMARY KEY(user_id, provider)
                );
                CREATE TABLE IF NOT EXISTS provider_preferences (
                    user_id TEXT PRIMARY KEY, priority TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_link_states (
                    state_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    def begin_oauth(self) -> tuple[str, str, str]:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        expires_at = (self._now() + timedelta(minutes=OAUTH_STATE_MINUTES)).isoformat()
        with self._connection() as connection:
            connection.execute("DELETE FROM oauth_states WHERE expires_at <= ?", (self._now().isoformat(),))
            connection.execute(
                "INSERT INTO oauth_states(state_hash, verifier, expires_at) VALUES (?, ?, ?)",
                (self._hash(state), verifier, expires_at),
            )
        return state, verifier, challenge

    def consume_oauth_verifier(self, state: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT verifier, expires_at FROM oauth_states WHERE state_hash = ?", (self._hash(state),)).fetchone()
            connection.execute("DELETE FROM oauth_states WHERE state_hash = ?", (self._hash(state),))
        if not row or row["expires_at"] <= self._now().isoformat():
            return None
        return str(row["verifier"])

    def begin_google_oauth(self) -> str:
        state = secrets.token_urlsafe(32)
        expires_at = (self._now() + timedelta(minutes=OAUTH_STATE_MINUTES)).isoformat()
        with self._connection() as connection:
            connection.execute("DELETE FROM google_oauth_states WHERE expires_at <= ?", (self._now().isoformat(),))
            connection.execute(
                "INSERT INTO google_oauth_states(state_hash, expires_at) VALUES (?, ?)",
                (self._hash(state), expires_at),
            )
        return state

    def consume_google_oauth_state(self, state: str) -> bool:
        with self._connection() as connection:
            row = connection.execute("SELECT expires_at FROM google_oauth_states WHERE state_hash = ?", (self._hash(state),)).fetchone()
            connection.execute("DELETE FROM google_oauth_states WHERE state_hash = ?", (self._hash(state),))
        return bool(row and row["expires_at"] > self._now().isoformat())

    def upsert_openrouter_user(self, openrouter_user_id: str, openrouter_key: str) -> AuthenticatedUser:
        if not self.cipher:
            raise RuntimeError("伺服器尚未設定 DIJI_CREDENTIAL_ENCRYPTION_KEY")
        now = self._now().isoformat()
        encrypted = self.cipher.encrypt(openrouter_key.encode("utf-8"))
        with self._connection() as connection:
            row = connection.execute("SELECT id FROM users WHERE openrouter_user_id = ?", (openrouter_user_id,)).fetchone()
            user_id = str(row["id"]) if row else secrets.token_urlsafe(18)
            connection.execute(
                """INSERT INTO users(id, openrouter_user_id, encrypted_openrouter_key, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(openrouter_user_id) DO UPDATE SET encrypted_openrouter_key = excluded.encrypted_openrouter_key, updated_at = excluded.updated_at""",
                (user_id, openrouter_user_id, encrypted, now, now),
            )
        return AuthenticatedUser(id=user_id, login_provider="openrouter", openrouter_user_id=openrouter_user_id)

    def upsert_google_user(self, google_subject: str, display_name: str, email: str) -> AuthenticatedUser:
        now = self._now().isoformat()
        with self._connection() as connection:
            row = connection.execute("SELECT id FROM google_users WHERE google_subject = ?", (google_subject,)).fetchone()
            user_id = str(row["id"]) if row else secrets.token_urlsafe(18)
            connection.execute(
                """INSERT INTO google_users(id, google_subject, display_name, email, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(google_subject) DO UPDATE SET display_name = excluded.display_name, email = excluded.email, updated_at = excluded.updated_at""",
                (user_id, google_subject, display_name, email, now, now),
            )
        return AuthenticatedUser(id=user_id, login_provider="google", display_name=display_name)

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(48)
        expires_at = (self._now() + timedelta(days=SESSION_DAYS)).isoformat()
        with self._connection() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (self._now().isoformat(),))
            connection.execute("INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)", (self._hash(token), user_id, expires_at))
        return token

    def create_google_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(48)
        expires_at = (self._now() + timedelta(days=SESSION_DAYS)).isoformat()
        with self._connection() as connection:
            connection.execute("DELETE FROM google_sessions WHERE expires_at <= ?", (self._now().isoformat(),))
            connection.execute("INSERT INTO google_sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)", (self._hash(token), user_id, expires_at))
        return token

    def user_for_session(self, token: str | None) -> AuthenticatedUser | None:
        if not token:
            return None
        with self._connection() as connection:
            row = connection.execute(
                """SELECT users.id, users.openrouter_user_id FROM sessions JOIN users ON users.id = sessions.user_id
                   WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
                (self._hash(token), self._now().isoformat()),
            ).fetchone()
        if row:
            return AuthenticatedUser(id=str(row["id"]), login_provider="openrouter", openrouter_user_id=str(row["openrouter_user_id"]))
        with self._connection() as connection:
            google_row = connection.execute(
                """SELECT google_users.id, google_users.display_name FROM google_sessions
                   JOIN google_users ON google_users.id = google_sessions.user_id
                   WHERE google_sessions.token_hash = ? AND google_sessions.expires_at > ?""",
                (self._hash(token), self._now().isoformat()),
            ).fetchone()
        return AuthenticatedUser(id=str(google_row["id"]), login_provider="google", display_name=str(google_row["display_name"])) if google_row else None

    def revoke_session(self, token: str | None) -> None:
        if token:
            with self._connection() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (self._hash(token),))
                connection.execute("DELETE FROM google_sessions WHERE token_hash = ?", (self._hash(token),))

    def openrouter_key_for(self, user_id: str) -> str | None:
        if not self.cipher:
            raise RuntimeError("伺服器尚未設定 DIJI_CREDENTIAL_ENCRYPTION_KEY")
        with self._connection() as connection:
            linked = connection.execute("SELECT encrypted_key FROM provider_connections WHERE user_id = ?", (user_id,)).fetchone()
            if linked:
                return self.cipher.decrypt(bytes(linked["encrypted_key"])).decode("utf-8")
            row = connection.execute("SELECT encrypted_openrouter_key FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return self.cipher.decrypt(bytes(row["encrypted_openrouter_key"])).decode("utf-8")

    def begin_provider_link(self, user_id: str) -> tuple[str, str]:
        state, _verifier, challenge = self.begin_oauth()
        with self._connection() as connection:
            connection.execute("INSERT INTO provider_link_states VALUES (?, ?)", (self._hash(state), user_id))
        return state, challenge

    def consume_provider_link(self, state: str, user_id: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT user_id FROM provider_link_states WHERE state_hash = ?", (self._hash(state),)).fetchone()
            if not row or row["user_id"] != user_id:
                return None
            connection.execute("DELETE FROM provider_link_states WHERE state_hash = ?", (self._hash(state),))
        return self.consume_oauth_verifier(state)

    def save_provider_key(self, user_id: str, key: str, provider: str = "openrouter") -> None:
        if not self.cipher:
            raise RuntimeError("伺服器尚未設定憑證加密")
        with self._connection() as connection:
            if provider != "openrouter":
                connection.execute("INSERT OR REPLACE INTO additional_provider_keys VALUES (?, ?, ?)", (user_id, provider, self.cipher.encrypt(key.encode())))
                return
            connection.execute("INSERT OR REPLACE INTO provider_connections VALUES (?, ?)", (user_id, self.cipher.encrypt(key.encode())))

    def provider_priority(self, user_id):
        with self._connection() as connection:
            row = connection.execute("SELECT priority FROM provider_preferences WHERE user_id = ?", (user_id,)).fetchone()
        return json.loads(row["priority"]) if row else ["openrouter", "bazaarlink"]

    def save_provider_priority(self, user_id, priority):
        if sorted(priority) != ["bazaarlink", "openrouter"]:
            raise ValueError("請選擇兩個不同的額度來源")
        with self._connection() as connection:
            connection.execute("INSERT OR REPLACE INTO provider_preferences VALUES (?, ?)", (user_id, json.dumps(priority)))

    def provider_credentials(self, user_id):
        keys = {"openrouter": self.openrouter_key_for(user_id)}
        with self._connection() as connection:
            row = connection.execute("SELECT encrypted_key FROM additional_provider_keys WHERE user_id = ? AND provider = ?", (user_id, "bazaarlink")).fetchone()
        if row and self.cipher:
            keys["bazaarlink"] = self.cipher.decrypt(bytes(row["encrypted_key"])).decode()
        return [(provider, keys[provider]) for provider in self.provider_priority(user_id) if keys.get(provider)]


def authorization_url(callback_url: str, state: str, challenge: str) -> str:
    return f"{OPENROUTER_AUTHORIZE_URL}?{urlencode({'callback_url': callback_url, 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'})}"


def google_authorization_url(callback_url: str, state: str, client_id: str) -> str:
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode({'client_id': client_id, 'redirect_uri': callback_url, 'response_type': 'code', 'scope': 'openid email profile', 'state': state, 'access_type': 'online', 'prompt': 'select_account'})}"

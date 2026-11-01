import asyncio
from base64 import urlsafe_b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
import sqlite3
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from diji.auth import AccountStore, GoogleOAuthClient, google_authorization_url


def test_binding_pkce_replay_and_atomic_consumption(tmp_path):
    store = AccountStore(tmp_path / "accounts.sqlite3", None)
    state, challenge, binding = store.begin_google_oauth_flow()
    assert store.consume_google_oauth_flow(state, None) is None
    assert store.consume_google_oauth_flow(state, "another-browser") is None
    assert not store.consume_google_oauth_state(state)
    query = parse_qs(urlparse(google_authorization_url("https://example.test/callback", state, "client", challenge)).query)
    assert query["code_challenge"] == [challenge]
    assert query["code_challenge_method"] == ["S256"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.consume_google_oauth_flow(state, binding), range(2)))
    verifiers = [value for value in results if value is not None]
    assert len(verifiers) == 1
    assert urlsafe_b64encode(sha256(verifiers[0].encode("ascii")).digest()).rstrip(b"=").decode("ascii") == challenge
    assert store.consume_google_oauth_flow(state, binding) is None


def test_expired_flow_rejected(tmp_path):
    store = AccountStore(tmp_path / "accounts.sqlite3", None)
    state, _, binding = store.begin_google_oauth_flow()
    with store._connection() as connection:
        connection.execute("UPDATE google_oauth_states SET expires_at = ? WHERE state_hash = ?", ((store._now() - timedelta(seconds=1)).isoformat(), store._hash(state)))
    assert store.consume_google_oauth_flow(state, binding) is None


def test_google_exchange_sends_verifier_and_failure_message_has_no_secrets():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/token":
            data = parse_qs(request.content.decode())
            assert data["code_verifier"] == ["test-verifier"]
            return httpx.Response(200, json={"access_token": "test-access-token"})
        return httpx.Response(200, json={"sub": "subject", "name": "name", "email": "mail"})

    result = asyncio.run(GoogleOAuthClient(httpx.MockTransport(handler)).exchange("test-code", "https://example.test/callback", "client", "test-secret", code_verifier="test-verifier"))
    assert result == ("subject", "name", "mail")

    def fail(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(httpx.HTTPStatusError) as error:
        asyncio.run(GoogleOAuthClient(httpx.MockTransport(fail)).exchange("test-code", "https://example.test/callback", "client", "test-secret", code_verifier="test-verifier"))
    assert all(secret not in str(error.value) for secret in ("test-code", "test-secret", "test-verifier", "test-access-token"))


def test_old_schema_migration_preserves_accounts_sessions_and_legacy_states(tmp_path):
    path = tmp_path / "accounts.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE google_oauth_states (state_hash TEXT PRIMARY KEY, expires_at TEXT NOT NULL);
            CREATE TABLE google_users (id TEXT PRIMARY KEY, google_subject TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, email TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE google_sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL);
            INSERT INTO google_users VALUES ('user', 'subject', 'name', 'mail', '2020', '2020');
        """)
        connection.execute("INSERT INTO google_sessions VALUES (?, 'user', '9999')", (AccountStore._hash("session"),))
        connection.execute("INSERT INTO google_oauth_states VALUES (?, '9999')", (AccountStore._hash("legacy"),))
    store = AccountStore(path, None)
    assert store.user_for_session("session").id == "user"
    assert store.consume_google_oauth_state("legacy")
    state, _, binding = store.begin_google_oauth_flow()
    assert store.consume_google_oauth_flow(state, binding)
    AccountStore(path, None)

import asyncio
import json
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import httpx

from diji.auth import AccountStore, AuthSettings, GoogleOAuthClient, OpenRouterOAuthClient
from diji.local_app import create_app
from diji.local_catalog import LocalCatalog


class FakeOAuthClient:
    async def exchange(self, code: str, verifier: str) -> tuple[str, str]:
        assert verifier
        if code == "second-code":
            return "or-user-456", "sk-or-v1-second-user-key"
        assert code == "returned-code"
        return "or-user-123", "sk-or-v1-user-owned-key"


class FakeGoogleOAuthClient:
    async def exchange(self, code: str, callback_url: str, client_id: str, client_secret: str) -> tuple[str, str, str]:
        assert code == "google-code"
        assert callback_url == "https://diji.example/api/auth/google/callback"
        assert client_id == "google-client-id"
        assert client_secret == "google-client-secret"
        return "google-subject-123", "玩家", "player@example.com"


def test_openrouter_exchange_sends_complete_pkce_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/keys"
        assert json.loads(request.content) == {
            "code": "auth-code",
            "code_verifier": "verifier",
            "code_challenge_method": "S256",
        }
        return httpx.Response(200, json={"key": "sk-or-v1-user-owned-key", "user_id": "or-user-123"})

    result = asyncio.run(OpenRouterOAuthClient(httpx.MockTransport(handler)).exchange("auth-code", "verifier"))

    assert result == ("or-user-123", "sk-or-v1-user-owned-key")


def test_openrouter_login_creates_a_session_and_isolates_conversations(tmp_path: Path) -> None:
    settings = AuthSettings(required=True, callback_url="http://testserver/api/auth/openrouter/callback", encryption_key=Fernet.generate_key().decode())
    accounts = AccountStore(tmp_path / "accounts.sqlite3", settings.encryption_key)
    app = create_app(
        LocalCatalog(tmp_path / "catalog.json"),
        account_store=accounts,
        auth_settings=settings,
        oauth_client=FakeOAuthClient(),
    )
    client = TestClient(app)

    assert client.get("/api/conversations").status_code == 401
    start = client.get("/api/auth/openrouter/start", follow_redirects=False)
    assert start.status_code == 303
    assert "code_challenge=" in start.headers["location"]
    state = start.headers["location"].split("state=", 1)[1].split("&", 1)[0]
    callback = client.get(f"/api/auth/openrouter/callback?code=returned-code&state={state}", follow_redirects=False)
    assert callback.status_code == 303
    assert "httponly" in callback.headers["set-cookie"].lower()
    assert callback.headers["cache-control"] == "no-store"

    session = client.get("/api/auth/session")
    assert session.json()["authenticated"] is True
    assert session.headers["cache-control"] == "no-store"

    created = client.post("/api/conversations", json={"chat_id": "private-chat", "character_id": "character", "character_name": "角色"})
    assert created.status_code == 200
    assert accounts.openrouter_key_for(session.json()["user"]["id"]) == "sk-or-v1-user-owned-key"
    assert (tmp_path / "accounts.sqlite3").stat().st_mode & 0o777 == 0o600

    second_client = TestClient(app)
    second_start = second_client.get("/api/auth/openrouter/start", follow_redirects=False)
    second_state = second_start.headers["location"].split("state=", 1)[1].split("&", 1)[0]
    assert second_client.get(f"/api/auth/openrouter/callback?code=second-code&state={second_state}", follow_redirects=False).status_code == 303
    assert second_client.get("/api/conversations").json() == []


def test_openrouter_callback_rejects_a_replayed_state(tmp_path: Path) -> None:
    settings = AuthSettings(required=True, callback_url="http://testserver/api/auth/openrouter/callback", encryption_key=Fernet.generate_key().decode())
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json"), account_store=AccountStore(tmp_path / "accounts.sqlite3", settings.encryption_key), auth_settings=settings, oauth_client=FakeOAuthClient()))
    start = client.get("/api/auth/openrouter/start", follow_redirects=False)
    state = start.headers["location"].split("state=", 1)[1].split("&", 1)[0]

    assert client.get(f"/api/auth/openrouter/callback?code=returned-code&state={state}", follow_redirects=False).status_code == 303
    assert client.get(f"/api/auth/openrouter/callback?code=returned-code&state={state}", follow_redirects=False).status_code == 400


def test_google_login_creates_a_diji_account_without_an_openrouter_key(tmp_path: Path) -> None:
    settings = AuthSettings(
        required=True,
        callback_url="http://testserver/api/auth/openrouter/callback",
        encryption_key=Fernet.generate_key().decode(),
        google_callback_url="https://diji.example/api/auth/google/callback",
        google_client_id="google-client-id",
        google_client_secret="google-client-secret",
    )
    accounts = AccountStore(tmp_path / "accounts.sqlite3", settings.encryption_key)
    app = create_app(
        LocalCatalog(tmp_path / "catalog.json"),
        account_store=accounts,
        auth_settings=settings,
        google_oauth_client=FakeGoogleOAuthClient(),
    )
    client = TestClient(app, base_url="https://testserver")

    start = client.get("/api/auth/google/start", follow_redirects=False)
    assert start.status_code == 303
    assert "accounts.google.com" in start.headers["location"]
    state = start.headers["location"].split("state=", 1)[1].split("&", 1)[0]
    callback = client.get(f"/api/auth/google/callback?code=google-code&state={state}", follow_redirects=False)
    assert callback.status_code == 303

    session = client.get("/api/auth/session")
    assert session.json()["authenticated"] is True
    assert session.json()["user"]["login_provider"] == "google"
    assert session.json()["user"]["display_name"] == "玩家"
    assert client.post("/api/conversations", json={"chat_id": "google-chat", "character_id": "character", "character_name": "角色"}).status_code == 200
    assert accounts.openrouter_key_for(session.json()["user"]["id"]) is None


def test_google_login_is_unavailable_until_google_oauth_is_configured(tmp_path: Path) -> None:
    settings = AuthSettings(required=True, callback_url="http://testserver/api/auth/openrouter/callback", encryption_key=Fernet.generate_key().decode())
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json"), account_store=AccountStore(tmp_path / "accounts.sqlite3", settings.encryption_key), auth_settings=settings))

    response = client.get("/api/auth/google/start", follow_redirects=False)
    assert response.status_code == 503
    assert "Google" in response.json()["detail"]

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import diji.local_app as module
from diji.auth import AccountStore, AuthSettings, SESSION_COOKIE
from diji.local_catalog import LocalCatalog


def test_private_characters_are_visible_only_to_their_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DEFAULT_USER_DIRECTORY", tmp_path / "users")
    settings = AuthSettings(required=True, callback_url="http://testserver/callback", encryption_key=Fernet.generate_key().decode())
    accounts = AccountStore(tmp_path / "accounts.sqlite3", settings.encryption_key)
    app = module.create_app(LocalCatalog(tmp_path / "catalog.json"), account_store=accounts, auth_settings=settings)
    owner, other, anonymous = TestClient(app), TestClient(app), TestClient(app)
    for client, subject in [(owner, "owner"), (other, "other")]:
        user = accounts.upsert_google_user(subject, subject, f"{subject}@example.test")
        client.cookies.set(SESSION_COOKIE, accounts.create_google_session(user.id))
    character = {"id": "private-example", "name": "測試角色", "premise": "測試", "voice": "測試"}
    saved = owner.put("/api/characters/private-example", json=character)
    assert saved.status_code == 200
    assert saved.json()["source"]["visibility"] == "private"
    assert owner.get("/api/characters/private-example").status_code == 200
    assert len(owner.get("/api/characters").json()) == 3
    for client in (other,):
        assert len(client.get("/api/characters").json()) == 2
        assert len(client.get("/api/bootstrap").json()["characters"]) == 2
        assert client.get("/api/characters/private-example").status_code == 404
    assert anonymous.get("/api/characters").status_code == 401
    assert anonymous.get("/api/bootstrap").status_code == 401
    assert anonymous.get("/api/characters/private-example").status_code == 401
    assert anonymous.put("/api/characters/private-example", json=character).status_code == 401
    assert other.post("/api/conversations", json={"chat_id": "private-chat", "character_id": "private-example", "character_name": "測試角色"}).status_code == 404
    assert other.put("/api/characters/yelan", json={**character, "id": "yelan"}).status_code == 409

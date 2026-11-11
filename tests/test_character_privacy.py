import uuid

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
    private_detail = owner.get("/api/characters/private-example")
    assert private_detail.status_code == 200
    assert "你是測試角色" in private_detail.json()["full_prompt"]
    assert len(owner.get("/api/characters").json()) == 3
    for client in (other,):
        assert len(client.get("/api/characters").json()) == 2
        assert len(client.get("/api/bootstrap").json()["characters"]) == 2
        assert client.get("/api/characters/private-example").status_code == 404
        assert client.put("/api/characters/private-example", json={**character, "premise": "跨帳號修改"}).status_code == 404
    assert anonymous.get("/api/characters").status_code == 401
    assert anonymous.get("/api/bootstrap").status_code == 401
    assert anonymous.get("/api/characters/private-example").status_code == 401
    assert anonymous.put("/api/characters/private-example", json=character).status_code == 401
    assert other.post("/api/conversations", json={"chat_id": "private-chat", "character_id": "private-example", "character_name": "測試角色"}).status_code == 404
    assert other.put("/api/characters/yelan", json={**character, "id": "yelan"}).status_code == 409


def test_default_character_copy_is_private_idempotent_and_editable(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DEFAULT_USER_DIRECTORY", tmp_path / "users")
    settings = AuthSettings(required=True, callback_url="http://testserver/callback", encryption_key=Fernet.generate_key().decode())
    accounts = AccountStore(tmp_path / "accounts.sqlite3", settings.encryption_key)
    client = TestClient(module.create_app(LocalCatalog(tmp_path / "catalog.json"), account_store=accounts, auth_settings=settings))
    other = TestClient(client.app)
    for target, subject in ((client, "copy-owner"), (other, "copy-other")):
        user = accounts.upsert_google_user(subject, subject, f"{subject}@example.test")
        target.cookies.set(SESSION_COOKIE, accounts.create_google_session(user.id))

    source_before = client.get("/api/characters/yelan").json()
    assert "你是夜蘭" in source_before["full_prompt"]
    key = str(uuid.uuid4())
    copied_response = client.post("/api/characters/yelan/copy", headers={"Idempotency-Key": key})
    assert copied_response.status_code == 201
    copied = copied_response.json()
    assert copied["id"] != source_before["id"]
    assert copied["source"] == {"visibility": "private", "copied_from": "yelan", "copy_request_id": key, "prompt_origin": "assembled"}
    assert copied["profile"] == source_before["profile"]
    assert copied["relationship_start"] == source_before["relationship_start"]
    assert copied["full_prompt"] == source_before["full_prompt"]
    assert client.post("/api/characters/yelan/copy", headers={"Idempotency-Key": key}).json() == copied
    assert len([row for row in client.get("/api/characters").json() if row["source"].get("copied_from") == "yelan"]) == 1
    assert TestClient(client.app).post("/api/characters/yelan/copy", headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 401

    edited = {**copied, "name": "夜蘭的個人版本", "premise": "我的角色修改", "relationship_start": "familiar"}
    saved = client.put(f"/api/characters/{copied['id']}", json=edited)
    assert saved.status_code == 200
    assert saved.json()["id"] == copied["id"]
    assert client.get(f"/api/characters/{copied['id']}").json()["premise"] == "我的角色修改"
    assert other.get(f"/api/characters/{copied['id']}").status_code == 404
    assert other.post("/api/characters/yelan/copy", headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 201
    assert client.get("/api/characters/yelan").json() == source_before
    private_copy_response = client.post(f"/api/characters/{copied['id']}/copy", headers={"Idempotency-Key": str(uuid.uuid4())})
    assert private_copy_response.status_code == 201
    private_copy = private_copy_response.json()
    assert private_copy["id"] != copied["id"]
    assert private_copy["source"]["visibility"] == "private"
    assert private_copy["source"]["copied_from"] == copied["id"]
    assert private_copy["full_prompt"] == copied["full_prompt"]
    assert other.post(f"/api/characters/{copied['id']}/copy", headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 404
    reloaded = TestClient(client.app)
    reloaded.cookies.set(SESSION_COOKIE, client.cookies.get(SESSION_COOKIE))
    assert reloaded.get(f"/api/characters/{copied['id']}").json()["premise"] == "我的角色修改"


def test_character_details_return_stored_full_prompt_without_truncation(tmp_path):
    catalog = LocalCatalog(tmp_path / "catalog.json")
    client = TestClient(module.create_app(catalog))
    long_prompt = "角色完整提示詞第一段。\n\n" + ("完整內容不可截斷。" * 700)
    original = catalog.snapshot().characters[0]
    catalog.save_character(original.model_copy(update={"full_prompt": long_prompt}))

    response = client.get(f"/api/characters/{original.id}")

    assert response.status_code == 200
    assert response.json()["full_prompt"] == long_prompt

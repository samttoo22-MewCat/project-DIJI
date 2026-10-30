from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from diji.auth import AccountStore, AuthSettings, SESSION_COOKIE
from diji.local_app import create_app


class FakeProvider:
    async def exchange(self, code, verifier):
        assert code == "approved" and verifier
        return "provider-user", "test-provider-key"


def test_link_preserves_account_and_rejects_other_sessions(tmp_path):
    settings = AuthSettings(required=True, callback_url="https://testserver/api/auth/openrouter/callback", encryption_key=Fernet.generate_key().decode())
    store = AccountStore(tmp_path / "accounts.db", settings.encryption_key)
    owner = store.upsert_google_user("owner", "owner", "owner@example.test")
    other = store.upsert_google_user("other", "other", "other@example.test")
    app = create_app(account_store=store, auth_settings=settings, oauth_client=FakeProvider())
    a, b = TestClient(app), TestClient(app)
    a.cookies.set(SESSION_COOKIE, store.create_google_session(owner.id))
    b.cookies.set(SESSION_COOKIE, store.create_google_session(other.id))
    assert a.get('/api/connections/openrouter/start', follow_redirects=False).status_code == 303
    state, _ = store.begin_provider_link(owner.id)
    url = f'/api/connections/openrouter/callback?code=approved&state={state}'
    assert b.get(url, follow_redirects=False).status_code == 400
    assert a.get(url, follow_redirects=False).status_code == 303
    assert a.get('/api/auth/session').json()['user']['id'] == owner.id
    assert store.openrouter_key_for(owner.id) == 'test-provider-key'
    assert store.openrouter_key_for(other.id) is None
    assert a.get(url, follow_redirects=False).status_code == 400

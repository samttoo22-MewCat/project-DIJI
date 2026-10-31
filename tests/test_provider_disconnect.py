from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from diji.auth import AccountStore, AuthSettings, SESSION_COOKIE
from diji.local_app import create_app


def test_disconnect_removes_only_owners_key_and_preserves_session_and_usage(tmp_path):
    settings = AuthSettings(required=True, callback_url='http://testserver/callback', encryption_key=Fernet.generate_key().decode())
    store = AccountStore(tmp_path/'accounts.db', settings.encryption_key)
    owner = store.upsert_openrouter_user('owner', 'legacy-test-key')
    other = store.upsert_google_user('other', 'other', 'other@example.test')
    store.save_provider_key(owner.id, 'linked-test-key')
    store.save_provider_key(owner.id, 'bazaar-test-key', 'bazaarlink')
    store.save_provider_key(other.id, 'other-test-key')
    store.record_provider_usage(owner.id, 'bazaarlink', 'request-1', '0.1')
    client = TestClient(create_app(account_store=store, auth_settings=settings))
    assert client.delete('/api/connections/openrouter').status_code == 401
    client.cookies.set(SESSION_COOKIE, store.create_session(owner.id))
    assert client.delete('/api/connections/openrouter').status_code == 204
    assert store.openrouter_key_for(owner.id) is None
    assert store.openrouter_key_for(other.id) == 'other-test-key'
    assert [p for p, _ in store.provider_credentials(owner.id)] == ['bazaarlink']
    assert client.delete('/api/connections/bazaarlink').status_code == 204
    assert not store.provider_credentials(owner.id)
    assert store.provider_usage(owner.id, 'bazaarlink')['total'] == '0.1'
    assert client.get('/api/auth/session').json()['authenticated']

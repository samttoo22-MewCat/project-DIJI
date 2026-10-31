from concurrent.futures import ThreadPoolExecutor
import pytest

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import diji.local_app as module
from diji.auth import AccountStore, AuthSettings, SESSION_COOKIE
from diji.local_catalog import LocalCatalog
from diji.memory_store import LocalMemoryStore, MemoryRecord


def test_memory_edit_delete_are_account_scoped_and_preserve_source(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'DEFAULT_USER_DIRECTORY', tmp_path / 'users')
    settings = AuthSettings(required=True, callback_url='http://testserver/callback', encryption_key=Fernet.generate_key().decode())
    accounts = AccountStore(tmp_path / 'accounts.sqlite3', settings.encryption_key)
    app = module.create_app(LocalCatalog(tmp_path / 'catalog.json'), account_store=accounts, auth_settings=settings)
    owner, other, anonymous = TestClient(app), TestClient(app), TestClient(app)
    for client, subject in [(owner, 'owner'), (other, 'other')]:
        user = accounts.upsert_google_user(subject, subject, f'{subject}@example.test')
        client.cookies.set(SESSION_COOKIE, accounts.create_google_session(user.id))
        assert client.post('/api/conversations', json={'chat_id':'edit-test','character_id':'yelan','character_name':'夜蘭'}).status_code == 200
    original = {'summary':'原摘要','type':'事件','keywords':{'人物':'青禾'},'user_message':'原始訊息','key_points':['約定'],'extraction_status':'extracted'}
    assert owner.put('/api/memories/edit-test', json=original).status_code == 200
    entry = owner.get('/api/memories/edit-test/entries').json()[0]
    path = f'/api/memories/edit-test/entries/{entry["record_id"]}'
    changes = {'summary':'修改後摘要','type':'偏好','keywords':{'物品':'桂花烏龍'},'key_points':['修正約定'],'character_response_summary':'回覆摘要'}
    assert anonymous.patch(path, json=changes).status_code == 401
    assert other.patch(path, json=changes).status_code == 404
    assert other.delete(path).status_code == 404
    assert owner.patch(path, json={**changes,'summary':''}).status_code == 422
    assert owner.patch(path, json={**changes,'user_message':'不允許改原文'}).status_code == 422
    saved = owner.patch(path, json=changes).json()
    assert saved['summary'] == '修改後摘要'
    assert saved['user_message'] == '原始訊息'
    assert saved['timestamp'] == entry['timestamp']
    assert saved['extraction_status'] == 'extracted'
    assert saved['manually_edited'] is True
    assert owner.patch(path, json=changes).status_code == 404
    assert owner.delete(path).status_code == 404
    assert owner.delete(f'/api/memories/edit-test/entries/{saved["record_id"]}').status_code == 204
    assert owner.get('/api/memories/edit-test/entries').json() == []
    assert owner.get('/api/conversations/edit-test').status_code == 200


def test_memory_mutations_keep_concurrent_appends_and_duplicate_records(tmp_path):
    store = LocalMemoryStore(tmp_path)
    store.add('edit-test', MemoryRecord(summary='相同內容', user_message='保留'))
    store.add('edit-test', MemoryRecord(summary='相同內容', user_message='保留'))
    first, second = store.entries('edit-test')
    assert first['record_id'] != second['record_id']
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(LocalMemoryStore(tmp_path).add, 'edit-test', MemoryRecord(summary=str(index))) for index in range(20)]
        editing = pool.submit(LocalMemoryStore(tmp_path).update_entry, 'edit-test', first['record_id'], {'summary':'編輯後'})
        futures.append(editing)
        for future in futures:
            try:
                future.result()
            except LookupError:
                assert future is editing
    assert len(store.entries('edit-test')) == 22
    assert store.entries('edit-test')[0]['summary'] in {'相同內容','編輯後'}
    store.delete_entry('edit-test', store.entries('edit-test')[1]['record_id'])
    assert len(store.entries('edit-test')) == 21
    assert (tmp_path / 'edit-test.json').stat().st_mode & 0o777 == 0o600


def test_stale_delete_cannot_remove_a_second_identical_memory(tmp_path):
    store = LocalMemoryStore(tmp_path)
    same = MemoryRecord(summary='相同內容')
    store.add('edit-test', same)
    store.add('edit-test', same)
    token = store.entries('edit-test')[0]['record_id']
    store.delete_entry('edit-test', token)
    with pytest.raises(LookupError):
        store.delete_entry('edit-test', token)
    assert len(store.entries('edit-test')) == 1

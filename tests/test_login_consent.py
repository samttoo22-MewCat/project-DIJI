from pathlib import Path
from urllib.parse import parse_qs,urlparse
import sqlite3

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest

from diji.auth import AccountStore,AuthSettings,SESSION_COOKIE
from diji.legal import LegalDocuments
from diji.local_app import create_app
from diji.local_catalog import LocalCatalog


@pytest.fixture
def consent_app(tmp_path):
    settings=AuthSettings(required=True,callback_url='https://testserver/api/auth/openrouter/callback',encryption_key=Fernet.generate_key().decode(),google_callback_url='https://testserver/api/auth/google/callback',google_client_id='qa-client',google_client_secret='qa-secret')
    accounts=AccountStore(tmp_path/'accounts.sqlite3',settings.encryption_key)
    calls=[]
    class Google:
        async def exchange(self,*args,**kwargs):calls.append('google');return 'qa-subject','QA','qa@example.test'
    class Router:
        async def exchange(self,*args,**kwargs):calls.append('openrouter');return 'qa-router','fake-router-key'
    def build(policies=None):return create_app(catalog=LocalCatalog(tmp_path/'catalog.json'),account_store=accounts,auth_settings=settings,google_oauth_client=Google(),oauth_client=Router(),legal_documents=policies)
    return TestClient(build(),base_url='https://testserver'),accounts,calls,build,tmp_path


def test_documents_are_public_and_reading_does_not_accept(consent_app):
    c,accounts,calls,*_=consent_app
    meta=c.get('/api/legal');assert meta.status_code==200 and len(meta.json()['version'])==64
    assert meta.headers['cache-control']=='no-store'
    for slug,heading in [('privacy','使用者隱私條款'),('terms','使用者規約')]:
        page=c.get('/legal/'+slug);assert page.status_code==200 and heading in page.text
        assert 'text/html' in page.headers['content-type'] and "script-src 'none'" in page.headers['content-security-policy']
        assert '閱讀文件不代表已同意' in page.text
    assert '<table>' in c.get('/legal/privacy').text
    assert c.get('/legal/unknown').status_code==404
    assert c.get('/legal.css').status_code==200
    with accounts._connection() as db:assert db.execute('SELECT COUNT(*) FROM legal_acceptances').fetchone()[0]==0
    assert not calls


@pytest.mark.parametrize('provider',['google','openrouter'])
def test_get_missing_outdated_or_cross_site_consent_cannot_start_login(consent_app,provider):
    c,accounts,calls,*_=consent_app
    version=c.get('/api/legal').json()['version'];url=f'/api/auth/{provider}/start'
    review=c.get(url,follow_redirects=False)
    assert review.status_code==303 and review.headers['location']=='/?login=required#home'
    origin={'origin':'https://testserver'}
    assert c.post(url,data={'policy_version':version},headers=origin,follow_redirects=False).status_code==400
    assert c.post(url,data={'terms_agreed':'no','policy_version':version},headers=origin,follow_redirects=False).status_code==400
    assert c.post(url,data={'terms_agreed':'yes','policy_version':version},headers={'origin':'https://attacker.example'},follow_redirects=False).status_code==403
    old=c.post(url,data={'terms_agreed':'yes','policy_version':'old'},headers=origin,follow_redirects=False)
    assert old.status_code==303 and 'reason=updated' in old.headers['location']
    with accounts._connection() as db:
        assert db.execute('SELECT COUNT(*) FROM oauth_policy_consents').fetchone()[0]==0
    assert not calls


@pytest.mark.parametrize('provider',['google','openrouter'])
def test_acceptance_is_bound_to_flow_and_recorded_after_login(consent_app,provider):
    c,accounts,calls,*_=consent_app
    version=c.get('/api/legal').json()['version']
    start=c.post(f'/api/auth/{provider}/start',data={'terms_agreed':'yes','policy_version':version},headers={'origin':'https://testserver'},follow_redirects=False)
    assert start.status_code==303
    state=parse_qs(urlparse(start.headers['location']).query)['state'][0]
    consent=accounts.pending_policy_consent(state,version);assert consent
    with accounts._connection() as db:assert db.execute('SELECT COUNT(*) FROM legal_acceptances').fetchone()[0]==0
    callback=f'/api/auth/{provider}/callback?code=qa-code&state={state}'
    other=TestClient(c.app,base_url='https://testserver')
    assert other.get(callback,follow_redirects=False).status_code==400 and not calls
    done=c.get(callback,follow_redirects=False);assert done.status_code==303 and calls==[provider]
    uid=c.get('/api/auth/session').json()['user']['id']
    with accounts._connection() as db:
        rows=db.execute('SELECT * FROM legal_acceptances').fetchall()
        assert len(rows)==1 and rows[0]['user_id']==uid and rows[0]['version']==version and rows[0]['accepted_at']==consent['accepted_at']
        assert db.execute('SELECT COUNT(*) FROM oauth_policy_consents').fetchone()[0]==0
        assert {row['name'] for row in db.execute('PRAGMA table_info(legal_acceptances)')}=={'user_id','version','accepted_at'}
    assert c.get(callback,follow_redirects=False).status_code==400


def test_callback_without_consent_cannot_bypass_form(consent_app):
    c,accounts,calls,*_=consent_app
    state,_,binding=accounts.begin_google_oauth_flow()
    c.cookies.set('__Host-diji_google_flow',binding)
    result=c.get(f'/api/auth/google/callback?code=qa-code&state={state}',follow_redirects=False)
    assert result.status_code==400 and not calls
    assert not c.get('/api/auth/session').json()['authenticated']


def test_existing_sessions_stay_valid_without_fabricated_acceptance(consent_app):
    c,accounts,*_=consent_app
    user=accounts.upsert_google_user('existing','QA','qa@example.test')
    c.cookies.set(SESSION_COOKIE,accounts.create_google_session(user.id))
    assert c.get('/api/auth/session').json()['authenticated']
    with accounts._connection() as db:assert not db.execute('SELECT 1 FROM legal_acceptances').fetchone()


def test_policy_update_requires_review_again_before_callback(consent_app):
    c,accounts,calls,build,root=consent_app
    old=c.get('/api/legal').json()['version']
    start=c.post('/api/auth/google/start',data={'terms_agreed':'yes','policy_version':old},headers={'origin':'https://testserver'},follow_redirects=False)
    state=parse_qs(urlparse(start.headers['location']).query)['state'][0]
    docs=root/'updated-docs';docs.mkdir()
    (docs/'privacy-policy.md').write_text('# QA 隱私\n最後更新：2026-11-01\n修改過的內容')
    (docs/'usage-notice.md').write_text('# QA 使用規約\n最後更新：2026-11-01')
    newer=TestClient(build(LegalDocuments(docs)),base_url='https://testserver');newer.cookies.update(c.cookies)
    assert newer.get('/api/legal').json()['version']!=old
    assert newer.get(f'/api/auth/google/callback?code=qa-code&state={state}',follow_redirects=False).status_code==400
    assert not calls

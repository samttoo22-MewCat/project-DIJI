from legal_helpers import start_with_test_consent
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs,urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import diji.local_app as module
import diji.work_limits as work_module
from diji.auth import AccountStore,AuthSettings,SESSION_COOKIE
from diji.experiments import ExperimentStore,JailbreakStore
from diji.local_catalog import LocalCatalog
from diji.memory_extraction import MemoryExtractor
from diji.memory_store import LocalMemoryStore
from diji.work_limits import WorkLimits,ModelWorkGate,GenerationBusy,is_model_work
from test_concurrent_usage import concurrent_app


def limited_app(ctx,limits):
    _,accounts,_,_,_,root=ctx
    return module.create_app(catalog=LocalCatalog(root/'catalog.json'),account_store=accounts,
        auth_settings=AuthSettings(required=True,callback_url='http://testserver/callback',encryption_key=None),
        jailbreak_store=JailbreakStore(root/'presets.json'),experiment_store=ExperimentStore(root/'experiments.json'),work_limits=limits)


def test_account_and_global_limits_do_not_charge_rejected_work(concurrent_app):
    _,_,players,payload,calls,root=concurrent_app
    app=limited_app(concurrent_app,WorkLimits(global_limit=3,user_limit=2))
    async def run():
        calls['started']=asyncio.Event();calls['release']=asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
            async def post(index,chat):
                return await c.post('/api/interactions',headers={'cookie':f'{SESSION_COOKIE}={players[index][1]}'},json={**payload,'chat_id':chat})
            first=asyncio.create_task(post(0,'quota-first'));await calls['started'].wait()
            second=asyncio.create_task(post(0,'quota-second'))
            while calls['total']<2:await asyncio.sleep(.005)
            rejected=await post(0,'quota-rejected')
            assert rejected.status_code==429 and rejected.headers['retry-after']=='10' and calls['total']==2
            third=asyncio.create_task(post(1,'quota-third'))
            while calls['total']<3:await asyncio.sleep(.005)
            assert (await post(2,'global-rejected')).status_code==429 and calls['total']==3
            assert (await c.get('/api/auth/session',headers={'cookie':f'{SESSION_COOKIE}={players[2][1]}'})).status_code==200
            calls['release'].set()
            assert all(r.status_code==200 for r in await asyncio.gather(first,second,third))
            assert (await post(2,'quota-after-release')).status_code==200
    asyncio.run(run())
    assert not (root/'users'/players[0][0].id/'conversations/quota-rejected.json').exists()
    assert not (root/'users'/players[2][0].id/'conversations/global-rejected.json').exists()


def test_default_capacity_rate_expiry_and_failure_cleanup(monkeypatch):
    gate=ModelWorkGate(WorkLimits())
    with ExitStack() as stack:
        for index in range(8):stack.enter_context(gate.lease(str(index)))
        with pytest.raises(GenerationBusy):
            with gate.lease('ninth'):pass
    assert gate.active==0 and not gate.users
    clock=[0]
    monkeypatch.setattr(work_module,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    rate=ModelWorkGate(WorkLimits(starts_per_minute=2))
    with pytest.raises(RuntimeError):
        with rate.lease('one'):raise RuntimeError('isolated')
    with rate.lease('one'):pass
    with pytest.raises(GenerationBusy):
        with rate.lease('one'):pass
    clock[0]=61
    with rate.lease('one'):pass
    assert rate.active==0


def test_timeout_cancels_generation_releases_lock_and_keeps_sent_text(concurrent_app):
    _,_,players,payload,calls,root=concurrent_app
    app=limited_app(concurrent_app,WorkLimits(global_limit=1,user_limit=1,timeout_seconds=.1))
    async def run():
        calls['started']=asyncio.Event();calls['release']=asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',cookies={SESSION_COOKIE:players[0][1]}) as c:
            first=await c.post('/api/interactions',json=payload)
            assert first.status_code==504 and calls['active']==0
            record=json.loads((root/'users'/players[0][0].id/'conversations/same-chat-id.json').read_text())
            assert len(record['messages'])==1 and record['messages'][0]['text']==payload['message']['text']
            calls['release'].set()
            assert (await c.post('/api/interactions',json=payload)).status_code==200
    asyncio.run(run())


@pytest.mark.parametrize('chunked',[False,True])
def test_large_bodies_rejected_even_without_content_length(concurrent_app,chunked):
    _,_,players,_,calls,_=concurrent_app
    app=limited_app(concurrent_app,WorkLimits(body_bytes=512))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',cookies={SESSION_COOKIE:players[0][1]}) as c:
            raw=b'{"id":"qa-flow","name":"'+b'x'*700+b'"}'
            async def chunks():
                for start in range(0,len(raw),64):yield raw[start:start+64]
            response=await c.put('/api/flows/qa-flow',content=chunks() if chunked else raw,headers={'content-type':'application/json'})
            assert response.status_code==413 and calls['total']==0
            assert (await c.put('/api/flows/qa-flow',json={'id':'qa-flow','name':'正常大小'})).status_code==200
    asyncio.run(run())


@pytest.mark.parametrize('path',[
    '/api/interactions','/api/characters/generate','/api/conversations/one/edit',
    '/api/character-generations/one/revise','/api/character-generations/one/test-interactions',
    '/api/character-generations/one/test-interactions/edit','/api/memories/one/extract','/api/memories/one/backfill'])
def test_all_model_work_paths_have_admission_control(path):
    assert is_model_work('POST',path)
    assert not is_model_work('GET',path)
    assert not is_model_work('POST',path+'/unrelated')


def test_public_unsafe_routes_rejected_before_any_generation(concurrent_app):
    app,_,players,payload,calls,root=concurrent_app
    c=TestClient(app);c.cookies.set(SESSION_COOKIE,players[0][1])
    unsafe={**payload,'llm':{'model':'orpo','url':'http://untrusted.example/100.108.209.35'}}
    assert c.post('/api/interactions',json=unsafe).status_code==400
    assert c.post('/api/conversations',json={'chat_id':'one','character_id':'qa-role','character_name':'QA'}).status_code==200
    source=c.get('/api/conversations/one').json()
    edited=c.post('/api/conversations/one/edit',json={'message_index':0,'expected_revision':source['revision'],'interaction':{**unsafe,'chat_id':'one'}})
    assert edited.status_code==400 and '公開模式' in edited.json()['detail']
    assert c.post('/api/characters/generate',json={'keywords':'測試','model':'DIGI-private'}).status_code==400
    from diji.player_activity import PlayerActivity
    activity=PlayerActivity(root/'users'/players[0][0].id/'player_activity.sqlite3')
    run_id=activity.begin('generation',{})
    activity.finish(run_id,'completed',{'draft':{'generation_id':run_id,'revision':0,'character':{'character_name':'QA'},'style_guide':'簡短','full_prompt':''}})
    revised=c.post(f'/api/character-generations/{run_id}/revise',json={'revision':0,'model':'skylark-private','instruction':'測試'})
    assert revised.status_code==400 and '公開模式' in revised.json()['detail']
    trial={'chat_id':'trial-qa','revision':0,'model':'orpo','text':'測試'}
    assert c.post(f'/api/character-generations/{run_id}/test-interactions',json=trial).status_code==400
    assert c.post(f'/api/character-generations/{run_id}/test-interactions/edit',json={**trial,'message_index':0,'expected_revision':'b'*64}).status_code==400
    assert calls['total']==0
    assert len(list((root/'users'/players[0][0].id).glob('conversations/*.json')))==1
    assert c.get('/api/conversations/one').json()==source


def test_flow_http_isolation_and_prompt_preview(concurrent_app):
    app,_,players,_,_,root=concurrent_app
    catalog=LocalCatalog(root/'catalog.json');before=catalog.path.read_bytes()
    clients=[TestClient(app),TestClient(app)]
    for c,(_,token) in zip(clients,players):c.cookies.set(SESSION_COOKIE,token)
    a,b=clients;default=a.get('/api/flows').json()[0]
    assert a.put('/api/flows/'+default['id'],json={**default,'name':'個人流程'}).status_code==200
    assert next(x for x in a.get('/api/flows').json() if x['id']==default['id'])['name']=='個人流程'
    assert next(x for x in b.get('/api/flows').json() if x['id']==default['id'])['name']==default['name']
    assert next(x for x in a.get('/api/bootstrap').json()['flows'] if x['id']==default['id'])['name']=='個人流程'
    assert a.put('/api/flows/qa-only',json={'id':'qa-only','name':'只有自己','layers':['character','scene','history','memory','template']}).status_code==200
    body={'chat_id':'qa-preview','character_id':'qa-role','flow_id':'qa-only','scene':'測試'}
    assert a.post('/api/prompt-preview',json=body).status_code==200
    assert b.post('/api/prompt-preview',json=body).status_code==404
    assert catalog.path.read_bytes()==before


def test_memory_diagnostics_and_legacy_responses_are_redacted(tmp_path,caplog):
    class Failure:
        async def create(self,**kwargs):raise RuntimeError('PRIVATE_DIAGNOSTIC_MARKER')
    records=asyncio.run(MemoryExtractor(Failure()).extract('測試'))
    raw=json.dumps([r.model_dump() for r in records])
    assert 'PRIVATE_DIAGNOSTIC_MARKER' not in raw and 'traceback' not in raw
    assert records[0].model_extra['error_id'] in caplog.text
    assert 'PRIVATE_DIAGNOSTIC_MARKER' not in caplog.text
    store=LocalMemoryStore(tmp_path)
    original=json.dumps([{'error':True,'error_message':'PRIVATE_DIAGNOSTIC_MARKER','traceback':'PRIVATE_STACK','summary':'PRIVATE_DIAGNOSTIC_MARKER'}])
    (tmp_path/'legacy.json').write_text(original)
    safe=json.dumps(store.entries('legacy'))
    assert 'PRIVATE_DIAGNOSTIC_MARKER' not in safe and 'PRIVATE_STACK' not in safe
    assert 'PRIVATE_DIAGNOSTIC_MARKER' not in json.dumps(store.snapshot('legacy'))
    assert (tmp_path/'legacy.json').read_text()==original


def test_public_provider_failure_never_returns_or_logs_exception(concurrent_app,monkeypatch,caplog):
    app,_,players,payload,_,_=concurrent_app
    class Failure:
        async def generate(self,*args):raise RuntimeError('PRIVATE_PROVIDER_MARKER')
    monkeypatch.setattr(module,'AiServerCompatibleAdapter',lambda key=None:Failure())
    c=TestClient(app);c.cookies.set(SESSION_COOKIE,players[0][1])
    response=c.post('/api/interactions',json=payload)
    assert response.status_code==502 and 'PRIVATE_PROVIDER_MARKER' not in response.text
    assert response.json()['error_id'] in caplog.text and 'PRIVATE_PROVIDER_MARKER' not in caplog.text


def test_google_flow_bound_to_browser_and_cookie_cleared(tmp_path):
    settings=AuthSettings(required=True,callback_url='https://testserver/callback',encryption_key=Fernet.generate_key().decode(),google_callback_url='https://testserver/api/auth/google/callback',google_client_id='fake-client',google_client_secret='fake-secret')
    calls=[]
    class Google:
        async def exchange(self,*args,code_verifier=None):
            calls.append(code_verifier);return 'subject','QA','qa@example.test'
    accounts=AccountStore(tmp_path/'accounts.sqlite3',settings.encryption_key)
    app=module.create_app(catalog=LocalCatalog(tmp_path/'catalog.json'),account_store=accounts,auth_settings=settings,google_oauth_client=Google())
    owner,other=TestClient(app,base_url='https://testserver'),TestClient(app,base_url='https://testserver')
    start=start_with_test_consent(owner)
    params=parse_qs(urlparse(start.headers['location']).query)
    assert params['code_challenge_method']==['S256']
    cookie=start.headers['set-cookie'];assert '__Host-diji_google_flow=' in cookie and all(x in cookie.lower() for x in ['httponly','secure','samesite=lax','path=/','max-age=600'])
    url='/api/auth/google/callback?code=fake-code&state='+params['state'][0]
    assert other.get(url,follow_redirects=False).status_code==400 and not calls
    assert owner.get(url,follow_redirects=False).status_code==303 and len(calls)==1 and calls[0]
    assert owner.get('/api/auth/session').json()['authenticated']
    assert '__Host-diji_google_flow' not in owner.cookies
    assert owner.get(url,follow_redirects=False).status_code==400


def test_legacy_openrouter_flow_also_requires_same_browser(tmp_path):
    class Router:
        async def exchange(self,code,verifier):return 'qa-owner','fake-provider-key'
    settings=AuthSettings(required=True,callback_url='https://testserver/api/auth/openrouter/callback',encryption_key=Fernet.generate_key().decode())
    app=module.create_app(catalog=LocalCatalog(tmp_path/'catalog.json'),account_store=AccountStore(tmp_path/'accounts.sqlite3',settings.encryption_key),auth_settings=settings,oauth_client=Router())
    owner,other=TestClient(app,base_url='https://testserver'),TestClient(app,base_url='https://testserver')
    start=start_with_test_consent(owner,'openrouter')
    state=parse_qs(urlparse(start.headers['location']).query)['state'][0]
    url='/api/auth/openrouter/callback?code=fake-code&state='+state
    assert other.get(url,follow_redirects=False).status_code==400
    assert owner.get(url,follow_redirects=False).status_code==303
    assert '__Host-diji_router_flow' not in owner.cookies
    assert owner.get('/api/auth/session').json()['authenticated']

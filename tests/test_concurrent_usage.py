"""Isolated concurrent players: fake models, real auth and persistence, no credits."""
import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

import diji.local_app as module
from diji.auth import AccountStore, AuthSettings, SESSION_COOKIE
from diji.local_catalog import LocalCatalog, CharacterSpec
from diji.provider_routing import provider_client, provider_session
from diji.experiments import ExperimentStore, JailbreakStore


@pytest.fixture
def concurrent_app(tmp_path, monkeypatch):
    monkeypatch.setattr(module,'DEFAULT_USER_DIRECTORY',tmp_path/'users')
    settings=AuthSettings(required=True,callback_url='http://testserver/callback',encryption_key=Fernet.generate_key().decode())
    class Accounts(AccountStore):
        sessions=0
        credentials=0
        def user_for_session(self,token):
            self.sessions+=1
            return super().user_for_session(token)
        def provider_credentials(self,user_id):
            self.credentials+=1
            return super().provider_credentials(user_id)
    accounts=Accounts(tmp_path/'accounts.sqlite3',settings.encryption_key)
    players=[]
    for index in range(20):
        user=accounts.upsert_google_user(f'qa-{index}',f'QA {index}',f'qa-{index}@example.test')
        accounts.save_provider_key(user.id,f'isolated-fake-key-{index}')
        players.append((user,accounts.create_google_session(user.id)))
    catalog=LocalCatalog(tmp_path/'catalog.json')
    catalog.save_character(CharacterSpec(id='qa-role',name='多人測試',premise='測試',voice='簡短'))
    calls={'active':0,'peak':0,'total':0,'started':None,'release':None}
    class Adapter:
        async def generate(self,config,messages):
            calls['active']+=1;calls['peak']=max(calls['peak'],calls['active']);calls['total']+=1
            try:
                if calls['started'] is not None:
                    calls['started'].set();await calls['release'].wait()
                else:await asyncio.sleep(.05)
                return '測試回覆 '+messages[-1]['content'].split('\n\n[OOC')[0]
            finally:calls['active']-=1
    class Extraction:
        async def create(self,**kwargs):
            return json.dumps({'summary':'隔離的測試記憶','type':'事件'})
    monkeypatch.setattr(module,'AiServerCompatibleAdapter',lambda key=None:Adapter())
    monkeypatch.setattr(module,'OpenRouterExtractionClient',lambda key=None:Extraction())
    app=module.create_app(catalog=catalog,account_store=accounts,auth_settings=settings,jailbreak_store=JailbreakStore(tmp_path/'presets.json'),experiment_store=ExperimentStore(tmp_path/'experiments.json'))
    payload={'chat_id':'same-chat-id','llm':{'model':'test/model'},'character':{'id':'qa-role','name':'多人測試','description':'測試背景'},'user':{'id':'local-user','persona':{'name':'玩家','chat_mode':'dialog'}},'message':{'sender_id':'local-user','text':'測試'},'enable_favorability':False}
    return app,accounts,players,payload,calls,tmp_path


def test_twenty_players_overlap_without_cross_account_data(concurrent_app):
    app,accounts,players,payload,calls,root=concurrent_app
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
            async def turn(index,player):
                user,token=player
                response=await c.post('/api/interactions',headers={'cookie':f'{SESSION_COOKIE}={token}'},json={**payload,'message':{'sender_id':'local-user','text':f'玩家-{index}'}})
                assert response.status_code==200
                assert f'玩家-{index}' in response.json()['text']
                record=json.loads((root/'users'/user.id/'conversations'/'same-chat-id.json').read_text())
                assert len(record['messages'])==2 and record['messages'][0]['text']==f'玩家-{index}'
            started=time.perf_counter()
            await asyncio.gather(*(turn(i,p) for i,p in enumerate(players)))
            print(f'QA concurrency: players=20 peak_model_calls={calls["peak"]} elapsed={time.perf_counter()-started:.3f}s session_lookups={accounts.sessions} credential_loads={accounts.credentials}')
    asyncio.run(run())
    assert calls['peak']>1 and calls['total']==20
    assert accounts.sessions==20 and accounts.credentials==20


def test_same_conversation_overlap_is_rejected_then_lock_released(concurrent_app):
    app,_,players,payload,calls,root=concurrent_app
    async def run():
        calls['started']=asyncio.Event();calls['release']=asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',cookies={SESSION_COOKIE:players[0][1]}) as c:
            first=asyncio.create_task(c.post('/api/interactions',json=payload))
            await asyncio.wait_for(calls['started'].wait(),2)
            second=await c.post('/api/interactions',json=payload)
            assert second.status_code==409 and calls['total']==1
            calls['release'].set();assert (await first).status_code==200
            assert (await c.post('/api/interactions',json=payload)).status_code==200
    asyncio.run(run())
    record=json.loads((root/'users'/players[0][0].id/'conversations'/'same-chat-id.json').read_text())
    assert [m['sender_type'] for m in record['messages']]==[1,2,1,2]


def test_slow_checkpoint_does_not_block_another_players_session(concurrent_app,monkeypatch):
    app,_,players,payload,_,_=concurrent_app
    entered=threading.Event();release=threading.Event()
    from diji.player_activity import PlayerActivity
    original=PlayerActivity.checkpoint
    def slow(self,*args):
        entered.set();assert release.wait(3)
        return original(self,*args)
    monkeypatch.setattr(PlayerActivity,'checkpoint',slow)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
            first=asyncio.create_task(c.post('/api/interactions',headers={'cookie':f'{SESSION_COOKIE}={players[0][1]}'},json=payload))
            while not entered.is_set():await asyncio.sleep(.005)
            try:
                response=await asyncio.wait_for(c.get('/api/auth/session',headers={'cookie':f'{SESSION_COOKIE}={players[1][1]}'}),1)
                assert response.status_code==200 and response.json()['user']['id']==players[1][0].id
            finally:release.set()
            assert (await first).status_code==200
    asyncio.run(run())


def test_provider_pool_is_request_scoped_reused_and_closed_on_failure():
    async def run():
        async with provider_session():
            first=provider_client('fake-key-one')
            assert provider_client('fake-key-one') is first
            other=provider_client('fake-key-two')
            assert first is not other
        assert first.is_closed() and other.is_closed()
        with pytest.raises(RuntimeError):
            async with provider_session():
                fresh=provider_client('fake-key-one');assert fresh is not first
                raise RuntimeError('isolated failure')
        assert fresh.is_closed()
        async def scope():
            async with provider_session():
                client=provider_client('same-fake-key');await asyncio.sleep(.01);return client
        one,two=await asyncio.gather(scope(),scope())
        assert one is not two and one.is_closed() and two.is_closed()
    asyncio.run(run())


def test_turn_lock_is_shared_by_store_instances_and_released_after_failure(tmp_path):
    from diji.conversation_store import ConversationStore,ConversationBusy
    one,two=ConversationStore(tmp_path),ConversationStore(tmp_path)
    with pytest.raises(RuntimeError):
        with one.turn('same'):
            with pytest.raises(ConversationBusy):
                with two.turn('same'):pass
            with two.turn('different'):pass
            raise RuntimeError('test')
    with two.turn('same'):pass


def test_account_connections_are_closed(concurrent_app):
    _,accounts,*_=concurrent_app
    with accounts._connection() as db:assert db.execute('SELECT 1').fetchone()[0]==1
    with pytest.raises(sqlite3.ProgrammingError):db.execute('SELECT 1')

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import diji.local_app as module
from diji.auth import AccountStore, AuthSettings, SESSION_COOKIE
from diji.character_generation import CharacterGenerationRequest, CharacterGenerationService
from diji.conversation_store import ConversationStore, ConversationMessage
from diji.experiments import JailbreakStore, JailbreakPreset
from diji.local_catalog import LocalCatalog
from diji.player_activity import PlayerActivity, RecordedGenerationClient


class Client:
    async def complete(self, **kwargs):
        return json.dumps({'character_name':'伺服器草稿', 'backstory':'記錄測試'}) if kwargs['json_mode'] else '測試風格'


def test_four_stage_inputs_outputs_and_reopening(tmp_path):
    activity = PlayerActivity(tmp_path / 'activity.sqlite3')
    run_id = activity.begin('generation', {'concept':'測試'})
    service = CharacterGenerationService(RecordedGenerationClient(Client(), activity, run_id))
    draft = asyncio.run(service.generate(CharacterGenerationRequest(keywords='測試', enable_search=False)))
    activity.finish(run_id, 'completed', {'draft':draft.model_dump()})
    reopened = PlayerActivity(activity.path).get(run_id)
    assert reopened['status'] == 'completed'
    assert [e['stage'] for e in reopened['events'][::2]] == RecordedGenerationClient.stages
    assert all(e['data'].get('prompt') for e in reopened['events'][::2])
    assert all(e['data'].get('output') for e in reopened['events'][1::2])
    assert activity.path.stat().st_mode & 0o777 == 0o600


def test_failures_keep_stage_input_without_exception_secrets(tmp_path):
    class Broken:
        async def complete(self, **kwargs):
            raise RuntimeError('secret-provider-key')
    activity = PlayerActivity(tmp_path / 'activity.sqlite3')
    run_id = activity.begin('generation', {})
    with pytest.raises(RuntimeError):
        asyncio.run(RecordedGenerationClient(Broken(),activity,run_id).complete(prompt='測試輸入',model='test',temperature=0.5,json_mode=False))
    record = activity.get(run_id)
    assert record['events'][-1]['status'] == 'failed'
    assert 'secret-provider-key' not in json.dumps(record)


def test_draft_revision_conflict_and_saved_role_link(tmp_path):
    activity = PlayerActivity(tmp_path / 'activity.sqlite3')
    run_id = activity.begin('generation', {})
    activity.finish(run_id,'completed',{})
    draft = activity.save_draft(run_id,0,{'character':{'character_name':'修改版'}})
    assert draft['revision'] == 1
    with pytest.raises(ValueError):
        activity.save_draft(run_id,0,{})
    character = LocalCatalog(tmp_path/'catalog.json').snapshot().characters[0].model_copy(update={'source':{'generation_id':run_id}})
    save_id=activity.begin('character_save',{'character':character.model_dump()})
    activity.character_saved(character,save_id)
    assert activity.get(run_id)['data']['saved_character_id'] == character.id
    with pytest.raises(ValueError):
        activity.save_draft(run_id,1,{})


def test_account_history_isolation_and_private_draft_save(tmp_path, monkeypatch):
    monkeypatch.setattr(module,'DEFAULT_USER_DIRECTORY',tmp_path/'users')
    settings=AuthSettings(required=True,callback_url='http://testserver/callback',encryption_key=Fernet.generate_key().decode())
    accounts=AccountStore(tmp_path/'accounts.sqlite3',settings.encryption_key)
    app=module.create_app(catalog=LocalCatalog(tmp_path/'catalog.json'),account_store=accounts,auth_settings=settings)
    owner, other, anonymous=TestClient(app),TestClient(app),TestClient(app)
    for client,sub in [(owner,'owner'),(other,'other')]:
        user=accounts.upsert_google_user(sub,sub,f'{sub}@example.test')
        client.cookies.set(SESSION_COOKIE,accounts.create_google_session(user.id))
        if sub=='owner': owner_id=user.id
    activity=PlayerActivity(module._user_directory(owner_id)/'player_activity.sqlite3')
    run_id=activity.begin('generation',{})
    activity.finish(run_id,'completed',{'draft':{'generation_id':run_id,'character':{'character_name':'私人草稿'},'style_guide':'測試','full_prompt':''}})
    assert anonymous.get('/api/character-generations').status_code==401
    assert other.get('/api/character-generations').json()==[]
    assert other.get(f'/api/character-generations/{run_id}').status_code==404
    response=owner.get(f'/api/character-generations/{run_id}')
    assert response.headers['cache-control']=='private, no-store'
    draft=response.json()['data']['draft']
    draft['character']['character_name']='修改草稿'
    assert owner.patch(f'/api/character-generations/{run_id}/draft',json=draft).status_code==200
    assert owner.patch(f'/api/character-generations/{run_id}/draft',json=draft).status_code==409
    assert other.patch(f'/api/character-generations/{run_id}/draft',json=draft).status_code==404
    character={'id':run_id,'name':'修改草稿','premise':'測試','voice':'測試','profile':draft['character'],'source':{'generated_file':'DIJI character creator','generation_id':run_id}}
    assert owner.put(f'/api/characters/{run_id}',json=character).status_code==200
    assert activity.get(run_id)['data']['saved_character_id']==run_id
    assert other.get(f'/api/characters/{run_id}').status_code==404


def test_generation_api_records_success_and_parse_failure(tmp_path):
    presets=JailbreakStore(tmp_path/'jailbreaks.json')
    presets.save(JailbreakPreset(id='approved',name='測試',model='test/model',last_updated='2026-11-01',source_url='https://example.test',prompt='已核准測試',review_status='approved',openrouter_models=['test/model']))
    catalog=LocalCatalog(tmp_path/'catalog.json')
    client=TestClient(module.create_app(catalog=catalog,jailbreak_store=presets,character_generator=CharacterGenerationService(Client())))
    response=client.post('/api/characters/generate',json={'keywords':'生成測試','model':'test/model','enable_search':False})
    assert response.status_code==200
    record=client.get('/api/character-generations/'+response.json()['generation_id']).json()
    assert record['status']=='completed' and len(record['events'])==8
    class Invalid:
        async def complete(self,**kwargs): return 'invalid JSON'
    broken=TestClient(module.create_app(catalog=catalog,jailbreak_store=presets,character_generator=CharacterGenerationService(Invalid())),raise_server_exceptions=False)
    assert broken.post('/api/characters/generate',json={'keywords':'失敗測試','model':'test/model'}).status_code==500
    assert broken.get('/api/character-generations').json()[0]['status']=='failed'


def test_concurrent_transcript_appends_survive_reopening(tmp_path):
    store=ConversationStore(tmp_path/'chats')
    def append(index):
        ConversationStore(store.directory).append('parallel','test','測試',ConversationMessage(sender_type=1,text=f'訊息 {index}'))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append,range(50)))
    messages=ConversationStore(store.directory).get('parallel').messages
    assert len(messages)==50
    assert {m.text for m in messages}=={f'訊息 {i}' for i in range(50)}


def test_turn_audit_and_transcript_survive_app_restart(tmp_path):
    class Interaction:
        async def respond(self, request):
            return {'chat_id':request.chat_id,'character_id':request.character.id,'text':'伺服器回覆','messages':[], 'memory_saved':True,'relationship_updated':False}
    catalog=LocalCatalog(tmp_path/'catalog.json')
    store=ConversationStore(tmp_path/'chats')
    app=module.create_app(catalog=catalog,conversation_store=store,interaction_service=Interaction())
    payload={'chat_id':'audit-chat','llm':{'model':'test','url':'https://secret@example.test'},'character':{'id':'test-character','name':'測試','description':'測試'},'user':{'id':'test-user','persona':{'name':'測試','chat_mode':'dialog'}},'message':{'sender_id':'test-user','text':'要保留的對話'},'is_nsfw':False,'enable_favorability':False}
    assert TestClient(app).post('/api/interactions',json=payload).status_code==200
    record=ConversationStore(store.directory).get('audit-chat')
    assert [m.text for m in record.messages]==['要保留的對話','伺服器回覆']
    activity=PlayerActivity(tmp_path/'player_activity.sqlite3')
    with activity.connect() as db:
        row=db.execute("SELECT id FROM runs WHERE kind='conversation_turn'").fetchone()
    run=activity.get(row['id'])
    assert run['status']=='completed' and run['data']['chat_mode']=='dialog'
    assert run['data']['reply']=='伺服器回覆'
    assert 'secret@example.test' not in json.dumps(run)

import json

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest

import diji.local_app as module
from diji.auth import AccountStore, AuthSettings, SESSION_COOKIE
from diji.conversation_store import ConversationStore
from diji.experiments import ExperimentStore, JailbreakStore, JailbreakPreset
from diji.local_catalog import LocalCatalog
from diji.player_activity import PlayerActivity
from diji.experiments.models import DEFAULT_DIALOG_STYLE, DEFAULT_STORY_STYLE


@pytest.fixture
def trial(tmp_path, monkeypatch):
    monkeypatch.setattr(module,'DEFAULT_USER_DIRECTORY',tmp_path/'users')
    settings=AuthSettings(required=True,callback_url='http://testserver/callback',encryption_key=Fernet.generate_key().decode())
    accounts=AccountStore(tmp_path/'accounts.sqlite3',settings.encryption_key)
    presets=JailbreakStore(tmp_path/'presets.json')
    presets.save(JailbreakPreset(id='approved',name='測試越獄',model='test/model',last_updated='2026-11-01',source_url='https://example.test',review_status='approved',prompt='測試核准內容',openrouter_models=['test/model']))
    calls=[]
    class Adapter:
        async def generate(self, config, messages):
            calls.append(messages)
            return '來自草稿\n測試回覆'
    class Extractor:
        async def create(self, **kwargs):
            return json.dumps({'type':'事件','summary':'測試記憶','user_message':'測試輸入','keywords':{'事件':'試聊'}})
    monkeypatch.setattr(module,'AiServerCompatibleAdapter',lambda key=None:Adapter())
    monkeypatch.setattr(module,'OpenRouterExtractionClient',lambda key=None:Extractor())
    app=module.create_app(catalog=LocalCatalog(tmp_path/'catalog.json'),account_store=accounts,auth_settings=settings,jailbreak_store=presets,experiment_store=ExperimentStore(tmp_path/'experiments.json'))
    owner,other,anonymous=TestClient(app),TestClient(app),TestClient(app)
    for client,sub in [(owner,'owner'),(other,'other')]:
        user=accounts.upsert_google_user(sub,sub,f'{sub}@example.test')
        client.cookies.set(SESSION_COOKIE,accounts.create_google_session(user.id))
        assert client.post('/api/player-personas',json={'label':'測試身分','name':'玩家'}).status_code==200
        if sub=='owner':
            root=module._user_directory(user.id)
            accounts.save_provider_key(user.id,'fake-provider-key')
    activity=PlayerActivity(root/'player_activity.sqlite3')
    run_id=activity.begin('generation',{})
    draft={'generation_id':run_id,'revision':0,'character':{'character_name':'尚未保存的草稿','backstory':'測試暗號：藍紙船','psychological_evolution':{'enabled':True}},'style_guide':'說話安靜簡潔','description_for_app':'測試用草稿','full_prompt':'過期的人設，不能使用'}
    activity.finish(run_id,'completed',{'draft':draft})
    payload={'chat_id':'trial-one','revision':0,'model':'test/model','text':'你好，請記住測試文字','chat_mode':'dialog','is_nsfw':False}
    return owner,other,anonymous,activity,root,run_id,payload,calls


def test_trial_uses_current_draft_same_prompt_pipeline_and_isolated_storage(trial):
    owner,_,_,activity,root,run_id,payload,calls=trial
    url=f'/api/character-generations/{run_id}/test-interactions'
    response=owner.post(url,json=payload)
    assert response.status_code==200
    assert response.json()['text']=='來自草稿\n測試回覆'
    assert '藍紙船' in calls[0][0]['content']
    assert '說話安靜簡潔' in calls[0][0]['content']
    assert '過期的人設' not in calls[0][0]['content']
    assert DEFAULT_DIALOG_STYLE in calls[0][0]['content']
    assert '<FAVORABILITY>' not in calls[0][0]['content']
    assert owner.post(url,json={**payload,'text':'繼續上一句','chat_mode':'story'}).status_code==200
    assert any(m['role']=='assistant' and m['content']=='來自草稿\n測試回覆' for m in calls[1])
    assert DEFAULT_STORY_STYLE in calls[1][0]['content']
    transcript=ConversationStore(root/'creator_trials'/'conversations').get('trial-one')
    assert transcript.chat_mode=='story' and len(transcript.messages)==4
    assert list((root/'creator_trials'/'memories').glob('*.json'))
    assert not (root/'memories').exists()
    assert owner.get('/api/conversations').json()==[]
    assert run_id not in {c['id'] for c in owner.get('/api/characters').json()}
    assert not activity.get(run_id)['data'].get('saved_character_id')
    with activity.connect() as db:
        runs=[json.loads(row['data']) for row in db.execute("SELECT data FROM runs WHERE kind='conversation_turn'")]
    assert len(runs)==2 and all(row['purpose']=='draft_trial' and row['generation_id']==run_id for row in runs)


def test_trial_rejects_other_accounts_stale_revision_and_saved_drafts(trial):
    owner,other,anonymous,activity,_,run_id,payload,calls=trial
    url=f'/api/character-generations/{run_id}/test-interactions'
    assert anonymous.post(url,json=payload).status_code==401
    assert other.post(url,json=payload).status_code==404
    assert owner.post(url,json={**payload,'revision':9}).status_code==409
    assert owner.post(url,json={**payload,'model':'unknown/model'}).status_code==400
    activity.finish(run_id,'completed',{'saved_character_id':run_id})
    assert owner.post(url,json=payload).status_code==409
    assert calls==[]


def test_trial_cannot_reuse_another_drafts_conversation(trial):
    owner,_,_,activity,_,run_id,payload,calls=trial
    assert owner.post(f'/api/character-generations/{run_id}/test-interactions',json=payload).status_code==200
    second=activity.begin('generation',{})
    activity.finish(second,'completed',{'draft':{**activity.get(run_id)['data']['draft'],'generation_id':second}})
    assert owner.post(f'/api/character-generations/{second}/test-interactions',json=payload).status_code==409
    assert len(calls)==1

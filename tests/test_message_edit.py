import json

import diji.local_app as module
from diji.conversation_store import ConversationStore, ConversationMessage
from diji.memory_store import LocalMemoryStore, MemoryRecord
from diji.relationship import RelationshipStore, RelationshipState
from diji.user_profile import UserProfileStore
from test_draft_trial import trial


def normal_chat(trial,monkeypatch):
    owner,other,anonymous,activity,root,run_id,_,_=trial
    calls=[]
    class Adapter:
        async def generate(self,config,messages):
            calls.append(messages)
            return '新回覆：'+messages[-1]['content'].split('\n\n[OOC')[0]
    monkeypatch.setattr(module,'AiServerCompatibleAdapter',lambda key=None:Adapter())
    character={'id':'edit-role','name':'編輯測試','premise':'測試','voice':'簡短','profile':{'backstory':'角色背景'}}
    assert owner.put('/api/characters/edit-role',json=character).status_code==200
    assert owner.post('/api/conversations',json={'chat_id':'original','character_id':'edit-role','character_name':'編輯測試','chat_mode':'dialog'}).status_code==200
    payload={'chat_id':'original','llm':{'model':'test/model'},'character':{'id':'edit-role','name':'編輯測試','description':'角色背景'},'user':{'id':'local-user','persona':{'name':'玩家','chat_mode':'dialog'}},'message':{'sender_id':'local-user','text':'第一句'},'is_nsfw':False,'enable_favorability':False}
    return owner,other,anonymous,activity,root,payload,calls


def test_edit_regenerates_from_target_and_restores_prior_state(trial,monkeypatch):
    owner,_,_,activity,root,payload,calls=normal_chat(trial,monkeypatch)
    assert owner.post('/api/interactions',json=payload).status_code==200
    uid=owner.get('/api/auth/session').json()['user']['id']
    profiles=UserProfileStore(root/'user_profiles');profiles.restore_snapshot(uid,{'preference':'當時偏好'})
    relationships=RelationshipStore(root/'relationships');relationships.restore_snapshot('original',RelationshipState(current_score=12).model_dump())
    second={**payload,'message':{'sender_id':'local-user','text':'舊第二句'}}
    assert owner.post('/api/interactions',json=second).status_code==200
    memories=LocalMemoryStore(root/'memories');memories.add('original',MemoryRecord(summary='後續情節不可帶入',user_message='未來資料'))
    relationships.restore_snapshot('original',RelationshipState(current_score=99).model_dump());profiles.restore_snapshot(uid,{'preference':'後來偏好'})
    source=owner.get('/api/conversations/original').json()
    edited={**payload,'message':{'sender_id':'local-user','text':'改過的第二句'}}
    response=owner.post('/api/conversations/original/edit',json={'message_index':2,'expected_revision':source['revision'],'interaction':edited})
    assert response.status_code==200
    branch=response.json()['conversation'];new_id=branch['chat_id']
    assert new_id!='original' and branch['parent_chat_id']=='original'
    assert branch['state_checkpoint_available'] is True
    assert [m['text'] for m in branch['messages'][:2]]==[m['text'] for m in source['messages'][:2]]
    assert branch['messages'][2]['text']=='改過的第二句'
    assert '改過的第二句' in branch['messages'][3]['text']
    assert '舊第二句' not in json.dumps(calls[-1],ensure_ascii=False)
    assert owner.get('/api/conversations/original').json()==source
    assert '後續情節不可帶入' not in json.dumps(memories.snapshot(new_id),ensure_ascii=False)
    assert relationships.get(new_id).current_score==12 and relationships.get('original').current_score==99
    assert UserProfileStore(root/'branch_profiles'/new_id).get(uid)=={'preference':'當時偏好'}
    assert profiles.get(uid)=={'preference':'後來偏好'}
    assert len(owner.get('/api/conversations').json())==2


def test_edit_auth_revision_and_author_guards(trial,monkeypatch):
    owner,other,anonymous,_,_,payload,calls=normal_chat(trial,monkeypatch)
    original=owner.get('/api/conversations/original').json()
    assert owner.post('/api/interactions',json=payload).status_code==200
    source=owner.get('/api/conversations/original').json()
    body={'message_index':0,'expected_revision':source['revision'],'interaction':payload}
    assert anonymous.post('/api/conversations/original/edit',json=body).status_code==401
    assert other.post('/api/conversations/original/edit',json=body).status_code==404
    assert owner.post('/api/conversations/original/edit',json={**body,'message_index':1}).status_code==400
    assert owner.post('/api/conversations/original/edit',json={**body,'expected_revision':original['revision']}).status_code==409
    assert len(calls)==1 and owner.get('/api/conversations/original').json()==source


def test_legacy_edit_does_not_copy_future_memory_or_preferences(trial,monkeypatch):
    owner,_,_,_,root,payload,_=normal_chat(trial,monkeypatch)
    chats=ConversationStore(root/'conversations')
    chats.append('original','edit-role','編輯測試',ConversationMessage(sender_type=1,text='舊版訊息'))
    chats.append('original','edit-role','編輯測試',ConversationMessage(sender_type=2,text='舊版回覆'))
    LocalMemoryStore(root/'memories').add('original',MemoryRecord(summary='舊回覆的未來情節'))
    source=chats.get('original')
    response=owner.post('/api/conversations/original/edit',json={'message_index':0,'expected_revision':source.revision,'interaction':{**payload,'message':{'sender_id':'local-user','text':'改過訊息'}}})
    assert response.status_code==200
    branch=response.json()['conversation']
    assert branch['state_checkpoint_available'] is False
    assert '舊回覆的未來情節' not in json.dumps(LocalMemoryStore(root/'memories').snapshot(branch['chat_id']),ensure_ascii=False)


def test_failed_regeneration_preserves_original_and_edited_branch(trial,monkeypatch):
    owner,_,_,_,_,payload,_=normal_chat(trial,monkeypatch)
    assert owner.post('/api/interactions',json=payload).status_code==200
    source=owner.get('/api/conversations/original').json()
    class Broken:
        async def generate(self,*args):raise RuntimeError('secret-provider-key')
    monkeypatch.setattr(module,'AiServerCompatibleAdapter',lambda key=None:Broken())
    edited={**payload,'message':{'sender_id':'local-user','text':'改好但回覆失敗'}}
    response=owner.post('/api/conversations/original/edit',json={'message_index':0,'expected_revision':source['revision'],'interaction':edited})
    assert response.status_code==502 and 'secret-provider-key' not in response.text
    assert response.json()['conversation']['messages'][0]['text']=='改好但回覆失敗'
    assert owner.get('/api/conversations/original').json()==source


def test_trial_edit_stays_in_trial_storage_and_keeps_original(trial):
    owner,other,_,_,root,run_id,payload,calls=trial
    url=f'/api/character-generations/{run_id}/test-interactions'
    assert owner.post(url,json=payload).status_code==200
    assert owner.post(url,json={**payload,'text':'第二句'}).status_code==200
    source=owner.get(f'/api/character-generations/{run_id}/test-conversations/{payload["chat_id"]}').json()
    assert other.get(f'/api/character-generations/{run_id}/test-conversations/{payload["chat_id"]}').status_code==404
    response=owner.post(url+'/edit',json={**payload,'text':'改過的試聊','message_index':0,'expected_revision':source['revision']})
    assert response.status_code==200
    branch=response.json()['conversation']
    assert len(branch['messages'])==2 and branch['messages'][0]['text']=='改過的試聊'
    assert branch['state_checkpoint_available'] is True
    assert owner.get(f'/api/character-generations/{run_id}/test-conversations/{payload["chat_id"]}').json()==source
    assert owner.get('/api/conversations').json()==[]
    assert (root/'creator_trials'/'conversations'/f"{branch['chat_id']}.json").exists()


def test_checkpoint_values_are_immutable_deduplicated_and_prefix_bound(trial):
    _,_,_,activity,*_=trial
    state={'memories':[{'summary':'原記憶'}],'relationship':{},'profile':{}}
    activity.checkpoint('one',0,'hash',state);activity.checkpoint('two',0,'hash',state)
    state['memories'][0]['summary']='之後的修改'
    assert activity.checkpoint_for('one',0,'hash')['memories'][0]['summary']=='原記憶'
    assert activity.checkpoint_for('one',0,'wrong') is None
    with activity.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM checkpoint_values').fetchone()[0]==2

import json

import pytest
from diji.conversation_store import ConversationStore
from diji.conversation_store import ConversationMessage
from diji.player_personas import PlayerPersonaInput, PlayerPersonaStore
from test_draft_trial import trial
from test_message_edit import normal_chat


def persona(name='霧川'):
    return {'label':'旅行者', 'name':name, 'sex':'女', 'age':'28', 'description':'來自海邊的調香師，喜歡雨天。'}


def test_persona_storage_reopens_and_validates(tmp_path):
    path=tmp_path/'private'/'personas.sqlite3'
    saved=PlayerPersonaStore(path).save(PlayerPersonaInput(**persona()))
    assert PlayerPersonaStore(path).get(saved.id)==saved
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    with pytest.raises(LookupError):PlayerPersonaStore(path).save(PlayerPersonaInput(**persona()),'another-owner')


def test_personas_are_private_and_require_login(trial):
    owner,other,anonymous,*_=trial
    assert anonymous.get('/api/player-personas').status_code==401
    saved=owner.post('/api/player-personas',json=persona()).json()
    assert saved['id'].startswith('player-')
    assert len(owner.get('/api/player-personas').json())==2
    assert saved['id'] not in [item['id'] for item in other.get('/api/player-personas').json()]
    assert other.put('/api/player-personas/'+saved['id'],json=persona('冒用')).status_code==404
    for field in ['label','name']:
        assert owner.post('/api/player-personas',json={**persona(),field:'   '}).status_code==422
    assert owner.post('/api/player-personas',json={**persona(),'description':'a'*8001}).status_code==422


def test_persona_snapshot_in_prompt_stays_fixed_and_switch_is_fresh(trial,monkeypatch):
    owner,other,_,_,root,payload,calls=normal_chat(trial,monkeypatch)
    saved=owner.post('/api/player-personas',json=persona()).json()
    start={'chat_id':'persona-original','character_id':'edit-role','character_name':'編輯測試','player_persona_id':saved['id']}
    first=owner.post('/api/conversations',json=start)
    assert first.status_code==200 and first.json()['player_persona']['name']=='霧川'
    assert other.post('/api/conversations',json={**start,'character_id':'yelan'}).status_code==404
    turn={**payload,'chat_id':start['chat_id'],'user':{'id':'local-user','persona':{'name':'偽造名稱','description':'偽造背景','chat_mode':'dialog'}}}
    assert owner.post('/api/interactions',json=turn).status_code==200
    prompt=json.dumps(calls[-1],ensure_ascii=False)
    for text in ['霧川','調香師','性別：女','年齡：28']:assert text in prompt
    assert '偽造名稱' not in prompt and '偽造背景' not in prompt
    original=owner.get('/api/conversations/persona-original').json()
    assert original['player_persona']['description']==persona()['description']
    changed={**persona('清河'),'description':'山城的醫師'}
    assert owner.put('/api/player-personas/'+saved['id'],json=changed).status_code==200
    assert owner.post('/api/interactions',json=turn).status_code==200
    assert '霧川' in json.dumps(calls[-1],ensure_ascii=False) and '清河' not in json.dumps(calls[-1],ensure_ascii=False)
    assert json.dumps(calls[-1],ensure_ascii=False).count('性別：女')==1
    second=owner.post('/api/conversations',json={**start,'chat_id':'persona-new'}).json()
    assert second['player_persona']['name']=='清河' and second['messages']==[]
    assert owner.get('/api/memories/persona-new').json()==[]
    assert owner.get('/api/relationships/persona-new').json()['current_score']==0
    assert owner.post('/api/interactions',json={**turn,'chat_id':'persona-new','history':[]}).status_code==200
    assert '清河' in json.dumps(calls[-1],ensure_ascii=False) and '霧川' not in json.dumps(calls[-1],ensure_ascii=False)
    assert ConversationStore(root/'conversations').get('persona-original').player_persona.name=='霧川'
    assert owner.get('/api/conversations').json()[0]['player_name'] in ['清河','霧川']
    another=owner.post('/api/player-personas',json=persona('另一人')).json()
    assert owner.post('/api/conversations',json={**start,'player_persona_id':another['id']}).status_code==409


def test_message_edit_branch_retains_persona_snapshot(trial,monkeypatch):
    owner,_,_,_,_,payload,_=normal_chat(trial,monkeypatch)
    saved=owner.post('/api/player-personas',json=persona()).json()
    owner.post('/api/conversations',json={'chat_id':'with-persona','character_id':'edit-role','character_name':'角色','player_persona_id':saved['id']})
    payload={**payload,'chat_id':'with-persona'}
    assert owner.post('/api/interactions',json=payload).status_code==200
    source=owner.get('/api/conversations/with-persona').json()
    response=owner.post('/api/conversations/with-persona/edit',json={'message_index':0,'expected_revision':source['revision'],'interaction':payload})
    assert response.status_code==200
    branch=response.json()['conversation']
    assert branch['player_persona']==source['player_persona'] and branch['player_persona_id']==saved['id']


def test_chat_and_trial_require_persona_before_model_call(trial):
    owner,_,_,_,root,run_id,trial_payload,calls=trial
    with PlayerPersonaStore(root/'player_personas.sqlite3').connect() as db:
        db.execute('DELETE FROM personas')
    assert owner.put('/api/characters/persona-role',json={'id':'persona-role','name':'角色','premise':'背景','voice':'簡短'}).status_code==200
    start={'chat_id':'requires-player','character_id':'persona-role','character_name':'角色'}
    payload={'chat_id':'requires-player','llm':{'model':'test/model'},'character':{'id':'persona-role','name':'角色','description':'背景'},'user':{'id':'local-user','persona':{'name':'自行偽造'}},'message':{'sender_id':'local-user','text':'你好'},'enable_favorability':False}
    assert owner.post('/api/conversations',json=start).status_code==409
    assert owner.post('/api/interactions',json=payload).status_code==409
    assert owner.post(f'/api/character-generations/{run_id}/test-interactions',json=trial_payload).status_code==409
    assert calls==[] and owner.get('/api/conversations').json()==[]
    saved=owner.post('/api/player-personas',json=persona()).json()
    assert owner.post('/api/conversations',json=start).json()['player_persona_id']==saved['id']
    second=owner.post('/api/player-personas',json=persona('另一份')).json()
    assert owner.post('/api/conversations',json={**start,'chat_id':'must-choose'}).status_code==409
    assert owner.post('/api/conversations',json={**start,'chat_id':'must-choose','player_persona_id':second['id']}).status_code==200
    chats=ConversationStore(root/'conversations')
    chats.append('legacy-no-persona','persona-role','角色',ConversationMessage(sender_type=1,text='既有內容'))
    original=chats.get('legacy-no-persona')
    assert owner.post('/api/interactions',json={**payload,'chat_id':'legacy-no-persona'}).status_code==409
    assert chats.get('legacy-no-persona')==original and calls==[]


def test_delete_persona_is_account_scoped_and_preserves_started_chats_and_trials(trial,monkeypatch):
    owner,other,anonymous,_,root,payload,calls=normal_chat(trial,monkeypatch)
    _,_,_,_,_,run_id,trial_payload,_=trial
    saved=owner.post('/api/player-personas',json=persona()).json()
    start={'chat_id':'keep-after-delete','character_id':'edit-role','character_name':'角色','player_persona_id':saved['id']}
    assert owner.post('/api/conversations',json=start).status_code==200
    turn={**payload,'chat_id':start['chat_id']}
    assert owner.post('/api/interactions',json=turn).status_code==200
    trial_payload={**trial_payload,'player_persona_id':saved['id']}
    trial_url=f'/api/character-generations/{run_id}/test-interactions'
    assert owner.post(trial_url,json=trial_payload).status_code==200
    source=owner.get('/api/conversations/'+start['chat_id']).json()
    memories=owner.get('/api/memories/'+start['chat_id']).json()
    relationship=owner.get('/api/relationships/'+start['chat_id']).json()
    trial_record=ConversationStore(root/'creator_trials'/'conversations').get(trial_payload['chat_id'])
    url='/api/player-personas/'+saved['id']
    assert anonymous.delete(url).status_code==401
    assert other.delete(url).status_code==404
    assert owner.delete(url).status_code==204
    assert owner.delete(url).status_code==404
    assert owner.get('/api/conversations/'+start['chat_id']).json()==source
    assert owner.get('/api/memories/'+start['chat_id']).json()==memories
    assert owner.get('/api/relationships/'+start['chat_id']).json()==relationship
    assert ConversationStore(root/'creator_trials'/'conversations').get(trial_payload['chat_id'])==trial_record
    assert owner.post('/api/conversations',json={**start,'chat_id':'deleted-cannot-start'}).status_code==404
    for record in owner.get('/api/player-personas').json():
        assert owner.delete('/api/player-personas/'+record['id']).status_code==204
    assert owner.get('/api/player-personas').json()==[]
    assert owner.post('/api/conversations',json={**start,'chat_id':'no-personas','player_persona_id':None}).status_code==409
    assert owner.post('/api/interactions',json=turn).status_code==200
    assert '霧川' in json.dumps(calls[-1],ensure_ascii=False)
    assert owner.post(trial_url,json=trial_payload).status_code==200
    assert '霧川' in json.dumps(calls[-1],ensure_ascii=False)
    latest=owner.get('/api/conversations/'+start['chat_id']).json()
    edited=owner.post('/api/conversations/'+start['chat_id']+'/edit',json={'message_index':0,'expected_revision':latest['revision'],'interaction':turn})
    assert edited.status_code==200 and edited.json()['conversation']['player_persona']==source['player_persona']
    trial_record=ConversationStore(root/'creator_trials'/'conversations').get(trial_payload['chat_id'])
    edited_trial=owner.post(trial_url+'/edit',json={**trial_payload,'message_index':0,'expected_revision':trial_record.revision})
    assert edited_trial.status_code==200 and edited_trial.json()['conversation']['player_persona']==trial_record.player_persona.model_dump()

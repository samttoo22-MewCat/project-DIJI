import json

import pytest

import diji.local_app as module
from diji.character_generation import CharacterGenerationResult
from diji.character_generation.revision import apply_proposal
from test_draft_trial import trial


def proposal(path=None,value='修改後背景'):
    return json.dumps({'summary':'只更新背景','changes':[{'path':path or ['character','backstory'],'value':value}]},ensure_ascii=False)


def fake_revision(monkeypatch, response, callback=None):
    calls=[]
    class Client:
        async def complete(self,**kwargs):
            calls.append(kwargs)
            if callback: callback()
            if isinstance(response,Exception): raise response
            return response
    monkeypatch.setattr(module,'OpenRouterGenerationClient',lambda key=None:Client())
    return calls


def test_revision_updates_only_named_leaf_and_rebuilds_prompt(trial):
    owner,other,anonymous,activity,root,run_id,payload,calls=trial
    before=CharacterGenerationResult.model_validate(activity.get(run_id)['data']['draft'])
    after,summary,paths=apply_proposal(before,proposal())
    assert after.character.backstory=='修改後背景'
    assert before.character.backstory=='測試暗號：藍紙船'
    assert after.character.psychological_evolution==before.character.psychological_evolution
    assert after.style_guide==before.style_guide
    assert '<ROLEPLAY_CONTRACT>' in after.full_prompt and '修改後背景' in after.full_prompt
    assert paths==[['character','backstory']]


@pytest.mark.parametrize('path,value',[
    (['character'],{}), (['generation_id'],'different'),
    (['character','missing'],'new'), (['character','backstory'],{}),
])
def test_revision_rejects_broad_or_invalid_model_changes(trial,path,value):
    owner,other,anonymous,activity,root,run_id,payload,calls=trial
    before=CharacterGenerationResult.model_validate(activity.get(run_id)['data']['draft'])
    with pytest.raises(ValueError): apply_proposal(before,proposal(path,value))


def test_revision_api_private_recorded_and_not_added_to_library(trial,monkeypatch):
    owner,other,anonymous,activity,root,run_id,payload,_=trial
    calls=fake_revision(monkeypatch,proposal())
    url=f'/api/character-generations/{run_id}/revise'
    request={'revision':0,'model':'test/model','instruction':'只修改背景，保留其他設定'}
    assert anonymous.post(url,json=request).status_code==401
    assert other.post(url,json=request).status_code==404
    response=owner.post(url,json=request)
    assert response.status_code==200
    assert response.json()['draft']['revision']==1
    assert response.json()['draft']['character']['backstory']=='修改後背景'
    assert '測試核准內容' in calls[0]['prompt'] and '藍紙船' in calls[0]['prompt']
    assert run_id not in {c['id'] for c in owner.get('/api/characters').json()}
    assert owner.post(url,json=request).status_code==409
    with activity.connect() as db:
        row=db.execute("SELECT id FROM runs WHERE kind='draft_revision'").fetchone()
    record=activity.get(row['id'])
    assert record['status']=='completed' and record['data']['result_revision']==1
    assert record['data']['instruction']==request['instruction']
    assert len(record['events'])==2


def test_revision_conflict_preserves_newer_manual_draft(trial,monkeypatch):
    owner,_,_,activity,root,run_id,payload,_=trial
    def manual_change():
        draft=activity.get(run_id)['data']['draft']
        draft['character']['backstory']='另一頁較新的手動修改'
        activity.save_draft(run_id,0,draft)
    fake_revision(monkeypatch,proposal(),manual_change)
    response=owner.post(f'/api/character-generations/{run_id}/revise',json={'revision':0,'model':'test/model','instruction':'修改背景'})
    assert response.status_code==409
    assert activity.get(run_id)['data']['draft']['character']['backstory']=='另一頁較新的手動修改'


@pytest.mark.parametrize('output',[proposal(['character'],{}),'not JSON',RuntimeError('secret-provider-key')])
def test_revision_failure_keeps_original_and_hides_exception_secrets(trial,monkeypatch,output):
    owner,_,_,activity,root,run_id,payload,_=trial
    original=activity.get(run_id)['data']['draft']
    fake_revision(monkeypatch,output)
    response=owner.post(f'/api/character-generations/{run_id}/revise',json={'revision':0,'model':'test/model','instruction':'修改背景'})
    assert response.status_code==502
    assert activity.get(run_id)['data']['draft']==original
    assert 'secret-provider-key' not in response.text
    with activity.connect() as db:
        row=db.execute("SELECT id FROM runs WHERE kind='draft_revision'").fetchone()
    record=activity.get(row['id'])
    assert record['status']=='failed'
    assert 'secret-provider-key' not in json.dumps(record)

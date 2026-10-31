from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from diji.player_activity import PlayerActivity
from test_draft_trial import trial


def test_every_commit_and_rollback_are_immutable_after_reopening(trial):
    owner,_,_,activity,root,run_id,payload,_=trial
    first=activity.get(run_id)['data']['draft']
    second=activity.save_draft(run_id,0,{**first,'style_guide':'第二版風格'})
    third=activity.save_draft(run_id,1,{**second,'hobbies':'收藏茶杯'},source='ai',note='追加嗜好')
    restored=activity.restore_version(run_id,0,2)
    assert restored['revision']==3 and restored['style_guide']==first['style_guide']
    reopened=PlayerActivity(activity.path)
    assert [v['revision'] for v in reopened.versions(run_id)['versions']]==[3,2,1,0]
    assert reopened.version(run_id,1)['draft']['style_guide']=='第二版風格'
    assert reopened.version(run_id,2)['draft']['hobbies']=='收藏茶杯'
    assert reopened.version(run_id,3)['source']=='rollback'
    assert reopened.version(run_id,3)['restored_from']==0
    reopened.restore_version(run_id,2,3)
    assert reopened.get(run_id)['data']['draft']['hobbies']=='收藏茶杯'
    assert reopened.version(run_id,0)['draft']=={**first,'generation_id':run_id,'revision':0}


def test_concurrent_old_pages_cannot_overwrite_versions(trial):
    _,_,_,activity,_,run_id,_,_=trial
    first=activity.get(run_id)['data']['draft']
    def write(value):
        try:
            return activity.save_draft(run_id,0,{**first,'hobbies':value})['revision']
        except ValueError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(write,['甲版','乙版']))
    assert sorted(map(str,result))==['1','conflict']
    assert len(activity.versions(run_id)['versions'])==2
    with pytest.raises(ValueError):activity.restore_version(run_id,0,0)
    assert activity.get(run_id)['revision']==1


def test_version_api_is_scoped_and_requires_explicit_restore(trial):
    owner,other,anonymous,activity,_,run_id,_,calls=trial
    base=f'/api/character-generations/{run_id}'
    assert anonymous.get(base+'/versions').status_code==401
    assert other.get(base+'/versions').status_code==404
    assert other.get(base+'/versions/0').status_code==404
    assert other.post(base+'/rollback',json={'revision':0,'target_revision':0}).status_code==404
    assert owner.get(base+'/versions').headers['cache-control']=='private, no-store'
    response=owner.get(base+'/versions/0')
    assert response.status_code==200 and response.json()['draft']['character']['character_name']=='尚未保存的草稿'
    assert activity.get(run_id)['revision']==0
    assert owner.post(base+'/rollback',json={'revision':0,'target_revision':99}).status_code==404
    assert activity.get(run_id)['revision']==0
    response=owner.post(base+'/rollback',json={'revision':0,'target_revision':0})
    assert response.status_code==200 and response.json()['revision']==1
    assert calls==[]


def test_archived_character_rollback_forks_a_draft_without_changing_original(trial):
    owner,_,_,activity,_,run_id,_,calls=trial
    original=activity.get(run_id)['data']['draft']
    activity.finish(run_id,'completed',{'saved_character_id':'existing-character'})
    response=owner.post(f'/api/character-generations/{run_id}/rollback',json={'revision':0,'target_revision':0})
    assert response.status_code==200
    restored=response.json()
    assert restored['generation_id']!=run_id and restored['revision']==0
    assert activity.get(run_id)['data']['saved_character_id']=='existing-character'
    assert activity.get(run_id)['data']['draft']==original
    fork=activity.get(restored['generation_id'])
    assert fork['data']['parent_generation_id']==run_id
    assert activity.version(restored['generation_id'],0)['source']=='rollback'
    activity.save_draft(restored['generation_id'],0,restored)
    assert len(owner.get('/api/characters').json())==2 and calls==[]


def test_pagination_can_reach_all_versions(trial):
    _,_,_,activity,_,run_id,_,_=trial
    for i in range(5):
        draft=activity.get(run_id)['data']['draft']
        activity.save_draft(run_id,i,{**draft,'hobbies':str(i)})
    page=activity.versions(run_id,limit=2)
    revisions=[v['revision'] for v in page['versions']]
    while page['has_more']:
        page=activity.versions(run_id,before=page['next_before'],limit=2)
        revisions.extend(v['revision'] for v in page['versions'])
    assert revisions==[5,4,3,2,1,0]


def test_legacy_backfill_recovers_only_existing_snapshots_and_stage_outputs(trial):
    _,_,_,activity,_,run_id,_,_=trial
    original=activity.get(run_id)['data']['draft']
    stages={'character_profile':json.dumps(original['character']),'style_guide':original['style_guide'],
            'presentation':json.dumps({'description_for_app':original['description_for_app']}),'hobbies':'最初嗜好'}
    for stage,raw in stages.items():activity.event(run_id,stage,'completed',{'output':raw})
    current={**original,'revision':5,'hobbies':'現存第五版'}
    audit=activity.begin('draft_revision',{'generation_id':run_id,'base_revision':3,'before':{**original,'revision':3,'hobbies':'修改前快照'}})
    activity.finish(audit,'completed',{'result_revision':4,'proposed':{**original,'revision':4,'hobbies':'模型完成快照'},'summary':'歷史 AI 修改'})
    with activity.connect() as db:
        db.execute('DELETE FROM draft_versions WHERE run_id=?',(run_id,))
        db.execute('UPDATE runs SET data=?,revision=5 WHERE id=?',(json.dumps({'draft':current}),run_id))
    versions=activity.versions(run_id)['versions']
    assert [v['revision'] for v in versions]==[5,4,3,0]
    assert activity.version(run_id,0)['draft']['hobbies']=='最初嗜好'
    assert activity.version(run_id,3)['draft']['hobbies']=='修改前快照'
    assert activity.version(run_id,4)['draft']['hobbies']=='模型完成快照'
    with pytest.raises(LookupError):activity.version(run_id,2)
    assert len(activity.versions(run_id)['versions'])==4


def test_confirmed_role_records_last_unsynced_content_as_its_own_version(trial):
    owner,_,_,activity,_,run_id,_,_=trial
    original=activity.get(run_id)['data']['draft']
    profile={**original['character'],'backstory':'儲存角色時最後修改'}
    response=owner.put(f'/api/characters/{run_id}',json={'id':run_id,'name':profile['character_name'],'premise':'測試用草稿',
        'voice':'測試','profile':profile,'style_guide':original['style_guide'],'source':{'generated_file':'DIJI character creator','generation_id':run_id}})
    assert response.status_code==200
    assert activity.version(run_id,0)['draft']['character']['backstory']==original['character']['backstory']
    assert activity.versions(run_id)['versions'][0]['source']=='confirmed'
    assert activity.get(run_id)['data']['draft']['character']['backstory']=='儲存角色時最後修改'

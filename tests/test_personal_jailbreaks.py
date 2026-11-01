import json
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

import diji.local_app as module
from diji.auth import SESSION_COOKIE
from diji.experiments import JailbreakStore,JailbreakPreset
from diji.experiments.account_store import AccountPresetStore
from test_concurrent_usage import concurrent_app


def setup_players(ctx):
    app,_,players,payload,_,root=ctx
    defaults=JailbreakStore(root/'presets.json')
    preset=JailbreakPreset(id='qa-default',name='預設測試',model='test/model',last_updated='2026-11-01',source_url='https://example.test',review_status='approved',prompt='DEFAULT_PRESET_MARKER',openrouter_models=['test/model'])
    defaults.save(preset)
    owner,other,anonymous=TestClient(app),TestClient(app),TestClient(app)
    owner.cookies.set(SESSION_COOKIE,players[0][1]);other.cookies.set(SESSION_COOKIE,players[1][1])
    return owner,other,anonymous,defaults,preset,payload,root,players


def test_edits_are_private_and_deleting_override_restores_default(concurrent_app):
    owner,other,anonymous,defaults,preset,_,root,players=setup_players(concurrent_app)
    before=defaults.path.read_bytes()
    assert owner.get('/api/jailbreaks').json()[0]['storage_scope']=='default'
    assert not (root/'users'/players[0][0].id/'jailbreaks.json').exists()
    changed={**preset.model_dump(),'prompt':'PERSONAL_PRESET_MARKER','storage_scope':'default'}
    assert anonymous.put('/api/jailbreaks/qa-default',json=changed).status_code==401
    response=owner.put('/api/jailbreaks/qa-default',json=changed)
    assert response.status_code==200 and response.json()['storage_scope']=='personal'
    assert other.get('/api/jailbreaks').json()[0]['prompt']==preset.prompt
    assert defaults.path.read_bytes()==before
    private=root/'users'/players[0][0].id/'jailbreaks.json'
    assert private.stat().st_mode & 0o777==0o600 and len(json.loads(private.read_text()))==1
    assert owner.delete('/api/jailbreaks/qa-default').status_code==200
    assert owner.get('/api/jailbreaks').json()[0]['prompt']==preset.prompt
    assert owner.delete('/api/jailbreaks/qa-default').status_code==403
    assert defaults.path.read_bytes()==before
    assert 'no-store' in owner.get('/api/jailbreaks').headers['cache-control']


def test_chat_uses_own_preset_and_internal_experiments_are_private(concurrent_app):
    owner,other,_,defaults,preset,payload,root,players=setup_players(concurrent_app)
    owner.put('/api/jailbreaks/qa-default',json={**preset.model_dump(),'prompt':'PERSONAL_PRESET_MARKER'})
    body={**payload,'is_nsfw':True}
    first=owner.post('/api/interactions',json=body);second=other.post('/api/interactions',json=body)
    assert first.status_code==second.status_code==200
    own=json.dumps(first.json()['messages']);other_messages=json.dumps(second.json()['messages'])
    assert 'PERSONAL_PRESET_MARKER' in own and 'DEFAULT_PRESET_MARKER' not in own
    assert 'DEFAULT_PRESET_MARKER' in other_messages and 'PERSONAL_PRESET_MARKER' not in other_messages
    assert not (root/'experiments.json').exists()
    assert (root/'users'/players[0][0].id/'experiments.json').exists()
    assert owner.put('/api/experiments/qa-private',json={'id':'qa-private','name':'私人設定'}).status_code==200
    assert not any(x['id']=='qa-private' for x in other.get('/api/experiments').json())
    assert defaults.get('qa-default').prompt=='DEFAULT_PRESET_MARKER'


def test_character_generation_uses_personal_preset(concurrent_app,monkeypatch):
    owner,_,_,_,preset,_,_,_=setup_players(concurrent_app)
    owner.put('/api/jailbreaks/qa-default',json={**preset.model_dump(),'prompt':'PERSONAL_CREATOR_MARKER'})
    prompts=[];outputs=['{"character_name":"隔離草稿"}','簡短風格','{"description_for_app":"測試"}','閱讀']
    class Generation:
        async def complete(self,**kwargs):
            prompts.append(kwargs['prompt']);return outputs[len(prompts)-1]
    monkeypatch.setattr(module,'OpenRouterGenerationClient',lambda key=None:Generation())
    response=owner.post('/api/characters/generate',json={'keywords':'隔離測試','model':'test/model','enable_search':False,'is_nsfw':True})
    assert response.status_code==200
    assert 'PERSONAL_CREATOR_MARKER' in prompts[0] and 'PERSONAL_CREATOR_MARKER' in prompts[1]
    assert all('DEFAULT_PRESET_MARKER' not in p for p in prompts)


def test_custom_presets_imports_and_concurrent_saves_do_not_modify_defaults(concurrent_app):
    owner,other,_,defaults,preset,_,root,players=setup_players(concurrent_app)
    before=defaults.path.read_bytes()
    assert owner.post('/api/jailbreaks/import-recent').status_code==200
    assert len(other.get('/api/jailbreaks').json())==1 and defaults.path.read_bytes()==before
    store=AccountPresetStore(defaults,JailbreakStore(root/'users'/players[0][0].id/'jailbreaks.json'))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i:store.save(preset.model_copy(update={'id':f'qa-own-{i}'})),range(20)))
    assert len([p for p in store.list() if p.id.startswith('qa-own-')])==20
    assert not any(p['id'].startswith('qa-own-') for p in other.get('/api/jailbreaks').json())
    assert owner.delete('/api/jailbreaks/qa-own-1').status_code==200
    assert all(p['id']!='qa-own-1' for p in owner.get('/api/jailbreaks').json())

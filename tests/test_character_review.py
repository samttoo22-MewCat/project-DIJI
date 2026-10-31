from fastapi.testclient import TestClient
from diji.local_app import create_app
from diji.local_catalog import LocalCatalog


def test_review_edits_rebuild_full_prompt_without_duplicate_character(tmp_path):
    client = TestClient(create_app(catalog=LocalCatalog(tmp_path / 'catalog.json')))
    payload = {'id':'review-test', 'name':'修改後名稱', 'premise':'修改後簡介', 'voice':'新的說話方式',
               'profile':{'character_name':'原名稱', 'backstory':'修改後背景', 'personality':{'core_traits':['沉穩','細心']}},
               'style_guide':'修改後風格指南', 'full_prompt':'過時的人設內容',
               'generation_metadata': {'brief_description':'一句話', 'category':'未分類', 'hobbies':'修復古書、品茶'},
               'source':{'generated_file':'DIJI character creator'}}
    first = client.put('/api/characters/review-test', json=payload)
    assert first.status_code == 200
    saved = first.json()
    assert saved['profile']['character_name'] == '修改後名稱'
    assert '修改後背景' in saved['full_prompt']
    assert '修改後風格指南' in saved['full_prompt']
    assert '過時的人設內容' not in saved['full_prompt']
    assert '<ROLEPLAY_CONTRACT>' in saved['full_prompt']
    assert saved['generation_metadata'] == payload['generation_metadata']
    assert client.put('/api/characters/review-test', json=payload).status_code == 200
    assert sum(item['id']=='review-test' for item in client.get('/api/characters').json()) == 1

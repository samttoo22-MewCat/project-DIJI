from diji.memory_store import LocalMemoryStore, MemoryRecord


def test_multi_value_keywords_match_each_value_without_changing_order(tmp_path):
    store = LocalMemoryStore(tmp_path)
    for day, value in [('01', '青禾、夜蘭'), ('02', '青禾，沈舟;嘉維斯\n月橋書店')]:
        store.add('keyword-test', MemoryRecord(timestamp=f'2026-11-{day} 10:00', summary=day, keywords={'人物': value}))
    assert [r.summary for r in store.relevant_for_message('keyword-test', '青禾喜歡什麼')] == ['02', '01']
    assert [r.summary for r in store.search_by_text('keyword-test', '夜蘭的約定')] == ['01']
    assert [r.summary for r in store.search_by_text('keyword-test', '嘉維斯去月橋書店')] == ['02']
    assert store.search_by_text('keyword-test', '陌生人') == []
    assert store.search_by_text('keyword-test', '青') == []


def test_keyword_phrases_keep_spaces_and_ignore_empty_parts(tmp_path):
    store = LocalMemoryStore(tmp_path)
    store.add('keyword-test', MemoryRecord(summary='地點', keywords={'地點': 'New York、、月橋書店，'}))
    assert store.search_by_text('keyword-test', 'New York 見面')
    assert store.search_by_text('keyword-test', '月橋書店在哪')
    assert store.search_by_text('keyword-test', 'York') == []
    assert store.search_by_text('keyword-test', '') == []


def test_memory_page_can_read_more_records_without_changing_sidebar_default(tmp_path):
    from fastapi.testclient import TestClient
    from diji.local_app import create_app
    from diji.local_catalog import LocalCatalog

    store = LocalMemoryStore(tmp_path / 'memories')
    for index in range(15):
        store.add('keyword-test', MemoryRecord(summary=str(index)))
    client = TestClient(create_app(LocalCatalog(tmp_path / 'catalog.json'), memory_store=store))
    assert len(client.get('/api/memories/keyword-test').json()) == 10
    assert len(client.get('/api/memories/keyword-test?limit=100').json()) == 15
    assert client.get('/api/memories/keyword-test?limit=501').status_code == 422

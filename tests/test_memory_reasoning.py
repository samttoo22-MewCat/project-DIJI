import asyncio
import json

import httpx
from openai import AsyncOpenAI

from diji.memory_extraction import MemoryExtractor, OpenRouterExtractionClient


def test_extraction_keeps_the_budget_for_structured_memory_instead_of_reasoning():
    def respond(request):
        body = json.loads(request.content)
        assert body['model'] == 'deepseek/deepseek-v4.1-flash'
        assert body['max_tokens'] == 1000
        assert body['response_format'] == {'type': 'json_object'}
        disabled = body.get('reasoning', {}).get('enabled') is False
        content = json.dumps({'type': '偏好', 'summary': '青禾喜歡桂花烏龍', 'keywords': {'人物': '青禾', '物品': '桂花烏龍'}}, ensure_ascii=False) if disabled else ''
        return httpx.Response(200, json={
            'id': 'memory-test', 'object': 'chat.completion', 'created': 0,
            'model': body['model'], 'choices': [{'index': 0, 'finish_reason': 'stop' if disabled else 'length', 'message': {'role': 'assistant', 'content': content, 'reasoning': '' if disabled else 'thinking'}}],
        })

    async def extract():
        adapter = OpenRouterExtractionClient('test-only-key')
        async with AsyncOpenAI(api_key='test-only-key', base_url='https://provider.example/v1', http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            adapter.client = client
            return await MemoryExtractor(adapter).extract('青禾喜歡桂花烏龍')

    records = asyncio.run(extract())
    assert len(records) == 1
    assert records[0].keywords['人物'] == '青禾'

import asyncio
import httpx
import pytest
from diji.provider_routing import CreditRoutingTransport


@pytest.mark.parametrize('status,expected', [(402, ['api.bazaarlink.ai', 'openrouter.ai']), (500, ['api.bazaarlink.ai']), (200, ['api.bazaarlink.ai'])])
def test_only_credit_rejection_uses_second_provider(status, expected):
    calls = []
    async def handler(request):
        calls.append(request.url.host)
        assert request.url.path.endswith('/chat/completions')
        assert request.headers['authorization'] == ('Bearer bazaar-test' if request.url.host == 'api.bazaarlink.ai' else 'Bearer router-test')
        return httpx.Response(status if len(calls) == 1 else 200, json={'ok': True})
    async def run():
        transport = CreditRoutingTransport([('bazaarlink','bazaar-test'),('openrouter','router-test')], httpx.MockTransport(handler))
        async with httpx.AsyncClient(transport=transport) as client:
            await client.post('https://openrouter.ai/api/v1/chat/completions', json={'model':'test'})
    asyncio.run(run())
    assert calls == expected

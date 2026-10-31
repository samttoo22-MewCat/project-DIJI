import asyncio
from decimal import Decimal
import httpx
from cryptography.fernet import Fernet
from diji.auth import AccountStore
from diji.provider_routing import ProviderCredentials, CreditRoutingTransport


def test_response_cost_is_recorded_once_and_survives_reopen(tmp_path):
    key = Fernet.generate_key().decode()
    store = AccountStore(tmp_path / 'accounts.db', key)
    credentials = ProviderCredentials([('bazaarlink', 'test-key')], lambda provider, rid, cost: store.record_provider_usage('owner', provider, rid, cost))
    def handler(request):
        return httpx.Response(200, json={'id':'response-1', 'usage':{'cost':0.012345}, 'choices':[]})
    async def run():
        async with httpx.AsyncClient(transport=CreditRoutingTransport(credentials, httpx.MockTransport(handler))) as client:
            for _ in range(2):
                result = await client.post('https://openrouter.ai/api/v1/chat/completions', json={})
                assert result.json()['id'] == 'response-1'
    asyncio.run(run())
    reopened = AccountStore(tmp_path / 'accounts.db', key)
    usage = reopened.provider_usage('owner', 'bazaarlink')
    assert usage['requests'] == 1
    assert Decimal(usage['total']) == Decimal('0.012345')
    assert reopened.provider_usage('other', 'bazaarlink')['total'] is None
    reopened.record_provider_usage('owner','bazaarlink','bad','NaN')
    assert reopened.provider_usage('owner','bazaarlink')['requests'] == 1

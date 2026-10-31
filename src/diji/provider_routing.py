"""Route each model call using the account's ordered, encrypted credentials."""
import httpx
from openai import AsyncOpenAI

BASES = {"openrouter": "https://openrouter.ai/api/v1", "bazaarlink": "https://api.bazaarlink.ai/v1"}


class CreditRoutingTransport(httpx.AsyncBaseTransport):
    def __init__(self, credentials, transport=None):
        self.credentials = credentials
        self.transport = transport or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request):
        body = await request.aread()
        for index, (provider, key) in enumerate(self.credentials):
            headers = dict(request.headers)
            headers.pop("host", None)
            headers["authorization"] = f"Bearer {key}"
            url = BASES[provider] + request.url.path.removeprefix("/api/v1")
            outgoing = httpx.Request(request.method, url, headers=headers, content=body, extensions=request.extensions)
            response = await self.transport.handle_async_request(outgoing)
            # Only an explicit rejection for insufficient credit permits trying the next account.
            if response.status_code == 402 and index + 1 < len(self.credentials):
                await response.aclose()
                continue
            return response

    async def aclose(self):
        await self.transport.aclose()


def provider_client(api_key, base_url="https://openrouter.ai/api/v1"):
    if isinstance(api_key, list):
        return AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key="server-routed", max_retries=0,
                           http_client=httpx.AsyncClient(transport=CreditRoutingTransport(api_key)))
    return AsyncOpenAI(base_url=base_url, api_key=api_key)

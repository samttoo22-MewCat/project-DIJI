import pytest

from diji.domain import ModelConfiguration
from diji.provider_routing import ProviderCredentials
from diji.public_models import PublicModelError, validate_public_model


def credentials(*providers):
    return ProviderCredentials([(provider, 'account-key') for provider in providers], None)


@pytest.mark.parametrize('model', [
    'DIGI', 'digi-v1', 'DIGI/provider', 'Joi', 'jOi', 'DIJI-Joi',
    'orpo', 'ORPO', '/models/orpo_merged_qwen35_gptq',
    'skylark-model', 'SKYLARK-model', 'skylark-model/provider',
    'https://example.test/model', 'provider/model/extra', 'provider/model:ONLINE',
    ' provider/model', 'provider/model\n',
])
def test_public_rejects_internal_aliases_and_invalid_ids(model):
    with pytest.raises(PublicModelError):
        validate_public_model(ModelConfiguration(model=model), required=True, credentials=credentials('openrouter'))


@pytest.mark.parametrize('url', ['https://openrouter.ai/api/v1', 'http://127.0.0.1:8000', 'http://100.108.209.35:8000', ''])
def test_public_rejects_every_supplied_url(url):
    with pytest.raises(PublicModelError):
        validate_public_model(ModelConfiguration(model='test/model', url=url), required=True, credentials=credentials('openrouter'))


@pytest.mark.parametrize('creds', [None, 'site-key', [], [('openrouter', 'account-key')], credentials('other'), credentials('openrouter', 'other'), credentials()])
def test_public_requires_account_routed_supported_credentials(creds):
    with pytest.raises(PublicModelError):
        validate_public_model(ModelConfiguration(model='test/model'), required=True, credentials=creds)


@pytest.mark.parametrize('model', ['test/model', 'deepseek/deepseek-v4.1-flash', 'google/gemini-2.5-pro:online', 'provider/model:free'])
@pytest.mark.parametrize('provider', ['openrouter', 'bazaarlink'])
def test_public_allows_normal_models_and_account_providers(model, provider):
    validate_public_model(ModelConfiguration(model=model), required=True, credentials=credentials(provider))


def test_local_mode_preserves_existing_routing():
    validate_public_model(ModelConfiguration(model='DIGI', url='http://127.0.0.1:8000'), required=False, credentials=None)

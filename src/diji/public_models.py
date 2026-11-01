"""Validate untrusted model selections before public-mode model calls."""

from __future__ import annotations

import re

from .domain import ModelConfiguration
from .provider_routing import ProviderCredentials


class PublicModelError(ValueError):
    """A public request cannot safely use the supplied model or credentials."""


_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*(?::(?:online|free))?", re.ASCII)
_PROVIDERS = frozenset({"openrouter", "bazaarlink"})


def validate_public_model(config: ModelConfiguration, *, required: bool, credentials: object) -> None:
    """Reject unsafe public routing; callers must supply credentials for the current account.

    This does not determine whether a model has an approved adult-content preset.
    Local mode leaves the existing ai-server routing untouched.
    """
    if not required:
        return
    if not isinstance(credentials, ProviderCredentials) or not credentials:
        raise PublicModelError("此帳號尚未設定模型連線")
    if any(not isinstance(item, tuple) or len(item) != 2 or item[0] not in _PROVIDERS
           or not isinstance(item[1], str) or not item[1].strip() for item in credentials):
        raise PublicModelError("模型連線無效")
    model = config.model
    lowered = model.casefold()
    if (config.url is not None or lowered.startswith(("digi", "skylark-"))
            or lowered in {"joi", "diji-joi", "orpo", "/models/orpo_merged_qwen35_gptq"}
            or not _MODEL_ID.fullmatch(model)):
        raise PublicModelError("公開模式不支援此模型或自訂網址")

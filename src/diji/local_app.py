"""Local HTTP composition root. Model calls happen only through explicit POST routes."""

from __future__ import annotations

from pathlib import Path
import os
import uuid
from contextvars import ContextVar
from typing import Literal

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, SecretStr

from .local_catalog import CatalogSnapshot, CharacterSpec, FlowSpec, LocalCatalog
from .character_generation.service import GeneratedCharacter
from .character_generation.revision import DraftRevisionRequest, revision_prompt, apply_proposal
from .conversation_store import ConversationBusy, ConversationMessage, ConversationRecord, ConversationStore, ConversationSummary
from .provider_routing import provider_session
from .character_import import CharacterImporter, CharacterImportPreview, CharacterImportRequest, CharacterImportResult
from .memory_store import LocalMemoryStore, MemoryRecord
from .player_activity import PlayerActivity, RecordedGenerationClient
from .memory_extraction import MemoryExtractor, OpenRouterExtractionClient
from .prompt_assembly import PromptBundle, PromptPreviewRequest, assemble_prompt
from .domain import InteractionRequest, InteractionResponse
from .experiments import ExperimentStore, JailbreakPreset, JailbreakStore, PromptExperiment
from .experiments.account_store import AccountPresetStore
from .interaction import InteractionService
from .model_adapter import AiServerCompatibleAdapter
from .relationship import RelationshipStore, RelationshipState
from .user_profile import UserProfileStore
from .favorability_judge import OpenRouterFavorabilityJudge
from .character_generation import (
    CharacterGenerationRequest,
    CharacterGenerationResult,
    CharacterGenerationService,
    OpenRouterGenerationClient,
)
from .auth import (
    AccountStore,
    AuthSettings,
    AuthenticatedUser,
    GoogleOAuthClient,
    OpenRouterOAuthClient,
    SESSION_COOKIE,
    SESSION_DAYS,
    google_authorization_url,
    authorization_url,
)


PROJECT_ROOT = Path(__file__).parents[2]
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "runtime" / "catalog.json"
DEFAULT_MEMORY_DIRECTORY = PROJECT_ROOT / "runtime" / "memories"
DEFAULT_CONVERSATION_DIRECTORY = PROJECT_ROOT / "runtime" / "conversations"
DEFAULT_RELATIONSHIP_DIRECTORY = PROJECT_ROOT / "runtime" / "relationships"
DEFAULT_USER_PROFILE_DIRECTORY = PROJECT_ROOT / "runtime" / "user_profiles"
DEFAULT_EXPERIMENT_PATH = PROJECT_ROOT / "runtime" / "experiments.json"
DEFAULT_JAILBREAK_PATH = PROJECT_ROOT / "runtime" / "jailbreaks.json"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_ACCOUNT_DATABASE_PATH = PROJECT_ROOT / "runtime" / "accounts.sqlite3"
DEFAULT_USER_DIRECTORY = PROJECT_ROOT / "runtime" / "users"
DEFAULT_AI_SERVER_OUTPUT_DIRECTORY = Path(
    os.getenv("DIJI_AI_SERVER_OUTPUT_DIR", PROJECT_ROOT.parent / "ai-server" / "api_server" / "configs" / "output")
)
UI_DIRECTORY = PROJECT_ROOT / "ui"


class OpenRouterKeyUpdate(BaseModel):
    openrouter_api_key: SecretStr = Field(min_length=1, max_length=1024)


class ConversationStart(BaseModel):
    chat_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    character_id: str = Field(min_length=1, max_length=64)
    character_name: str = Field(min_length=1, max_length=80)
    chat_mode: Literal["story", "dialog"] = "story"


class ConversationModeUpdate(BaseModel):
    chat_mode: Literal["story", "dialog"]


class MemoryUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    type: Literal["事實", "偏好", "事件", "標記", "event"]
    summary: str = Field(min_length=1, max_length=60)
    keywords: dict[str, str] = Field(default_factory=dict, max_length=32)
    key_points: list[str] = Field(default_factory=list, max_length=5)
    character_response_summary: str | None = Field(default=None, max_length=2000)


def _user_directory(user_id: str) -> Path:
    if not user_id or any(part in user_id for part in ("/", "\\", "..")):
        raise ValueError("Invalid user id")
    return DEFAULT_USER_DIRECTORY / user_id


def save_openrouter_key(path: Path, key: str) -> None:
    """Persist a local provider key without ever returning or logging it."""
    value = key.strip()
    if not value or "\n" in value or "\r" in value:
        raise ValueError("OpenRouter key must be one line")
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    replacement = f"OPENROUTER_API_KEY={value}"
    updated = [replacement if line.startswith("OPENROUTER_API_KEY=") else line for line in lines]
    if not any(line.startswith("OPENROUTER_API_KEY=") for line in lines):
        updated.append(replacement)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)
    os.environ["OPENROUTER_API_KEY"] = value


class DraftTrialRequest(BaseModel):
    chat_id: str = Field(pattern=r'^trial-[a-z0-9-]{1,57}$')
    revision: int = Field(ge=0)
    model: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=16_000)
    chat_mode: Literal['story', 'dialog'] = 'dialog'
    is_nsfw: bool = False


class DraftRollbackRequest(BaseModel):
    revision: int = Field(ge=0)
    target_revision: int = Field(ge=0)


class ConversationEditRequest(BaseModel):
    message_index: int = Field(ge=0,le=4999)
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    interaction: InteractionRequest


class TrialEditRequest(DraftTrialRequest):
    message_index: int = Field(ge=0,le=4999)
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


def create_app(
    catalog: LocalCatalog | None = None,
    memory_store: LocalMemoryStore | None = None,
    memory_extractor: MemoryExtractor | None = None,
    relationship_store: RelationshipStore | None = None,
    experiment_store: ExperimentStore | None = None,
    jailbreak_store: JailbreakStore | None = None,
    interaction_service: InteractionService | None = None,
    character_generator: CharacterGenerationService | None = None,
    character_importer: CharacterImporter | None = None,
    env_path: Path | None = None,
    conversation_store: ConversationStore | None = None,
    user_profile_store: UserProfileStore | None = None,
    account_store: AccountStore | None = None,
    auth_settings: AuthSettings | None = None,
    oauth_client: OpenRouterOAuthClient | None = None,
    google_oauth_client: GoogleOAuthClient | None = None,
) -> FastAPI:
    """Create the local app without sending any provider request during startup."""

    local_catalog = catalog or LocalCatalog(DEFAULT_CATALOG_PATH)
    local_memories = memory_store or LocalMemoryStore(DEFAULT_MEMORY_DIRECTORY)
    conversations = conversation_store or ConversationStore(DEFAULT_CONVERSATION_DIRECTORY)
    extractor = memory_extractor or MemoryExtractor(OpenRouterExtractionClient())
    relationships = relationship_store or RelationshipStore(DEFAULT_RELATIONSHIP_DIRECTORY)
    profiles = user_profile_store or UserProfileStore(DEFAULT_USER_PROFILE_DIRECTORY)
    experiments = experiment_store or ExperimentStore(DEFAULT_EXPERIMENT_PATH)
    jailbreaks = jailbreak_store or JailbreakStore(DEFAULT_JAILBREAK_PATH)
    interactions = interaction_service or InteractionService(
        AiServerCompatibleAdapter(), local_memories, extractor, relationships, experiments, OpenRouterFavorabilityJudge(), jailbreaks, profiles
    )
    generator = character_generator or CharacterGenerationService(OpenRouterGenerationClient())
    importer = character_importer or CharacterImporter(DEFAULT_AI_SERVER_OUTPUT_DIRECTORY)
    environment_file = env_path or DEFAULT_ENV_PATH
    auth = auth_settings or AuthSettings.from_environment()
    accounts = account_store or AccountStore(DEFAULT_ACCOUNT_DATABASE_PATH, auth.encryption_key)
    oauth = oauth_client or OpenRouterOAuthClient()
    google_oauth = google_oauth_client or GoogleOAuthClient()
    app = FastAPI(title="DIJI Local Workbench", docs_url=None, redoc_url=None)
    request_cache = ContextVar('diji_request_cache', default=None)

    def cached(key, factory):
        cache = request_cache.get()
        if cache is None:
            return factory()
        if key not in cache:
            cache[key] = factory()
        return cache[key]

    def credentials_for(user_id):
        return cached(('credentials', user_id), lambda: accounts.provider_credentials(user_id))

    @app.middleware("http")
    async def protect_workspace(request: Request, call_next):
        public_auth = {
            "/api/auth/session", "/api/auth/google/start", "/api/auth/google/callback",
            "/api/auth/logout", "/api/auth/openrouter/start", "/api/auth/openrouter/callback",
        }
        path = request.url.path
        token = request_cache.set({})
        try:
            if path.startswith('/api/') or path == '/openapi.json':
                request.state.diji_user = await run_in_threadpool(accounts.user_for_session, request.cookies.get(SESSION_COOKIE))
                if auth.required and path not in public_auth and not request.state.diji_user:
                    return JSONResponse({"detail": "請先使用 Google 登入 DIJI"}, status_code=401, headers={"Cache-Control": "no-store"})
            async with provider_session():
                return await call_next(request)
        finally:
            request_cache.reset(token)

    def session_user(request):
        if hasattr(request.state, 'diji_user'):
            return request.state.diji_user
        return accounts.user_for_session(request.cookies.get(SESSION_COOKIE))

    def current_user(request: Request) -> AuthenticatedUser:
        user = session_user(request)
        if auth.required and not user:
            raise HTTPException(status_code=401, detail="請先登入 DIJI")
        return user or AuthenticatedUser(id="local-user", login_provider="local", display_name="本機使用者", openrouter_user_id="local-user")

    def activity_for(user: AuthenticatedUser) -> PlayerActivity:
        root = _user_directory(user.id) if auth.required else local_catalog.path.parent
        return cached(('activity', user.id), lambda: PlayerActivity(root / 'player_activity.sqlite3'))

    def jailbreaks_for(user):
        if not auth.required:return jailbreaks
        return cached(('jailbreaks',user.id),lambda: AccountPresetStore(jailbreaks,JailbreakStore(_user_directory(user.id)/'jailbreaks.json')))

    def experiments_for(user):
        if not auth.required:return experiments
        return cached(('experiments',user.id),lambda: AccountPresetStore(experiments,ExperimentStore(_user_directory(user.id)/'experiments.json')))

    def stores_for(user: AuthenticatedUser, *, trial: bool = False, profile_chat_id: str | None = None) -> tuple[LocalMemoryStore, ConversationStore, RelationshipStore, UserProfileStore, InteractionService, CharacterGenerationService]:
        return cached(('stores',user.id,trial,profile_chat_id),lambda: make_stores(user,trial=trial,profile_chat_id=profile_chat_id))

    def make_stores(user, *, trial=False, profile_chat_id=None):
        if not auth.required and not trial and profile_chat_id is None:
            return local_memories, conversations, relationships, profiles, interactions, generator
        root = _user_directory(user.id) if auth.required else local_catalog.path.parent
        if trial:
            root = root / 'creator_trials'
        root.mkdir(parents=True, exist_ok=True)
        root.chmod(0o700)
        user_memories = LocalMemoryStore(root / "memories")
        user_relationships = RelationshipStore(root / "relationships")
        user_profiles = UserProfileStore(root / 'branch_profiles' / profile_chat_id if profile_chat_id else root / 'user_profiles')
        api_key = credentials_for(user.id)
        user_interactions = InteractionService(
            AiServerCompatibleAdapter(api_key),
            user_memories,
            MemoryExtractor(OpenRouterExtractionClient(api_key)),
            user_relationships,
            experiments_for(user),
            OpenRouterFavorabilityJudge(api_key),
            jailbreaks_for(user),
            user_profiles,
        )
        return (
            user_memories,
            ConversationStore(root / "conversations"),
            user_relationships,
            user_profiles,
            user_interactions,
            CharacterGenerationService(OpenRouterGenerationClient(api_key)),
        )

    @app.get("/api/auth/session")
    def session(request: Request, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        user = session_user(request)
        return {
            "auth_required": auth.required,
            "authenticated": bool(user),
            "user": user.model_dump() if user else None,
            "google_login_available": auth.google_login_available,
        }

    @app.get("/api/auth/google/start")
    def start_google_login() -> RedirectResponse:
        if not auth.google_login_available:
            raise HTTPException(status_code=503, detail="Google 登入尚未設定 DIJI_GOOGLE_CLIENT_ID、DIJI_GOOGLE_CLIENT_SECRET 與 DIJI_GOOGLE_OAUTH_CALLBACK_URL")
        state = accounts.begin_google_oauth()
        response = RedirectResponse(google_authorization_url(auth.google_callback_url or "", state, auth.google_client_id or ""), status_code=303)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/auth/google/callback")
    async def finish_google_login(code: str, state: str) -> RedirectResponse:
        if not auth.google_login_available:
            raise HTTPException(status_code=503, detail="Google 登入尚未設定")
        if not accounts.consume_google_oauth_state(state):
            raise HTTPException(status_code=400, detail="登入連線已過期，請重新開始")
        try:
            subject, display_name, email = await google_oauth.exchange(code, auth.google_callback_url or "", auth.google_client_id or "", auth.google_client_secret or "")
            user = accounts.upsert_google_user(subject, display_name, email)
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(status_code=400, detail=f"Google 登入未完成：{error}") from error
        response = RedirectResponse("/", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            SESSION_COOKIE,
            accounts.create_google_session(user.id),
            max_age=SESSION_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=auth.secure_cookie,
            samesite="lax",
            path="/",
        )
        return response

    @app.get("/api/auth/openrouter/start")
    def start_openrouter_login() -> RedirectResponse:
        if not auth.encryption_key:
            raise HTTPException(status_code=503, detail="伺服器尚未設定 DIJI_CREDENTIAL_ENCRYPTION_KEY")
        state, _verifier, challenge = accounts.begin_oauth()
        response = RedirectResponse(authorization_url(auth.callback_url, state, challenge), status_code=303)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/auth/openrouter/callback")
    async def finish_openrouter_login(code: str, state: str) -> RedirectResponse:
        verifier = accounts.consume_oauth_verifier(state)
        if not verifier:
            raise HTTPException(status_code=400, detail="登入連線已過期，請重新開始")
        try:
            openrouter_user_id, key = await oauth.exchange(code, verifier)
            user = accounts.upsert_openrouter_user(openrouter_user_id, key)
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=400, detail=f"OpenRouter 登入未完成：{error}") from error
        response = RedirectResponse("/", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            SESSION_COOKIE,
            accounts.create_session(user.id),
            max_age=SESSION_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=auth.secure_cookie,
            samesite="lax",
            path="/",
        )
        return response

    @app.get("/api/connections/openrouter/start")
    def connect_openrouter(http_request: Request) -> RedirectResponse:
        user = current_user(http_request)
        state, challenge = accounts.begin_provider_link(user.id)
        base = (auth.google_callback_url or auth.callback_url).split("/api/", 1)[0]
        callback = f"{base}/api/connections/openrouter/callback?state={state}"
        response = RedirectResponse(authorization_url(callback, state, challenge), status_code=303)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/connections/openrouter/callback")
    async def connected_openrouter(code: str, state: str, http_request: Request) -> RedirectResponse:
        user = current_user(http_request)
        verifier = accounts.consume_provider_link(state, user.id)
        if not verifier:
            raise HTTPException(status_code=400, detail="連接已過期，請重新連接 OpenRouter")
        try:
            _provider_id, key = await oauth.exchange(code, verifier)
            accounts.save_provider_key(user.id, key)
        except (httpx.HTTPError, ValueError, RuntimeError):
            raise HTTPException(status_code=400, detail="OpenRouter 連接失敗，請重新授權")
        return RedirectResponse("/?openrouter=connected#chat", status_code=303, headers={"Cache-Control": "no-store"})

    @app.get("/api/connections/openrouter")
    async def openrouter_connection(http_request: Request, response: Response) -> dict:
        response.headers["Cache-Control"] = "private, no-store"
        user = accounts.user_for_session(http_request.cookies.get(SESSION_COOKIE))
        if not user:
            return {"connected": False, "usage": None}
        key = accounts.openrouter_key_for(user.id)
        if not key:
            return {"connected": False, "usage": None}
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                result = await client.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"})
                result.raise_for_status()
                data = result.json()["data"]
            return {"connected": True, "usage": data.get("usage"), "usage_daily": data.get("usage_daily"), "currency": "USD"}
        except (httpx.HTTPError, ValueError, KeyError):
            return {"connected": True, "usage": None, "error": "暫時無法取得用量，請稍後更新"}

    @app.get("/api/connections/bazaarlink/start")
    def connect_bazaarlink(http_request: Request) -> RedirectResponse:
        user = current_user(http_request)
        state, challenge = accounts.begin_provider_link(f"bazaarlink:{user.id}")
        base = (auth.google_callback_url or auth.callback_url).split("/api/", 1)[0]
        callback = f"{base}/api/connections/bazaarlink/callback"
        url = authorization_url(callback, state, challenge).replace("https://openrouter.ai/auth?", "https://bazaarlink.ai/auth?")
        return RedirectResponse(url, status_code=303, headers={"Cache-Control": "no-store"})

    @app.get("/api/connections/bazaarlink/callback")
    async def connected_bazaarlink(code: str, state: str, http_request: Request) -> RedirectResponse:
        user = current_user(http_request)
        verifier = accounts.consume_provider_link(state, f"bazaarlink:{user.id}")
        if not verifier:
            raise HTTPException(status_code=400, detail="授權已過期，請重新連接 BazaarLink")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                result = await client.post("https://bazaarlink.ai/api/v1/auth/keys", json={"code": code, "code_verifier": verifier, "code_challenge_method": "S256"})
                result.raise_for_status()
                key = result.json().get("key")
                if not isinstance(key, str) or not key:
                    raise ValueError()
            accounts.save_provider_key(user.id, key, "bazaarlink")
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=400, detail="BazaarLink 授權失敗，請重新連接")
        return RedirectResponse("/?openrouter=connected#connections", status_code=303, headers={"Cache-Control": "no-store"})

    @app.get("/api/connections/priority")
    def provider_priority(http_request: Request, response: Response) -> dict:
        user = current_user(http_request)
        response.headers["Cache-Control"] = "private, no-store"
        return {"priority": accounts.provider_priority(user.id), "connected": [p for p, _ in credentials_for(user.id)]}

    @app.delete("/api/connections/{provider}", status_code=204, response_model=None)
    def disconnect_provider(provider: Literal["openrouter", "bazaarlink"], http_request: Request, response: Response) -> None:
        accounts.disconnect_provider(current_user(http_request).id, provider)
        response.headers["Cache-Control"] = "no-store"

    @app.get("/api/connections/bazaarlink/usage")
    def bazaarlink_usage(http_request: Request, response: Response) -> dict:
        user = current_user(http_request)
        response.headers["Cache-Control"] = "private, no-store"
        return accounts.provider_usage(user.id, "bazaarlink")

    @app.put("/api/connections/priority")
    def save_priority(http_request: Request, priority: list[str] = Body(...)) -> dict:
        user = current_user(http_request)
        try:
            accounts.save_provider_priority(user.id, priority)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {"priority": priority}

    @app.post("/api/auth/logout", status_code=204, response_model=None)
    def logout(request: Request, response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"
        accounts.revoke_session(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE, path="/")

    @app.put("/api/settings/openrouter-key", status_code=204, response_model=None)
    def update_openrouter_key(request: OpenRouterKeyUpdate, http_request: Request) -> None:
        if auth.required:
            current_user(http_request)
            raise HTTPException(status_code=410, detail="公開模式的模型連線設定尚未開放")
        try:
            save_openrouter_key(environment_file, request.openrouter_api_key.get_secret_value())
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    def private_catalog(request: Request) -> LocalCatalog:
        user = current_user(request)
        if not auth.required:
            return local_catalog
        path = _user_directory(user.id) / "catalog.json"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_text(CatalogSnapshot(characters=[], flows=[]).model_dump_json())
            path.chmod(0o600)
        return LocalCatalog(path)

    def visible_catalog(request: Request) -> CatalogSnapshot:
        snapshot = local_catalog.snapshot()
        user = session_user(request)
        if auth.required and user:
            snapshot.characters += private_catalog(request).snapshot().characters
        return snapshot

    def visible_character(request: Request, character_id: str) -> CharacterSpec:
        character = next((item for item in visible_catalog(request).characters if item.id == character_id), None)
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found")
        return character

    @app.get("/api/bootstrap", response_model=CatalogSnapshot)
    def bootstrap(http_request: Request, response: Response) -> CatalogSnapshot:
        response.headers["Cache-Control"] = "private, no-store"
        return visible_catalog(http_request)

    @app.get("/api/characters", response_model=list[CharacterSpec])
    def list_characters(http_request: Request, response: Response) -> list[CharacterSpec]:
        response.headers["Cache-Control"] = "private, no-store"
        return visible_catalog(http_request).characters

    @app.get("/api/characters/{character_id}", response_model=CharacterSpec)
    def get_character(character_id: str, http_request: Request, response: Response) -> CharacterSpec:
        response.headers["Cache-Control"] = "private, no-store"
        return visible_character(http_request, character_id)

    @app.put("/api/characters/{character_id}", response_model=CharacterSpec)
    def save_character(character_id: str, character: CharacterSpec, http_request: Request) -> CharacterSpec:
        if character_id != character.id:
            raise HTTPException(status_code=400, detail="Character id must match the URL")
        target = private_catalog(http_request)
        if character.source.get("generated_file") == "DIJI character creator":
            profile = {**character.profile, "character_name": character.name}
            character = character.model_copy(update={"profile": profile, "full_prompt": CharacterGenerationService._full_prompt(GeneratedCharacter.model_validate(profile), character.style_guide)})
        if auth.required:
            if any(item.id == character_id for item in local_catalog.snapshot().characters):
                raise HTTPException(status_code=409, detail="請使用新的角色識別碼建立個人角色")
            character = character.model_copy(update={"source": {**character.source, "visibility": "private"}})
        activity = activity_for(current_user(http_request))
        if character.source.get('generation_id'):
            try:
                run = activity.get(character.source['generation_id'])
                if run['kind'] != 'generation':
                    raise LookupError('生成紀錄不存在')
                if run['status'] != 'completed' or run['data'].get('saved_character_id') not in (None, character_id):
                    raise HTTPException(status_code=409, detail='生成尚未完成或已保存為其他角色')
            except LookupError as error:
                raise HTTPException(status_code=404, detail="生成紀錄不存在") from error
        save_id = activity.begin('character_save', {'character':character.model_dump()})
        try:
            saved = target.save_character(character)
            activity.character_saved(saved, save_id)
        except BaseException as error:
            activity.finish(save_id, 'failed', {'error_type':type(error).__name__})
            raise
        return saved

    @app.get("/api/character-imports/preview", response_model=CharacterImportPreview)
    def preview_character_imports() -> CharacterImportPreview:
        return importer.preview()

    @app.post("/api/character-imports", response_model=CharacterImportResult)
    def import_characters(request: CharacterImportRequest, http_request: Request) -> CharacterImportResult:
        target = private_catalog(http_request)
        result = importer.import_selected(target, request.ids)
        if auth.required:
            for character in target.snapshot().characters:
                target.save_character(character.model_copy(update={"source": {**character.source, "visibility": "private"}}))
        return result

    @app.get("/api/flows", response_model=list[FlowSpec])
    def list_flows() -> list[FlowSpec]:
        return local_catalog.snapshot().flows

    @app.put("/api/flows/{flow_id}", response_model=FlowSpec)
    def save_flow(flow_id: str, flow: FlowSpec) -> FlowSpec:
        if flow_id != flow.id:
            raise HTTPException(status_code=400, detail="Flow id must match the URL")
        return local_catalog.save_flow(flow)

    @app.post("/api/prompt-preview", response_model=PromptBundle)
    def prompt_preview(request: PromptPreviewRequest, http_request: Request) -> PromptBundle:
        user_memories, _conversations, _relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        try:
            character = visible_character(http_request, request.character_id)
            flow = local_catalog.flow(request.flow_id)
        except StopIteration as error:
            raise HTTPException(status_code=404, detail="Character or flow not found") from error
        return assemble_prompt(character, flow, request, user_memories.recent(request.chat_id))

    @app.get("/api/memories/{chat_id}", response_model=list[MemoryRecord])
    def list_memories(chat_id: str, http_request: Request, limit: int = Query(default=10, ge=1, le=500)) -> list[MemoryRecord]:
        user_memories, _conversations, _relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        try:
            return user_memories.recent(chat_id, limit=limit)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/memories/{chat_id}/entries")
    def memory_entries(chat_id: str, http_request: Request) -> list[dict]:
        memories, chats, *_ = stores_for(current_user(http_request))
        try:
            chats.get(chat_id)
            return memories.entries(chat_id)
        except (StopIteration, LookupError) as error:
            raise HTTPException(status_code=404, detail="對話不存在") from error

    @app.patch("/api/memories/{chat_id}/entries/{record_id}")
    def update_memory_entry(chat_id: str, record_id: str, changes: MemoryUpdate, http_request: Request) -> dict:
        memories, chats, *_ = stores_for(current_user(http_request))
        try:
            chats.get(chat_id)
            return memories.update_entry(chat_id, record_id, changes.model_dump())
        except (StopIteration, LookupError) as error:
            raise HTTPException(status_code=404, detail="記憶已變更或不存在，請重新載入後再操作。") from error

    @app.delete("/api/memories/{chat_id}/entries/{record_id}", status_code=204, response_model=None)
    def delete_memory_entry(chat_id: str, record_id: str, http_request: Request) -> None:
        memories, chats, *_ = stores_for(current_user(http_request))
        try:
            chats.get(chat_id)
            memories.delete_entry(chat_id, record_id)
        except (StopIteration, LookupError) as error:
            raise HTTPException(status_code=404, detail="記憶已變更或不存在，請重新載入後再操作。") from error

    @app.get("/api/conversations", response_model=list[ConversationSummary])
    def list_conversations(http_request: Request) -> list[ConversationSummary]:
        _memories, user_conversations, _relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        return user_conversations.list()

    @app.post("/api/conversations", response_model=ConversationRecord)
    def start_conversation(request: ConversationStart, http_request: Request) -> ConversationRecord:
        if auth.required:
            visible_character(http_request, request.character_id)
        _memories, user_conversations, _relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        try:
            return user_conversations.start(request.chat_id, request.character_id, request.character_name, request.chat_mode)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/conversations/{chat_id}", response_model=ConversationRecord)
    def get_conversation(chat_id: str, http_request: Request) -> ConversationRecord:
        _memories, user_conversations, _relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        try:
            return user_conversations.get(chat_id)
        except StopIteration as error:
            raise HTTPException(status_code=404, detail="Conversation not found") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    def edited_branch(user, chat_id, index, expected_revision, text, *, trial=False):
        _memories,chats,*_ = stores_for(user,trial=trial)
        try:
            source=chats.get(chat_id)
        except StopIteration as error:
            raise HTTPException(status_code=404,detail='對話不存在') from error
        if index>=len(source.messages) or source.messages[index].sender_type!=1:
            raise HTTPException(status_code=400,detail='只能編輯玩家已送出的訊息')
        activity=activity_for(user)
        prefix_hash=chats.prefix_fingerprint(source.messages[:index])
        snapshot=activity.checkpoint_for(chat_id,index,prefix_hash)
        new_id=('trial-' if trial else 'chat-')+str(uuid.uuid4())
        try:
            branch=chats.fork_edit(chat_id,index,expected_revision,new_id,checkpoint_available=snapshot is not None)
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error
        memories,_,relationships,profiles,*_=stores_for(user,trial=trial,profile_chat_id=new_id)
        snapshot=snapshot or {'memories':[],'relationship':RelationshipState().model_dump(),'profile':{}}
        memories.restore_snapshot(new_id,snapshot['memories'])
        relationships.restore_snapshot(new_id,snapshot['relationship'])
        profiles.restore_snapshot(user.id,snapshot['profile'])
        audit_id=activity.begin('conversation_edit',{'parent_chat_id':chat_id,'chat_id':new_id,'message_index':index,
            'original_text':source.messages[index].text,'edited_text':text,'state_checkpoint_available':branch.state_checkpoint_available,'trial':trial})
        activity.finish(audit_id,'completed',{})
        return branch

    @app.post('/api/conversations/{chat_id}/edit')
    async def edit_message(chat_id: str, request: ConversationEditRequest, http_request: Request):
        user=current_user(http_request)
        _,chats,*_=stores_for(user)
        try:source=chats.get(chat_id)
        except StopIteration as error:raise HTTPException(status_code=404,detail='對話不存在') from error
        if request.interaction.chat_id!=chat_id or request.interaction.character.id!=source.character_id:
            raise HTTPException(status_code=400,detail='對話與角色不符')
        if auth.required:
            visible_character(http_request,source.character_id)
            if not credentials_for(user.id):raise HTTPException(status_code=409,detail='此帳號尚未設定模型連線')
        if request.interaction.is_nsfw and not any(p.review_status=='approved' and p.prompt and request.interaction.llm.model.removesuffix(':online') in p.openrouter_models for p in jailbreaks_for(user).list()):
            raise HTTPException(status_code=400,detail='此模型沒有已核准的越獄')
        branch=edited_branch(user,chat_id,request.message_index,request.expected_revision,request.interaction.message.text)
        if branch.chat_mode!=request.interaction.user.persona.chat_mode:
            chats.set_mode(branch.chat_id,request.interaction.user.persona.chat_mode)
        payload=request.interaction.model_dump()
        payload.update(chat_id=branch.chat_id,reset=False,history=[m.model_dump() for m in branch.messages[-500:]])
        interaction=InteractionRequest.model_validate(payload)
        try:
            response=await execute_interaction(interaction,http_request)
            return {'conversation':chats.get(branch.chat_id).model_dump(),'response':response.model_dump()}
        except Exception:
            return JSONResponse({'detail':'重新生成未完成；修改與新分支已保留，可再次編輯或繼續對話','conversation':chats.get(branch.chat_id).model_dump()},status_code=502)

    @app.put("/api/conversations/{chat_id}/mode", response_model=ConversationRecord)
    def update_conversation_mode(chat_id: str, request: ConversationModeUpdate, http_request: Request) -> ConversationRecord:
        _memories, user_conversations, _relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        try:
            return user_conversations.set_mode(chat_id, request.chat_mode)
        except StopIteration as error:
            raise HTTPException(status_code=404, detail="Conversation not found") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.put("/api/memories/{chat_id}", response_model=MemoryRecord)
    def add_memory(chat_id: str, memory: MemoryRecord, http_request: Request) -> MemoryRecord:
        user_memories, _conversations, _relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        try:
            return user_memories.add(chat_id, memory)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/memories/{chat_id}/extract", response_model=list[MemoryRecord])
    async def extract_memory(chat_id: str, http_request: Request, conversation: str = Body(embed=True)) -> list[MemoryRecord]:
        """Use the same extraction prompt and model settings as ai-server when explicitly requested."""
        if not conversation.strip():
            raise HTTPException(status_code=400, detail="Conversation must not be empty")
        user = current_user(http_request)
        user_memories, _conversations, _relationships, _profiles, _interactions, _generator = stores_for(user)
        api_key = credentials_for(user.id) if auth.required else None
        if auth.required and not api_key:
            raise HTTPException(status_code=409, detail="此帳號尚未設定模型連線")
        records = await (extractor if not auth.required else MemoryExtractor(OpenRouterExtractionClient(api_key))).extract(conversation)
        try:
            for record in records:
                user_memories.add(chat_id, record)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return records

    @app.post("/api/memories/{chat_id}/backfill")
    async def backfill_memory(chat_id: str, http_request: Request) -> dict[str, int | bool]:
        """Create event memories for one saved transcript without partial writes."""
        user = current_user(http_request)
        user_memories, user_conversations, _relationships, _profiles, user_interactions, _generator = stores_for(user)
        try:
            if user_memories.recent(chat_id):
                return {"created": 0, "skipped": True}
            record = user_conversations.get(chat_id)
        except (ValueError, StopIteration) as error:
            raise HTTPException(status_code=404, detail="找不到這段對話") from error
        if not record.messages:
            return {"created": 0, "skipped": True}
        if auth.required and not credentials_for(user.id):
            raise HTTPException(status_code=409, detail="此帳號尚未設定模型連線")
        generated: list[MemoryRecord] = []
        recent_messages = record.messages[-80:]
        for offset in range(0, len(recent_messages), 8):
            batch = recent_messages[offset:offset + 8]
            conversation = "\n".join(
                f"{'使用者' if item.sender_type == 1 else record.character_name}：{item.text}"
                for item in batch
            )
            records = await user_interactions.extractor.extract(conversation)
            generated.extend(records)
        for memory in generated:
            user_memories.add(chat_id, memory)
        return {"created": len(generated), "skipped": False}

    @app.get("/api/experiments", response_model=list[PromptExperiment])
    def list_experiments(http_request: Request, response: Response) -> list[PromptExperiment]:
        response.headers['Cache-Control']='private, no-store'
        return experiments_for(current_user(http_request)).list()

    @app.put("/api/experiments/{experiment_id}", response_model=PromptExperiment)
    def save_experiment(experiment_id: str, experiment: PromptExperiment, http_request: Request) -> PromptExperiment:
        if experiment_id != experiment.id:
            raise HTTPException(status_code=400, detail="Experiment id must match the URL")
        return experiments_for(current_user(http_request)).save(experiment)

    @app.get("/api/jailbreaks", response_model=list[JailbreakPreset])
    def list_jailbreaks(http_request: Request, response: Response) -> list[JailbreakPreset]:
        response.headers['Cache-Control']='private, no-store'
        return jailbreaks_for(current_user(http_request)).list()

    @app.post("/api/jailbreaks/import-recent", response_model=list[JailbreakPreset])
    def import_recent_jailbreak_metadata(http_request: Request) -> list[JailbreakPreset]:
        return jailbreaks_for(current_user(http_request)).import_recent_catalog()

    @app.put("/api/jailbreaks/{preset_id}", response_model=JailbreakPreset)
    def save_jailbreak(preset_id: str, preset: JailbreakPreset, http_request: Request) -> JailbreakPreset:
        if preset_id != preset.id:
            raise HTTPException(status_code=400, detail="Jailbreak id must match the URL")
        return jailbreaks_for(current_user(http_request)).save(preset)

    @app.delete("/api/jailbreaks/{preset_id}", response_model=JailbreakPreset)
    def delete_jailbreak(preset_id: str, http_request: Request) -> JailbreakPreset:
        try:
            return jailbreaks_for(current_user(http_request)).delete(preset_id)
        except StopIteration as error:
            raise HTTPException(status_code=404, detail="Jailbreak not found") from error
        except ValueError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @app.post("/api/characters/generate", response_model=CharacterGenerationResult)
    async def generate_character(request: CharacterGenerationRequest, http_request: Request) -> CharacterGenerationResult:
        user = current_user(http_request)
        if auth.required and not credentials_for(user.id):
            raise HTTPException(status_code=409, detail="此帳號尚未設定模型連線")
        _memories, _conversations, _relationships, _profiles, _interactions, user_generator = stores_for(user)
        model_id = request.model.removesuffix(":online")
        preset = next((item for item in jailbreaks_for(user).list() if item.review_status == "approved" and model_id in item.openrouter_models), None)
        if not preset or not preset.prompt:
            raise HTTPException(status_code=400, detail="此模型沒有已核准的越獄，不能用於角色生成")
        activity = activity_for(user)
        run_id = activity.begin('generation',{'request':request.model_dump(exclude={'jailbreak_prompt'}),'jailbreak':{'id':preset.id,'name':preset.name,'last_updated':preset.last_updated}})
        traced = CharacterGenerationService(RecordedGenerationClient(user_generator.client,activity,run_id))
        try:
            result = await traced.generate(request.model_copy(update={"jailbreak_prompt":preset.prompt}))
            result = result.model_copy(update={'generation_id':run_id})
            activity.finish(run_id,'completed',{'draft':result.model_dump()})
            return result
        except BaseException as error:
            activity.finish(run_id,'failed',{'error_type':type(error).__name__})
            raise

    @app.get('/api/character-generations')
    def generation_history(http_request: Request, response: Response):
        response.headers['Cache-Control']='private, no-store'
        return activity_for(current_user(http_request)).list_generations()

    @app.get('/api/character-generations/{run_id}')
    def generation_record(run_id: str, http_request: Request, response: Response):
        response.headers['Cache-Control']='private, no-store'
        try:
            return activity_for(current_user(http_request)).get(run_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail='生成紀錄不存在') from error

    @app.patch('/api/character-generations/{run_id}/draft', response_model=CharacterGenerationResult)
    def save_generation_draft(run_id: str, draft: CharacterGenerationResult, http_request: Request):
        if draft.generation_id != run_id:
            raise HTTPException(status_code=400, detail='草稿識別碼不符')
        try:
            draft = draft.model_copy(update={'full_prompt':CharacterGenerationService._full_prompt(draft.character,draft.style_guide)})
            return activity_for(current_user(http_request)).save_draft(run_id,draft.revision,draft.model_dump())
        except LookupError as error:
            raise HTTPException(status_code=404, detail='草稿不存在') from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get('/api/character-generations/{run_id}/versions')
    def draft_versions(run_id: str, http_request: Request, response: Response, before: int | None = Query(default=None,ge=0)):
        response.headers['Cache-Control']='private, no-store'
        try:
            return activity_for(current_user(http_request)).versions(run_id,before)
        except LookupError as error:
            raise HTTPException(status_code=404,detail='草稿不存在') from error

    @app.get('/api/character-generations/{run_id}/versions/{revision}')
    def draft_version(run_id: str, revision: int, http_request: Request, response: Response):
        response.headers['Cache-Control']='private, no-store'
        try:
            return activity_for(current_user(http_request)).version(run_id,revision)
        except LookupError as error:
            raise HTTPException(status_code=404,detail='版本不存在') from error

    @app.post('/api/character-generations/{run_id}/rollback', response_model=CharacterGenerationResult)
    def rollback_draft(run_id: str, request: DraftRollbackRequest, http_request: Request):
        try:
            return activity_for(current_user(http_request)).restore_version(run_id,request.target_revision,request.revision)
        except LookupError as error:
            raise HTTPException(status_code=404,detail='草稿或版本不存在') from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @app.post('/api/character-generations/{run_id}/revise')
    async def revise_draft(run_id: str, request: DraftRevisionRequest, http_request: Request):
        user = current_user(http_request)
        activity = activity_for(user)
        try:
            run = activity.get(run_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail='草稿不存在') from error
        if run['kind'] != 'generation' or run['status'] != 'completed' or run['data'].get('saved_character_id') or run['revision'] != request.revision:
            raise HTTPException(status_code=409, detail='草稿已變更或已儲存為角色，請重新讀取')
        if auth.required and not credentials_for(user.id):
            raise HTTPException(status_code=409, detail='此帳號尚未設定模型連線')
        preset = next((p for p in jailbreaks_for(user).list() if p.review_status == 'approved' and p.prompt and request.model.removesuffix(':online') in p.openrouter_models),None)
        if preset is None:
            raise HTTPException(status_code=400, detail='請選擇有已核准越獄的模型')
        try:
            base = activity.version(run_id,request.base_revision)['draft'] if request.base_revision is not None else run['data']['draft']
        except LookupError as error:
            raise HTTPException(status_code=404,detail='修改前的草稿版本不存在') from error
        before = CharacterGenerationResult.model_validate(base)
        prompt = revision_prompt(before,request.instruction,preset.prompt,request.is_nsfw)
        revision_id = activity.begin('draft_revision',{'generation_id':run_id,'base_revision':request.base_revision if request.base_revision is not None else request.revision,'expected_revision':request.revision,'model':request.model,'instruction':request.instruction,'before':before.model_dump(),'jailbreak_id':preset.id,'jailbreak_updated':preset.last_updated})
        activity.event(revision_id,'revise','started',{'prompt':prompt})
        try:
            *_, user_generator = stores_for(user)
            raw = await user_generator.client.complete(model=request.model,temperature=0.5,prompt=prompt,json_mode=True)
            activity.event(revision_id,'revise','completed',{'output':raw})
            proposed, summary, paths = apply_proposal(before,raw)
            activity.finish(revision_id,'running',{'proposed':proposed.model_dump(),'summary':summary,'changed_fields':paths})
            try:
                saved = activity.save_draft(run_id,request.revision,proposed.model_dump(),source='ai',note=summary)
            except ValueError as error:
                raise HTTPException(status_code=409, detail='修改期間草稿已變更，這次結果未覆蓋新版本，請重新讀取') from error
            activity.finish(revision_id,'completed',{'result_revision':saved['revision']})
            return {'draft':saved,'summary':summary,'changed_fields':paths}
        except HTTPException:
            activity.finish(revision_id,'failed',{'error_type':'RevisionConflict'})
            raise
        except BaseException as error:
            activity.finish(revision_id,'failed',{'error_type':type(error).__name__})
            if isinstance(error,Exception):
                raise HTTPException(status_code=502,detail='AI 修改未完成，原草稿仍保留，請稍後重試') from error
            raise

    @app.post("/api/interactions", response_model=InteractionResponse)
    async def interact(request: InteractionRequest, http_request: Request) -> InteractionResponse:
        return await execute_interaction(request, http_request)

    @app.post('/api/character-generations/{run_id}/test-interactions', response_model=InteractionResponse)
    async def test_draft(run_id: str, trial: DraftTrialRequest, http_request: Request):
        return await run_draft_trial(run_id,trial,http_request)

    @app.get('/api/character-generations/{run_id}/test-conversations/{chat_id}', response_model=ConversationRecord)
    def trial_conversation(run_id: str, chat_id: str, http_request: Request):
        user=current_user(http_request)
        _,chats,*_=stores_for(user,trial=True)
        try:
            record=chats.get(chat_id)
            if record.character_id!=run_id:raise StopIteration()
            return record
        except StopIteration as error:raise HTTPException(status_code=404,detail='測試對話不存在') from error

    @app.post('/api/character-generations/{run_id}/test-interactions/edit')
    async def edit_trial(run_id: str, trial: TrialEditRequest, http_request: Request):
        return await run_draft_trial(run_id,trial,http_request,edit=trial)

    async def run_draft_trial(run_id: str, trial: DraftTrialRequest, http_request: Request, edit: TrialEditRequest | None = None):
        user = current_user(http_request)
        try:
            run = activity_for(user).get(run_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail='草稿不存在') from error
        if run['kind'] != 'generation' or run['status'] != 'completed' or run['data'].get('saved_character_id'):
            raise HTTPException(status_code=409, detail='請使用尚未加入角色庫的完整草稿試聊')
        if run['revision'] != trial.revision:
            raise HTTPException(status_code=409, detail='草稿版本已變更，請返回審核並重新開啟測試對話')
        if not any(p.review_status == 'approved' and p.prompt and trial.model.removesuffix(':online') in p.openrouter_models for p in jailbreaks_for(user).list()):
            raise HTTPException(status_code=400, detail='請選擇有已核准越獄的模型')
        draft = CharacterGenerationResult.model_validate(run['data']['draft'])
        branch=None
        if edit is not None:
            if auth.required and not credentials_for(user.id):raise HTTPException(status_code=409,detail='此帳號尚未設定模型連線')
            _,source_chats,*_=stores_for(user,trial=True)
            try:source=source_chats.get(trial.chat_id)
            except StopIteration as error:raise HTTPException(status_code=404,detail='測試對話不存在') from error
            if source.character_id!=run_id:raise HTTPException(status_code=404,detail='測試對話不存在')
            branch=edited_branch(user,trial.chat_id,edit.message_index,edit.expected_revision,trial.text,trial=True)
            trial=trial.model_copy(update={'chat_id':branch.chat_id})
        profile = draft.character.model_dump()
        samples = profile.get('language_style')
        request = InteractionRequest.model_validate({
            'chat_id':trial.chat_id, 'llm':{'model':trial.model},
            'character':{'id':run_id, 'name':draft.character.character_name,
                'brief_description':draft.description_for_app or draft.brief_description,
                'description':CharacterGenerationService._full_prompt(draft.character,draft.style_guide),
                'sample_dialog':[{'sender_type':2,'text':str(line)[:800]} for line in samples[:10]] if isinstance(samples,list) else [],
                **{key:profile.get(key) for key in ('psychological_evolution','behavioral_boundaries','evolution_requirements')}},
            'user':{'id':'local-user', 'persona':{'name':'使用者','chat_mode':trial.chat_mode}},
            'message':{'sender_id':user.id,'text':trial.text},
            'style_prompt':draft.style_guide, 'is_nsfw':trial.is_nsfw, 'enable_favorability':False,
        })
        _, chats, *_ = stores_for(user, trial=True)
        try:
            previous = chats.get(trial.chat_id)
            if previous.character_id != run_id:
                raise HTTPException(status_code=409, detail='測試對話不屬於這份草稿')
            if previous.chat_mode != trial.chat_mode:
                chats.set_mode(trial.chat_id,trial.chat_mode)
            payload = request.model_dump()
            payload['history'] = [{'sender_type':m.sender_type,'text':m.text,'timestamp':m.timestamp} for m in previous.messages[-500:]]
            request = InteractionRequest.model_validate(payload)
        except StopIteration:
            pass
        try:
            response=await execute_interaction(request, http_request, trial_data={'generation_id':run_id,'revision':trial.revision,'character':profile})
            return {'conversation':chats.get(branch.chat_id).model_dump(),'response':response.model_dump()} if branch else response
        except Exception:
            if branch:return JSONResponse({'detail':'重新生成未完成，修改與新分支已保留','conversation':chats.get(branch.chat_id).model_dump()},status_code=502)
            raise

    async def execute_interaction(request: InteractionRequest, http_request: Request, trial_data: dict | None = None) -> InteractionResponse:
        user=current_user(http_request)
        _,chats,*_=stores_for(user,trial=trial_data is not None)
        try:
            with chats.turn(request.chat_id):
                return await execute_turn(request,http_request,trial_data)
        except ConversationBusy as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    async def execute_turn(request: InteractionRequest, http_request: Request, trial_data: dict | None = None) -> InteractionResponse:
        user = current_user(http_request)
        if auth.required and trial_data is None:
            visible_character(http_request, request.character.id)
        if auth.required and not credentials_for(user.id):
            raise HTTPException(status_code=409, detail="此帳號尚未設定模型連線")
        user_memories, user_conversations, user_relationships, _profiles, user_interactions, _generator = stores_for(user, trial=trial_data is not None)
        try:existing=user_conversations.get(request.chat_id)
        except StopIteration:existing=None
        if existing is not None and existing.parent_chat_id:
            user_memories,user_conversations,user_relationships,_profiles,user_interactions,_generator=stores_for(user,trial=trial_data is not None,profile_chat_id=request.chat_id)
        request = request.model_copy(update={"user": request.user.model_copy(update={"id": user.id}), "message": request.message.model_copy(update={"sender_id": user.id})})
        if request.reset:
            try:
                user_memories.delete(request.chat_id)
                user_relationships.delete(request.chat_id)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return InteractionResponse(
                chat_id=request.chat_id,
                character_id=request.character.id,
                text="上下文已重置。",
                messages=[],
                memory_saved=False,
                relationship_updated=False,
            )
        if request.is_nsfw:
            model_id = request.llm.model.removesuffix(":online")
            preset = next(
                (
                    item
                    for item in jailbreaks_for(user).list()
                    if item.review_status == "approved" and item.prompt and model_id in item.openrouter_models
                ),
                None,
            )
            if not preset:
                raise HTTPException(status_code=400, detail="此模型沒有已核准的越獄，不能用於成人虛構互動")
            experiment_id = f"interaction-{preset.id}"
            experiments_for(user).save(
                PromptExperiment(
                    id=experiment_id,
                    name=f"{preset.name} 互動越獄",
                    jailbreak_id=preset.id,
                )
            )
            request = request.model_copy(update={"experiment_id": experiment_id})
        try:
            activity = activity_for(user)
            def prepare_turn():
                before=user_conversations.start(request.chat_id,request.character.id,request.character.name,request.user.persona.chat_mode)
                activity.checkpoint(request.chat_id,len(before.messages),user_conversations.prefix_fingerprint(before.messages),
                    {'memories':user_memories.snapshot(request.chat_id),'relationship':user_relationships.get(request.chat_id).model_dump(),'profile':_profiles.get(user.id)})
                turn_id=activity.begin('conversation_turn',{'chat_id':request.chat_id,'character_id':request.character.id,'model':request.llm.model_dump(exclude={'url'}),'message':request.message.text,'history_count':len(request.history),'chat_mode':request.user.persona.chat_mode,'is_nsfw':request.is_nsfw,'enable_favorability':request.enable_favorability})
                if trial_data is not None:
                    activity.finish(turn_id,'running',{'purpose':'draft_trial',**trial_data})
                user_conversations.append(request.chat_id,request.character.id,request.character.name,ConversationMessage(sender_type=1,text=request.message.text))
                return turn_id
            turn_id=await run_in_threadpool(prepare_turn)
            response = InteractionResponse.model_validate(await user_interactions.respond(request))
            await run_in_threadpool(user_conversations.append,
                request.chat_id,
                request.character.id,
                request.character.name,
                ConversationMessage(sender_type=2, text=response.text),
            )
            await run_in_threadpool(activity.finish,turn_id,'completed',{'reply':response.text,'memory_saved':response.memory_saved,'relationship_updated':response.relationship_updated})
            return response
        except ValueError as error:
            if 'turn_id' in locals(): activity.finish(turn_id,'failed',{'error_type':type(error).__name__})
            raise HTTPException(status_code=400, detail=str(error)) from error
        except BaseException as error:
            if 'turn_id' in locals(): activity.finish(turn_id,'failed',{'error_type':type(error).__name__})
            raise

    @app.get("/api/relationships/{chat_id}", response_model=RelationshipState)
    def relationship(chat_id: str, http_request: Request) -> RelationshipState:
        _memories, _conversations, user_relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        try:
            return user_relationships.get(chat_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    app.mount("/", StaticFiles(directory=UI_DIRECTORY, html=True), name="ui")
    return app

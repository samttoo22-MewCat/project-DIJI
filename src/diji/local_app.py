"""Local HTTP composition root. Model calls happen only through explicit POST routes."""

from __future__ import annotations

from pathlib import Path
import os
from typing import Literal

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr

from .local_catalog import CatalogSnapshot, CharacterSpec, FlowSpec, LocalCatalog
from .character_generation.service import GeneratedCharacter
from .conversation_store import ConversationMessage, ConversationRecord, ConversationStore, ConversationSummary
from .character_import import CharacterImporter, CharacterImportPreview, CharacterImportRequest, CharacterImportResult
from .memory_store import LocalMemoryStore, MemoryRecord
from .memory_extraction import MemoryExtractor, OpenRouterExtractionClient
from .prompt_assembly import PromptBundle, PromptPreviewRequest, assemble_prompt
from .domain import InteractionRequest, InteractionResponse
from .experiments import ExperimentStore, JailbreakPreset, JailbreakStore, PromptExperiment
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

    @app.middleware("http")
    async def protect_workspace(request: Request, call_next):
        public_auth = {
            "/api/auth/session", "/api/auth/google/start", "/api/auth/google/callback",
            "/api/auth/logout", "/api/auth/openrouter/start", "/api/auth/openrouter/callback",
        }
        path = request.url.path
        if auth.required and (path.startswith("/api/") or path == "/openapi.json") and path not in public_auth:
            if not accounts.user_for_session(request.cookies.get(SESSION_COOKIE)):
                return JSONResponse({"detail": "請先使用 Google 登入 DIJI"}, status_code=401, headers={"Cache-Control": "no-store"})
        return await call_next(request)

    def current_user(request: Request) -> AuthenticatedUser:
        user = accounts.user_for_session(request.cookies.get(SESSION_COOKIE))
        if auth.required and not user:
            raise HTTPException(status_code=401, detail="請先登入 DIJI")
        return user or AuthenticatedUser(id="local-user", login_provider="local", display_name="本機使用者", openrouter_user_id="local-user")

    def stores_for(user: AuthenticatedUser) -> tuple[LocalMemoryStore, ConversationStore, RelationshipStore, UserProfileStore, InteractionService, CharacterGenerationService]:
        if not auth.required:
            return local_memories, conversations, relationships, profiles, interactions, generator
        root = _user_directory(user.id)
        root.mkdir(parents=True, exist_ok=True)
        root.chmod(0o700)
        user_memories = LocalMemoryStore(root / "memories")
        user_relationships = RelationshipStore(root / "relationships")
        user_profiles = UserProfileStore(root / "user_profiles")
        api_key = accounts.provider_credentials(user.id)
        user_interactions = InteractionService(
            AiServerCompatibleAdapter(api_key),
            user_memories,
            MemoryExtractor(OpenRouterExtractionClient(api_key)),
            user_relationships,
            experiments,
            OpenRouterFavorabilityJudge(api_key),
            jailbreaks,
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
        user = accounts.user_for_session(request.cookies.get(SESSION_COOKIE))
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
        return {"priority": accounts.provider_priority(user.id), "connected": [p for p, _ in accounts.provider_credentials(user.id)]}

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
        user = accounts.user_for_session(request.cookies.get(SESSION_COOKIE))
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
        return target.save_character(character)

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
        api_key = accounts.provider_credentials(user.id) if auth.required else None
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
        if auth.required and not accounts.provider_credentials(user.id):
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
    def list_experiments() -> list[PromptExperiment]:
        return experiments.list()

    @app.put("/api/experiments/{experiment_id}", response_model=PromptExperiment)
    def save_experiment(experiment_id: str, experiment: PromptExperiment) -> PromptExperiment:
        if experiment_id != experiment.id:
            raise HTTPException(status_code=400, detail="Experiment id must match the URL")
        return experiments.save(experiment)

    @app.get("/api/jailbreaks", response_model=list[JailbreakPreset])
    def list_jailbreaks() -> list[JailbreakPreset]:
        return jailbreaks.list()

    @app.post("/api/jailbreaks/import-recent", response_model=list[JailbreakPreset])
    def import_recent_jailbreak_metadata() -> list[JailbreakPreset]:
        return jailbreaks.import_recent_catalog()

    @app.put("/api/jailbreaks/{preset_id}", response_model=JailbreakPreset)
    def save_jailbreak(preset_id: str, preset: JailbreakPreset) -> JailbreakPreset:
        if preset_id != preset.id:
            raise HTTPException(status_code=400, detail="Jailbreak id must match the URL")
        return jailbreaks.save(preset)

    @app.delete("/api/jailbreaks/{preset_id}", response_model=JailbreakPreset)
    def delete_jailbreak(preset_id: str) -> JailbreakPreset:
        try:
            return jailbreaks.delete(preset_id)
        except StopIteration as error:
            raise HTTPException(status_code=404, detail="Jailbreak not found") from error

    @app.post("/api/characters/generate", response_model=CharacterGenerationResult)
    async def generate_character(request: CharacterGenerationRequest, http_request: Request) -> CharacterGenerationResult:
        user = current_user(http_request)
        if auth.required and not accounts.provider_credentials(user.id):
            raise HTTPException(status_code=409, detail="此帳號尚未設定模型連線")
        _memories, _conversations, _relationships, _profiles, _interactions, user_generator = stores_for(user)
        model_id = request.model.removesuffix(":online")
        preset = next((item for item in jailbreaks.list() if item.review_status == "approved" and model_id in item.openrouter_models), None)
        if not preset or not preset.prompt:
            raise HTTPException(status_code=400, detail="此模型沒有已核准的越獄，不能用於角色生成")
        return await user_generator.generate(request.model_copy(update={"jailbreak_prompt": preset.prompt if preset else ""}))

    @app.post("/api/interactions", response_model=InteractionResponse)
    async def interact(request: InteractionRequest, http_request: Request) -> InteractionResponse:
        user = current_user(http_request)
        if auth.required:
            visible_character(http_request, request.character.id)
        if auth.required and not accounts.provider_credentials(user.id):
            raise HTTPException(status_code=409, detail="此帳號尚未設定模型連線")
        user_memories, user_conversations, user_relationships, _profiles, user_interactions, _generator = stores_for(user)
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
                    for item in jailbreaks.list()
                    if item.review_status == "approved" and item.prompt and model_id in item.openrouter_models
                ),
                None,
            )
            if not preset:
                raise HTTPException(status_code=400, detail="此模型沒有已核准的越獄，不能用於成人虛構互動")
            experiment_id = f"interaction-{preset.id}"
            experiments.save(
                PromptExperiment(
                    id=experiment_id,
                    name=f"{preset.name} 互動越獄",
                    jailbreak_id=preset.id,
                )
            )
            request = request.model_copy(update={"experiment_id": experiment_id})
        try:
            user_conversations.append(
                request.chat_id,
                request.character.id,
                request.character.name,
                ConversationMessage(sender_type=1, text=request.message.text),
            )
            response = InteractionResponse.model_validate(await user_interactions.respond(request))
            user_conversations.append(
                request.chat_id,
                request.character.id,
                request.character.name,
                ConversationMessage(sender_type=2, text=response.text),
            )
            return response
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/relationships/{chat_id}", response_model=RelationshipState)
    def relationship(chat_id: str, http_request: Request) -> RelationshipState:
        _memories, _conversations, user_relationships, _profiles, _interactions, _generator = stores_for(current_user(http_request))
        try:
            return user_relationships.get(chat_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    app.mount("/", StaticFiles(directory=UI_DIRECTORY, html=True), name="ui")
    return app

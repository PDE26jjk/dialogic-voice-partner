from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from .export import export_line as export_line_file
from .export import render_range, retry_writeback
from .generation import (
    _resolve_defaults,
    _validate_params,
    generate_batch,
    generate_take,
    save_pcm_take,
)
from .providers.registry import get_provider, provider_infos
from .storage.project import DEFAULT_CHARACTER_ID
from .schemas import (
    AssetFromTakeRequest,
    AssetInfo,
    BatchGenerateResult,
    CleanupResult,
    CredentialRequest,
    GenerateBatchRequest,
    Job,
    ReloadResult,
    SectionOrderRequest,
    SelectionAssetRequest,
    CleanupResult,
    ReloadResult,
    SectionOrderRequest,
    ActiveProject,
    AddTakeRequest,
    AssetFromTakeRequest,
    AssetInfo,
    BlockDocument,
    CharacterInfo,
    CharacterSettings,
    CreateBlockRequest,
    CreateCharacterRequest,
    CreateProjectRequest,
    CreateSectionRequest,
    EnsureSlotRequest,
    ExportLineRequest,
    ExportResult,
    GenerateRequest,
    HealthResponse,
    LineDocument,
    LineOrderRequest,
    ProjectSettings,
    ProviderInfo,
    PushLinesRequest,
    PushLinesResult,
    Section,
    SetCharacterVoiceRequest,
    Track,
    UpdateBlockRequest,
    UpdateCharacterProviderRequest,
    UpdateCharacterRequest,
    UpdateLineRequest,
    UpdateSettingsRequest,
    UpdateSectionRequest,
    UpdateSlotRequest,
    WorkspaceState,
)
from .storage import (
    activate_section,
    active_project,
    build_index,
    cleanup_orphans,
    index_to_json,
    load_index,
    reload_index,
    add_take,
    add_take_file,
    convert_slot,
    create_block,
    create_project,
    add_character,
    ensure_default_character,
    clear_character_provider,
    create_section,
    delete_section,
    delete_block,
    duplicate_block,
    delete_take,
    ensure_section,
    ensure_slot,
    clear_active_project,
    get_active_project,
    recent_projects,
    import_asset,
    load_secrets,
    list_assets,
    list_blocks,
    list_lines,
    load_block,
    load_line,
    load_project,
    load_workspace,
    reorder_lines,
    reorder_sections,
    revert_prompt,
    save_asset,
    configured_providers,
    create_job,
    fail_interrupted,
    list_jobs,
    save_secret,
    save_job,
    save_line,
    save_project,
    save_workspace,
    set_active_project,
    slot_key,
    update_block,
    update_line,
    update_settings,
    remove_character,
    rename_character,
    set_character_name,
    update_character_provider,
    update_section,
    update_slot,
    upsert_lines,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Jobs left running by a previous process are failed, not lost.
    try:
        fail_interrupted(_active_root())
    except Exception:  # noqa: BLE001 - startup must never fail on this
        pass
    yield


app = FastAPI(title="Dialogic Voice Partner Service", version="0.1.0", lifespan=lifespan)


def _active_root() -> Path:
    """Resolve the project the app is working in, or fail with a 409."""
    result = active_project()
    if result is None:
        raise HTTPException(status_code=409, detail="No active project.")
    return result[0]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe used by the desktop shell before enabling the UI."""
    return HealthResponse(status="ok")


@app.post("/projects", response_model=ProjectSettings, status_code=201)
def create_project_endpoint(request: CreateProjectRequest) -> ProjectSettings:
    try:
        settings = create_project(Path(request.root), request.godot_project, request.name)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    set_active_project(Path(request.root))
    return settings


@app.post("/projects/activate", response_model=ProjectSettings)
def activate_project(root: str = Query(min_length=1)) -> ProjectSettings:
    try:
        settings = load_project(Path(root))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    set_active_project(Path(root))
    return settings


@app.get("/projects", response_model=ProjectSettings)
def open_project(root: str = Query(min_length=1)) -> ProjectSettings:
    try:
        return load_project(Path(root))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/projects/close")
def close_project_endpoint() -> dict:
    """Detach the active project without touching its files."""
    clear_active_project()
    return {"active": None}


@app.get("/projects/recent", response_model=list[str])
def recent_projects_endpoint() -> list[str]:
    """Most recently opened project roots, newest first."""
    return recent_projects()


@app.get("/projects/{section_id}/workspace", response_model=WorkspaceState | None)
def get_workspace(section_id: str, root: str = Query(min_length=1)) -> WorkspaceState | None:
    try:
        return load_workspace(Path(root), section_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/projects/{section_id}/workspace", response_model=WorkspaceState)
def put_workspace(
    section_id: str,
    state: WorkspaceState,
    root: str = Query(min_length=1),
) -> WorkspaceState:
    if state.section != section_id:
        raise HTTPException(
            status_code=400,
            detail="section in body does not match the section in the path",
        )
    try:
        return save_workspace(Path(root), state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sync/lines", response_model=PushLinesResult)
def sync_lines(request: PushLinesRequest) -> PushLinesResult:
    """Create or update line documents pushed from the Godot editor extension.

    The target project is the one passed in the request, or the project the app
    has active. The Godot side therefore never needs to know a project path.
    """
    root_value = request.project_root or get_active_project()
    if not root_value:
        raise HTTPException(
            status_code=409,
            detail="No active project. Create one or activate it first.",
        )

    root = Path(root_value)
    try:
        _, section = ensure_section(root)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        created, updated = upsert_lines(root, request.dtl, request.lines, section)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PushLinesResult(created=created, updated=updated, section=section)


@app.get("/providers", response_model=list[ProviderInfo])
def list_providers_endpoint() -> list[ProviderInfo]:
    """Describe the registered providers so the UI can build its model picker."""
    return provider_infos()


@app.post("/assets/import", response_model=AssetInfo)
async def import_asset_endpoint(request: Request, name: str = Query(default="dropped")) -> AssetInfo:
    """Copy a dropped audio file into the pool, skipping identical content."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else "wav"
    if extension not in {"wav", "mp3", "ogg", "flac", "m4a", "webm"}:
        raise HTTPException(status_code=400, detail=f"Unsupported audio type: {extension}")
    return import_asset(_active_root(), name, body, extension)


@app.post("/assets/from-take", response_model=AssetInfo)
def asset_from_take_endpoint(request: AssetFromTakeRequest) -> AssetInfo:
    """Turn a block take into a plain audio asset in the shared pool."""
    root = _active_root()
    try:
        block = load_block(root, request.block)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    take = next((item for item in block.takes if item.id == request.take), None)
    if take is None:
        raise HTTPException(status_code=404, detail=f"Unknown take: {request.take}")

    path = root / take.asset
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Missing take file: {take.asset}")

    name = request.name or f"{block.title} · {take.id}"
    return import_asset(root, name, path.read_bytes(), path.suffix.lstrip("."), take.duration_ms)


@app.get("/assets", response_model=list[AssetInfo])
def list_assets_endpoint() -> list[AssetInfo]:
    """List recorded and uploaded audio available to every line."""
    return list_assets(_active_root())


@app.post("/assets", response_model=AssetInfo, status_code=201)
async def save_asset_endpoint(
    request: Request,
    name: str = Query(min_length=1),
    extension: str = Query("webm", pattern=r"^[a-z0-9]{2,5}$"),
    duration_ms: int = Query(0, ge=0),
) -> AssetInfo:
    """Store the raw request body as a new asset; used by the recorder and uploads."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    return save_asset(
        _active_root(),
        name,
        body,
        extension,
        duration_ms or None,
    )


@app.get("/media/{path:path}")
def get_media(path: str) -> FileResponse:
    """Serve generated audio; the browser needs it for playback and export preview."""
    root = _active_root()
    media_root = (root / "media").resolve()
    target = (media_root / path).resolve()
    if media_root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail=f"No media file: {path}")
    return FileResponse(target)


@app.get("/blocks", response_model=list[BlockDocument])
def list_blocks_endpoint(
    section: str | None = None,
    line: str | None = None,
) -> list[BlockDocument]:
    """List project blocks, optionally filtered by linked section or line."""
    return list_blocks(_active_root(), section, line)


@app.get("/blocks/{block_id}", response_model=BlockDocument)
def get_block_endpoint(block_id: str) -> BlockDocument:
    try:
        return load_block(_active_root(), block_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/blocks", response_model=BlockDocument, status_code=201)
def create_block_endpoint(request: CreateBlockRequest) -> BlockDocument:
    """Create a block, optionally merging one or several lines into it."""
    try:
        return create_block(
            _active_root(),
            request.line_uuid,
            request.title,
            request.section,
            request.line_uuids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/blocks/{block_id}", response_model=BlockDocument)
def update_block_endpoint(block_id: str, request: UpdateBlockRequest) -> BlockDocument:
    try:
        return update_block(
            _active_root(),
            block_id,
            request.title,
            request.links,
            request.active_slot,
            request.active_take,
            request.character,
            request.character_name,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/blocks/{block_id}", status_code=204)
def delete_block_endpoint(block_id: str) -> None:
    try:
        delete_block(_active_root(), block_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/blocks/{block_id}/takes/import", response_model=BlockDocument)
async def import_take_endpoint(
    block_id: str,
    request: Request,
    name: str = Query(default="dropped"),
    provider: str | None = None,
    model: str | None = None,
) -> BlockDocument:
    """Store a dropped audio file as a take of the block."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else "wav"

    root_dir = _active_root()
    try:
        block = load_block(root_dir, block_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    key = block.active_slot or slot_key(provider or "sapi", model or "system")
    if provider and model:
        key = slot_key(provider, model)
    return add_take_file(root_dir, block_id, key, body, extension)


@app.post("/blocks/{block_id}/slots", response_model=BlockDocument, status_code=201)
def ensure_slot_endpoint(block_id: str, request: EnsureSlotRequest) -> BlockDocument:
    """Create the provider/model slot on first use, keeping existing prompts."""
    try:
        return ensure_slot(_active_root(), block_id, request.provider, request.model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/blocks/{block_id}/slots", response_model=BlockDocument)
def update_slot_endpoint(
    block_id: str,
    request: UpdateSlotRequest,
    provider: str = Query(min_length=1),
    model: str = Query(min_length=1),
) -> BlockDocument:
    try:
        return update_slot(
            _active_root(),
            block_id,
            slot_key(provider, model),
            request.prompt,
            request.params,
            request.voice,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/blocks/{block_id}/slots/convert", response_model=BlockDocument)
def convert_slot_endpoint(
    block_id: str,
    provider: str = Query(min_length=1),
    model: str = Query(min_length=1),
) -> BlockDocument:
    """Rewrite the slot prompt into a plain sentence for the selected model."""
    try:
        return convert_slot(_active_root(), block_id, slot_key(provider, model))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/blocks/{block_id}/slots/revert", response_model=BlockDocument)
def revert_prompt_endpoint(
    block_id: str,
    provider: str = Query(min_length=1),
    model: str = Query(min_length=1),
) -> BlockDocument:
    """Restore the previous prompt of a slot."""
    try:
        return revert_prompt(_active_root(), block_id, slot_key(provider, model))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/blocks/{block_id}/takes", response_model=BlockDocument, status_code=201)
def add_take_endpoint(block_id: str, request: AddTakeRequest) -> BlockDocument:
    """Append a take to the block's shared history."""
    try:
        return add_take(
            _active_root(), block_id, request.slot, request.asset, request.duration_ms
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/blocks/{block_id}/takes/{take_id}", response_model=BlockDocument)
def delete_take_endpoint(block_id: str, take_id: str) -> BlockDocument:
    """Delete a take unless a clip still references it."""
    try:
        return delete_take(_active_root(), block_id, take_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/jobs", response_model=list[Job])
def list_jobs_endpoint() -> list[Job]:
    """Generation history, newest last; interrupted jobs show as failed."""
    return list_jobs(_active_root())


@app.post("/blocks/{block_id}/generate-batch", response_model=list[BatchGenerateResult])
def generate_batch_endpoint(
    block_id: str,
    request: GenerateBatchRequest,
) -> list[BatchGenerateResult]:
    """One take per provider; a provider error never blocks the rest."""
    try:
        return generate_batch(
            _active_root(), block_id, request.providers, raw=request.raw
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/credentials", response_model=list[str])
def list_credentials_endpoint() -> list[str]:
    """Providers that have stored credentials; values are never returned."""
    return configured_providers(_active_root())


@app.put("/credentials/{provider}", response_model=list[str])
def put_credentials_endpoint(provider: str, request: CredentialRequest) -> list[str]:
    return save_secret(_active_root(), provider, request.values)


@app.post("/blocks/{block_id}/generate-stream")
def generate_stream_endpoint(
    block_id: str, request: GenerateRequest
) -> StreamingResponse:
    """Stream the audio as it is produced, then save it as a take.

    The client hears the same samples that end up in the take, so a preview can
    never disagree with the saved result.
    """
    root = _active_root()
    try:
        block = load_block(root, block_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    key = slot_key(request.provider, request.model)
    slot = block.slots.get(key)
    if slot is None:
        raise HTTPException(status_code=404, detail=f"Unknown slot: {key}")

    provider = get_provider(request.provider)
    if not provider.supports_stream:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{request.provider}' does not support streaming",
        )

    try:
        voice, overrides = _resolve_defaults(root, block, slot, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    model_info = provider.find_model(request.model)
    params = {**model_info.defaults(), **overrides}
    _validate_params(model_info, params)
    credentials = load_secrets(root).get(provider.id, {})

    prompt = slot.prompt
    rate = provider.pcm_rate

    def stream():
        chunks: list[bytes] = []
        try:
            for chunk in provider.stream_pcm(
                request.model, prompt, params, voice, credentials
            ):
                chunks.append(chunk)
                yield chunk
        except Exception:  # noqa: BLE001 - client sees a truncated stream
            return

        pcm = b"".join(chunks)
        if pcm:
            save_pcm_take(root, block_id, key, pcm, rate)

    return StreamingResponse(
        stream(),
        media_type="application/octet-stream",
        headers={"X-Sample-Rate": str(rate), "Cache-Control": "no-store"},
    )


@app.post("/blocks/{block_id}/generate", response_model=BlockDocument)
def generate_endpoint(block_id: str, request: GenerateRequest) -> BlockDocument:
    """Synthesize the slot prompt now and append the audio as a new take."""
    try:
        return generate_take(
            _active_root(), block_id, request.provider, request.model, raw=request.raw
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects/index")
def project_index(root: str | None = None) -> dict:
    """Derived lookups for the whole project, rebuilding the cache if needed."""
    target = Path(root).expanduser().resolve() if root else _active_root()
    return index_to_json(load_index(target))


@app.post("/projects/reload", response_model=ReloadResult)
def project_reload(root: str | None = None) -> ReloadResult:
    """Pick up documents edited outside the app without a restart."""
    target = Path(root).expanduser().resolve() if root else _active_root()
    index = reload_index(target)
    return ReloadResult(
        sections=len(index.sections),
        lines=len(index.lines),
        blocks=len(index.blocks),
        orphans=len(index.orphans),
        take_refs=len(index.take_refs),
    )


@app.post("/projects/cleanup", response_model=CleanupResult)
def project_cleanup(
    root: str | None = None,
    remove_files: bool = True,
) -> CleanupResult:
    """Delete orphaned blocks and the take files nothing references."""
    target = Path(root).expanduser().resolve() if root else _active_root()
    return cleanup_orphans(target, remove_files=remove_files)


@app.get("/projects/active", response_model=ActiveProject | None)
def get_active_project_endpoint() -> ActiveProject | None:
    """Return the project the app is working in, or null when none is active."""
    result = active_project()
    if result is None:
        return None
    root, settings = result
    return ActiveProject(root=str(root), project=settings)


@app.get("/lines", response_model=list[LineDocument])
def list_lines_endpoint(
    section: str | None = None,
    root: str | None = None,
) -> list[LineDocument]:
    """List line documents of the active project, in the user's arrangement."""
    if root:
        project_root = Path(root)
        return list_lines(project_root, section, load_project(project_root).line_order)

    result = active_project()
    if result is None:
        raise HTTPException(status_code=409, detail="No active project.")
    project_root, settings = result
    return list_lines(project_root, section, settings.line_order)


@app.put("/lines/order", response_model=list[LineDocument])
def reorder_lines_endpoint(request: LineOrderRequest) -> list[LineDocument]:
    """Persist a drag-to-reorder result and return the list in the new order."""
    project_root = _active_root()
    settings = reorder_lines(project_root, request.uuids)
    return list_lines(project_root, None, settings.line_order)


@app.patch("/lines/{line_uuid}", response_model=LineDocument)
def update_line_endpoint(line_uuid: str, request: UpdateLineRequest) -> LineDocument:
    """Edit a line's text or character; clips are preserved."""
    try:
        return update_line(
            _active_root(),
            line_uuid,
            request.text,
            request.character,
            request.character_name,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/projects/settings", response_model=ProjectSettings)
def update_settings_endpoint(request: UpdateSettingsRequest) -> ProjectSettings:
    """Update project-level preferences such as the recording countdown."""
    return update_settings(_active_root(), request.recording_countdown_ms, request.export)


@app.post("/lines/{line_uuid}/export", response_model=ExportResult)
def export_line_endpoint(line_uuid: str) -> ExportResult:
    """Mix one line to a WAV next to the Godot project and remember the path."""
    root = _active_root()
    settings = load_project(root)
    try:
        line = load_line(root, line_uuid)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return ExportResult(**export_line_file(root, settings, line))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/assets/render", response_model=AssetInfo)
def render_asset_endpoint(request: SelectionAssetRequest) -> AssetInfo:
    """Save the selected slice of a line as a shared asset."""
    root = _active_root()
    settings = load_project(root)
    try:
        line = load_line(root, request.line_uuid)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        payload, duration_ms = render_range(
            root,
            line,
            request.start_ms,
            request.end_ms,
            settings.export,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    name = request.name or f"{line.character_name or line.character or 'selection'} {request.start_ms}-{request.end_ms}ms"
    return save_asset(root, name, payload, "wav", duration_ms)


@app.post("/assets/upload", response_model=AssetInfo)
async def upload_asset_endpoint(request: Request, name: str = Query(default="upload")) -> AssetInfo:
    """Store an audio file posted as a raw body and list it in the pool."""
    root = _active_root()
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty upload")
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else "wav"
    if extension not in {"wav", "mp3", "ogg", "flac", "m4a"}:
        raise HTTPException(status_code=400, detail=f"Unsupported audio type: {extension}")
    return save_asset(root, name, body, extension, None)


@app.post("/lines/{line_uuid}/writeback", response_model=ExportResult)
def retry_writeback_endpoint(line_uuid: str) -> ExportResult:
    """Re-send a pending write-back for an already rendered line."""
    root = _active_root()
    settings = load_project(root)
    try:
        line = load_line(root, line_uuid)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        ok, error = retry_writeback(root, settings, line)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ExportResult(
        line_uuid=line.uuid,
        ok=ok,
        path=line.export_path,
        writeback_ok=ok,
        writeback_error=error,
        error=None if ok else "write-back failed",
    )


@app.post("/blocks/{block_id}/duplicate", response_model=BlockDocument)
def duplicate_block_endpoint(block_id: str) -> BlockDocument:
    """Copy a block; the audio files are shared, slots and prompt are copied."""
    try:
        return duplicate_block(_active_root(), block_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/export", response_model=list[ExportResult])
def export_batch_endpoint(request: ExportLineRequest) -> list[ExportResult]:
    """Render several lines; one failure is reported without aborting the rest."""
    root = _active_root()
    settings = load_project(root)
    uuids = request.uuids or [line.uuid for line in list_lines(root)]
    results: list[ExportResult] = []
    for uuid_value in uuids:
        try:
            line = load_line(root, uuid_value)
            results.append(ExportResult(**export_line_file(root, settings, line)))
        except Exception as exc:  # noqa: BLE001 - report per line, not the batch
            results.append(
                ExportResult(line_uuid=uuid_value, ok=False, error=str(exc))
            )
    return results


@app.get("/characters", response_model=list[CharacterInfo])
def list_characters_endpoint() -> list[CharacterInfo]:
    """List project characters; characters first seen in lines are adopted."""
    root = _active_root()
    settings = load_project(root)

    counts: dict[str, int] = {}
    adopted = False
    for line in list_lines(root):
        if not line.character:
            continue
        counts[line.character] = counts.get(line.character, 0) + 1
        if line.character not in settings.characters:
            settings.characters[line.character] = CharacterSettings(
                name=line.character_name or line.character
            )
            adopted = True

    if ensure_default_character(settings):
        adopted = True
    if adopted:
        settings = save_project(root, settings)

    return [
        _character_info(character, entry, counts.get(character, 0))
        for character, entry in sorted(settings.characters.items())
    ]


def _character_info(character: str, entry: CharacterSettings, lines: int) -> CharacterInfo:
    return CharacterInfo(
        id=character,
        name=entry.name or character,
        lines=lines,
        providers=entry.providers,
        is_default=character == DEFAULT_CHARACTER_ID,
    )


@app.post("/characters", response_model=CharacterInfo, status_code=201)
def create_character_endpoint(request: CreateCharacterRequest) -> CharacterInfo:
    """Add a character whose provider defaults start from the fallback one."""
    root = _active_root()
    try:
        settings = add_character(root, request.id, request.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _character_info(request.id, settings.characters[request.id], 0)


@app.patch("/characters/{character}", response_model=CharacterInfo)
def patch_character_endpoint(
    character: str, request: UpdateCharacterRequest
) -> CharacterInfo:
    """Rename a character, optionally moving it to a new Dialogic id."""
    root = _active_root()
    settings = load_project(root)
    if character not in settings.characters:
        raise HTTPException(status_code=404, detail=f"Unknown character: {character}")

    target = character
    if request.id is not None and request.id.strip() and request.id.strip() != character:
        try:
            settings = rename_character(root, character, request.id.strip())
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        target = request.id.strip()

    if request.name is not None and request.name.strip():
        settings = set_character_name(root, target, request.name.strip())

    lines = sum(1 for line in list_lines(root) if line.character == target)
    return _character_info(target, settings.characters[target], lines)


@app.delete("/characters/{character}", status_code=204)
def delete_character_endpoint(character: str) -> None:
    """Remove a character unless lines still use it or it is the fallback."""
    root = _active_root()
    used = [line for line in list_lines(root) if line.character == character]
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"{len(used)} line(s) still use character '{character}'",
        )
    try:
        remove_character(root, character)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.put("/characters/{character}/providers/{provider_id}", response_model=CharacterInfo)
def set_character_provider_endpoint(
    character: str,
    provider_id: str,
    request: UpdateCharacterProviderRequest,
) -> CharacterInfo:
    """Set one provider's voice and parameters for a character."""
    root = _active_root()
    try:
        provider = get_provider(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if provider.voice_mode == "select" and provider.voices and request.voice:
        if not any(item.id == request.voice for item in provider.voices):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown voice '{request.voice}' for provider '{provider_id}'",
            )

    try:
        settings = update_character_provider(
            root, character, provider_id, request.voice, request.params
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    lines = sum(1 for line in list_lines(root) if line.character == character)
    return _character_info(character, settings.characters[character], lines)


@app.delete("/characters/{character}/providers/{provider_id}", status_code=204)
def clear_character_provider_endpoint(character: str, provider_id: str) -> None:
    """Reset one provider's defaults so the provider defaults apply again."""
    try:
        clear_character_provider(_active_root(), character, provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/lines/{line_uuid}/track", response_model=LineDocument)
def put_track_endpoint(line_uuid: str, track: Track) -> LineDocument:
    """Replace a line's whole track; the editor sends the complete clip list.

    Sending everything keeps the stored track identical to what the timeline
    shows, so a failed drag can never leave half an edit behind.
    """
    project_root = _active_root()
    try:
        document = load_line(project_root, line_uuid)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    for clip in track.clips:
        if clip.out_ms <= clip.in_ms:
            raise HTTPException(
                status_code=400,
                detail=f"Clip out_ms must be greater than in_ms (got {clip.in_ms}..{clip.out_ms})",
            )

    document.track = track
    return save_line(project_root, document)


@app.post("/projects/sections", response_model=Section, status_code=201)
def create_section_endpoint(request: CreateSectionRequest) -> Section:
    result = active_project()
    if result is None:
        raise HTTPException(status_code=409, detail="No active project.")
    root, _ = result
    try:
        return create_section(root, request.id, request.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/projects/sections/order", response_model=list[Section])
def reorder_sections_endpoint(request: SectionOrderRequest) -> list[Section]:
    """Persist the user's section order."""
    return reorder_sections(_active_root(), request.ids)


@app.delete("/projects/sections/{section_id}", response_model=list[Section])
def delete_section_endpoint(section_id: str) -> list[Section]:
    """Remove a section and its workspace, keeping at least one section."""
    try:
        return delete_section(_active_root(), section_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/projects/sections/{section_id}", response_model=Section)
def update_section_endpoint(section_id: str, request: UpdateSectionRequest) -> Section:
    result = active_project()
    if result is None:
        raise HTTPException(status_code=409, detail="No active project.")
    root, _ = result
    try:
        return update_section(root, section_id, request.name, request.order)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/sections/{section_id}/activate", response_model=Section)
def activate_section_endpoint(section_id: str) -> Section:
    result = active_project()
    if result is None:
        raise HTTPException(status_code=409, detail="No active project.")
    root, settings = result
    try:
        activate_section(root, section_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for section in settings.sections:
        if section.id == section_id:
            return section
    raise HTTPException(status_code=404, detail=f"Unknown section: {section_id}")

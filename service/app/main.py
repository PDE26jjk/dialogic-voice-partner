from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .export import export_line as export_line_file
from .generation import generate_take
from .providers.registry import get_provider, provider_infos
from .schemas import (
    ActiveProject,
    AddTakeRequest,
    AssetInfo,
    BlockDocument,
    CharacterInfo,
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
    add_take,
    convert_slot,
    create_block,
    create_project,
    create_section,
    delete_block,
    find_character_voice,
    delete_take,
    ensure_section,
    ensure_slot,
    get_active_project,
    set_character_voice,
    list_assets,
    list_blocks,
    list_lines,
    load_block,
    load_line,
    load_project,
    load_workspace,
    reorder_lines,
    revert_prompt,
    save_asset,
    save_line,
    save_project,
    save_workspace,
    set_active_project,
    slot_key,
    update_block,
    update_line,
    update_settings,
    update_section,
    update_slot,
    upsert_lines,
)

app = FastAPI(title="Dialogic Voice Partner Service", version="0.1.0")


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


@app.post("/blocks/{block_id}/generate", response_model=BlockDocument)
def generate_endpoint(block_id: str, request: GenerateRequest) -> BlockDocument:
    """Synthesize the slot prompt now and append the audio as a new take."""
    try:
        return generate_take(_active_root(), block_id, request.provider, request.model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    return update_settings(_active_root(), request.recording_countdown_ms)


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
            settings.characters[line.character] = line.character_name or line.character
            adopted = True
    if adopted:
        settings = save_project(root, settings)

    return [
        _character_info(character, {"name": name, "lines": counts.get(character, 0)}, settings)
        for character, name in sorted(settings.characters.items())
    ]


@app.post("/characters", response_model=CharacterInfo, status_code=201)
def create_character_endpoint(request: CreateCharacterRequest) -> CharacterInfo:
    """Add a character that is not referenced by a line yet."""
    root = _active_root()
    settings = load_project(root)
    if request.id in settings.characters:
        raise HTTPException(status_code=409, detail=f"Character already exists: {request.id}")
    settings.characters[request.id] = request.name
    settings = save_project(root, settings)
    return _character_info(request.id, {"name": request.name, "lines": 0}, settings)


@app.patch("/characters/{character}", response_model=CharacterInfo)
def rename_character_endpoint(
    character: str, request: UpdateCharacterRequest
) -> CharacterInfo:
    """Rename a character, optionally moving it to a new Dialogic id.

    Changing the id migrates the local lines and every provider voice mapping, so
    the character keeps its history and voice.
    """
    root = _active_root()
    settings = load_project(root)
    if character not in settings.characters:
        raise HTTPException(status_code=404, detail=f"Unknown character: {character}")

    target = (request.id or character).strip() or character
    if target != character:
        if target in settings.characters:
            raise HTTPException(status_code=409, detail=f"Character already exists: {target}")
        settings.characters[target] = settings.characters.pop(character)
        for entry in settings.providers.values():
            if isinstance(entry, dict) and isinstance(entry.get("voices"), dict):
                voices = entry["voices"]
                if character in voices:
                    voices[target] = voices.pop(character)
        for line in list_lines(root):
            if line.character == character:
                line.character = target
                save_line(root, line)

    if request.name is not None and request.name.strip():
        settings.characters[target] = request.name.strip()
    else:
        settings.characters.setdefault(target, target)

    settings = save_project(root, settings)
    lines = [line for line in list_lines(root) if line.character == target]
    return _character_info(
        target,
        {"name": settings.characters[target], "lines": len(lines)},
        settings,
    )


@app.delete("/characters/{character}", status_code=204)
def delete_character_endpoint(character: str) -> None:
    """Remove a character and its voice mappings, unless lines still use it."""
    root = _active_root()
    settings = load_project(root)
    if character not in settings.characters:
        raise HTTPException(status_code=404, detail=f"Unknown character: {character}")
    used = [line for line in list_lines(root) if line.character == character]
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"{len(used)} line(s) still use character '{character}'",
        )

    del settings.characters[character]
    for entry in settings.providers.values():
        if isinstance(entry, dict) and isinstance(entry.get("voices"), dict):
            entry["voices"].pop(character, None)
    save_project(root, settings)


def _character_info(character: str, info: dict, settings: ProjectSettings) -> CharacterInfo:
    provider, voice = find_character_voice(settings, character)
    label = None
    if provider and voice:
        try:
            match = next(
                (item for item in get_provider(provider).voices if item.id == voice),
                None,
            )
            label = match.label if match else voice
        except KeyError:
            label = voice
    return CharacterInfo(
        id=character,
        name=info["name"],
        lines=info["lines"],
        provider=provider,
        voice=voice,
        voice_label=label,
    )


@app.put("/characters/{character}/voice", response_model=CharacterInfo)
def set_character_voice_endpoint(
    character: str, request: SetCharacterVoiceRequest
) -> CharacterInfo:
    """Map one character to a voice on a provider."""
    root = _active_root()
    try:
        provider = get_provider(request.provider)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if provider.voices and not any(item.id == request.voice for item in provider.voices):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice '{request.voice}' for provider '{request.provider}'",
        )

    settings = set_character_voice(root, character, request.provider, request.voice)
    lines = [line for line in list_lines(root) if line.character == character]
    name = next(
        (line.character_name for line in lines if line.character_name),
        character,
    )
    return _character_info(character, {"name": name, "lines": len(lines)}, settings)


@app.delete("/characters/{character}/voice", status_code=204)
def clear_character_voice_endpoint(character: str) -> None:
    """Reset a character to the default: no voice mapped on any provider."""
    root = _active_root()
    settings = load_project(root)
    if character not in settings.characters:
        raise HTTPException(status_code=404, detail=f"Unknown character: {character}")
    for entry in settings.providers.values():
        if isinstance(entry, dict) and isinstance(entry.get("voices"), dict):
            entry["voices"].pop(character, None)
    save_project(root, settings)


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

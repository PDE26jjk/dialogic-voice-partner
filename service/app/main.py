from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .generation import generate_take
from .providers.registry import provider_infos
from .schemas import (
    ActiveProject,
    AddTakeRequest,
    BlockDocument,
    CreateBlockRequest,
    CreateProjectRequest,
    CreateSectionRequest,
    EnsureSlotRequest,
    GenerateRequest,
    HealthResponse,
    LineDocument,
    LineOrderRequest,
    ProjectSettings,
    ProviderInfo,
    PushLinesRequest,
    PushLinesResult,
    Section,
    UpdateBlockRequest,
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
    delete_take,
    ensure_section,
    ensure_slot,
    get_active_project,
    list_blocks,
    list_lines,
    load_block,
    load_project,
    load_workspace,
    reorder_lines,
    revert_prompt,
    save_workspace,
    set_active_project,
    slot_key,
    update_block,
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
    """Create a block, optionally copying character and text from a line."""
    try:
        return create_block(
            _active_root(), request.line_uuid, request.title, request.section
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

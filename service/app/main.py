from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from .schemas import (
    CreateProjectRequest,
    HealthResponse,
    ProjectSettings,
    PushLinesRequest,
    PushLinesResult,
    WorkspaceState,
)
from .storage import (
    create_project,
    ensure_section,
    get_active_project,
    load_project,
    load_workspace,
    save_workspace,
    set_active_project,
    upsert_lines,
)

app = FastAPI(title="Dialogic Voice Partner Service", version="0.1.0")


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

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from .schemas import (
    CreateProjectRequest,
    HealthResponse,
    ProjectSettings,
    WorkspaceState,
)
from .storage import create_project, load_project, load_workspace, save_workspace

app = FastAPI(title="Dialogic Voice Partner Service", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe used by the desktop shell before enabling the UI."""
    return HealthResponse(status="ok")


@app.post("/projects", response_model=ProjectSettings, status_code=201)
def create_project_endpoint(request: CreateProjectRequest) -> ProjectSettings:
    try:
        return create_project(Path(request.root), request.godot_project, request.name)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness payload returned by the local service."""

    status: str = Field(description="Always 'ok' while the service is accepting requests")


class Section(BaseModel):
    """A page of lines inside one project."""

    id: str = Field(description="Stable identifier, also used as the workspace file name")
    name: str = Field(description="Display name shown in the section picker")
    order: int = Field(default=0, description="Ascending sort position")


class SourceRef(BaseModel):
    """Where a clip or workspace source takes its audio from."""

    kind: Literal["take", "asset"] = Field(description="Where the audio comes from")
    block: str | None = Field(default=None, description="Block id for a take source")
    take: str | None = Field(default=None, description="Take id for a take source")
    asset: str | None = Field(default=None, description="Asset id for an asset source")


class Clip(BaseModel):
    """One placement on a line's single track, in milliseconds."""

    source: SourceRef
    in_ms: int = Field(ge=0, description="Source in point")
    out_ms: int = Field(ge=0, description="Source out point")
    start_ms: int = Field(ge=0, description="Position on the line timeline")


class Track(BaseModel):
    clips: list[Clip] = Field(default_factory=list)


class Selection(BaseModel):
    in_ms: int = Field(ge=0, description="Selection start in milliseconds")
    out_ms: int = Field(ge=0, description="Selection end in milliseconds")


class WorkspaceState(BaseModel):
    """Per-section workspace document (`workspaces/<section_id>.json`)."""

    section: str = Field(description="Section this workspace belongs to")
    source: SourceRef | None = Field(default=None, description="Loaded source, if any")
    in_ms: int = Field(default=0, ge=0, description="Workspace in point in milliseconds")
    out_ms: int = Field(default=0, ge=0, description="Workspace out point in milliseconds")
    selection: Selection | None = Field(default=None, description="Active selection, if any")
    updated_at: datetime | None = None


class ProjectSettings(BaseModel):
    """`project.json`: one project bound to one Godot project."""

    version: int = 1
    name: str
    godot_project: str = Field(description="Absolute path of the bound Godot project")
    sections: list[Section] = Field(default_factory=list)
    current_section: str | None = Field(default=None, description="Section receiving new lines")
    providers: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-provider settings, including character to voice mappings",
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateProjectRequest(BaseModel):
    root: str = Field(description="Absolute folder that will hold the project documents")
    godot_project: str = Field(description="Absolute path of the Godot project to bind")
    name: str = Field(min_length=1, description="Human-readable project name")


class LineDocument(BaseModel):
    """`lines/<uuid>.json`: one Dialogic voice line and its single track."""

    uuid: str = Field(description="Godot-generated UUID of the voice event")
    section: str
    dtl: str = Field(description="Source `.dtl` path inside the Godot project")
    character: str = Field(description="Dialogic character identifier")
    character_name: str | None = Field(default=None, description="Character display name")
    text: str = Field(description="Spoken text copied from the paired text event")
    track: Track = Field(default_factory=Track)
    updated_at: datetime | None = None


class PushLine(BaseModel):
    """One voice line sent by the Godot editor extension."""

    uuid: str = Field(min_length=8, max_length=64, description="UUID written on the voice event")
    character: str = Field(description="Dialogic character identifier")
    character_name: str | None = None
    text: str = Field(description="Spoken text of the paired text event")
    voice_file: str | None = Field(default=None, description="Existing voice file path, if any")
    volume: float = 0
    bus: str = "Master"


class PushLinesRequest(BaseModel):
    project_root: str = Field(description="Companion project folder that receives the lines")
    dtl: str = Field(description="Source `.dtl` path inside the Godot project")
    lines: list[PushLine] = Field(min_length=1)


class PushLinesResult(BaseModel):
    created: int
    updated: int
    section: str

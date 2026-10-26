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


class WorkspaceClip(BaseModel):
    """One placed segment on a workbench lane; trims are per clip, not per lane."""

    id: str
    name: str = Field(default="", description="Display label, usually the take or file name")
    source: SourceRef
    start_ms: int = Field(default=0, ge=0, description="Position on the shared timeline")
    in_ms: int = Field(default=0, ge=0, description="Trim start inside the source")
    out_ms: int = Field(default=0, ge=0, description="Trim end inside the source")


class WorkspaceTrack(BaseModel):
    """One lane of the workbench. Lanes only stack audio; they add no trim."""

    id: str
    name: str = Field(default="")
    clips: list[WorkspaceClip] = Field(default_factory=list)
    muted: bool = Field(default=False, description="Silenced during workbench playback")
    solo: bool = Field(default=False, description="Only solo lanes are audible")
    armed: bool = Field(default=False, description="Receives recordings from the R shortcut")


class WorkspaceState(BaseModel):
    """Per-section workbench (`workspaces/<section_id>.json`).

    The workbench is a small multitrack editor: lanes hold clips that reference
    takes or assets, and everything sums together. Inserting a clip into a line
    copies the reference, never the audio.
    """

    section: str = Field(description="Section this workspace belongs to")
    tracks: list[WorkspaceTrack] = Field(default_factory=list)
    selected_clip: str | None = Field(default=None, description="Clip shown as selected")
    updated_at: datetime | None = None


class ProjectSettings(BaseModel):
    """`project.json`: one project bound to one Godot project."""

    version: int = 1
    name: str
    godot_project: str = Field(description="Absolute path of the bound Godot project")
    sections: list[Section] = Field(default_factory=list)
    current_section: str | None = Field(default=None, description="Section receiving new lines")
    line_order: list[str] = Field(
        default_factory=list,
        description="Line UUIDs in the order the user arranged them",
    )
    recording_countdown_ms: int = Field(
        default=2000,
        ge=0,
        le=10000,
        description="Delay before recording starts, in milliseconds",
    )
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
    project_root: str | None = Field(
        default=None,
        description="Target project folder; defaults to the app's active project",
    )
    dtl: str = Field(description="Source `.dtl` path inside the Godot project")
    lines: list[PushLine] = Field(min_length=1)


class PushLinesResult(BaseModel):
    created: int
    updated: int
    section: str


class ActiveProject(BaseModel):
    """The project the app is currently working in."""

    root: str = Field(description="Absolute folder of the project documents")
    project: ProjectSettings


class CreateSectionRequest(BaseModel):
    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Identifier used in the workspace file name",
    )
    name: str = Field(min_length=1, description="Display name")


class UpdateSectionRequest(BaseModel):
    name: str | None = None
    order: int | None = None


class BlockLinks(BaseModel):
    """Lines and sections a block is attached to; links never imply ownership."""

    lines: list[str] = Field(default_factory=list, description="Line UUIDs")
    sections: list[str] = Field(default_factory=list, description="Section ids")


class BlockSlot(BaseModel):
    """One provider/model slot of a block, created on first use."""

    provider: str
    model: str
    prompt: str = Field(default="", description="Prompt sent to this model")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-native parameters for this model",
    )
    history: list[str] = Field(
        default_factory=list,
        description="Previous prompts, oldest first, so conversion stays reversible",
    )
    updated_at: datetime | None = None


class Take(BaseModel):
    """One generated audio file in a block's shared take history."""

    id: str
    slot: str = Field(description="Slot key this take was produced with")
    provider: str
    model: str
    asset: str = Field(description="Path of the audio file relative to the project root")
    duration_ms: int | None = None
    created_at: datetime | None = None


class BlockDocument(BaseModel):
    """`blocks/<id>.json`: a project-level generation unit."""

    version: int = 1
    id: str
    title: str
    character: str = Field(default="", description="Dialogic character identifier")
    character_name: str | None = None
    text: str = Field(default="", description="Line text this block started from")
    links: BlockLinks = Field(default_factory=BlockLinks)
    slots: dict[str, BlockSlot] = Field(
        default_factory=dict,
        description="Slots keyed by '<provider>/<model>'",
    )
    active_slot: str | None = None
    active_take: str | None = Field(
        default=None,
        description="Take used when a clip is created from this block",
    )
    takes: list[Take] = Field(default_factory=list, description="Shared, append-only history")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateBlockRequest(BaseModel):
    line_uuid: str | None = Field(
        default=None,
        description="Line to copy character and text from; links the block to it",
    )
    line_uuids: list[str] = Field(
        default_factory=list,
        description="Several lines merged into one block; overrides line_uuid",
    )
    title: str | None = None
    section: str | None = Field(default=None, description="Section to link the block to")


class UpdateBlockRequest(BaseModel):
    title: str | None = None
    links: BlockLinks | None = None
    active_slot: str | None = None
    active_take: str | None = None


class EnsureSlotRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class UpdateSlotRequest(BaseModel):
    prompt: str | None = None
    params: dict[str, Any] | None = None


class AddTakeRequest(BaseModel):
    slot: str = Field(min_length=1)
    asset: str = Field(min_length=1)
    duration_ms: int | None = None


class ProviderModel(BaseModel):
    id: str
    label: str


class ProviderInfo(BaseModel):
    """One registered provider and the models its adapter offers."""

    id: str
    label: str
    models: list[ProviderModel]


class GenerateRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class AssetInfo(BaseModel):
    """An uploaded or recorded audio file in the shared pool."""

    id: str
    name: str
    path: str = Field(description="Path relative to the project root")
    duration_ms: int | None = None
    created_at: datetime | None = None


class LineOrderRequest(BaseModel):
    """The full line order after a drag, top to bottom."""

    uuids: list[str] = Field(default_factory=list)


class UpdateLineRequest(BaseModel):
    """Editable line fields; the Godot timeline is still the source for events."""

    text: str | None = None
    character: str | None = None
    character_name: str | None = None


class UpdateSettingsRequest(BaseModel):
    recording_countdown_ms: int | None = Field(default=None, ge=0, le=10000)

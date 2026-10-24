## Why

Dialogic authors write voice lines as text inside `.dtl` timelines, but generating,
auditioning, arranging and exporting the actual audio happens nowhere in Godot: the
Voice event only accepts a path to a file that must already exist. Every line becomes a
manual round trip through an external TTS site, a file manager, and a timeline editor,
and there is no place to keep multiple takes or to re-render a line after a text edit.

This change establishes the initial framework for a desktop voice-production companion
that treats Dialogic lines as the unit of work, keeps a project-wide pool of generation
blocks, arranges takes on a per-line single track, and exports finished audio back into
the Godot project through the editor extension over MCP.

## What Changes

- Add a desktop application (Electron shell + React UI + local FastAPI service) that owns
  the framing of a single voice-production project bound 1:1 to one Godot project.
- Add a Godot-side contract: the Dialogic voice event carries a Godot-generated UUID, and
  a manual push action sends one or many selected lines to the companion (upsert by UUID,
  never the reverse direction).
- Add a project-level block pool. A block is independent of any timeline and can be linked
  to several lines and sections. Each block holds per-provider/model slots (prompt and
  provider-specific parameters, created lazily on first use of that model) and one shared,
  append-only list of takes across all models.
- Add per-line single-track timelines whose clips reference either a block take or a media
  asset, with fixed in/out points selected when the clip is created, free placement, and
  additive overlap.
- Add a shared workspace for trimming, cutting, auditioning, uploading and recording audio,
  producing reusable assets.
- Add remote TTS provider adapters that translate a common intent into each provider's own
  parameters and inline tags, with per-provider character-to-voice mappings in project
  settings, and asynchronous generation jobs dispatched without an app-level concurrency cap.
- Add line-level export: render one line or a batch of lines to configured audio formats and
  deliver the files into the Godot project, then ask the Dialogic extension over its local
  HTTP endpoint to update the corresponding voice events.
- Store project data as a plain JSON file tree (no relational database) that is readable and
  diffable in git.

## Capabilities

### New Capabilities

- `app-shell`: desktop shell, local service lifecycle, same-origin API transport, and the
  five-region workspace layout (projects, lines, block pool, inspector, shared workspace).
- `project-storage`: the project folder contract, JSON document trees, atomic writes,
  in-memory indexing, section list, and orphan handling.
- `line-sync`: the Godot push contract (manual, multi-select, UUID upsert, orphan marking)
  and the project binding rules.
- `block-pool`: project-level blocks, provider/model slots, prompt initialization and
  conversion, shared takes, duplication and regeneration history.
- `line-timeline`: per-line single-track timeline, clip sources (take or asset), in/out
  points, placement, additive overlap, and line duration rules.
- `shared-workspace`: trimming and cutting surface, uploads, recordings, and asset creation.
- `provider-adapters`: remote provider registry, intent-to-parameters/tag compilation,
  project-level character-to-voice settings, and asynchronous generation jobs.
- `line-export`: line and batch rendering, format settings, destination naming in the Godot
  project, and MCP-driven write-back of voice events.

### Modified Capabilities

None. This is the initial framework; no existing specs are affected.

## Impact

- New repository `dialogic-voice-partner`; no existing application code is modified.
- New dependency on Godot + Dialogic (2.0 alpha) project layout, `.dtl` text format, and an
  editor extension supplied alongside this project.
- New dependency on an editor HTTP endpoint exposed by the Godot extension for write-back
  after export.
- New dependency on remote TTS provider HTTP APIs and their credentials, stored per project.
- Out of scope for this change: local TTS engines, multi-track timelines, background music
  or SFX tracks, in-app video, real-time streaming playback, collaboration, and cloud sync.

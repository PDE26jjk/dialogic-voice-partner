## Context

See [proposal.md](proposal.md) for motivation and [specs/](specs/) for the behavior contract.
This document records the technical approach that those specs assume.

Current state and constraints that shape the design:

- Target content is a Godot 4.x project (the sample runs Godot 4.7) with Dialogic
  2.0-alpha-21. A Dialogic *line* is a voice event followed by a text event; the voice event
  must sit immediately before the text event it voices.
- `.dtl` is a line-based text DSL with no stable event identifiers. The Godot extension will
  add a UUID to the voice event, which becomes the identity used everywhere else.
- The companion is the only place that stores generation state, takes and timelines. Godot
  remains the authority for line text, character and timeline structure.
- Single local user, Windows-first. Projects must stay readable and diffable in git, and the
  user explicitly rejected a relational database.
- Generation is remote-provider-only. No local model inference, no streaming playback.
- Write-back into `.dtl` is performed by the Godot extension, reached over its MCP endpoint.

## Goals / Non-Goals

**Goals:**

- A desktop application that can be developed and run without bundling Python or models.
- A plain-file project format that survives hand edits and partial writes.
- A working vertical slice: push → block → generate → take → timeline → export → MCP write-back.
- Clean seams so that storage, providers, playback and the Godot bridge can be replaced
  independently.

**Non-Goals:**

- Bundling a Python runtime into an installer (development-time `uv` is enough for this change).
- Multi-track timelines, background music, SFX beds or cross-line mixing.
- Real-time streaming synthesis or progressive audio playback while generating.
- Multiple projects open at once, collaboration, or cloud sync.
- Replacing or forking Dialogic itself.

## Decisions

### D1. Shell: Electron + electron-vite, renderer in React, service in FastAPI

The renderer is React 19 with TypeScript, written in a deliberately small subset: function
components, `useState` / `useEffect` / `useRef`, plain CSS, `fetch`, and no router, state
library or component library. The goal is readability for a maintainer returning to
front-end work, not fluency in the ecosystem.

- Alternatives: Vue 3 (the ComfyUI front end uses it and it is simpler to learn, but the
  maintainer rejected it after seeing uncompiled template placeholders); Svelte (smallest
  code, smallest ecosystem); a framework-free TypeScript UI (fastest to load, but timeline
  state and drag targets become imperative and harder to follow).
- Consequence: the service is a child process with its own lifecycle; the renderer cannot
  assume it is up on first paint.

### D2. Transport: custom app scheme proxying `/api`, plus WebSocket for job events

The renderer always calls `/api/...`. In development a Vite proxy forwards to the service; in
production a privileged custom scheme handler forwards with `net.fetch`, preserving Range
requests so large audio files stream.

- Alternatives: direct `http://127.0.0.1:<port>` calls (CORS plus a token to distribute);
  IPC-only bridge (hard to stream audio and hard to debug with curl).
- Consequence: one relative base URL for all data calls; audio elements can use `/api/media/...`.

### D3. Storage: one JSON document per entity, atomic writes, in-memory index

`project.json` holds settings, provider credentials and the section list. `blocks/<id>.json`,
`lines/<uuid>.json`, `workspaces/<section>.json` and `media/` hold the rest. Writes go to a
temporary file and are renamed
into place. Opening a project scans documents once and builds reverse indexes (blocks per
line, takes referenced by clips, section membership).

- Alternatives: a single `project.json` (rewrites megabytes per take), SQLite (rejected by the
  user; opaque in git), an embedded document store (extra dependency, no human readability).
- Consequence: cross-document integrity is application-enforced; the index must be rebuilt on
  external edits, so a "reload project" action is mandatory.

### D4. Block identity and take sharing

A block is a project-level document with `links` (line UUIDs, section IDs), `slots` keyed by
`<provider>/<model>`, and one `takes` array. Slots are created lazily on first generation with
that model; takes carry the slot key but are never partitioned by model. Take deletion checks
clip references through the index.

- Alternatives: per-model take arrays (splits history and complicates filtering), blocks owned
  by a line (breaks cross-line borrowing, which the user requires).

### D5. Clip model: reference plus fixed span

A clip stores `source` (take reference or asset reference), `in`, `out` and `start` on a
per-line local timeline. `in`/`out` are captured from the first take at creation and never
follow later take changes. Rendering places the active take at `start`, truncates it at `out`,
and pads the remainder with silence.

- Alternatives: clip stores a rendered segment file (loses the ability to switch takes),
  in/out recomputed when the take changes (breaks layout stability and overlap math).

### D6. Playback: one WebAudio graph owned by a single engine module

All previews and timeline playback go through one audio engine. Timeline playback schedules
every clip source at its absolute offset in a single `AudioContext` timeline, so additive
overlap is a property of the graph rather than of application code. Any new playback first
stops the engine.

- Alternatives: several `<audio>` elements (overlap drift and inconsistent stop semantics), a
  service-side player (streaming latency and IPC round trips for scrubbing).

### D7. Providers: registry + adapter, intent compiled to native parameters

Each provider module declares its models and a parameter schema, and implements
`compile(intent, rawPrompt) → request` plus `generate(request) → audio bytes`. Character to
voice mapping lives in `project.json` under `providers.<id>.voices.<character>`.

- Alternatives: free-form per-provider JSON edited by hand (no validation, unusable defaults),
  one unified schema forced onto every provider (loses native controls such as stability or
  emotion vectors).

### D8. Write-back over the editor's local HTTP endpoint, with export decoupled from it

Export writes the file first, then POSTs `{line_uuid, audio_res_path, dtl_path}` to the editor
extension's local endpoint. The extension applies the change and returns a receipt; a failed
call leaves the file on disk and marks the line `exported_pending_writeback` so it can be
retried alone.

- Alternatives: the service edits `.dtl` itself (format and concurrency risk); an outbox file
  polled by the extension (works, but the result is delayed and harder to diagnose than an
  HTTP receipt); the local Godot MCP server (it exposes only scene/project tools, has no
  script-execution tool, pins an abandoned MCP SDK, and is documented as unreliable); one
  headless Godot process per write (1–2 s per call, and it races the open editor).

### D9. Generation jobs: persisted state machine, no application concurrency cap

Jobs are rows in `jobs.jsonl`-style append-only storage with states
`queued → generating → succeeded | failed | cancelled`. Submission sends every job; provider
rate limits surface as per-job failures. A restart marks in-flight jobs failed (retryable)
rather than pretending they are running.

- Alternatives: an in-memory queue (loses state on restart), a global semaphore (the user
  explicitly rejected app-level limits).

### D10. Workspace state is section-scoped

`workspaces/<section_id>.json` stores the current source reference, in/out points and
selection for one section. Switching sections swaps the document; edits debounce to the
current section only. Assets produced by a workspace live in the shared `media/assets/` pool,
so sections reference shared media instead of copying it.

- Alternatives: one global workspace (loses context when an author jumps between scenes);
  embedding workspace state in `project.json` (rewrites the whole settings document on every
  marker drag).

## Risks / Trade-offs

- **Dialogic is 2.0 alpha and its event API may change** → isolate all Dialogic interaction
  in the Godot extension, pin the tested Dialogic version, and keep the companion dependent
  only on the push payload and the editor endpoint contract.
- **Editor endpoint availability and port choice are environment-specific** → make the
  endpoint configurable, fail write-back with a retryable state, and never couple export to it.
- **No database means no transactions** → atomic file replacement, index rebuild on reload,
  single-instance lock, and a “reload project” path after external edits.
- **Cross-line take borrowing makes deletion protection non-local** → maintain a reverse index
  from take to referencing clips and refuse deletion with the list of referrers.
- **Audio is binary and projects live in git** → keep media under `media/` and recommend
  Git LFS; do not delete media on take removal until the index confirms no references.
- **Additive overlap can clip** → normalize the rendered line to a configurable peak ceiling
  (default -1 dBFS) and surface a warning instead of silently distorting.
- **Long Windows paths and CJK names** → treat all project paths as UTF-8, avoid fixed-length
  assumptions, and surface path errors with the offending path.

## Migration Plan

No migration: this is the first change in a new repository. Rollout is staged by the vertical
slice order in `tasks.md`; each stage leaves the previous stage usable. Rollback is deleting
the change's code paths; project documents are versioned by their own presence, so a failed
stage never rewrites documents another stage produced.

## Open Questions

- Which host/port the extension listens on (configurable; the payload contract above is fixed).
- Which two providers ship first (the registry is provider-agnostic).
- Whether exported masters need loudness normalization beyond peak limiting (format settings
  already model it; the default is peak-only).

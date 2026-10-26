## 1. Workspace skeleton

- [x] 1.1 Create the repository layout (`src/main`, `src/preload`, `src/renderer`, `service/`, `godot/`, `scripts/`) and verify the directories exist and are tracked by git
- [x] 1.2 Add the Electron main/preload/renderer bootstrap with electron-vite and verify `npm run dev` opens a window showing a placeholder route
- [x] 1.3 Add the FastAPI service with a `/health` endpoint and verify `uv run --project service uvicorn app.main:app --app-dir service --port 3900` answers `{"status":"ok"}`
- [ ] 1.4 Implement service supervision in the Electron main process (spawn, health poll, restart, clean quit) and verify killing the service process triggers a visible failure state and a working restart
- [x] 1.5 Add the same-origin `/api` proxy for development and packaged builds and verify a renderer `fetch('/api/health')` succeeds in both modes
- [x] 1.6 Define shared request/response types generated from the service OpenAPI schema and verify the typecheck fails if a field is added to the schema but not regenerated

## 2. Project storage

- [x] 2.1 Define the `project.json` schema (bound Godot path, section list, current section, provider settings) and verify a created project folder matches the documented tree
- [x] 2.2 Implement atomic document writes (temp file plus rename) and verify an interrupted write leaves the previous document readable
- [ ] 2.3 Implement the project index (sections, lines, blocks, takes, links, take-to-clip references) and verify a fixture project loads with expected lookup results
- [ ] 2.4 Implement section creation, reordering, selection and the default “Inbox” behavior and verify the spec scenarios for current-section assignment pass
- [ ] 2.5 Implement orphan marking and explicit orphan cleanup with take protection and verify a block whose line is gone survives until cleanup and a referenced take is never deleted
- [ ] 2.6 Implement “reload project” after external edits and verify a hand-edited block document is picked up without restart
- [x] 2.7 Implement per-section workspace documents (`workspaces/<section_id>.json`) and verify switching sections restores that section's source and in/out points

## 3. Godot bridge

- [x] 3.1 Add the Godot extension skeleton (EditorPlugin with a menu entry and a dock) and verify the plugin enables in the sample project without errors
- [x] 3.2 Extend the Dialogic voice event with a Godot-generated UUID field and verify it round-trips through save and reload of a `.dtl`
- [x] 3.3 Implement the manual push action for one or many selected voice events and verify the service receives the documented payload
- [x] 3.4 Implement the push result summary in the editor output panel and verify created/updated counts appear and a stopped service yields a retryable failure message
- [ ] 3.5 Implement the editor-side endpoint `POST /apply-export` in the extension and verify a curl call updates the matching voice event and refreshes the editor filesystem
- [ ] 3.6 Implement the service-side HTTP client with configurable host/port and verify a failed call surfaces as a pending write-back rather than a failed export

## 4. Block pool

- [ ] 4.1 Implement block creation from a line with the default title and the first slot initialized from the line text and verify the title and prompt match the spec defaults
- [ ] 4.2 Implement lazy slot creation on model change and verify switching providers creates a slot once and switching back restores its prompt and parameters
- [ ] 4.3 Implement block linking to multiple lines and sections and verify one block appears under two lines without ownership changes
- [ ] 4.4 Implement the append-only shared take list with source metadata and verify takes from two models remain visible and filterable
- [ ] 4.5 Implement take deletion with reference protection and verify deleting a referenced take is refused with the referencing line list
- [ ] 4.6 Implement block duplication (shared media, copied slots) and regeneration into a new take and verify both spec scenarios pass
- [ ] 4.7 Implement prompt conversion action with undo of the previous prompt text and verify a converted prompt can be reverted

## 5. Provider adapters

- [ ] 5.1 Implement the provider registry with model lists and parameter schemas and verify the inspector renders only declared parameters for a chosen model
- [ ] 5.2 Implement per-provider character-to-voice settings in `project.json` and verify generation refuses an unmapped character with the documented message
- [ ] 5.3 Implement the common intent model and the adapter compile step for the first provider and verify the same intent yields different request bodies for two providers
- [ ] 5.4 Implement raw prompt passthrough and verify tags are sent unmodified when raw mode is enabled
- [ ] 5.5 Implement the persisted job state machine and verify a restart during generation restores the job as failed and retryable
- [ ] 5.6 Implement batch submission without an app-level cap and verify one provider error does not block the remaining jobs
- [ ] 5.7 Implement per-project credential storage and verify secrets never appear in logs, job payloads or exported documents

## 6. Line timeline

- [ ] 6.1 Implement the per-line single track model with local time and verify an empty line opens at zero with one track
- [ ] 6.2 Implement clip creation from a take and from an asset with fixed in/out at creation and verify the clip spans the source duration
- [ ] 6.3 Implement take switching that preserves in/out and silence padding for short sources and verify the span and overlap layout stay unchanged
- [ ] 6.4 Implement free placement, drag from pool and workspace, and the append-to-end action and verify all three create clips at the expected positions
- [ ] 6.5 Implement cross-line take borrowing and verify a clip on line A references a take from a block linked to line B
- [ ] 6.6 Implement the single audio engine with scheduling for additive overlap and verify starting any playback stops the previous source

## 7. Shared workspace

- [ ] 7.1 Implement loading a take, asset or render into the workspace with waveform display and verify the waveform matches the source duration
- [ ] 7.2 Implement non-destructive in/out selection and selection playback and verify the source file is unchanged after previewing
- [ ] 7.3 Implement “save selection as asset” and verify a new file appears under `media/assets/` and is usable by a clip
- [ ] 7.4 Implement file upload into the project and verify the asset appears in the pool for every line
- [ ] 7.5 Implement microphone recording with a level meter and verify the resulting asset is stored and playable
- [ ] 7.6 Persist the workspace source, in/out points and selection to the current section and verify a section switch saves the old state and restores the new one

## 8. Export

- [ ] 8.1 Implement line rendering (place clips, sum overlaps, pad silence, peak-limit) and verify the rendered duration equals the line duration
- [ ] 8.2 Implement export format settings (container, sample rate, bit depth, channels) and verify a WAV export at 48 kHz produces a matching file
- [ ] 8.3 Implement destination naming (`audio/voice/<section_slug>/<line_uuid>.<ext>`) with overwrite and verify a re-export leaves no duplicate file
- [ ] 8.4 Implement the editor-endpoint write-back after a successful write and verify success marks the line exported and failure marks it pending without deleting the file
- [ ] 8.5 Implement batch export with per-line results and verify one failing line does not abort the batch
- [ ] 8.6 Implement retry of pending write-backs only and verify a retried line updates the `.dtl` without re-rendering audio

## 9. Shell behavior

- [ ] 9.1 Implement the five-region layout with draggable dividers and verify region sizes persist across restart
- [ ] 9.2 Implement per-line timeline show/hide and height persistence and verify the state survives reopen
- [ ] 9.3 Implement cross-region drag with rejection reasons for silent sources and verify no clip is created for a block without takes
- [ ] 9.4 Implement workspace state persistence (project, section, panel visibility) and verify restore on launch

## 10. End-to-end verification

- [ ] 10.1 Run the vertical slice against the sample project: push two lines, create blocks, generate with one provider, place clips, export, and confirm the `.dtl` voice events point at the exported files
- [ ] 10.2 Verify a restart in the middle of the slice (during generation and during export) leaves no corrupted document and no lost take
- [ ] 10.3 Run `openspec validate bootstrap-voice-workspace --strict` and verify the change validates cleanly

# dialogic-voice-partner

Voice production companion for [Dialogic](https://github.com/dialogic-godot/dialogic) (Godot 4.5+).

Status: **framework in progress**. Design is captured in
[`openspec/changes/bootstrap-voice-workspace/`](openspec/changes/bootstrap-voice-workspace/).

## Stack

Deliberately small and readable:

| Layer | Choice |
|---|---|
| Desktop shell | Electron + electron-vite |
| UI | React 19 + TypeScript, function components, plain CSS, no router / state / UI library |
| Local service | Python 3.11+ / FastAPI + uvicorn |
| Storage | JSON documents on disk (no database) |
| Audio | ffmpeg via the service, WebAudio in the renderer |
| Godot side | GDScript editor plugin, local HTTP endpoint for write-back |

## Requirements

- Node.js 20.19+ (verified on 24.12)
- Python 3.11+ (verified on 3.13)
- [uv](https://docs.astral.sh/uv/) for the service environment

## Run

```powershell
npm install
npm run service:install   # uv sync for service/
npm run dev               # Electron window + managed service
```

The service listens on `127.0.0.1:3900`; the renderer calls `/api/...`,
which the dev server proxies to the service (see `electron.vite.config.ts`).

### Environment notes

- **Do not keep this repository inside the desktop harness workspace directory.** That
  directory carries an ACL entry (`S-1-4-…`, written by the harness's Windows sandbox), and
  any Electron binary started from below it crashes during `app.whenReady()`
  (`0xC0000005` / `0x80000003`). Keep the checkout in a plain directory outside it.
- Machine-specific paths and credentials belong in `.env.local` (git-ignored), never in
  tracked files.
- If your shell exports `ELECTRON_RUN_AS_NODE=1`, `npm run dev` clears it for the
  Electron child (see `scripts/dev.mjs`); otherwise Electron starts as plain Node and
  crashes on the first `require('electron')` API call.
- Browser-only fallback (no Electron window):

  ```powershell
  npm run dev:web   # service + Vite only; open http://localhost:5173
  ```

## Layout

```
src/main/            Electron main process (window + service supervisor)
src/preload/         contextBridge surface
src/renderer/        React UI
service/app/         FastAPI application
openspec/            change proposals, specs, design, tasks
```

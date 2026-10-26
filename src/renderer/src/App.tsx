import { useCallback, useEffect, useState } from 'react'
import { apiJson, sendJson, type HealthResponse } from './lib/api'
import { useResizable, usePaneOpen } from './lib/use-resizable'
import type {
  ActiveProject,
  BlockDocument,
  BlockSlot,
  LineDocument,
  ProviderInfo
} from './lib/api-types'

type ServiceState = 'starting' | 'ready' | 'failed' | 'stopped'

interface ServiceStatus {
  state: ServiceState
  detail: string
  port: number
  pid: number | null
}

const STATE_LABEL: Record<ServiceState, string> = {
  starting: 'Starting',
  ready: 'Ready',
  failed: 'Failed',
  stopped: 'Stopped'
}

function toMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : String(caught)
}

/** Move one array item to another index; used by the line drag and drop. */
function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

export default function App() {
  const [status, setStatus] = useState<ServiceStatus | null>(null)
  const [project, setProject] = useState<ActiveProject | null>(null)
  const [lines, setLines] = useState<LineDocument[]>([])
  const [blocks, setBlocks] = useState<BlockDocument[]>([])
  const [selectedLine, setSelectedLine] = useState<string | null>(null)
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [newProviderId, setNewProviderId] = useState('')
  const [newModelId, setNewModelId] = useState('')
  const [leftOpen, toggleLeft] = usePaneOpen('dvp.pane.left.open')
  const [rightOpen, toggleRight] = usePaneOpen('dvp.pane.right.open')
  const [bottomOpen, toggleBottom] = usePaneOpen('dvp.pane.workspace.open')
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const left = useResizable({
    storageKey: 'dvp.pane.left',
    axis: 'x',
    minimum: 200,
    initial: 240,
    maximum: 440
  })
  const right = useResizable({
    storageKey: 'dvp.pane.right',
    axis: 'x',
    invert: true,
    minimum: 280,
    initial: 380,
    maximum: 640
  })
  const bottom = useResizable({
    storageKey: 'dvp.pane.workspace',
    axis: 'y',
    invert: true,
    minimum: 120,
    initial: 180,
    maximum: 520
  })

  useEffect(() => {
    const bridge = window.voicepartner
    if (bridge) {
      let alive = true
      void bridge.getServiceStatus().then((next) => {
        if (alive) setStatus(next)
      })
      const unsubscribe = bridge.onServiceStatus((next) => {
        if (alive) setStatus(next)
      })
      return () => {
        alive = false
        unsubscribe()
      }
    }

    // Browser mode: no preload bridge, the Vite proxy reaches the service directly.
    let alive = true
    const check = (): void => {
      apiJson<HealthResponse>('/health')
        .then(() => {
          if (alive) {
            setStatus({ state: 'ready', detail: 'Browser mode (Vite proxy)', port: 3900, pid: null })
          }
        })
        .catch(() => {
          if (alive) {
            setStatus({ state: 'failed', detail: 'Service unreachable', port: 3900, pid: null })
          }
        })
    }
    check()
    const timer = setInterval(check, 2000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  const load = useCallback(async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const active = await apiJson<ActiveProject | null>('/projects/active')
      setProject(active)
      if (!active) {
        setLines([])
        setBlocks([])
        return
      }
      const [items, pool, registry] = await Promise.all([
        apiJson<LineDocument[]>('/lines'),
        apiJson<BlockDocument[]>('/blocks'),
        apiJson<ProviderInfo[]>('/providers')
      ])
      setLines(items)
      setBlocks(pool)
      setProviders(registry)
    } catch (caught) {
      setError(toMessage(caught))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /** Replace one block in the pool after a write, without reloading the project. */
  const applyBlock = (updated: BlockDocument): void => {
    setBlocks((previous) =>
      previous.map((block) => (block.id === updated.id ? updated : block))
    )
  }

  const switchSection = async (sectionId: string): Promise<void> => {
    setError(null)
    try {
      await sendJson('POST', `/projects/sections/${sectionId}/activate`)
      setSelectedLine(null)
      setSelectedBlock(null)
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const createBlock = async (): Promise<void> => {
    if (!selectedLine) return
    setError(null)
    try {
      const block = await sendJson<BlockDocument>('POST', '/blocks', {
        line_uuid: selectedLine
      })
      setSelectedBlock(block.id)
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const chosenProvider = providers.find((provider) => provider.id === newProviderId) ?? providers[0]
  const chosenModel =
    chosenProvider?.models.find((model) => model.id === newModelId) ?? chosenProvider?.models[0]

  const createSlot = async (): Promise<void> => {
    const current = blocks.find((block) => block.id === selectedBlock)
    if (!current || !chosenProvider || !chosenModel) return
    setError(null)
    try {
      const updated = await sendJson<BlockDocument>('POST', `/blocks/${current.id}/slots`, {
        provider: chosenProvider.id,
        model: chosenModel.id
      })
      applyBlock(updated)
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const dropLine = async (target: number): Promise<void> => {
    const from = dragIndex
    setDragIndex(null)
    setOverIndex(null)
    if (from === null || from === target) return

    const next = moveItem(lines, from, target)
    setLines(next)
    try {
      await sendJson<LineDocument[]>('PUT', '/lines/order', {
        uuids: next.map((line) => line.uuid)
      })
    } catch (caught) {
      setError(toMessage(caught))
      await load()
    }
  }

  const currentBlock = blocks.find((block) => block.id === selectedBlock) ?? null
  const currentLine = lines.find((line) => line.uuid === selectedLine) ?? null
  const sections = project?.project.sections ?? []

  return (
    <div className="app">
      <header className="topbar">
        <strong>Dialogic Voice Partner</strong>
        <span className={`badge badge-${status?.state ?? 'starting'}`}>
          {status ? STATE_LABEL[status.state] : 'Starting'}
        </span>
        <span className="detail">{status?.detail ?? 'Connecting…'}</span>

        <div className="pane-toggles">
          <button
            type="button"
            className={`toggle${leftOpen ? ' on' : ''}`}
            onClick={toggleLeft}
          >
            Project
          </button>
          <button
            type="button"
            className={`toggle${rightOpen ? ' on' : ''}`}
            onClick={toggleRight}
          >
            Blocks
          </button>
          <button
            type="button"
            className={`toggle${bottomOpen ? ' on' : ''}`}
            onClick={toggleBottom}
          >
            Workspace
          </button>
        </div>
      </header>

      <main className="layout">
        {leftOpen ? (
          <>
            <aside className="pane projects" style={{ width: left.size }}>
              <h2>Project</h2>
              {project ? (
                <div className="project-card">
                  <strong>{project.project.name}</strong>
                  <p className="muted">{project.root}</p>

                  <h3>Sections</h3>
                  {sections.length === 0 ? (
                    <p className="muted">No sections yet.</p>
                  ) : (
                    <ul className="section-list">
                      {[...sections]
                        .sort((a, b) => a.order - b.order)
                        .map((section) => (
                          <li key={section.id}>
                            <button
                              type="button"
                              className={`section-row${
                                section.id === project.project.current_section ? ' active' : ''
                              }`}
                              onClick={() => void switchSection(section.id)}
                            >
                              {section.name}
                              <span className="muted"> · {section.id}</span>
                            </button>
                          </li>
                        ))}
                    </ul>
                  )}
                </div>
              ) : (
                <p className="muted">
                  No active project. Create one through the API, then press Refresh.
                </p>
              )}

              <button
                className="button"
                type="button"
                onClick={() => void load()}
                disabled={loading}
              >
                {loading ? 'Loading…' : 'Refresh'}
              </button>

              {error ? <p className="error">{error}</p> : null}
            </aside>
            <div className="splitter col" {...left.separatorProps} />
          </>
        ) : null}

        <section className="pane lines">
          <h2>Lines ({lines.length})</h2>
          {lines.length === 0 ? (
            <p className="muted">No lines yet. Push voice lines from the Godot editor.</p>
          ) : (
            <ul className="line-list">
              {lines.map((line, index) => (
                <li
                  className={`line-row${line.uuid === selectedLine ? ' selected' : ''}${
                    dragIndex === index ? ' dragging' : ''
                  }${overIndex === index && dragIndex !== index ? ' drop-target' : ''}`}
                  key={line.uuid}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.effectAllowed = 'move'
                    setDragIndex(index)
                  }}
                  onDragOver={(event) => {
                    event.preventDefault()
                    event.dataTransfer.dropEffect = 'move'
                    if (overIndex !== index) setOverIndex(index)
                  }}
                  onDrop={(event) => {
                    event.preventDefault()
                    void dropLine(index)
                  }}
                  onDragEnd={() => {
                    setDragIndex(null)
                    setOverIndex(null)
                  }}
                  onClick={() => {
                    setSelectedLine(line.uuid)
                    setSelectedBlock(null)
                  }}
                >
                  <span className="line-speaker">
                    {line.character_name || line.character || 'Narrator'}
                  </span>
                  <span className="line-text">{line.text}</span>
                  <span className="line-blocks">
                    {blocks.filter((block) => block.links.lines.includes(line.uuid)).length} block(s)
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {rightOpen ? (
          <>
            <div className="splitter col" {...right.separatorProps} />
            <aside className="right" style={{ width: right.size }}>
              <div className="pane pool">
            <h2>Blocks ({blocks.length})</h2>
            {selectedLine ? (
              <p className="muted">
                Line selected: {(currentLine?.character_name || currentLine?.character || 'Narrator')}
                <button className="button small" type="button" onClick={() => void createBlock()}>
                  New block from this line
                </button>
              </p>
            ) : (
              <p className="muted">The pool is project wide. Select a line to create a block.</p>
            )}

            {blocks.length === 0 ? (
              <p className="muted">No blocks yet.</p>
            ) : (
              <ul className="block-list">
                {blocks.map((block) => (
                  <li
                    key={block.id}
                    className={`block-card${block.id === selectedBlock ? ' selected' : ''}`}
                    onClick={() => setSelectedBlock(block.id)}
                  >
                    <span className="block-title">{block.title}</span>
                    <span className="block-meta">
                      {Object.keys(block.slots).length} slot(s) · {block.takes.length} take(s)
                      {selectedLine && block.links.lines.includes(selectedLine) ? ' · linked' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="pane inspector">
            <h2>Inspector</h2>
            {currentBlock ? (
              <div className="block-detail">
                <p>
                  <strong>{currentBlock.title}</strong>
                </p>
                <p className="muted">{currentBlock.text}</p>

                <h3>Model slots</h3>
                {Object.entries(currentBlock.slots).length === 0 ? (
                  <p className="muted">No model slot yet. Add one below.</p>
                ) : (
                  Object.entries(currentBlock.slots).map(([key, slot]) => (
                    <SlotEditor
                      key={key}
                      block={currentBlock}
                      slotKey={key}
                      slot={slot}
                      onUpdated={applyBlock}
                      onError={(message) => setError(message)}
                    />
                  ))
                )}

                <div className="slot-form">
                  <select
                    value={chosenProvider?.id ?? ''}
                    onChange={(event) => {
                      setNewProviderId(event.target.value)
                      setNewModelId('')
                    }}
                  >
                    {providers.map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.label}
                      </option>
                    ))}
                  </select>
                  <select
                    value={chosenModel?.id ?? ''}
                    onChange={(event) => setNewModelId(event.target.value)}
                  >
                    {(chosenProvider?.models ?? []).map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.label}
                      </option>
                    ))}
                  </select>
                  <button className="button small" type="button" onClick={() => void createSlot()}>
                    Add slot
                  </button>
                </div>

                <h3>Takes ({currentBlock.takes.length})</h3>
                {currentBlock.takes.length === 0 ? (
                  <p className="muted">No takes yet. Generate one from a slot.</p>
                ) : (
                  <ul className="take-list">
                    {currentBlock.takes.map((take) => (
                      <li key={take.id} className="take-row">
                        <span className="take-meta">
                          {take.provider}/{take.model} ·{' '}
                          {take.duration_ms ? `${(take.duration_ms / 1000).toFixed(2)}s` : '—'}
                        </span>
                        <audio controls src={`/api/${take.asset}`} />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="muted">Select a block to edit its prompts.</p>
            )}
          </div>
        </aside>
          </>
        ) : null}
      </main>

      {bottomOpen ? (
        <>
          <div className="splitter row" {...bottom.separatorProps} />
          <footer className="pane workspace" style={{ height: bottom.size }}>
            <h2>Workspace</h2>
            <p className="muted">Waveform, in/out points and cutting tools land here.</p>
          </footer>
        </>
      ) : null}
    </div>
  )
}

interface SlotEditorProps {
  block: BlockDocument
  slotKey: string
  slot: BlockSlot
  onUpdated: (block: BlockDocument) => void
  onError: (message: string) => void
}

/** One provider/model slot: edit its prompt, convert it, or revert the last change. */
function SlotEditor({ block, slotKey, slot, onUpdated, onError }: SlotEditorProps) {
  const [draft, setDraft] = useState(slot.prompt)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setDraft(slot.prompt)
  }, [slot.prompt])

  const query = `?provider=${encodeURIComponent(slot.provider)}&model=${encodeURIComponent(slot.model)}`

  const run = async (call: () => Promise<BlockDocument>): Promise<void> => {
    setBusy(true)
    try {
      const updated = await call()
      onUpdated(updated)
      onError('')
    } catch (caught) {
      onError(toMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="slot-card">
      <div className="slot-head">
        <strong>{slotKey}</strong>
        {block.active_slot === slotKey ? <span className="tag">active</span> : null}
      </div>
      <textarea
        rows={3}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        disabled={busy}
      />
      <div className="slot-actions">
        <button
          className="button small"
          type="button"
          disabled={busy || draft === slot.prompt}
          onClick={() =>
            void run(() =>
              sendJson<BlockDocument>('PATCH', `/blocks/${block.id}/slots${query}`, {
                prompt: draft
              })
            )
          }
        >
          Save prompt
        </button>
        <button
          className="button small"
          type="button"
          disabled={busy}
          onClick={() =>
            void run(() => sendJson<BlockDocument>('POST', `/blocks/${block.id}/slots/convert${query}`))
          }
        >
          Convert for this model
        </button>
        <button
          className="button small"
          type="button"
          disabled={busy || slot.history.length === 0}
          onClick={() =>
            void run(() => sendJson<BlockDocument>('POST', `/blocks/${block.id}/slots/revert${query}`))
          }
        >
          Revert
        </button>
        <button
          className="button small primary"
          type="button"
          disabled={busy}
          onClick={() =>
            void run(() =>
              sendJson<BlockDocument>('POST', `/blocks/${block.id}/generate`, {
                provider: slot.provider,
                model: slot.model
              })
            )
          }
        >
          {busy ? 'Working…' : 'Generate take'}
        </button>
      </div>
    </div>
  )
}

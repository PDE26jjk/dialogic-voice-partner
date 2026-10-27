import { useCallback, useEffect, useState } from 'react'
import { apiJson, sendJson, type HealthResponse } from './lib/api'
import { useResizable, usePaneOpen } from './lib/use-resizable'
import LineTrack from './LineTrack'
import SectionWorkbench from './SectionWorkbench'
import type {
  ActiveProject,
  BlockDocument,
  BlockSlot,
  CharacterInfo,
  ExportResult,
  LineDocument,
  ProjectSettings,
  ProviderInfo,
  ProviderParam,
  ProviderVoice,
  Section,
  WorkspaceClip
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
  const [selectedLines, setSelectedLines] = useState<string[]>([])
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [characters, setCharacters] = useState<CharacterInfo[]>([])
  const [leftOpen, toggleLeft] = usePaneOpen('dvp.pane.left.open')
  const [rightOpen, toggleRight] = usePaneOpen('dvp.pane.right.open')
  const [bottomOpen, toggleBottom] = usePaneOpen('dvp.pane.workspace.open')
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const [reorderMode, setReorderMode] = useState(false)
  const [expandedLines, setExpandedLines] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem('dvp.expandedLines')
      return stored ? (JSON.parse(stored) as string[]) : []
    } catch {
      return []
    }
  })
  const [lineDraft, setLineDraft] = useState('')
  const [lineHeights, setLineHeights] = useState<Record<string, number>>(() => {
    try {
      const stored = localStorage.getItem('dvp.lineHeights')
      return stored ? (JSON.parse(stored) as Record<string, number>) : {}
    } catch {
      return {}
    }
  })
  const [clipInfo, setClipInfo] = useState<WorkspaceClip | null>(null)
  const [blockMenu, setBlockMenu] = useState<{ x: number; y: number; blockId: string } | null>(
    null
  )
  const [countdownDraft, setCountdownDraft] = useState('')
  const [exportRate, setExportRate] = useState('')
  const [exportDepth, setExportDepth] = useState('')
  const [exportChannels, setExportChannels] = useState('')
  const exportFormat = project?.project.export
  const exportRateValue = exportFormat?.sample_rate ?? 44100
  const exportDepthValue = exportFormat?.bit_depth ?? 16
  const exportChannelsValue = exportFormat?.channels ?? 1
  const [newCharacterId, setNewCharacterId] = useState('')
  const [newCharacterName, setNewCharacterName] = useState('')
  const [activeCharacterId, setActiveCharacterId] = useState<string | null>(null)
  const [blockView, setBlockView] = useState<'linked' | 'orphan' | 'all'>('all')
  const [blockTab, setBlockTab] = useState<'details' | 'takes'>('details')
  const [mainTab, setMainTab] = useState<'lines' | 'characters'>('lines')
  const [slotKey, setSlotKey] = useState<string | null>(null)
  const [maximized, setMaximized] = useState(false)
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
    initial: 300,
    maximum: 640
  })
  const inspector = useResizable({
    storageKey: 'dvp.pane.inspector',
    axis: 'y',
    invert: true,
    minimum: 180,
    initial: 320,
    maximum: 900
  })

  const bridge = window.voicepartner

  useEffect(() => {
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
      const [items, pool, registry, roles] = await Promise.all([
        apiJson<LineDocument[]>('/lines'),
        apiJson<BlockDocument[]>('/blocks'),
        apiJson<ProviderInfo[]>('/providers'),
        apiJson<CharacterInfo[]>('/characters')
      ])
      setLines(items)
      setBlocks(pool)
      setProviders(registry)
      setCharacters(roles)
    } catch (caught) {
      setError(toMessage(caught))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem('dvp.lineHeights', JSON.stringify(lineHeights))
    } catch {
      // Non-critical.
    }
  }, [lineHeights])

  useEffect(() => {
    try {
      localStorage.setItem('dvp.expandedLines', JSON.stringify(expandedLines))
    } catch {
      // Storage can be unavailable; expansion is a convenience, not state.
    }
  }, [expandedLines])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!bridge) return
    void bridge.isMaximized().then(setMaximized)
    return bridge.onMaximizedChange(setMaximized)
  }, [bridge])

  /** Replace one block in the pool after a write, without reloading the project. */
  const applyBlock = (updated: BlockDocument): void => {
    setBlocks((previous) =>
      previous.map((block) => (block.id === updated.id ? updated : block))
    )
  }

  const saveCharacterVoice = async (
    id: string,
    provider: string,
    voice: string
  ): Promise<void> => {
    setError(null)
    try {
      const updated = await sendJson<CharacterInfo>(
        'PUT',
        `/characters/${encodeURIComponent(id)}/voice`,
        { provider, voice }
      )
      setCharacters((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      )
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const createCharacter = async (): Promise<void> => {
    const id = newCharacterId.trim()
    const name = newCharacterName.trim() || id
    if (!id) return
    setError(null)
    try {
      const created = await sendJson<CharacterInfo>('POST', '/characters', { id, name })
      setCharacters((current) => [...current, created])
      setNewCharacterId('')
      setNewCharacterName('')
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const updateCharacter = async (
    id: string,
    patch: { id?: string; name?: string }
  ): Promise<void> => {
    setError(null)
    try {
      const updated = await sendJson<CharacterInfo>(
        'PATCH',
        `/characters/${encodeURIComponent(id)}`,
        patch
      )
      setCharacters((current) =>
        current.map((item) => (item.id === id || item.id === updated.id ? updated : item))
      )
      setActiveCharacterId(updated.id)
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const resetCharacterVoice = async (id: string): Promise<void> => {
    setError(null)
    try {
      await sendJson('DELETE', `/characters/${encodeURIComponent(id)}/voice`)
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const deleteCharacter = async (id: string): Promise<void> => {
    setError(null)
    try {
      await sendJson('DELETE', `/characters/${encodeURIComponent(id)}`)
      setCharacters((current) => current.filter((item) => item.id !== id))
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const moveSection = async (sectionId: string, delta: number): Promise<void> => {
    const ordered = [...sections].sort((a, b) => a.order - b.order)
    const index = ordered.findIndex((section) => section.id === sectionId)
    const target = index + delta
    if (index < 0 || target < 0 || target >= ordered.length) return
    const next = [...ordered]
    const [moved] = next.splice(index, 1)
    next.splice(target, 0, moved)
    setError(null)
    try {
      const saved = await sendJson<Section[]>(
        'PUT',
        '/projects/sections/order',
        { ids: next.map((section) => section.id) }
      )
      setProject((current) =>
        current ? { ...current, project: { ...current.project, sections: saved } } : current
      )
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const restartService = async (): Promise<void> => {
    await window.voicepartner?.restartService()
    await load()
  }

  const switchSection = async (sectionId: string): Promise<void> => {
    setError(null)
    try {
      await sendJson('POST', `/projects/sections/${sectionId}/activate`)
      setSelectedLines([])
      setSelectedBlock(null)
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const createBlock = async (): Promise<void> => {
    if (selectedLines.length === 0) return
    setError(null)
    try {
      // Several selected lines become one block whose prompt joins their text.
      const block = await sendJson<BlockDocument>('POST', '/blocks', {
        line_uuids: selectedLines
      })
      setSelectedBlock(block.id)
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }


  /** A provider is what the UI calls a model; its first model is used internally. */
  const selectModel = async (providerId: string): Promise<void> => {
    if (!currentBlock) return
    const provider = providers.find((item) => item.id === providerId)
    const model = provider?.models[0]
    if (!provider || !model) return
    const key = `${provider.id}/${model.id}`
    setSlotKey(key)
    if (currentBlock.slots[key]) return
    setError(null)
    try {
      const updated = await sendJson<BlockDocument>('POST', `/blocks/${currentBlock.id}/slots`, {
        provider: provider.id,
        model: model.id
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
  const selectedLine = selectedLines.at(-1) ?? null
  const currentLine = lines.find((line) => line.uuid === selectedLine) ?? null

  const activeCharacter =
    characters.find((character) => character.id === activeCharacterId) ?? characters[0] ?? null
  const activeSlotKey =
    slotKey ?? currentBlock?.active_slot ?? Object.keys(currentBlock?.slots ?? {})[0] ?? null

  const activeSlot = currentBlock && activeSlotKey ? currentBlock.slots[activeSlotKey] : null
  const activeProvider =
    providers.find((provider) => provider.id === activeSlot?.provider) ??
    providers[0] ??
    null
  const activeModelDef =
    activeProvider?.models.find((model) => model.id === activeSlot?.model) ??
    activeProvider?.models[0] ??
    null
  const activeModelParams = activeModelDef?.params ?? []

  const visibleBlocks = blocks.filter((block) => {
    if (blockView === 'orphan') return block.links.lines.length === 0
    if (blockView === 'linked') {
      return selectedLine ? block.links.lines.includes(selectedLine) : false
    }
    return true
  })

  useEffect(() => {
    setSlotKey(currentBlock?.active_slot ?? Object.keys(currentBlock?.slots ?? {})[0] ?? null)
    setBlockTab('details')
  }, [currentBlock?.id])
  const sections = project?.project.sections ?? []

  const exportLine = async (uuid: string): Promise<void> => {
    setError(null)
    try {
      const result = await sendJson<ExportResult>('POST', `/lines/${uuid}/export`)
      if (!result.ok) {
        setError(result.error ?? 'Export failed')
      } else if (!result.writeback_ok) {
        setError(
          `Audio exported, but the Godot editor is not reachable: ${result.writeback_error ?? ''}`
        )
      }
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const exportAll = async (): Promise<void> => {
    setError(null)
    try {
      const results = await sendJson<ExportResult[]>('POST', '/export', {
        uuids: lines.map((line) => line.uuid)
      })
      const failed = results.filter((result) => !result.ok)
      if (failed.length > 0) {
        setError(
          `${failed.length}/${results.length} line(s) failed: ${failed[0].error ?? 'unknown error'}`
        )
      }
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const saveLineText = async (): Promise<void> => {
    if (!currentLine) return
    setError(null)
    try {
      const saved = await sendJson<LineDocument>('PATCH', `/lines/${currentLine.uuid}`, {
        text: lineDraft
      })
      setLines((current) =>
        current.map((item) => (item.uuid === saved.uuid ? saved : item))
      )
    } catch (caught) {
      setError(toMessage(caught))
    }
  }


  const setLineCharacter = async (
    line: LineDocument,
    characterId: string
  ): Promise<void> => {
    const character = characters.find((item) => item.id === characterId)
    setError(null)
    try {
      const saved = await sendJson<LineDocument>('PATCH', `/lines/${line.uuid}`, {
        character: characterId,
        character_name: character?.name ?? characterId
      })
      setLines((current) =>
        current.map((item) => (item.uuid === saved.uuid ? saved : item))
      )
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const updateBlockField = async (
    id: string,
    patch: Record<string, unknown>
  ): Promise<void> => {
    setError(null)
    try {
      const updated = await sendJson<BlockDocument>('PATCH', `/blocks/${id}`, patch)
      applyBlock(updated)
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const activateTake = async (takeId: string): Promise<void> => {
    if (!currentBlock) return
    setError(null)
    try {
      const updated = await sendJson<BlockDocument>('PATCH', `/blocks/${currentBlock.id}`, {
        active_take: takeId
      })
      applyBlock(updated)
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  /** Append a block's active take to the currently selected line. */
  const appendBlockToLine = async (block: BlockDocument): Promise<void> => {
    if (!currentLine) {
      setError('Select a line first.')
      return
    }
    const take =
      block.takes.find((item) => item.id === block.active_take) ?? block.takes.at(-1)
    if (!take) {
      setError('That block has no take yet.')
      return
    }
    const duration = Math.max(
      0,
      ...currentLine.track.clips.map((clip) => clip.start_ms + (clip.out_ms - clip.in_ms))
    )
    try {
      const saved = await sendJson<LineDocument>('PUT', `/lines/${currentLine.uuid}/track`, {
        clips: [
          ...currentLine.track.clips,
          {
            source: { kind: 'take', block: block.id, take: take.id },
            in_ms: 0,
            out_ms: take.duration_ms ?? 1000,
            start_ms: duration
          }
        ]
      })
      setLines((current) =>
        current.map((item) => (item.uuid === saved.uuid ? saved : item))
      )
      setExpandedLines((current) =>
        current.includes(saved.uuid) ? current : [...current, saved.uuid]
      )
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  useEffect(() => {
    setLineDraft(currentLine?.text ?? '')
  }, [currentLine?.uuid, currentLine?.text])

  useEffect(() => {
    setCountdownDraft(String(project?.project.recording_countdown_ms ?? 2000))
  }, [project?.project.recording_countdown_ms])

  useEffect(() => {
    const close = (): void => setBlockMenu(null)
    window.addEventListener('pointerdown', close)
    return () => window.removeEventListener('pointerdown', close)
  }, [])

  const saveExport = async (patch: {
    sample_rate?: number
    bit_depth?: number
    channels?: number
  }): Promise<void> => {
    setError(null)
    try {
      const saved = await sendJson<ProjectSettings>('PATCH', '/projects/settings', {
        export: { container: 'wav', sample_rate: Number(exportRate), bit_depth: Number(exportDepth), channels: Number(exportChannels), ...patch }
      })
      setProject((current) => (current ? { ...current, project: saved } : current))
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const uploadAsset = async (file: File): Promise<void> => {
    setError(null)
    try {
      const query = new URLSearchParams({ name: file.name })
      const response = await fetch(`/api/assets/upload?${query}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: await file.arrayBuffer()
      })
      if (!response.ok) throw new Error(`Upload failed: ${response.status}`)
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const retryPending = async (): Promise<void> => {
    setError(null)
    try {
      const pending = lines.filter((line) => line.export_status === 'pending_writeback')
      for (const line of pending) {
        await sendJson('POST', `/lines/${encodeURIComponent(line.uuid)}/writeback`)
      }
      await load()
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const duplicateBlock = async (id: string): Promise<void> => {
    setError(null)
    try {
      const copy = await sendJson<BlockDocument>('POST', `/blocks/${id}/duplicate`)
      setBlocks((current) => [...current, copy])
      setSelectedBlock(copy.id)
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const saveCountdown = async (): Promise<void> => {
    const value = Math.max(0, Math.min(10000, Number(countdownDraft) || 0))
    setError(null)
    try {
      const saved = await sendJson<ProjectSettings>('PATCH', '/projects/settings', {
        recording_countdown_ms: value
      })
      setProject((current) => (current ? { ...current, project: saved } : current))
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  return (
    <div className={`app${bridge ? ' desktop' : ''}`}>
      <header className="topbar">
        <div
          className="titlebar-drag"
          onDoubleClick={() => void window.voicepartner?.toggleMaximize()}
        >
          <strong>Dialogic Voice Partner</strong>
          <span className={`badge badge-${status?.state ?? 'starting'}`}>
            {status ? STATE_LABEL[status.state] : 'Starting'}
          </span>
          <span className="detail">{status?.detail ?? 'Connecting…'}</span>
        </div>

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

        {bridge ? (
          <div className="window-controls">
            <button type="button" title="Minimize" onClick={() => void bridge.minimize()}>
              ─
            </button>
            <button
              type="button"
              title={maximized ? 'Restore' : 'Maximize'}
              onClick={() => void bridge.toggleMaximize()}
            >
              {maximized ? '❐' : '□'}
            </button>
            <button
              type="button"
              className="close"
              title="Close"
              onClick={() => void bridge.close()}
            >
              ✕
            </button>
          </div>
        ) : null}
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
                            <div className="section-line">
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
                              <button
                                className="icon-button"
                                type="button"
                                title="Move up"
                                onClick={() => void moveSection(section.id, -1)}
                              >
                                ↑
                              </button>
                              <button
                                className="icon-button"
                                type="button"
                                title="Move down"
                                onClick={() => void moveSection(section.id, 1)}
                              >
                                ↓
                              </button>
                            </div>
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

              <h3>Settings</h3>
              <label className="setting">
                <span className="muted">Record countdown (ms)</span>
                <input
                  type="number"
                  min={0}
                  max={10000}
                  step={500}
                  value={countdownDraft}
                  onChange={(event) => setCountdownDraft(event.target.value)}
                  onBlur={() => void saveCountdown()}
                />
              </label>

              <label className="setting">
                <span className="muted">Export sample rate</span>
                <select value={exportRate || String(exportRateValue)} onChange={(event) => {
                    setExportRate(event.target.value)
                    void saveExport({ sample_rate: Number(event.target.value) })
                  }}>
                  <option value="22050">22050</option>
                  <option value="44100">44100</option>
                  <option value="48000">48000</option>
                </select>
              </label>
              <label className="setting">
                <span className="muted">Export bit depth</span>
                <select value={exportDepth || String(exportDepthValue)} onChange={(event) => {
                    setExportDepth(event.target.value)
                    void saveExport({ bit_depth: Number(event.target.value) })
                  }}>
                  <option value="8">8-bit</option>
                  <option value="16">16-bit</option>
                  <option value="24">24-bit</option>
                </select>
              </label>
              <label className="setting">
                <span className="muted">Export channels</span>
                <select value={exportChannels || String(exportChannelsValue)} onChange={(event) => {
                    setExportChannels(event.target.value)
                    void saveExport({ channels: Number(event.target.value) })
                  }}>
                  <option value="1">Mono</option>
                  <option value="2">Stereo</option>
                </select>
              </label>

              <label className="setting">
                <span className="muted">Upload asset</span>
                <input
                  type="file"
                  accept="audio/*"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void uploadAsset(file)
                    event.target.value = ''
                  }}
                />
              </label>

              <button className="button" type="button" onClick={() => void retryPending()}>
                Retry pending writes
              </button>

              <button
                className="button"
                type="button"
                onClick={() => void restartService()}
                disabled={!bridge}
              >
                Restart service
              </button>

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
          <div className="main-tabs">
            <button
              type="button"
              className={`tab${mainTab === 'lines' ? ' on' : ''}`}
              onClick={() => setMainTab('lines')}
            >
              Lines ({lines.length})
            </button>
            <button
              type="button"
              className={`tab${mainTab === 'characters' ? ' on' : ''}`}
              onClick={() => setMainTab('characters')}
            >
              Characters ({characters.length})
            </button>
          </div>

          {mainTab === 'characters' ? (
            <div className="characters-page">
              {characters.length === 0 ? (
                <p className="muted">No characters in this project yet.</p>
              ) : (
                <div className="character-picker">
                  <select
                    value={activeCharacter?.id ?? ''}
                    onChange={(event) => setActiveCharacterId(event.target.value)}
                  >
                    {characters.map((character) => (
                      <option key={character.id} value={character.id}>
                        {character.name} ({character.lines} line(s))
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {activeCharacter ? (
                <div className="character-detail wide" key={activeCharacter.id}>
                  <label className="field">
                    <span className="muted">ID (pushed by Dialogic)</span>
                    <input
                      defaultValue={activeCharacter.id}
                      key={`id-${activeCharacter.id}`}
                      onBlur={(event) => {
                        const next = event.target.value.trim()
                        if (next && next !== activeCharacter.id) {
                          void updateCharacter(activeCharacter.id, { id: next })
                        }
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="muted">Display name</span>
                    <input
                      defaultValue={activeCharacter.name}
                      key={`name-${activeCharacter.id}`}
                      onBlur={(event) => {
                        const next = event.target.value.trim()
                        if (next && next !== activeCharacter.name) {
                          void updateCharacter(activeCharacter.id, { name: next })
                        }
                      }}
                    />
                  </label>
                  <label className="field">
                    <span className="muted">Provider</span>
                    <select
                      value={activeCharacter.provider ?? providers[0]?.id ?? ''}
                      onChange={(event) => {
                        const next = providers.find(
                          (provider) => provider.id === event.target.value
                        )
                        const voice = next?.voices[0]
                        if (next && voice) {
                          void saveCharacterVoice(activeCharacter.id, next.id, voice.id)
                        }
                      }}
                    >
                      {providers.map((provider) => (
                        <option key={provider.id} value={provider.id}>
                          {provider.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="muted">Voice</span>
                    <select
                      value={activeCharacter.voice ?? ''}
                      onChange={(event) => {
                        const provider =
                          providers.find((item) => item.id === activeCharacter.provider) ??
                          providers[0]
                        if (provider) {
                          void saveCharacterVoice(
                            activeCharacter.id,
                            provider.id,
                            event.target.value
                          )
                        }
                      }}
                    >
                      {(
                        providers.find(
                          (provider) => provider.id === activeCharacter.provider
                        )?.voices ??
                        providers[0]?.voices ??
                        []
                      ).map((voice) => (
                        <option key={voice.id} value={voice.id}>
                          {voice.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="slot-actions">
                    <button
                      className="button small"
                      type="button"
                      onClick={() => void resetCharacterVoice(activeCharacter.id)}
                    >
                      Reset voice
                    </button>
                    <button
                      className="button small"
                      type="button"
                      onClick={() => void deleteCharacter(activeCharacter.id)}
                    >
                      Delete character
                    </button>
                  </div>
                </div>
              ) : null}

              <div className="character-new">
                <input
                  placeholder="id"
                  value={newCharacterId}
                  onChange={(event) => setNewCharacterId(event.target.value)}
                />
                <input
                  placeholder="name"
                  value={newCharacterName}
                  onChange={(event) => setNewCharacterName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void createCharacter()
                  }}
                />
                <button
                  className="button small"
                  type="button"
                  disabled={!newCharacterId.trim()}
                  onClick={() => void createCharacter()}
                >
                  Add
                </button>
              </div>
            </div>
          ) : (
            <>
          <div className="lines-head">
            <h2>Lines ({lines.length})</h2>
            <div className="head-actions">
              <button className="toggle" type="button" onClick={() => void exportAll()}>
                Export all
              </button>
              <button
                type="button"
                className={`toggle${reorderMode ? ' on' : ''}`}
                onClick={() => setReorderMode((enabled) => !enabled)}
                title="Show drag handles to reorder lines"
              >
                Reorder
              </button>
            </div>
          </div>
          {lines.length === 0 ? (
            <p className="muted">No lines yet. Push voice lines from the Godot editor.</p>
          ) : (
            <ul className="line-list">
              {lines.map((line, index) => (
                <li className="line-wrapper" key={line.uuid}>
                  <div
                    className={`line-row${selectedLines.includes(line.uuid) ? ' selected' : ''}${
                      dragIndex === index ? ' dragging' : ''
                    }${overIndex === index && dragIndex !== index ? ' drop-target' : ''}`}
                    draggable={reorderMode}
                    onDragStart={(event) => {
                      if (!reorderMode) return
                      event.dataTransfer.effectAllowed = 'move'
                      setDragIndex(index)
                    }}
                    onDragOver={(event) => {
                      if (dragIndex === null) return
                      event.preventDefault()
                      event.dataTransfer.dropEffect = 'move'
                      if (overIndex !== index) setOverIndex(index)
                    }}
                    onDrop={(event) => {
                      if (dragIndex === null) return
                      event.preventDefault()
                      void dropLine(index)
                    }}
                    onDragEnd={() => {
                      setDragIndex(null)
                      setOverIndex(null)
                    }}
                    onClick={(event) => {
                      setSelectedBlock(null)
                      setClipInfo(null)
                      if (event.ctrlKey || event.metaKey || event.shiftKey) {
                        setSelectedLines((current) =>
                          current.includes(line.uuid)
                            ? current.filter((uuid) => uuid !== line.uuid)
                            : [...current, line.uuid]
                        )
                      } else {
                        setSelectedLines([line.uuid])
                      }
                    }}
                  >
                    {reorderMode ? <span className="drag-handle">⠿</span> : null}
                    <button
                      className="line-expand"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        setExpandedLines((current) =>
                          current.includes(line.uuid)
                            ? current.filter((uuid) => uuid !== line.uuid)
                            : [...current, line.uuid]
                        )
                      }}
                    >
                      {expandedLines.includes(line.uuid) ? '▾' : '▸'}
                    </button>
                    <span className="line-speaker">
                      {line.character_name || line.character || 'Narrator'}
                    </span>
                    <span className="line-text">{line.text}</span>
                    <span className="line-blocks">
                      {line.track.clips.length} clip(s) ·{' '}
                      {blocks.filter((block) => block.links.lines.includes(line.uuid)).length}{' '}
                      block(s)
                    </span>
                  </div>

                  {expandedLines.includes(line.uuid) ? (
                    <LineTrack
                      line={line}
                      blocks={blocks}
                      countdownMs={project?.project.recording_countdown_ms ?? 2000}
                      height={lineHeights[line.uuid] ?? 150}
                      onResize={(next) =>
                        setLineHeights((current) => ({ ...current, [line.uuid]: next }))
                      }
                      onSaved={(saved) => {
                        setLines((current) =>
                          current.map((item) => (item.uuid === saved.uuid ? saved : item))
                        )
                      }}
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          )}
            </>
          )}
        </section>

        {rightOpen ? (
          <>
            <div className="splitter col" {...right.separatorProps} />
            <aside className="right" style={{ width: right.size }}>
              <div className="pane pool">
            <h2>Blocks ({visibleBlocks.length})</h2>
            <div className="view-switch" role="group" aria-label="Block filter">
              {(
                [
                  ['linked', 'Linked'],
                  ['orphan', 'Orphans'],
                  ['all', 'All']
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`toggle${blockView === value ? ' on' : ''}`}
                  onClick={() => setBlockView(value)}
                >
                  {label}
                </button>
              ))}
            </div>

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

            {visibleBlocks.length === 0 ? (
              <p className="muted">
                {blockView === 'linked'
                  ? selectedLine
                    ? 'No blocks linked to this line.'
                    : 'Select a line to see the blocks linked to it.'
                  : blockView === 'orphan'
                    ? 'No orphan blocks.'
                    : 'No blocks yet.'}
              </p>
            ) : (
              <ul className="block-list">
                {visibleBlocks.map((block) => (
                  <li
                    key={block.id}
                    className={`block-card${block.id === selectedBlock ? ' selected' : ''}`}
                    draggable
                    title="Drag onto the workbench"
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = 'copy'
                      event.dataTransfer.setData('application/x-dvp-block', block.id)
                    }}
                    onContextMenu={(event) => {
                      event.preventDefault()
                      setBlockMenu({
                        x: Math.min(event.clientX, window.innerWidth - 190),
                        y: Math.min(event.clientY, window.innerHeight - 120),
                        blockId: block.id
                      })
                    }}
                    onClick={() => {
                      setSelectedBlock(block.id)
                      setClipInfo(null)
                    }}
                  >
                    <span className="block-title">{block.title}</span>
                    <span className="block-meta">
                      {Object.keys(block.slots).length} slot(s) · {block.takes.length} take(s)
                      {block.links.lines.length === 0 ? ' · orphan' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="splitter row" {...inspector.separatorProps} />

          <div className="pane inspector" style={{ height: inspector.size }}>
            <h2>Inspector</h2>
            {currentBlock ? (
              <div className="block-detail">
                <div className="tab-row">
                  <button
                    type="button"
                    className={`tab${blockTab === 'details' ? ' on' : ''}`}
                    onClick={() => setBlockTab('details')}
                  >
                    Details
                  </button>
                  <button
                    type="button"
                    className={`tab${blockTab === 'takes' ? ' on' : ''}`}
                    onClick={() => setBlockTab('takes')}
                  >
                    Takes ({currentBlock.takes.length})
                  </button>
                </div>

                {blockTab === 'details' ? (
                  <>
                    <input
                      className="block-title-input"
                      defaultValue={currentBlock.title}
                      key={`title-${currentBlock.id}`}
                      onBlur={(event) => {
                        const next = event.target.value.trim()
                        if (next && next !== currentBlock.title) {
                          void updateBlockField(currentBlock.id, { title: next })
                        }
                      }}
                    />
                    <label className="field">
                      <span className="muted">Character</span>
                      <select
                        value={currentBlock.character}
                        onChange={(event) => {
                          const character = characters.find(
                            (item) => item.id === event.target.value
                          )
                          void updateBlockField(currentBlock.id, {
                            character: event.target.value,
                            character_name: character?.name ?? event.target.value
                          })
                        }}
                      >
                        {!characters.some((item) => item.id === currentBlock.character) ? (
                          <option value={currentBlock.character}>
                            {currentBlock.character || 'none'}
                          </option>
                        ) : null}
                        {characters.map((character) => (
                          <option key={character.id} value={character.id}>
                            {character.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="muted">{currentBlock.text}</p>
                    <div className="slot-actions">
                      <button
                        className="button small"
                        type="button"
                        onClick={() => void duplicateBlock(currentBlock.id)}
                      >
                        Duplicate block
                      </button>
                    </div>

                    <h3>Model</h3>
                    <select
                      className="slot-select"
                      value={activeProvider?.id ?? ''}
                      onChange={(event) => void selectModel(event.target.value)}
                    >
                      {providers.map((provider) => (
                        <option key={provider.id} value={provider.id}>
                          {provider.label}
                        </option>
                      ))}
                    </select>
                    {activeSlotKey && currentBlock.slots[activeSlotKey] ? (
                      <SlotEditor
                        key={activeSlotKey}
                        block={currentBlock}
                        slot={currentBlock.slots[activeSlotKey]}
                        providerLabel={activeProvider?.label ?? activeSlotKey}
                        voices={activeProvider?.voices ?? []}
                        paramDefs={activeModelParams}
                        onUpdated={applyBlock}
                        onError={(message) => setError(message)}
                      />
                    ) : (
                      <p className="muted">Selecting a model creates its slot.</p>
                    )}
                  </>
                ) : currentBlock.takes.length === 0 ? (
                  <p className="muted">No takes yet. Generate one from a slot.</p>
                ) : (
                  <ul className="take-list">
                    {currentBlock.takes.map((take) => (
                      <li
                        key={take.id}
                        className="take-row"
                        draggable
                        title="Drag onto a line timeline"
                        onDragStart={(event) => {
                          event.dataTransfer.effectAllowed = 'copy'
                          event.dataTransfer.setData(
                            'application/x-dvp-take',
                            JSON.stringify({ block: currentBlock.id, take: take.id })
                          )
                        }}
                      >
                        <span className="take-meta">
                          {take.provider}/{take.model} ·{' '}
                          {take.duration_ms ? `${(take.duration_ms / 1000).toFixed(2)}s` : '—'}
                          {take.id === currentBlock.active_take ? ' · active' : ''}
                        </span>
                        <audio controls src={`/api/${take.asset}`} />
                        <button
                          className="button small"
                          type="button"
                          disabled={take.id === currentBlock.active_take}
                          onClick={() => {
                            void activateTake(take.id)
                            setBlockTab('details')
                          }}
                        >
                          {take.id === currentBlock.active_take ? 'Active' : 'Use'}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : clipInfo ? (
              <div className="block-detail">
                <p>
                  <strong>{clipInfo.name}</strong>
                </p>
                <p className="muted">
                  start {clipInfo.start_ms}ms · in {clipInfo.in_ms}ms · out {clipInfo.out_ms}ms
                </p>
                <p className="muted">
                  source: {clipInfo.source.kind === 'take' ? clipInfo.source.take : clipInfo.source.asset}
                </p>
              </div>
            ) : currentLine ? (
              <div className="block-detail">
                <p className="muted">{currentLine.dtl}</p>
                <label className="field">
                  <span className="muted">Character</span>
                  <select
                    value={currentLine.character}
                    onChange={(event) =>
                      void setLineCharacter(currentLine, event.target.value)
                    }
                  >
                    {!characters.some((item) => item.id === currentLine.character) ? (
                      <option value={currentLine.character}>
                        {currentLine.character || 'none'}
                      </option>
                    ) : null}
                    {characters.map((character) => (
                      <option key={character.id} value={character.id}>
                        {character.name}
                      </option>
                    ))}
                  </select>
                </label>
                <h3>Text</h3>
                <textarea
                  rows={4}
                  value={lineDraft}
                  onChange={(event) => setLineDraft(event.target.value)}
                  onBlur={() => {
                    if (lineDraft !== currentLine.text) void saveLineText()
                  }}
                />
                <div className="slot-actions">
                  <button
                    className="button small primary"
                    type="button"
                    disabled={currentLine.track.clips.length === 0}
                    onClick={() => void exportLine(currentLine.uuid)}
                  >
                    Export to Godot
                  </button>
                </div>
                {currentLine.export_path ? (
                  <p className="muted export-path">
                    {currentLine.export_status === 'pending_writeback' ? 'Pending write-back' : 'Exported'}:{' '}
                    {currentLine.export_path}
                  </p>
                ) : null}
                <h3>Clips ({currentLine.track.clips.length})</h3>
              </div>
            ) : (
              <p className="muted">Select a block, a line, or a clip.</p>
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
            {project ? (
              <SectionWorkbench
                section={project.project.current_section ?? 'inbox'}
                root={project.root}
                lines={lines}
                blocks={blocks}
                selectedLine={selectedLine}
                countdownMs={project.project.recording_countdown_ms ?? 2000}
                onLineSaved={(saved) => {
                  setLines((current) =>
                    current.map((item) => (item.uuid === saved.uuid ? saved : item))
                  )
                }}
                onInserted={(lineUuid) =>
                  setExpandedLines((current) =>
                    current.includes(lineUuid) ? current : [...current, lineUuid]
                  )
                }
                onClipSelected={setClipInfo}
              />
            ) : (
              <p className="muted">Open a project to use the section workbench.</p>
            )}
          </footer>
        </>
      ) : null}

      {blockMenu ? (
        <div
          className="context-menu"
          style={{ left: blockMenu.x, top: blockMenu.y }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => {
              const block = blocks.find((item) => item.id === blockMenu.blockId)
              if (block) void appendBlockToLine(block)
              setBlockMenu(null)
            }}
          >
            Append to selected line
          </button>
          <button
            type="button"
            onClick={() => {
              setSelectedBlock(blockMenu.blockId)
              setBlockMenu(null)
            }}
          >
            Edit block
          </button>
        </div>
      ) : null}
    </div>
  )
}

interface SlotEditorProps {
  block: BlockDocument
  slot: BlockSlot
  providerLabel: string
  voices: ProviderVoice[]
  paramDefs: ProviderParam[]
  onUpdated: (block: BlockDocument) => void
  onError: (message: string) => void
}

/** One provider/model slot: edit its prompt, convert it, or revert the last change. */
function SlotEditor({
  block,
  slot,
  providerLabel,
  voices,
  paramDefs,
  onUpdated,
  onError
}: SlotEditorProps) {
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
        <strong>{providerLabel}</strong>
      </div>
      <textarea
        rows={4}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          if (draft !== slot.prompt && !busy) {
            void run(() =>
              sendJson<BlockDocument>('PATCH', `/blocks/${block.id}/slots${query}`, {
                prompt: draft
              })
            )
          }
        }}
        disabled={busy}
      />
      {voices.length > 0 ? (
        <div className="param">
          <span className="muted">Voice</span>
          <div className="param-row">
            <select
              value={slot.voice ?? ''}
              disabled={busy}
              onChange={(event) => {
                const value = event.target.value
                void run(() =>
                  sendJson<BlockDocument>('PATCH', `/blocks/${block.id}/slots${query}`, {
                    voice: value
                  })
                )
              }}
            >
              <option value="">(character default)</option>
              {voices.map((voice) => (
                <option key={voice.id} value={voice.id}>
                  {voice.label}
                </option>
              ))}
            </select>
            <button
              className="revert"
              type="button"
              title="Reset to the character mapping"
              disabled={busy || !slot.voice}
              onClick={() =>
                void run(() =>
                  sendJson<BlockDocument>('PATCH', `/blocks/${block.id}/slots${query}`, {
                    voice: ''
                  })
                )
              }
            >
              ↺
            </button>
          </div>
        </div>
      ) : null}
      {paramDefs.length > 0 ? (
        <div className="param-grid">
          {paramDefs.map((param) => {
            const value = slot.params[param.id] ?? param.default
            return (
              <div key={param.id} className="param">
                <span className="muted">{param.label}</span>
                <div className="param-row">
                <input
                  type={param.type === 'number' ? 'number' : 'text'}
                  defaultValue={value === null || value === undefined ? '' : String(value)}
                  min={param.minimum ?? undefined}
                  max={param.maximum ?? undefined}
                  step={param.step ?? undefined}
                  disabled={busy}
                  onBlur={(event) => {
                    const parsed =
                      param.type === 'number' ? Number(event.target.value) : event.target.value
                    if (parsed === value) return
                    void run(() =>
                      sendJson<BlockDocument>('PATCH', `/blocks/${block.id}/slots${query}`, {
                        params: { ...slot.params, [param.id]: parsed }
                      })
                    )
                  }}
                />
                <button
                  className="revert"
                  type="button"
                  title={`Reset to ${String(param.default)}`}
                  disabled={busy || value === param.default}
                  onClick={() =>
                    void run(() =>
                      sendJson<BlockDocument>('PATCH', `/blocks/${block.id}/slots${query}`, {
                        params: { ...slot.params, [param.id]: param.default }
                      })
                    )
                  }
                >
                  ↺
                </button>
                </div>
              </div>
            )
          })}
        </div>
      ) : null}
      <div className="slot-actions">
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

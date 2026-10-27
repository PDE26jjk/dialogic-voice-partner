import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { apiJson, sendJson } from './lib/api'
import { useClipsPlayback } from './lib/use-clips-playback'
import { drawClipWave, useTakeAudio } from './lib/use-take-audio'
import type {
  AssetInfo,
  BlockDocument,
  Clip,
  LineDocument,
  WorkspaceClip,
  WorkspaceState,
  WorkspaceTrack
} from './lib/api-types'

const RULER_HEIGHT = 26
const LANE_HEIGHT = 64
const LANE_GAP = 1
const MIN_ZOOM = 8
const MAX_ZOOM = 1600
const MIN_CLIP_MS = 80
const HISTORY_LIMIT = 120
const FPS = 30

type Tool = 'select' | 'razor'

interface SectionWorkbenchProps {
  section: string
  root: string
  lines: LineDocument[]
  blocks: BlockDocument[]
  selectedLine: string | null
  countdownMs: number
  onLineSaved: (line: LineDocument) => void
  onInserted: (lineUuid: string) => void
  onClipSelected: (clip: WorkspaceClip | null) => void
}

interface ClipDrag {
  primary: string
  mode: 'move' | 'in' | 'out'
  startX: number
  startY: number
  originals: Array<{ clip: WorkspaceClip; lane: number }>
  moved: boolean
  /** Movement below this many pixels counts as a click, not a drag. */
  pastThreshold: boolean
  /** When set, a click without dragging collapses the selection to this clip. */
  collapseTo: string | null
  before: WorkspaceTrack[]
}

interface ContextMenu {
  x: number
  y: number
  lane: number
  clipId: string
}

function toMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : String(caught)
}

function newId(): string {
  return crypto.randomUUID().replace(/-/g, '').slice(0, 12)
}

function clipLength(clip: { in_ms: number; out_ms: number }): number {
  return Math.max(0, clip.out_ms - clip.in_ms)
}

function clipEnd(clip: { start_ms: number; in_ms: number; out_ms: number }): number {
  return clip.start_ms + clipLength(clip)
}

/** Cut a clip down to the selected in/out range, rebased to the range start. */
function sliceToRange(
  clip: WorkspaceClip,
  range: { in: number; out: number }
): WorkspaceClip | null {
  const start = Math.round(Math.max(clip.start_ms, range.in))
  const end = Math.round(Math.min(clipEnd(clip), range.out))
  if (end - start < MIN_CLIP_MS) return null
  return {
    ...clip,
    id: newId(),
    start_ms: Math.max(0, start - Math.round(range.in)),
    in_ms: Math.round(clip.in_ms + (start - clip.start_ms)),
    out_ms: Math.round(clip.in_ms + (end - clip.start_ms))
  }
}

function formatTimecode(ms: number): string {
  const safe = Math.max(0, ms)
  const minutes = Math.floor(safe / 60000)
  const seconds = Math.floor((safe % 60000) / 1000)
  const frames = Math.floor((safe % 1000) / (1000 / FPS))
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}:${String(frames).padStart(2, '0')}`
}

function clone(tracks: WorkspaceTrack[]): WorkspaceTrack[] {
  return structuredClone(tracks)
}

/**
 * Multitrack workbench for the current section.
 *
 * Lanes only stack audio: the mix is the sum of every clip. Trims belong to
 * clips, so moving a clip between lanes never changes what it contains.
 */
export default function SectionWorkbench({
  section,
  root,
  lines,
  blocks,
  selectedLine,
  countdownMs,
  onLineSaved,
  onInserted,
  onClipSelected
}: SectionWorkbenchProps) {
  const [tracks, setTracks] = useState<WorkspaceTrack[]>([])
  const [selectedClip, setSelectedClip] = useState<string | null>(null)
  const [selectedClips, setSelectedClips] = useState<string[]>([])
  const [snapEnabled, setSnapEnabled] = useState(true)
  const [selectedLane, setSelectedLane] = useState<number | null>(null)
  const [zoom, setZoom] = useState(80)
  const [tool, setTool] = useState<Tool>('select')
  const [range, setRange] = useState<{ in: number; out: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [menu, setMenu] = useState<ContextMenu | null>(null)
  const [recording, setRecording] = useState(false)
  const [counting, setCounting] = useState(0)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)

  const canvas = useRef<HTMLCanvasElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const panRef = useRef<{ x: number; y: number; left: number; top: number } | null>(null)
  const pendingScrollRef = useRef<number | null>(null)
  const headsRef = useRef<HTMLDivElement>(null)
  const ruler = useRef<HTMLCanvasElement>(null)
  const drag = useRef<ClipDrag | null>(null)
  const saving = useRef<Promise<void>>(Promise.resolve())
  const recorder = useRef<MediaRecorder | null>(null)
  const recordingStart = useRef(0)
  const recordingLane = useRef(0)
  const chunks = useRef<Blob[]>([])
  const tracksRef = useRef(tracks)
  const history = useRef<{ stack: WorkspaceTrack[][]; index: number }>({ stack: [], index: -1 })

  tracksRef.current = tracks

  const { assetFor, ensure, audioContext, buffers, peaks, version } = useTakeAudio(blocks)

  const allClips = tracks.flatMap((track) => track.clips)
  const totalMs = Math.max(12000, ...allClips.map((clip) => clip.start_ms + clipLength(clip) + 1000))
  const width = Math.ceil((totalMs / 1000) * zoom)
  const contentHeight = RULER_HEIGHT + Math.max(1, tracks.length) * (LANE_HEIGHT + LANE_GAP)

  const soloed = tracks.some((track) => track.solo)
  const audible = (
    soloed ? tracks.filter((track) => track.solo) : tracks.filter((track) => !track.muted)
  ).flatMap((track) => track.clips)

  const playbackEnd = range ? Math.min(range.out, totalMs) : totalMs
  const { playing, playhead, play, stop, seek } = useClipsPlayback({
    clips: audible as unknown as Clip[],
    totalMs: playbackEnd,
    assetFor,
    audioContext,
    buffers: buffers.current,
    load: ensure
  })

  const playheadRef = useRef(playhead)
  playheadRef.current = playhead

  const syncHistoryFlags = (): void => {
    setCanUndo(history.current.index > 0)
    setCanRedo(history.current.index < history.current.stack.length - 1)
  }

  /** Push a completed state; identical states never create an extra step. */
  const pushHistory = (snapshot: WorkspaceTrack[]): void => {
    const { stack, index } = history.current
    const current = stack[index]
    if (current && JSON.stringify(current) === JSON.stringify(snapshot)) return

    const trimmed = stack.slice(0, index + 1)
    trimmed.push(clone(snapshot))
    if (trimmed.length > HISTORY_LIMIT) trimmed.shift()
    history.current = { stack: trimmed, index: trimmed.length - 1 }
    syncHistoryFlags()
  }

  const saveWorkspace = (next: WorkspaceTrack[], nextSelected: string | null): void => {
    const query = new URLSearchParams({ root })
    saving.current = saving.current
      .then(() =>
        sendJson<WorkspaceState>('PUT', `/projects/${section}/workspace?${query}`, {
          section,
          tracks: next,
          selected_clip: nextSelected
        }).then(() => undefined)
      )
      .catch((caught) => setError(toMessage(caught)))
  }

  const applyTracks = (next: WorkspaceTrack[]): void => {
    tracksRef.current = next
    setTracks(next)
  }

  const commit = (
    next: WorkspaceTrack[],
    nextSelected: string | null = selectedClip,
    recordHistory = true
  ): void => {
    applyTracks(next)
    setSelectedClip(nextSelected)
    setError(null)
    // The stack holds states, so the new one becomes the current entry.
    if (recordHistory) pushHistory(next)
    saveWorkspace(next, nextSelected)
  }

  const undo = (): void => {
    const { stack, index } = history.current
    if (index <= 0) return
    const next = clone(stack[index - 1])
    history.current = { stack, index: index - 1 }
    syncHistoryFlags()
    applyTracks(next)
    saveWorkspace(next, selectedClip)
  }

  const redo = (): void => {
    const { stack, index } = history.current
    if (index >= stack.length - 1) return
    const next = clone(stack[index + 1])
    history.current = { stack, index: index + 1 }
    syncHistoryFlags()
    applyTracks(next)
    saveWorkspace(next, selectedClip)
  }

  const zoomRef = useRef(zoom)
  zoomRef.current = zoom

  // Wheel zooms the timeline around the pointer, like a DAW.
  useEffect(() => {
    const element = scrollRef.current
    if (!element) return

    const onWheel = (event: WheelEvent): void => {
      // Modifiers keep native behaviour (Shift + wheel scrolls horizontally).
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return
      event.preventDefault()
      const current = zoomRef.current
      const factor = event.deltaY < 0 ? 1.2 : 1 / 1.2
      const next = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(current * factor)))
      if (next === current) return

      const rect = element.getBoundingClientRect()
      const pointerX = event.clientX - rect.left + element.scrollLeft
      const atMs = (pointerX / current) * 1000
      // Apply the scroll offset in the same commit as the new zoom, otherwise the
      // layout paints once at the old offset and the view visibly jumps.
      pendingScrollRef.current = Math.max(0, (atMs / 1000) * next - (event.clientX - rect.left))
      setZoom(next)
    }

    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [])

  useLayoutEffect(() => {
    const pending = pendingScrollRef.current
    if (pending === null) return
    pendingScrollRef.current = null
    if (scrollRef.current) scrollRef.current.scrollLeft = pending
  }, [zoom])

  useEffect(() => {
    let alive = true
    void (async () => {
      try {
        const query = new URLSearchParams({ root })
        const state = await apiJson<WorkspaceState | null>(
          `/projects/${section}/workspace?${query}`
        )
        if (!alive) return
        const loaded = state?.tracks ?? []
        applyTracks(loaded)
        setSelectedClip(state?.selected_clip ?? null)
        history.current = { stack: [clone(loaded)], index: 0 }
        syncHistoryFlags()
      } catch (caught) {
        if (alive) setError(toMessage(caught))
      }
    })()
    return () => {
      alive = false
    }
  }, [section, root])

  useEffect(() => {
    apiJson<AssetInfo[]>('/assets').catch(() => undefined)
  }, [section])

  useEffect(() => {
    for (const clip of allClips) {
      const asset = assetFor(clip as unknown as Clip)
      if (asset) void ensure(asset)
    }
    // Decoding is cached per asset; the clip list changes on every edit.
  }, [allClips, assetFor, ensure])

  // Lane grid + clip waveforms.
  useEffect(() => {
    const element = canvas.current
    if (!element) return
    const context = element.getContext('2d')
    if (!context) return

    const dpr = window.devicePixelRatio || 1
    const lanesHeight = contentHeight - RULER_HEIGHT
    element.width = Math.round(width * dpr)
    element.height = Math.round(lanesHeight * dpr)
    element.style.width = `${width}px`
    element.style.height = `${lanesHeight}px`
    context.setTransform(dpr, 0, 0, dpr, 0, 0)
    context.clearRect(0, 0, width, lanesHeight)

    const styles = getComputedStyle(element)
    const border = styles.getPropertyValue('--border').trim() || '#2a2f3c'
    const muted = styles.getPropertyValue('--muted').trim() || '#8b93a7'

    context.strokeStyle = border
    context.lineWidth = 1
    context.beginPath()
    for (let second = 0; second * zoom <= width; second += 1) {
      const x = Math.round(second * zoom) + 0.5
      context.moveTo(x, 0)
      context.lineTo(x, lanesHeight)
    }
    context.stroke()

    context.beginPath()
    for (let lane = 0; lane <= tracks.length; lane += 1) {
      const y = Math.round(lane * (LANE_HEIGHT + LANE_GAP)) + 0.5
      context.moveTo(0, y)
      context.lineTo(width, y)
    }
    context.stroke()

    tracks.forEach((track, index) => {
      const top = index * (LANE_HEIGHT + LANE_GAP)
      if (index % 2 === 1) {
        context.fillStyle = 'rgba(255, 255, 255, 0.015)'
        context.fillRect(0, top, width, LANE_HEIGHT)
      }
      for (const clip of track.clips) {
        const data = peaks.current.get(assetFor(clip as unknown as Clip) ?? '')
        if (!data) continue
        context.save()
        context.translate(0, top)
        context.globalAlpha = track.muted ? 0.35 : 1
        drawClipWave(context, data, clip as unknown as Clip, zoom, LANE_HEIGHT, muted)
        context.restore()
      }
    })
    // `version` is read so a finished decode repaints every lane.
  }, [tracks, zoom, width, contentHeight, version, assetFor, peaks])

  // Ruler with timecode labels.
  useEffect(() => {
    const element = ruler.current
    if (!element) return
    const context = element.getContext('2d')
    if (!context) return

    const dpr = window.devicePixelRatio || 1
    element.width = Math.round(width * dpr)
    element.height = Math.round(RULER_HEIGHT * dpr)
    element.style.width = `${width}px`
    element.style.height = `${RULER_HEIGHT}px`
    context.setTransform(dpr, 0, 0, dpr, 0, 0)
    context.clearRect(0, 0, width, RULER_HEIGHT)

    const styles = getComputedStyle(element)
    const border = styles.getPropertyValue('--border').trim() || '#2a2f3c'
    const muted = styles.getPropertyValue('--muted').trim() || '#8b93a7'
    const accent = styles.getPropertyValue('--accent').trim() || '#5b8cff'

    if (range) {
      context.fillStyle = accent
      context.globalAlpha = 0.18
      context.fillRect(
        (range.in / 1000) * zoom,
        0,
        ((range.out - range.in) / 1000) * zoom,
        RULER_HEIGHT
      )
      context.globalAlpha = 1
    }

    context.strokeStyle = border
    context.fillStyle = muted
    context.font = '10px "Segoe UI", sans-serif'
    context.textBaseline = 'middle'

    const step = zoom >= 120 ? 1 : zoom >= 60 ? 2 : zoom >= 24 ? 5 : 10
    for (let second = 0; second * zoom <= width; second += step) {
      const x = Math.round(second * zoom) + 0.5
      context.beginPath()
      context.moveTo(x, RULER_HEIGHT - 6)
      context.lineTo(x, RULER_HEIGHT)
      context.stroke()
      context.fillText(formatTimecode(second * 1000), x + 4, 9)
    }
  }, [width, zoom, range])

  const seekFromEvent = (event: React.PointerEvent<HTMLElement>): void => {
    const box = event.currentTarget.getBoundingClientRect()
    const ms = Math.round(((event.clientX - box.left) / zoom) * 1000)
    seek(Math.max(0, Math.min(Math.round(totalMs), ms)))
  }

  const beginRulerDrag = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (event.button !== 0) return
    event.preventDefault()
    seekFromEvent(event)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const moveRulerDrag = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
    seekFromEvent(event)
  }

  const sourceDuration = (clip: WorkspaceClip): number => {
    const data = peaks.current.get(assetFor(clip as unknown as Clip) ?? '')
    return data?.durationMs ?? clip.out_ms
  }

  const addClip = (
    lane: number,
    source: WorkspaceClip['source'],
    name: string,
    startMs: number,
    sourceMs: number
  ): void => {
    const lanes: WorkspaceTrack[] =
      tracks.length === 0
        ? [
            {
              id: newId(),
              name: 'Lane 1',
              clips: [],
              muted: false,
              solo: false,
              armed: false
            }
          ]
        : tracks
    const target = Math.max(0, Math.min(lanes.length - 1, lane))
    const clip: WorkspaceClip = {
      id: newId(),
      name,
      source,
      start_ms: Math.max(0, Math.round(startMs)),
      in_ms: 0,
      out_ms: sourceMs
    }
    const next = lanes.map((track, index) =>
      index === target ? { ...track, clips: [...track.clips, clip] } : track
    )
    commit(next, clip.id)
  }

  const beginClipDrag = (
    event: React.PointerEvent<HTMLElement>,_lane: number,
    clip: WorkspaceClip,
    mode: ClipDrag['mode']
  ): void => {
    if (event.button !== 0) return
    if (tool === 'razor') return
    event.preventDefault()
    event.stopPropagation()
    setMenu(null)

    const additive = event.ctrlKey || event.metaKey || event.shiftKey
    let selection = selectedClips
    let collapseTo: string | null = null
    if (additive) {
      selection = selectedClips.includes(clip.id)
        ? selectedClips.filter((id) => id !== clip.id)
        : [...selectedClips, clip.id]
      setSelectedClips(selection)
      if (!selection.includes(clip.id)) return
    } else if (!selection.includes(clip.id)) {
      selection = [clip.id]
      setSelectedClips(selection)
    } else {
      // Keep the multi-selection alive for a drag; a plain click collapses it.
      collapseTo = clip.id
    }

    setSelectedClip(clip.id)
    onClipSelected(clip)

    const movingIds = mode === 'move' ? selection : [clip.id]
    const originals: Array<{ clip: WorkspaceClip; lane: number }> = []
    tracksRef.current.forEach((track, index) => {
      for (const item of track.clips) {
        if (movingIds.includes(item.id)) originals.push({ clip: item, lane: index })
      }
    })

    drag.current = {
      primary: clip.id,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      originals,
      moved: false,
      pastThreshold: false,
      collapseTo,
      before: clone(tracksRef.current)
    }
    const move = (native: PointerEvent): void => moveClipDrag(native)
    const up = (native: PointerEvent): void => {
      endClipDrag(native)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
  }

  const moveClipDrag = (event: { clientX: number; clientY: number }): void => {
    const active = drag.current
    if (!active) return

    // Dead zone: a few pixels of jitter on click must not move the clip.
    if (!active.pastThreshold) {
      const dx = Math.abs(event.clientX - active.startX)
      const dy = Math.abs(event.clientY - active.startY)
      if (dx < 4 && dy < 4) return
      active.pastThreshold = true
    }

    const deltaMs = Math.round(((event.clientX - active.startX) / zoom) * 1000)
    const laneShift = Math.round((event.clientY - active.startY) / (LANE_HEIGHT + LANE_GAP))
    if (deltaMs !== 0 || laneShift !== 0) active.moved = true

    if (active.mode !== 'move') {
      const entry = active.originals[0]
      if (!entry) return
      const original = entry.clip
      const updated: WorkspaceClip =
        active.mode === 'in'
          ? (() => {
              // Trimming the head moves the clip and the in point together, so
              // the remaining audio stays at the same place on the timeline.
              const lower = Math.max(-original.start_ms, -original.in_ms)
              const upper = original.out_ms - MIN_CLIP_MS - original.in_ms
              const applied = Math.max(lower, Math.min(deltaMs, upper))
              return {
                ...original,
                in_ms: original.in_ms + applied,
                start_ms: original.start_ms + applied
              }
            })()
          : {
              ...original,
              // The out point can never pass the end of the source material.
              out_ms: Math.max(
                original.in_ms + MIN_CLIP_MS,
                Math.min(sourceDuration(original), original.out_ms + deltaMs)
              )
            }
      applyTracks(
        tracksRef.current.map((track, index) =>
          index === entry.lane
            ? {
                ...track,
                clips: track.clips.map((clip) => (clip.id === original.id ? updated : clip))
              }
            : track
        )
      )
      return
    }

    // Snap the group by its primary clip's edges, then move everything together.
    let effectiveDelta = deltaMs
    if (snapEnabled) {
      const primary = active.originals.find((entry) => entry.clip.id === active.primary)
      if (primary) {
        const excluded = new Set(active.originals.map((entry) => entry.clip.id))
        effectiveDelta = snapDelta(primary.clip, deltaMs, excluded)
      }
    }

    // Multi-clip move: pull every selected clip out, then place them all back.
    const moving = new Set(active.originals.map((entry) => entry.clip.id))
    const next = tracksRef.current.map((track) => ({
      ...track,
      clips: track.clips.filter((clip) => !moving.has(clip.id))
    }))
    for (const entry of active.originals) {
      const targetLane = Math.max(0, Math.min(next.length - 1, entry.lane + laneShift))
      const moved: WorkspaceClip = {
        ...entry.clip,
        start_ms: Math.max(0, entry.clip.start_ms + effectiveDelta)
      }
      next[targetLane] = {
        ...next[targetLane],
        clips: [...next[targetLane].clips, moved]
      }
    }
    applyTracks(next)
  }

  /** Pull a moved edge onto the nearest edge of any other clip. */
  const snapDelta = (clip: WorkspaceClip, deltaMs: number, excluded: Set<string>): number => {
    const threshold = (8 / zoom) * 1000
    const proposedStart = clip.start_ms + deltaMs
    const proposedEnd = proposedStart + clipLength(clip)
    let best: number | null = null

    for (const other of allClips) {
      if (excluded.has(other.id)) continue
      for (const edge of [other.start_ms, other.start_ms + clipLength(other)]) {
        for (const candidate of [proposedStart, proposedEnd]) {
          const diff = edge - candidate
          if (Math.abs(diff) <= threshold && (best === null || Math.abs(diff) < Math.abs(best))) {
            best = diff
          }
        }
      }
    }
    return best === null ? deltaMs : deltaMs + best
  }

  const endClipDrag = (_event: { clientX: number; clientY: number }): void => {
    const active = drag.current
    if (!active) return
    drag.current = null
    if (active.moved) {
      pushHistory(tracksRef.current)
      saveWorkspace(tracksRef.current, active.primary)
      const moved = tracksRef.current
        .flatMap((track) => track.clips)
        .find((clip) => clip.id === active.primary)
      if (moved) onClipSelected(moved)
      return
    }

    // A click without a drag collapses a multi-selection to the clicked clip.
    if (active.collapseTo) {
      setSelectedClips([active.collapseTo])
    }
    setSelectedClip(active.primary)
  }
  const razorAt = (event: React.MouseEvent<HTMLElement>, clip: WorkspaceClip): void => {
    event.stopPropagation()
    const box = event.currentTarget.getBoundingClientRect()
    const cutMs = Math.round(((event.clientX - box.left) / zoom) * 1000)
    if (cutMs < MIN_CLIP_MS || cutMs > clipLength(clip) - MIN_CLIP_MS) return

    const next = tracks.map((track) => ({
      ...track,
      clips: track.clips.flatMap((item) => {
        if (item.id !== clip.id) return [item]
        return [
          { ...item, id: newId(), out_ms: item.in_ms + cutMs },
          {
            ...item,
            id: newId(),
            start_ms: item.start_ms + cutMs,
            in_ms: item.in_ms + cutMs
          }
        ]
      })
    }))
    commit(next, null)
  }

  const removeClip = (clipId: string): void => {
    const next = tracks.map((track) => ({
      ...track,
      clips: track.clips.filter((clip) => clip.id !== clipId)
    }))
    commit(next, null)
  }

  const removeLane = (lane: number): void => {
    commit(
      tracks.filter((_, index) => index !== lane),
      null
    )
    setSelectedLane(null)
  }

  const clearWorkbench = (): void => {
    const next = tracks.map((track) => ({ ...track, clips: [] }))
    commit(next, null)
  }

  const duplicateClip = (lane: number, clipId: string): void => {
    const track = tracks[lane]
    const clip = track?.clips.find((item) => item.id === clipId)
    if (!track || !clip) return
    const copy: WorkspaceClip = {
      ...structuredClone(clip),
      id: newId(),
      start_ms: clip.start_ms + clipLength(clip)
    }
    const next = tracks.map((item, index) =>
      index === lane ? { ...item, clips: [...item.clips, copy] } : item
    )
    commit(next, copy.id)
  }

  const toggleLane = (lane: number, key: 'muted' | 'solo' | 'armed'): void => {
    const next = tracks.map((track, index) =>
      index === lane ? { ...track, [key]: !track[key] } : track
    )
    commit(next)
  }

  const addLane = (): void => {
    commit([
      ...tracks,
      {
        id: newId(),
        name: `Lane ${tracks.length + 1}`,
        clips: [],
        muted: false,
        solo: false,
        armed: false
      }
    ])
  }

  /** The in/out range becomes the span of every selected clip. */
  const setInOutToSelection = (fallbackId: string): void => {
    const ids = selectedClips.includes(fallbackId) ? selectedClips : [fallbackId]
    const chosen = allClips.filter((clip) => ids.includes(clip.id))
    if (chosen.length === 0) return
    const start = Math.min(...chosen.map((clip) => clip.start_ms))
    const end = Math.max(...chosen.map((clip) => clip.start_ms + clipLength(clip)))
    setRange({ in: start, out: end })
  }

  const setIn = (): void => {
    const inMs = playheadRef.current
    setRange({ in: inMs, out: Math.max(inMs + 200, range?.out ?? totalMs) })
  }

  const setOut = (): void => {
    const outMs = playheadRef.current
    setRange({ in: Math.min(range?.in ?? 0, outMs - 200), out: outMs })
  }

  // With an in/out range, the range itself is the selection; otherwise the
  // single selected clip is. The range is sliced per clip, so partial overlaps
  // still land on the line with the right audio.
  const clipsToInsert = range
    ? allClips
        .map((clip) => sliceToRange(clip, range))
        .filter((clip): clip is WorkspaceClip => clip !== null)
    : allClips.filter((clip) => clip.id === selectedClip)

  const insertIntoLine = async (): Promise<void> => {
    const line = lines.find((item) => item.uuid === selectedLine)
    if (clipsToInsert.length === 0) {
      setError('Select a clip, or set in/out and select a range with material.')
      return
    }
    if (!line) {
      setError('Select a line in the list first.')
      return
    }
    const offset = Math.max(
      0,
      ...line.track.clips.map((item) => item.start_ms + clipLength(item))
    )
    try {
      const saved = await sendJson<LineDocument>('PUT', `/lines/${line.uuid}/track`, {
        clips: [
          ...line.track.clips,
          ...clipsToInsert.map((clip) => ({
            source: clip.source,
            in_ms: Math.round(clip.in_ms),
            out_ms: Math.round(clip.out_ms),
            start_ms: Math.round(offset + clip.start_ms)
          }))
        ]
      })
      onLineSaved(saved)
      onInserted(line.uuid)
      if (range) setRange(null)
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const dropMaterial = (event: React.DragEvent<HTMLDivElement>): void => {
    const takePayload = event.dataTransfer.getData('application/x-dvp-take')
    const blockPayload = event.dataTransfer.getData('application/x-dvp-block')
    if (!takePayload && !blockPayload) return
    event.preventDefault()

    const bounds = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - bounds.left
    const y = event.clientY - bounds.top - RULER_HEIGHT
    const lane = Math.max(
      0,
      Math.min(Math.max(0, tracks.length - 1), Math.floor(y / (LANE_HEIGHT + LANE_GAP)))
    )
    const startMs = Math.max(0, (x / zoom) * 1000)

    let block: BlockDocument | undefined
    let takeId = ''
    try {
      if (takePayload) {
        const payload = JSON.parse(takePayload) as { block: string; take: string }
        block = blocks.find((item) => item.id === payload.block)
        takeId = payload.take
      } else {
        block = blocks.find((item) => item.id === blockPayload)
        takeId = block?.takes.at(-1)?.id ?? ''
      }
    } catch {
      setError('Could not read the dropped material.')
      return
    }

    const take = block?.takes.find((item) => item.id === takeId)
    if (!block || !take) {
      setError('That block has no take yet.')
      return
    }
    addClip(
      lane,
      { kind: 'take', block: block.id, take: take.id },
      `${block.title} · ${take.provider}/${take.model}`,
      startMs,
      take.duration_ms ?? 1000
    )
  }

  const startRecording = async (lane: number): Promise<void> => {
    if (recording || counting > 0) return
    setError(null)
    setSelectedLane(lane)
    recordingStart.current = playheadRef.current
    recordingLane.current = lane

    const delay = Math.max(0, countdownMs)
    const steps = Math.ceil(delay / 1000)
    for (let left = steps; left > 0; left -= 1) {
      setCounting(left)
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }
    setCounting(0)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const media = new MediaRecorder(stream)
      chunks.current = []
      media.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.current.push(event.data)
      }
      media.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        void finishRecording(media.mimeType, recordingLane.current)
      }
      media.start()
      recorder.current = media
      setRecording(true)
      // Roll the existing mix from the playhead so the take can be recorded along.
      if (audible.length > 0) void play(recordingStart.current)
    } catch (caught) {
      setError(`Microphone unavailable: ${toMessage(caught)}`)
    }
  }

  const stopRecording = (): void => {
    recorder.current?.stop()
    recorder.current = null
    setRecording(false)
    stop()
  }

  const finishRecording = async (mime: string, lane: number): Promise<void> => {
    try {
      const blob = new Blob(chunks.current, { type: mime || 'audio/webm' })
      chunks.current = []
      const context = audioContext()
      const bytes = await blob.arrayBuffer()
      const buffer = await context.decodeAudioData(bytes.slice(0))
      const durationMs = Math.round(buffer.duration * 1000)
      const query = new URLSearchParams({
        name: `Recording ${new Date().toLocaleTimeString()}`,
        extension: 'webm',
        duration_ms: String(durationMs)
      })
      const response = await fetch(`/api/assets?${query}`, { method: 'POST', body: blob })
      if (!response.ok) throw new Error(`Upload failed: HTTP ${response.status}`)
      const asset = (await response.json()) as AssetInfo
      addClip(
        lane,
        { kind: 'asset', asset: asset.path },
        asset.name,
        recordingStart.current,
        durationMs
      )
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  // Space plays from the playhead, R records into the armed lane.
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      const target = event.target as HTMLElement | null
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return

      if (event.code === 'Space') {
        event.preventDefault()
        if (recording) {
          stopRecording()
        } else if (playing) {
          stop()
        } else {
          void play(playheadRef.current)
        }
        return
      }
      if (event.key.toLowerCase() === 'r') {
        event.preventDefault()
        const lane = selectedLane ?? tracks.findIndex((track) => track.armed)
        if (recording) stopRecording()
        else if (lane >= 0) void startRecording(lane)
        return
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        if (event.shiftKey) redo()
        else undo()
        return
      }
      if (event.key === 'Delete' || event.key === 'Backspace') {
        if (!selectedClip) return
        event.preventDefault()
        removeClip(selectedClip)
        return
      }
      if (event.key.toLowerCase() === 'i') {
        event.preventDefault()
        setIn()
      }
      if (event.key.toLowerCase() === 'o') {
        event.preventDefault()
        setOut()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  useEffect(() => {
    const close = (): void => setMenu(null)
    window.addEventListener('pointerdown', close)
    return () => window.removeEventListener('pointerdown', close)
  }, [])

  const target = lines.find((item) => item.uuid === selectedLine) ?? null
  const menuClip = menu
    ? tracks[menu.lane]?.clips.find((clip) => clip.id === menu.clipId)
    : undefined

  return (
    <div className={`editor tool-${tool}`}>
      <div className="workspace-toolbar">
        <div className="tool-group">
          <button
            type="button"
            className={`tool${tool === 'select' ? ' on' : ''}`}
            title="Select tool (drag clips, trim edges)"
            onClick={() => setTool('select')}
          >
            ↖
          </button>
          <button
            type="button"
            className={`tool${tool === 'razor' ? ' on' : ''}`}
            title="Razor tool (click a clip to cut)"
            onClick={() => setTool('razor')}
          >
            ✂
          </button>
        </div>

        <div className="tool-group">
          <button type="button" className="tool" title="Set in point (I)" onClick={setIn}>
            I
          </button>
          <button type="button" className="tool" title="Set out point (O)" onClick={setOut}>
            O
          </button>
          <button
            type="button"
            className="tool"
            title="Clear in/out"
            onClick={() => setRange(null)}
            disabled={!range}
          >
            ⌫
          </button>
          <button
            type="button"
            className="tool"
            title="Go to in point"
            onClick={() => seek(range?.in ?? 0)}
            disabled={!range}
          >
            ⇤
          </button>
        </div>

        <button
          className="button small"
          type="button"
          onClick={() => (playing ? stop() : void play(playheadRef.current))}
          disabled={audible.length === 0}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <span className="timecode">{formatTimecode(playhead)}</span>
        {counting > 0 ? <span className="countdown">● {counting}</span> : null}
        {recording ? <span className="countdown">REC</span> : null}

        <span className="divider" />
        <button className="button small" type="button" onClick={addLane}>
          + Lane
        </button>
        <button
          className="button small"
          type="button"
          onClick={undo}
          disabled={!canUndo}
          title="Undo (Ctrl+Z)"
        >
          ↺
        </button>
        <button
          className="button small"
          type="button"
          onClick={redo}
          disabled={!canRedo}
          title="Redo (Ctrl+Shift+Z)"
        >
          ↻
        </button>
        <button
          className="button small"
          type="button"
          onClick={clearWorkbench}
          disabled={allClips.length === 0}
          title="Remove every clip from every lane"
        >
          Clear
        </button>

        <span className="divider" />
        <span className="muted">
          {!target
            ? 'Select a line in the list to insert into it'
            : clipsToInsert.length === 0
              ? 'Nothing to insert: select a clip, or set in/out over some clips'
              : `Insert ${clipsToInsert.length} clip(s) into: ${
                  (target.character_name || target.character || 'Narrator') +
                  ' · ' +
                  target.text.slice(0, 16)
                }`}
        </span>
        <button
          className="button small primary"
          type="button"
          disabled={!target || clipsToInsert.length === 0}
          title={
            range
              ? `${clipsToInsert.length} clip(s) inside the in/out range`
              : 'The selected clip, or set in/out to insert a range'
          }
          onClick={() => void insertIntoLine()}
        >
          {clipsToInsert.length > 1
            ? `Insert ${clipsToInsert.length} clips`
            : clipsToInsert.length === 1
              ? 'Insert 1 clip'
              : 'Insert into line'}
        </button>

        <button
          type="button"
          className={`toggle${snapEnabled ? ' on' : ''}`}
          title="Snap dragged clips to nearby clip edges"
          onClick={() => setSnapEnabled((value) => !value)}
        >
          Snap
        </button>

        <div className="zoom">
          <button
            className="button small"
            type="button"
            onClick={() => setZoom((value) => Math.max(MIN_ZOOM, Math.round(value / 1.5)))}
          >
            −
          </button>
          <button
            className="button small"
            type="button"
            onClick={() => setZoom((value) => Math.min(MAX_ZOOM, Math.round(value * 1.5)))}
          >
            +
          </button>
        </div>

        <span className="muted">
          {allClips.length} clip(s) · {tracks.length} lane(s)
        </span>
      </div>

      {error ? <p className="error">{error}</p> : null}

      <div className="editor-main">
        <div className="editor-heads">
          <div className="editor-heads-inner" ref={headsRef}>
          <div className="ruler-corner" style={{ height: RULER_HEIGHT }} />
          {tracks.map((track, index) => (
            <div className="editor-head" key={track.id} style={{ height: LANE_HEIGHT }}>
              <div
                className={`head-row${selectedLane === index ? ' selected' : ''}`}
                onClick={() => setSelectedLane(index)}
              >
                <span className="lane-index">{index + 1}</span>
                <div className="head-buttons">
                  <button
                    type="button"
                    className={`mini${track.muted ? ' on' : ''}`}
                    title="Mute"
                    onClick={(event) => {
                      event.stopPropagation()
                      toggleLane(index, 'muted')
                    }}
                  >
                    M
                  </button>
                  <button
                    type="button"
                    className={`mini${track.solo ? ' on' : ''}`}
                    title="Solo"
                    onClick={(event) => {
                      event.stopPropagation()
                      toggleLane(index, 'solo')
                    }}
                  >
                    S
                  </button>
                  <button
                    type="button"
                    className={`mini${track.armed ? ' on rec' : ''}`}
                    title="Record into this lane (R)"
                    onClick={(event) => {
                      event.stopPropagation()
                      setSelectedLane(index)
                      if (recording) stopRecording()
                      else void startRecording(index)
                    }}
                  >
                    R
                  </button>
                  <button
                    type="button"
                    className="mini remove"
                    title="Remove lane"
                    onClick={(event) => {
                      event.stopPropagation()
                      removeLane(index)
                    }}
                  >
                    ×
                  </button>
                </div>
              </div>
            </div>
          ))}
          </div>
        </div>

        <div
          ref={scrollRef}
          className="editor-scroll"
          onScroll={(event) => {
            if (headsRef.current) {
              headsRef.current.style.transform = `translateY(-${event.currentTarget.scrollTop}px)`
            }
          }}
          onPointerDown={(event) => {
            if (event.button !== 1) return
            event.preventDefault()
            panRef.current = {
              x: event.clientX,
              y: event.clientY,
              left: event.currentTarget.scrollLeft,
              top: event.currentTarget.scrollTop
            }
            try {
              event.currentTarget.setPointerCapture(event.pointerId)
            } catch {
              // Synthetic pointers have no capture support.
            }
          }}
          onPointerMove={(event) => {
            const pan = panRef.current
            if (!pan) return
            event.currentTarget.scrollLeft = Math.max(0, pan.left - (event.clientX - pan.x))
            event.currentTarget.scrollTop = Math.max(0, pan.top - (event.clientY - pan.y))
          }}
          onPointerUp={(event) => {
            if (!panRef.current) return
            panRef.current = null
            if (event.currentTarget.hasPointerCapture(event.pointerId)) {
              event.currentTarget.releasePointerCapture(event.pointerId)
            }
          }}
        >
          <div
            ref={contentRef}
            className="editor-content"
            style={{ width, height: contentHeight }}
            onPointerDown={(event) => {
              if ((event.target as HTMLElement).closest('.lane-clip')) return
              setSelectedClips([])
              setSelectedClip(null)
              onClipSelected(null)
            }}
            onDragOver={(event) => {
              if (
                event.dataTransfer.types.includes('application/x-dvp-take') ||
                event.dataTransfer.types.includes('application/x-dvp-block')
              ) {
                event.preventDefault()
                event.dataTransfer.dropEffect = 'copy'
              }
            }}
            onDrop={dropMaterial}
          >
            <div
              className="ruler-strip"
              style={{ height: RULER_HEIGHT }}
              onPointerDown={beginRulerDrag}
              onPointerMove={moveRulerDrag}
            >
              <canvas ref={ruler} className="ruler-canvas" />
            </div>

            <canvas ref={canvas} className="editor-canvas" style={{ top: RULER_HEIGHT }} />

            {tracks.map((track, lane) =>
              track.clips.map((clip) => (
                <div
                  key={clip.id}
                  className={`lane-clip${selectedClips.includes(clip.id) ? ' selected' : ''}${
                    track.muted ? ' muted' : ''
                  }`}
                  style={{
                    left: (clip.start_ms / 1000) * zoom,
                    width: Math.max(8, (clipLength(clip) / 1000) * zoom),
                    top: RULER_HEIGHT + lane * (LANE_HEIGHT + LANE_GAP) + 2,
                    height: LANE_HEIGHT - 4
                  }}
                  onPointerDown={(event) => beginClipDrag(event, lane, clip, 'move')}
                  onClick={(event) => {
                    if (tool === 'razor') razorAt(event, clip)
                  }}
                  onContextMenu={(event) => {
                    event.preventDefault()
                    const width = 190
                    const height = 170
                    setMenu({
                      x: Math.min(event.clientX, window.innerWidth - width),
                      y: Math.min(event.clientY, window.innerHeight - height),
                      lane,
                      clipId: clip.id
                    })
                  }}
                >
                  <span
                    className="clip-grip left"
                    onPointerDown={(event) => beginClipDrag(event, lane, clip, 'in')}
                  />
                  <span className="clip-name">{clip.name}</span>
                  <button
                    className="clip-remove"
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={() => removeClip(clip.id)}
                  >
                    ×
                  </button>
                  <span
                    className="clip-grip right"
                    onPointerDown={(event) => beginClipDrag(event, lane, clip, 'out')}
                  />
                </div>
              ))
            )}

            <div className="playhead" style={{ left: (playhead / 1000) * zoom, top: 0 }} />
          </div>
        </div>
      </div>

      {menu && menuClip ? (
        <div
          className="context-menu"
          style={{ left: menu.x, top: menu.y }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => {
              duplicateClip(menu.lane, menu.clipId)
              setMenu(null)
            }}
          >
            Duplicate
          </button>
          <button
            type="button"
            onClick={() => {
              removeClip(menu.clipId)
              setMenu(null)
            }}
          >
            Delete
          </button>
          <button
            type="button"
            onClick={() => {
              setInOutToSelection(menu.clipId)
              setMenu(null)
            }}
          >
            In/out to selection
          </button>
          <button
            type="button"
            onClick={() => {
              setSelectedClip(menu.clipId)
              setSelectedClips([menu.clipId])
              setMenu(null)
            }}
          >
            Select only this
          </button>
        </div>
      ) : null}
    </div>
  )
}

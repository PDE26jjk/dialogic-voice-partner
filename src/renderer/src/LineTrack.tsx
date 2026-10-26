import { useEffect, useRef, useState } from 'react'
import { sendJson } from './lib/api'
import { useClipsPlayback } from './lib/use-clips-playback'
import { drawClipWave, useTakeAudio } from './lib/use-take-audio'
import type { AssetInfo, BlockDocument, Clip, LineDocument } from './lib/api-types'

const RULER_HEIGHT = 20
const CANVAS_HEIGHT = 64
const MIN_ZOOM = 24
const MAX_ZOOM = 480
const FPS = 30

interface LineTrackProps {
  line: LineDocument
  blocks: BlockDocument[]
  countdownMs: number
  onSaved: (line: LineDocument) => void
}

function toMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : String(caught)
}

function clipLength(clip: Clip): number {
  return Math.max(0, clip.out_ms - clip.in_ms)
}

function formatTimecode(ms: number): string {
  const safe = Math.max(0, ms)
  const minutes = Math.floor(safe / 60000)
  const seconds = Math.floor((safe % 60000) / 1000)
  const frames = Math.floor((safe % 1000) / (1000 / FPS))
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}:${String(frames).padStart(2, '0')}`
}

/**
 * The single track a line owns: one local timeline starting at zero, clips that
 * may overlap, and no cross-line state.
 */
export default function LineTrack({ line, blocks, countdownMs, onSaved }: LineTrackProps) {
  const [zoom, setZoom] = useState(64)
  const [preview, setPreview] = useState<Clip[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  const [counting, setCounting] = useState(0)
  const [dropActive, setDropActive] = useState(false)

  const canvas = useRef<HTMLCanvasElement>(null)
  const ruler = useRef<HTMLCanvasElement>(null)
  const drag = useRef<{ index: number; startX: number; start: number; moved: boolean } | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const recordStart = useRef(0)

  const { assetFor, ensure, audioContext, buffers, peaks, version } = useTakeAudio(blocks)
  const clips = preview ?? line.track.clips
  const duration = Math.max(1500, ...clips.map((clip) => clip.start_ms + clipLength(clip)))
  const width = Math.ceil((duration / 1000) * zoom)

  const { playing, playhead, play, stop, seek } = useClipsPlayback({
    clips,
    totalMs: duration,
    assetFor,
    audioContext,
    buffers: buffers.current,
    load: ensure
  })

  const playheadRef = useRef(playhead)
  playheadRef.current = playhead

  useEffect(() => {
    setPreview(null)
  }, [line.uuid])

  useEffect(() => {
    for (const clip of clips) {
      const asset = assetFor(clip)
      if (asset) void ensure(asset)
    }
  }, [clips, assetFor, ensure])

  useEffect(() => {
    const element = canvas.current
    if (!element) return
    const context = element.getContext('2d')
    if (!context) return

    const dpr = window.devicePixelRatio || 1
    element.width = Math.round(width * dpr)
    element.height = Math.round(CANVAS_HEIGHT * dpr)
    element.style.width = `${width}px`
    element.style.height = `${CANVAS_HEIGHT}px`
    context.setTransform(dpr, 0, 0, dpr, 0, 0)
    context.clearRect(0, 0, width, CANVAS_HEIGHT)

    const styles = getComputedStyle(element)
    const border = styles.getPropertyValue('--border').trim() || '#2a2f3c'
    const muted = styles.getPropertyValue('--muted').trim() || '#8b93a7'

    context.strokeStyle = border
    context.lineWidth = 1
    context.beginPath()
    for (let second = 0; second * zoom <= width; second += 1) {
      const x = Math.round(second * zoom) + 0.5
      context.moveTo(x, 0)
      context.lineTo(x, CANVAS_HEIGHT)
    }
    context.stroke()

    for (const clip of clips) {
      const asset = assetFor(clip)
      const data = asset ? peaks.current.get(asset) : null
      if (!data) {
        context.globalAlpha = 0.16
        context.fillStyle = muted
        context.fillRect(
          (clip.start_ms / 1000) * zoom,
          6,
          Math.max(1, (clipLength(clip) / 1000) * zoom),
          CANVAS_HEIGHT - 12
        )
        context.globalAlpha = 1
        continue
      }
      drawClipWave(context, data, clip, zoom, CANVAS_HEIGHT, muted)
    }
  }, [clips, zoom, width, version, assetFor, peaks])

  // Ruler: seconds ticks, timecode labels, and the playhead can be dragged.
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

    context.strokeStyle = border
    context.fillStyle = muted
    context.font = '10px "Segoe UI", sans-serif'
    context.textBaseline = 'middle'

    const step = zoom >= 100 ? 1 : zoom >= 50 ? 2 : 5
    for (let second = 0; second * zoom <= width; second += step) {
      const x = Math.round(second * zoom) + 0.5
      context.beginPath()
      context.moveTo(x, RULER_HEIGHT - 5)
      context.lineTo(x, RULER_HEIGHT)
      context.stroke()
      context.fillText(formatTimecode(second * 1000), x + 4, 8)
    }
  }, [width, zoom])

  const seekFromEvent = (event: React.PointerEvent<HTMLElement>): void => {
    const box = event.currentTarget.getBoundingClientRect()
    const ms = Math.round(((event.clientX - box.left) / zoom) * 1000)
    seek(Math.max(0, Math.min(Math.round(duration), ms)))
  }

  const beginRuler = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (event.button !== 0) return
    event.preventDefault()
    seekFromEvent(event)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const moveRuler = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
    seekFromEvent(event)
  }

  const save = async (next: Clip[]): Promise<void> => {
    setError(null)
    try {
      const saved = await sendJson<LineDocument>('PUT', `/lines/${line.uuid}/track`, {
        clips: next
      })
      onSaved(saved)
      setPreview(null)
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const append = async (
    source: Clip['source'],
    sourceMs: number,
    startMs = duration
  ): Promise<void> => {
    const next: Clip[] = [
      ...clips,
      { source, in_ms: 0, out_ms: sourceMs, start_ms: Math.max(0, Math.round(startMs)) }
    ]
    setPreview(next)
    await save(next)
  }

  const appendTake = async (blockId: string, takeId: string): Promise<void> => {
    const block = blocks.find((item) => item.id === blockId)
    const take = block?.takes.find((item) => item.id === takeId)
    if (!block || !take) {
      setError('That block has no take yet. Generate one first.')
      return
    }
    await append(
      { kind: 'take', block: block.id, take: take.id, asset: take.asset },
      take.duration_ms ?? 1000
    )
  }

  const beginDrag = (event: React.PointerEvent<HTMLElement>, index: number): void => {
    if (event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    drag.current = { index, startX: event.clientX, start: clips[index].start_ms, moved: false }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const moveDrag = (event: React.PointerEvent<HTMLElement>): void => {
    const active = drag.current
    if (!active) return
    const delta = Math.round(((event.clientX - active.startX) / zoom) * 1000)
    if (delta !== 0) active.moved = true
    setPreview(
      clips.map((clip, index) =>
        index === active.index
          ? { ...clip, start_ms: Math.max(0, active.start + delta) }
          : clip
      )
    )
  }

  const endDrag = (event: React.PointerEvent<HTMLElement>): void => {
    const active = drag.current
    if (!active) return
    drag.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    if (active.moved) void save(clips)
    else setPreview(null)
  }

  const removeClip = (index: number): void => {
    const next = clips.filter((_, position) => position !== index)
    setPreview(next)
    void save(next)
  }

  const startRecording = async (): Promise<void> => {
    if (recording || counting > 0) return
    setError(null)
    recordStart.current = playheadRef.current
    const steps = Math.ceil(Math.max(0, countdownMs) / 1000)
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
        void finishRecording(media.mimeType)
      }
      media.start()
      recorder.current = media
      setRecording(true)
      // Roll the line from the playhead so the take can be recorded against it.
      if (clips.length > 0) void play(recordStart.current)
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

  const finishRecording = async (mime: string): Promise<void> => {
    try {
      const blob = new Blob(chunks.current, { type: mime || 'audio/webm' })
      chunks.current = []
      const audio = audioContext()
      const bytes = await blob.arrayBuffer()
      const buffer = await audio.decodeAudioData(bytes.slice(0))
      const durationMs = Math.round(buffer.duration * 1000)

      const query = new URLSearchParams({
        name: `Recording ${new Date().toLocaleTimeString()}`,
        extension: 'webm',
        duration_ms: String(durationMs)
      })
      const response = await fetch(`/api/assets?${query}`, { method: 'POST', body: blob })
      if (!response.ok) throw new Error(`Upload failed: HTTP ${response.status}`)
      const asset = (await response.json()) as AssetInfo
      await append(
        { kind: 'asset', asset: asset.path },
        asset.duration_ms ?? durationMs,
        recordStart.current
      )
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  return (
    <div className="line-track">
      <div className="line-track-head">
        <button
          className="button small"
          type="button"
          onClick={() => (playing ? stop() : void play(playheadRef.current))}
          disabled={clips.length === 0}
        >
          {playing ? 'Stop' : 'Play'}
        </button>
        <span className="timecode">{formatTimecode(playhead)}</span>
        {counting > 0 ? <span className="countdown">● {counting}</span> : null}
        {recording ? <span className="countdown">REC</span> : null}
        <span className="muted">
          {clips.length} clip(s) · {(duration / 1000).toFixed(2)}s
        </span>

        <div className="zoom">
          <button
            className="button small"
            type="button"
            onClick={() => setZoom((value) => Math.max(MIN_ZOOM, Math.round(value / 1.5)))}
          >
            −
          </button>
          <span className="muted">{zoom}px/s</span>
          <button
            className="button small"
            type="button"
            onClick={() => setZoom((value) => Math.min(MAX_ZOOM, Math.round(value * 1.5)))}
          >
            +
          </button>
        </div>

        <div className="clip-form">
          <button
            className={`button small${recording ? ' primary' : ''}`}
            type="button"
            onClick={() => (recording ? stopRecording() : void startRecording())}
          >
            {recording ? 'Stop recording' : 'Record'}
          </button>
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}

      <div className="line-track-scroll">
        <div
          className="line-track-content"
          style={{ width, height: RULER_HEIGHT + CANVAS_HEIGHT }}
        >
          <div
            className="line-ruler"
            style={{ height: RULER_HEIGHT }}
            onPointerDown={beginRuler}
            onPointerMove={moveRuler}
          >
            <canvas ref={ruler} className="line-ruler-canvas" />
          </div>

          <div
            className={`line-track-body${dropActive ? ' drop-active' : ''}`}
            style={{ top: RULER_HEIGHT, height: CANVAS_HEIGHT }}
            onDragOver={(event) => {
              if (!event.dataTransfer.types.includes('application/x-dvp-take')) return
              event.preventDefault()
              event.dataTransfer.dropEffect = 'copy'
              setDropActive(true)
            }}
            onDragLeave={() => setDropActive(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDropActive(false)
              const raw = event.dataTransfer.getData('application/x-dvp-take')
              if (!raw) return
              try {
                const payload = JSON.parse(raw) as { block: string; take: string }
                void appendTake(payload.block, payload.take)
              } catch {
                setError('Could not read the dropped take.')
              }
            }}
          >
            <canvas ref={canvas} className="line-track-canvas" />
            {clips.map((clip, index) => (
              <div
                key={`${clip.source.take ?? clip.source.asset ?? 'clip'}-${index}`}
                className="line-clip"
                style={{
                  left: (clip.start_ms / 1000) * zoom,
                  width: Math.max(6, (clipLength(clip) / 1000) * zoom)
                }}
                onPointerDown={(event) => beginDrag(event, index)}
                onPointerMove={moveDrag}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
              >
                <span className="line-clip-label">{clip.start_ms}ms</span>
                <button
                  className="clip-remove"
                  type="button"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => removeClip(index)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <div className="playhead" style={{ left: (playhead / 1000) * zoom, top: 0 }} />
        </div>
      </div>
    </div>
  )
}

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
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
  height: number
  selectedClip: {
    index: number
    gain: number
    in_ms: number
    out_ms: number
    start_ms: number
  } | null
  onAssetSaved?: () => void
  onClipSelected: (
    payload: {
      index: number
      gain: number
      in_ms: number
      out_ms: number
      start_ms: number
    } | null
  ) => void
  onSaved: (line: LineDocument) => void
}

/** Encode a decoded buffer as 16-bit mono WAV, the format the service reads. */
function encodeWav(buffer: AudioBuffer): Blob {
  const channels = Math.min(2, buffer.numberOfChannels)
  const frames = buffer.length
  const bytesPerSample = 2
  const blockAlign = channels * bytesPerSample
  const dataSize = frames * blockAlign
  const view = new DataView(new ArrayBuffer(44 + dataSize))

  const writeText = (offset: number, value: string): void => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index))
    }
  }

  writeText(0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, channels, true)
  view.setUint32(24, buffer.sampleRate, true)
  view.setUint32(28, buffer.sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeText(36, 'data')
  view.setUint32(40, dataSize, true)

  const channelData: Float32Array[] = []
  for (let channel = 0; channel < channels; channel += 1) {
    channelData.push(buffer.getChannelData(channel))
  }

  let offset = 44
  for (let frame = 0; frame < frames; frame += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      const sample = Math.max(-1, Math.min(1, channelData[channel][frame]))
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
      offset += 2
    }
  }

  return new Blob([view.buffer], { type: 'audio/wav' })
}

/** Moving the pointer onto a timeline takes focus away from any slider. */
function blurActiveField(): void {
  const active = document.activeElement
  if (
    active instanceof HTMLInputElement ||
    active instanceof HTMLTextAreaElement ||
    active instanceof HTMLSelectElement
  ) {
    active.blur()
  }
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
export default function LineTrack({
  line,
  blocks,
  countdownMs,
  height,
  selectedClip,
  onAssetSaved,
  onClipSelected,
  onSaved
}: LineTrackProps) {
  const [zoom, setZoom] = useState(64)
  const [preview, setPreview] = useState<Clip[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  const [level, setLevel] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const meterFrame = useRef<number | null>(null)
  const [counting, setCounting] = useState(0)
  const [dropActive, setDropActive] = useState(false)
  const gainTimer = useRef<number | null>(null)

  const canvas = useRef<HTMLCanvasElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const panRef = useRef<{ x: number; y: number; left: number } | null>(null)
  const pendingScrollRef = useRef<number | null>(null)
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

  // Collapsing a line must not leave the microphone open.
  useEffect(() => {
    return () => {
      recorder.current?.stream.getTracks().forEach((track) => track.stop())
      recorder.current = null
      analyserRef.current = null
      if (meterFrame.current !== null) {
        cancelAnimationFrame(meterFrame.current)
        meterFrame.current = null
      }
    }
  }, [])

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

  const zoomRef = useRef(zoom)
  zoomRef.current = zoom

  // Wheel zooms the line timeline around the pointer.
  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    const onWheel = (event: WheelEvent): void => {
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return
      event.preventDefault()
      const current = zoomRef.current
      const factor = event.deltaY < 0 ? 1.2 : 1 / 1.2
      const next = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(current * factor)))
      if (next === current) return
      const rect = element.getBoundingClientRect()
      const pointerX = event.clientX - rect.left + element.scrollLeft
      const atMs = (pointerX / current) * 1000
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
      { source, in_ms: 0, out_ms: sourceMs, start_ms: Math.max(0, Math.round(startMs)), gain: 1 }
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
    // A dropped take is frozen into an asset: later generations cannot change
    // what this clip plays. Dropping the block keeps the live reference.
    try {
      const asset = await sendJson<AssetInfo>('POST', '/assets/from-take', {
        block: block.id,
        take: take.id
      })
      await append(
        { kind: 'asset', asset: asset.path },
        asset.duration_ms ?? take.duration_ms ?? 1000
      )
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  /** Change one clip's volume and save once the slider settles. */
  const updateGain = (index: number, value: number): void => {
    if (!clips[index]) return
    const next = clips.map((clip, position) =>
      position === index ? { ...clip, gain: value } : clip
    )
    setPreview(next)
    if (gainTimer.current !== null) window.clearTimeout(gainTimer.current)
    gainTimer.current = window.setTimeout(() => {
      gainTimer.current = null
      void save(next)
    }, 250)
  }

  useEffect(() => {
    if (!selectedClip) return
    updateGain(selectedClip.index, selectedClip.gain)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedClip?.index, selectedClip?.gain])

  const beginDrag = (event: React.PointerEvent<HTMLElement>, index: number): void => {
    if (event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    onClipSelected({
      index,
      gain: clips[index].gain ?? 1,
      in_ms: clips[index].in_ms,
      out_ms: clips[index].out_ms,
      start_ms: clips[index].start_ms
    })
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

  const playSource = `line:${line.uuid}`

  // Starting one timeline stops every other one.
  useEffect(() => {
    const onPlay = (event: Event): void => {
      if ((event as CustomEvent<string>).detail !== playSource) stop()
    }
    window.addEventListener('dvp:play', onPlay)
    return () => window.removeEventListener('dvp:play', onPlay)
  }, [playSource, stop])

  // Space plays this line only while the pointer is over it.
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      const target = event.target as HTMLElement | null
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
      if (event.code !== 'Space') return
      // The page must never scroll while the user is driving a timeline.
      event.preventDefault()
      if (!rootRef.current?.matches(':hover')) return
      if (playing) {
        stop()
      } else {
        window.dispatchEvent(new CustomEvent('dvp:play', { detail: playSource }))
        void play(playhead)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [playing, stop, play, playhead, playSource])

  /** Copy a dropped file into the pool and place it at the drop position. */
  const importFile = async (file: File, event: React.DragEvent<HTMLDivElement>): Promise<void> => {
    setError(null)
    try {
      const query = new URLSearchParams({ name: file.name })
      const response = await fetch(`/api/assets/import?${query}`, {
        method: 'POST',
        body: await file.arrayBuffer()
      })
      if (!response.ok) throw new Error(`Import failed: HTTP ${response.status}`)
      const asset = (await response.json()) as AssetInfo
      const box = event.currentTarget.getBoundingClientRect()
      const start = Math.max(0, Math.round(((event.clientX - box.left) / zoom) * 1000))
      const decoded = await audioContext().decodeAudioData(await file.arrayBuffer())
      const duration = Math.round(decoded.duration * 1000)
      const next: Clip[] = [
        ...clips,
        { source: { kind: 'asset', asset: asset.path }, in_ms: 0, out_ms: duration, start_ms: start, gain: 1 }
      ]
      await save(next)
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  /** Render the whole line and keep the result in the shared asset pool. */
  const saveAsAsset = async (): Promise<void> => {
    setError(null)
    try {
      const end = clips.reduce(
        (total, clip) => Math.max(total, clip.start_ms + clip.out_ms - clip.in_ms),
        0
      )
      if (end <= 0) return
      await sendJson('POST', '/assets/render', {
        line_uuid: line.uuid,
        start_ms: 0,
        end_ms: Math.round(end),
        name: `Line ${line.uuid.slice(0, 6)} render`
      })
    } catch (caught) {
      setError(toMessage(caught))
    }
  }

  const startRecording = async (): Promise<void> => {
    if (recording || counting > 0) return
    setError(null)

    // The countdown is pre-roll: roll the timeline back and play existing audio
    // so the performer hears context, then start recording at the playhead.
    const target = playheadRef.current
    const preRoll = Math.min(Math.max(0, countdownMs), target)
    const waitMs = Math.max(0, countdownMs - preRoll)
    recordStart.current = target

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

      if (waitMs > 0) {
        const steps = Math.ceil(waitMs / 1000)
        for (let left = steps; left > 0; left -= 1) {
          setCounting(left)
          await new Promise((resolve) => setTimeout(resolve, 1000))
        }
        setCounting(0)
      }
      const media = new MediaRecorder(stream)
      chunks.current = []
      media.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.current.push(event.data)
      }
      media.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        void finishRecording(media.mimeType)
      }
      const context = audioContext()
      const analyser = context.createAnalyser()
      analyser.fftSize = 256
      context.createMediaStreamSource(stream).connect(analyser)
      analyserRef.current = analyser
      const data = new Uint8Array(analyser.frequencyBinCount)
      const tick = (): void => {
        const node = analyserRef.current
        if (!node) return
        node.getByteTimeDomainData(data)
        let peak = 0
        for (const value of data) peak = Math.max(peak, Math.abs(value - 128) / 128)
        setLevel(peak)
        meterFrame.current = requestAnimationFrame(tick)
      }
      tick()
      // Play back from before the playhead; recording starts when it arrives.
      if (clips.length > 0) void play(Math.max(0, target - preRoll))
      if (preRoll > 0) {
        await new Promise((resolve) => setTimeout(resolve, preRoll))
      }

      media.start()
      recorder.current = media
      setRecording(true)
    } catch (caught) {
      setError(`Microphone unavailable: ${toMessage(caught)}`)
    }
  }

  const stopRecording = (): void => {
    recorder.current?.stop()
    recorder.current = null
    setRecording(false)
    setLevel(0)
    analyserRef.current = null
    if (meterFrame.current !== null) {
      cancelAnimationFrame(meterFrame.current)
      meterFrame.current = null
    }
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
        extension: 'wav',
        duration_ms: String(durationMs)
      })
      const response = await fetch(`/api/assets?${query}`, {
        method: 'POST',
        body: encodeWav(buffer)
      })
      if (!response.ok) throw new Error(`Upload failed: HTTP ${response.status}`)
      const asset = (await response.json()) as AssetInfo
      onAssetSaved?.()
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
    <div
      className="line-track"
      style={{ height }}
      ref={rootRef}
      onPointerDownCapture={blurActiveField}
    >
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
            className="button small"
            type="button"
            disabled={clips.length === 0}
            onClick={() => void save([])}
          >
            Clear
          </button>
          <button
            className={`button small${recording ? ' primary' : ''}`}
            type="button"
            onClick={() => (recording ? stopRecording() : void startRecording())}
          >
            {recording ? 'Stop recording' : 'Record'}
          </button>
          <button
            className="button small"
            type="button"
            disabled={clips.length === 0}
            onClick={() => void saveAsAsset()}
          >
            Save as asset
          </button>
          {recording ? (
            <span className="level-meter" title="Input level">
              <span style={{ width: `${Math.round(level * 100)}%` }} />
            </span>
          ) : null}
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}


      <div
        ref={scrollRef}
        className="line-track-scroll"
        onPointerDown={(event) => {
          if (event.button !== 1) return
          event.preventDefault()
          panRef.current = {
            x: event.clientX,
            y: event.clientY,
            left: event.currentTarget.scrollLeft
          }
          event.currentTarget.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          const pan = panRef.current
          if (!pan) return
          event.currentTarget.scrollLeft = Math.max(0, pan.left - (event.clientX - pan.x))
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
              const types = event.dataTransfer.types
              if (
                !types.includes('application/x-dvp-take') &&
                !types.includes('application/x-dvp-asset')
              ) {
                return
              }
              event.preventDefault()
              event.dataTransfer.dropEffect = 'copy'
              setDropActive(true)
            }}
            onDragLeave={() => setDropActive(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDropActive(false)
              if (event.dataTransfer.files.length > 0) {
                void importFile(event.dataTransfer.files[0], event)
                return
              }
              const assetPayload = event.dataTransfer.getData('application/x-dvp-asset')
              if (assetPayload) {
                try {
                  const dropped = JSON.parse(assetPayload) as {
                    asset: string
                    duration_ms: number
                  }
                  const box = event.currentTarget.getBoundingClientRect()
                  const start = Math.max(
                    0,
                    Math.round(((event.clientX - box.left) / zoom) * 1000)
                  )
                  const duration = Math.max(120, dropped.duration_ms || 2000)
                  void save([
                    ...clips,
                    {
                      source: { kind: 'asset', asset: dropped.asset },
                      in_ms: 0,
                      out_ms: duration,
                      start_ms: start,
                      gain: 1
                    }
                  ])
                } catch {
                  setError('Could not read the dropped asset.')
                }
                return
              }

              const raw = event.dataTransfer.getData('application/x-dvp-take')
              if (!raw) return
              try {
                const payload = JSON.parse(raw) as { block: string; take: string }
                const block = blocks.find((item) => item.id === payload.block)
                if (!block || block.takes.length === 0) {
                  setError('That block has no takes yet; generate one first.')
                  return
                }
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
                className={`line-clip ${clip.source.kind}${
                  selectedClip?.index === index ? ' selected' : ''
                }`}
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

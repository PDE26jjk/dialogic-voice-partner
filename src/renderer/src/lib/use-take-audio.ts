import { useCallback, useRef, useState } from 'react'
import type { BlockDocument, Clip } from './api-types'

export interface Peaks {
  values: Float32Array
  durationMs: number
}

/** Enough points to stay smooth at any zoom; decoding happens once per asset. */
export const PEAK_BUCKETS = 4000

/**
 * Decodes the takes and assets clips point at, caching audio and peaks by path.
 *
 * `version` bumps when a decode finishes, so callers can put it in a drawing
 * effect instead of polling the refs.
 */
export function useTakeAudio(blocks: BlockDocument[]) {
  const context = useRef<AudioContext | null>(null)
  const buffers = useRef(new Map<string, AudioBuffer>())
  const peaks = useRef(new Map<string, Peaks>())
  const requested = useRef(new Set<string>())
  const [version, setVersion] = useState(0)

  const assetFor = useCallback(
    (clip: Clip): string | null => {
      if (clip.source.kind === 'asset') return clip.source.asset ?? null
      const block = blocks.find((item) => item.id === clip.source.block)
      const take = block?.takes.find((item) => item.id === clip.source.take)
      return take?.asset ?? clip.source.asset ?? null
    },
    [blocks]
  )

  const audioContext = useCallback((): AudioContext => {
    const current = context.current ?? new AudioContext()
    context.current = current
    return current
  }, [])

  const ensure = useCallback(async (asset: string): Promise<void> => {
    if (requested.current.has(asset)) return
    requested.current.add(asset)
    try {
      const response = await fetch(`/api/${asset}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const bytes = await response.arrayBuffer()
      const audio = audioContext()
      const buffer = await audio.decodeAudioData(bytes)
      buffers.current.set(asset, buffer)
      peaks.current.set(asset, computePeaks(buffer))
      setVersion((value) => value + 1)
    } catch {
      // A missing file should not block the rest of the timeline.
      requested.current.delete(asset)
    }
  }, [audioContext])

  return { assetFor, ensure, audioContext, buffers, peaks, version }
}

export function computePeaks(buffer: AudioBuffer): Peaks {
  const values = new Float32Array(PEAK_BUCKETS)
  const channel = buffer.getChannelData(0)
  const step = Math.max(1, Math.floor(channel.length / PEAK_BUCKETS))

  for (let bucket = 0; bucket < PEAK_BUCKETS; bucket += 1) {
    let peak = 0
    const start = bucket * step
    for (let index = start; index < start + step && index < channel.length; index += 1) {
      const value = Math.abs(channel[index])
      if (value > peak) peak = value
    }
    values[bucket] = peak
  }

  return { values, durationMs: Math.round(buffer.duration * 1000) }
}

/** Draw the in..out slice of a take into the clip's span at `zoom` px per second. */
export function drawClipWave(
  context: CanvasRenderingContext2D,
  data: Peaks,
  clip: Clip,
  zoom: number,
  height: number,
  color: string
): void {
  const startX = (clip.start_ms / 1000) * zoom
  const width = Math.max(1, ((clip.out_ms - clip.in_ms) / 1000) * zoom)
  const middle = height / 2
  const amplitude = (height / 2 - 8) * 0.9

  context.fillStyle = color
  for (let column = 0; column < width; column += 1) {
    const atMs = clip.in_ms + (column / width) * (clip.out_ms - clip.in_ms)
    const index = Math.min(
      data.values.length - 1,
      Math.max(0, Math.floor((atMs / data.durationMs) * data.values.length))
    )
    const value = data.values[index]
    if (value <= 0) continue
    const bar = Math.max(1, value * amplitude)
    context.fillRect(startX + column, middle - bar, 1, bar * 2)
  }
}

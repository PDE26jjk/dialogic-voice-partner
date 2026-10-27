import { useCallback, useEffect, useRef, useState } from 'react'
import type { Clip } from './api-types'

interface PlaybackOptions {
  clips: Clip[]
  totalMs: number
  assetFor: (clip: Clip) => string | null
  audioContext: () => AudioContext
  buffers: Map<string, AudioBuffer>
  load: (asset: string) => Promise<void>
}

/**
 * Schedules every clip on one AudioContext timeline.
 *
 * Overlap is additive because each clip is an independent source at an absolute
 * offset; nothing in application code sums samples. Playback can start anywhere
 * on the timeline: clips before the start point are skipped, clips spanning it
 * start part way in.
 */
export function useClipsPlayback({
  clips,
  totalMs,
  assetFor,
  audioContext,
  buffers,
  load
}: PlaybackOptions) {
  const sources = useRef<AudioBufferSourceNode[]>([])
  const frame = useRef(0)
  const [playing, setPlaying] = useState(false)
  const [playhead, setPlayhead] = useState(0)

  const stop = useCallback((): void => {
    for (const source of sources.current) {
      try {
        source.stop()
      } catch {
        // Already finished.
      }
    }
    sources.current = []
    cancelAnimationFrame(frame.current)
    setPlaying(false)
  }, [])

  useEffect(() => stop, [stop])

  const seek = useCallback((value: number): void => {
    setPlayhead(Math.max(0, value))
  }, [])

  const play = useCallback(
    async (fromMs = 0): Promise<void> => {
      if (clips.length === 0) return
      stop()

      const context = audioContext()
      await context.resume()
      const origin = context.currentTime + 0.06
      const start = Math.max(0, fromMs)

      for (const clip of clips) {
        const asset = assetFor(clip)
        if (!asset) continue
        let buffer = buffers.get(asset)
        if (!buffer) {
          await load(asset)
          buffer = buffers.get(asset)
        }
        if (!buffer) continue

        const length = clip.out_ms - clip.in_ms
        const offsetOnTimeline = clip.start_ms - start
        if (offsetOnTimeline + length <= 0) continue

        const skip = Math.max(0, -offsetOnTimeline)
        const duration = (length - skip) / 1000
        if (duration <= 0) continue

        const source = context.createBufferSource()
        source.buffer = buffer
        const gain = context.createGain()
        gain.gain.value = clip.gain ?? 1
        source.connect(gain)
        gain.connect(context.destination)
        source.start(
          origin + Math.max(0, offsetOnTimeline) / 1000,
          (clip.in_ms + skip) / 1000,
          duration
        )
        sources.current.push(source)
      }

      setPlayhead(start)
      setPlaying(true)
      const tick = (): void => {
        const elapsed = start + (context.currentTime - origin) * 1000
        if (elapsed > totalMs) {
          setPlayhead(totalMs)
          stop()
          return
        }
        setPlayhead(Math.max(0, elapsed))
        frame.current = requestAnimationFrame(tick)
      }
      frame.current = requestAnimationFrame(tick)
    },
    [clips, totalMs, assetFor, audioContext, buffers, load, stop]
  )

  return { playing, playhead, play, stop, seek, setPlayhead }
}

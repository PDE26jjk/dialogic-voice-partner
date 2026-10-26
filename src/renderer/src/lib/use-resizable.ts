import { useCallback, useEffect, useRef, useState } from 'react'
import type { HTMLAttributes } from 'react'

/**
 * Draggable pane size, remembered in localStorage.
 *
 * The separator returned by `separatorProps` is a real element the caller
 * renders between panes; dragging it with the pointer resizes the pane, the
 * arrow keys nudge it, and a double click restores the initial size.
 */
export interface ResizableOptions {
  storageKey: string
  axis: 'x' | 'y'
  /** True when a larger value means dragging towards the start of the axis. */
  invert?: boolean
  minimum: number
  initial: number
  maximum: number
  step?: number
}

export interface Resizable {
  size: number
  separatorProps: HTMLAttributes<HTMLDivElement>
}

export function useResizable({
  storageKey,
  axis,
  invert = false,
  minimum,
  initial,
  maximum,
  step = 20
}: ResizableOptions): Resizable {
  const [size, setSize] = useState(() => readSize(storageKey, minimum, initial, maximum))
  const drag = useRef<{ pointer: number; start: number; value: number } | null>(null)

  const clamp = useCallback(
    (value: number): number => Math.min(maximum, Math.max(minimum, Math.round(value))),
    [minimum, maximum]
  )

  const commit = useCallback(
    (value: number): void => {
      const next = clamp(value)
      setSize(next)
      try {
        localStorage.setItem(storageKey, String(next))
      } catch {
        // A blocked storage just means the layout is not remembered.
      }
    },
    [clamp, storageKey]
  )

  // Keep the remembered size inside the window when it shrinks.
  useEffect(() => {
    const onWindowResize = (): void => setSize((current) => clamp(current))
    window.addEventListener('resize', onWindowResize)
    return () => window.removeEventListener('resize', onWindowResize)
  }, [clamp])

  const keyboardStep = (event: React.KeyboardEvent<HTMLDivElement>, sign: 1 | -1): void => {
    event.preventDefault()
    commit(size + sign * step * (invert ? -1 : 1))
  }

  const separatorProps: HTMLAttributes<HTMLDivElement> = {
    role: 'separator',
    tabIndex: 0,
    'aria-orientation': axis === 'x' ? 'vertical' : 'horizontal',
    'aria-valuemin': minimum,
    'aria-valuemax': maximum,
    'aria-valuenow': size,
    onPointerDown: (event) => {
      if (event.button !== 0) return
      event.preventDefault()
      drag.current = {
        pointer: event.pointerId,
        start: axis === 'x' ? event.clientX : event.clientY,
        value: size
      }
      event.currentTarget.setPointerCapture(event.pointerId)
    },
    onPointerMove: (event) => {
      const active = drag.current
      if (!active || active.pointer !== event.pointerId) return
      const position = axis === 'x' ? event.clientX : event.clientY
      commit(active.value + (position - active.start) * (invert ? -1 : 1))
    },
    onPointerUp: (event) => {
      drag.current = null
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId)
      }
    },
    onPointerCancel: () => {
      drag.current = null
    },
    onDoubleClick: () => commit(initial),
    onKeyDown: (event) => {
      if (axis === 'x' && event.key === 'ArrowLeft') keyboardStep(event, -1)
      if (axis === 'x' && event.key === 'ArrowRight') keyboardStep(event, 1)
      if (axis === 'y' && event.key === 'ArrowUp') keyboardStep(event, 1)
      if (axis === 'y' && event.key === 'ArrowDown') keyboardStep(event, -1)
    }
  }

  return { size, separatorProps }
}

function readSize(storageKey: string, minimum: number, initial: number, maximum: number): number {
  try {
    const stored = Number(localStorage.getItem(storageKey))
    if (Number.isFinite(stored) && stored > 0) {
      return Math.min(maximum, Math.max(minimum, Math.round(stored)))
    }
  } catch {
    // Fall through to the initial size.
  }
  return initial
}

/** A boolean pane visibility that survives a reload. */
export function usePaneOpen(storageKey: string, initial = true): [boolean, () => void] {
  const [open, setOpen] = useState(() => {
    try {
      const stored = localStorage.getItem(storageKey)
      return stored === null ? initial : stored === '1'
    } catch {
      return initial
    }
  })

  const toggle = useCallback(() => {
    setOpen((current) => {
      try {
        localStorage.setItem(storageKey, current ? '0' : '1')
      } catch {
        // Visibility still toggles for this session.
      }
      return !current
    })
  }, [storageKey])

  return [open, toggle]
}

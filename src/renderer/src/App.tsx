import { useEffect, useState } from 'react'

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

export default function App() {
  const [status, setStatus] = useState<ServiceStatus | null>(null)
  const [roundTrip, setRoundTrip] = useState('—')

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
      fetch('/api/health')
        .then((response) => response.json())
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

  useEffect(() => {
    if (status?.state !== 'ready') return
    let alive = true
    fetch('/api/health')
      .then((response) => response.json())
      .then((body: { status: string }) => {
        if (alive) setRoundTrip(body.status)
      })
      .catch((error: unknown) => {
        if (alive) setRoundTrip(String(error))
      })
    return () => {
      alive = false
    }
  }, [status?.state])

  return (
    <div className="app">
      <header className="topbar">
        <strong>Dialogic Voice Partner</strong>
        <span className={`badge badge-${status?.state ?? 'starting'}`}>
          {status ? STATE_LABEL[status.state] : 'Starting'}
        </span>
        <span className="detail">{status?.detail ?? 'Connecting…'}</span>
        <span className="detail">api: {roundTrip}</span>
      </header>

      <main className="layout">
        <aside className="pane projects">
          <h2>Projects</h2>
          <p className="muted">No project open yet.</p>
        </aside>

        <section className="pane lines">
          <h2>Lines</h2>
          <p className="muted">Push voice lines from the Godot editor to fill this list.</p>
        </section>

        <aside className="right">
          <div className="pane pool">
            <h2>Blocks</h2>
            <p className="muted">Generated blocks and imported audio appear here.</p>
          </div>
          <div className="pane inspector">
            <h2>Inspector</h2>
            <p className="muted">Select a block or clip to edit its properties.</p>
          </div>
        </aside>
      </main>

      <footer className="pane workspace">
        <h2>Workspace</h2>
        <p className="muted">Waveform, in/out points and cutting tools land here.</p>
      </footer>
    </div>
  )
}

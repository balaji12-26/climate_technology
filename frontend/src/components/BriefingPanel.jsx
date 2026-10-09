import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function BriefingPanel({ planId }) {
  const [useLlm, setUseLlm] = useState(false)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = async (llm) => { setBusy(true); const d = await api.briefing(llm); setData(d); setBusy(false) }
  useEffect(() => { load(useLlm) }, [planId]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="panel" style={{ borderTopLeftRadius: 0 }}>
      <h3>
        <span>Operational briefing</span>
        <label className="toggle hint">
          <input type="checkbox" checked={useLlm} onChange={(e) => { setUseLlm(e.target.checked); load(e.target.checked) }} />
          format with Claude (optional)
        </label>
      </h3>
      {busy && <div className="hint">rendering…</div>}
      {data && data.status !== 'ERROR' && (
        <>
          <div className="hint" style={{ marginBottom: 6 }}>
            source: <b>{data.source}</b>{data.llm_note ? ` — ${data.llm_note}` : data.source === 'llm' ? ' — every number checked against the solver JSON' : ' — deterministic template, works offline'}
          </div>
          <pre className="brief">{data.text}</pre>
          <div className="row" style={{ marginTop: 6 }}>
            <button className="btn small" onClick={() => navigator.clipboard?.writeText(data.text)}>Copy</button>
            <button className="btn small" onClick={() => load(useLlm)} disabled={busy}>Regenerate</button>
          </div>
        </>
      )}
      {data && data.status === 'ERROR' && <div className="hint">{data.error}</div>}
    </div>
  )
}

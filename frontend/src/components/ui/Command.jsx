// cmdk Command component wrapped with our design system
// Used for the protein input with autocomplete behaviour
import { Command as CmdkCommand } from 'cmdk'
import { useState } from 'react'

const SUGGESTIONS = [
  { id: '4OLI', label: '4OLI — BRD4 Bromodomain' },
  { id: '2GS6', label: '2GS6 — MDM2' },
  { id: '1IVN', label: '1IVN — BCL-2' },
  { id: 'P04637', label: 'P04637 — TP53 (UniProt)' },
  { id: '6W9C', label: '6W9C — SARS-CoV-2 main protease' },
  { id: 'P00533', label: 'P00533 — EGFR (UniProt)' },
  { id: 'Q00987', label: 'Q00987 — MDM2 (UniProt)' },
  { id: '1TFU', label: '1TFU — Thrombin' },
]

export function ProteinInput({ value, onChange, onSubmit }) {
  const [open, setOpen] = useState(false)

  const filtered = value
    ? SUGGESTIONS.filter(s =>
        s.id.toLowerCase().includes(value.toLowerCase()) ||
        s.label.toLowerCase().includes(value.toLowerCase())
      )
    : SUGGESTIONS

  const inputStyle = {
    background: 'var(--bg-secondary)',
    border: '2px solid var(--border)',
    color: 'var(--accent-cyan)',
    fontFamily: 'Fragment Mono, monospace',
    fontSize: '14px',
    padding: '12px 16px',
    width: '100%',
    outline: 'none',
    display: 'block',
    borderRadius: '0',
  }

  return (
    <div style={{ position: 'relative' }}>
      <input
        type="text"
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={e => {
          if (e.key === 'Enter') { onSubmit?.(); setOpen(false) }
          if (e.key === 'Escape') setOpen(false)
        }}
        placeholder="Enter PDB code or UniProt ID  e.g. 4OLI"
        style={inputStyle}
        autoComplete="off"
        spellCheck="false"
      />

      {open && filtered.length > 0 && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          background: 'var(--bg-secondary)',
          border: '2px solid var(--border)',
          borderTop: '1px solid var(--border)',
          zIndex: 7000,
          maxHeight: '200px',
          overflowY: 'auto',
        }}>
          {filtered.map(s => (
            <div
              key={s.id}
              onMouseDown={() => { onChange(s.id); setOpen(false) }}
              style={{
                padding: '9px 16px',
                fontFamily: 'Fragment Mono, monospace',
                fontSize: '12px',
                color: 'var(--text-secondary)',
                cursor: 'crosshair',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                justifyContent: 'space-between',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = 'var(--bg-card)'
                e.currentTarget.style.color = 'var(--accent-cyan)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'transparent'
                e.currentTarget.style.color = 'var(--text-secondary)'
              }}
            >
              <span style={{ color: 'var(--accent-cyan)', marginRight: '12px' }}>{s.id}</span>
              <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
                {s.label.split('—')[1]?.trim()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

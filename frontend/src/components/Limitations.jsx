import { useState } from 'react'
import { Collapsible } from './ui/Collapsible'

const LINES = [
  '// Docking scores are proxies for binding affinity, not true Kd values',
  '// rna-tools 3D structures are computationally approximated, not experimental',
  '// Hook penalty uses literature Kd2 for pomalidomide/CRBN (5 nM fixed)',
  '// Ternary complex is modelled as rigid-body geometry — no protein flexibility or induced-fit',
  '// PEG linker contour length assumed 3.5 Å/unit; actual reach depends on conformation',
  '// Degradation model accuracy drops from 80.8% to 62.3% on novel targets (Ribes et al. 2024)',
]

export default function Limitations() {
  const [open, setOpen] = useState(false)

  const trigger = (
    <button
      style={{
        background: 'none',
        border: 'none',
        cursor: 'crosshair',
        padding: '0',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
      }}
    >
      <span style={{ fontFamily: 'DM Sans, sans-serif', fontSize: '13px', color: 'var(--text-muted)' }}>
        Known model limitations
      </span>
      <ChevronIcon open={open} />
    </button>
  )

  return (
    <div style={{ marginTop: '16px' }}>
      <Collapsible open={open} onOpenChange={setOpen} trigger={trigger}>
        <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', padding: '16px', marginTop: '12px' }}>
          {LINES.map((line, i) => (
            <div key={i} style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.8' }}>
              {line}
            </div>
          ))}
        </div>
      </Collapsible>
    </div>
  )
}

function ChevronIcon({ open }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12"
      style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.25s', flexShrink: 0 }}>
      <polyline points="2,4 6,8 10,4" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="square" />
    </svg>
  )
}

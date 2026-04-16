import { useState } from 'react'
import NumberFlow from '@number-flow/react'
import { Collapsible } from './ui/Collapsible'

const COMPONENT_KEYS = [
  'fold_stability',
  'binding_score',
  'epitope_quality',
  'lysine_accessibility',
  'ternary_feasibility',
  'hook_penalty',
]

const LABELS = {
  fold_stability:       'Fold Stability',
  binding_score:        'Binding Score',
  epitope_quality:      'Epitope Quality',
  lysine_accessibility: 'Lysine Accessibility',
  ternary_feasibility:  'Ternary Geometry',
  hook_penalty:         'Hook Effect Penalty',
}

export const DEFAULT_WEIGHTS = {
  fold_stability:       0.15,
  binding_score:        0.20,
  epitope_quality:      0.20,
  lysine_accessibility: 0.15,
  ternary_feasibility:  0.25,
  hook_penalty:         0.05,
}

export default function ScoringWeights({ weights, onWeightsChange }) {
  const [open, setOpen] = useState(false)

  const handleChange = (key, newVal) => {
    const raw = parseFloat(newVal) / 100
    const delta = raw - weights[key]
    const others = COMPONENT_KEYS.filter(k => k !== key)
    const totalOthers = others.reduce((s, k) => s + weights[k], 0)
    const updated = { ...weights, [key]: raw }
    if (totalOthers > 0) {
      others.forEach(k => {
        updated[k] = Math.max(0, weights[k] - delta * (weights[k] / totalOthers))
      })
    }
    const total = Object.values(updated).reduce((s, v) => s + v, 0)
    COMPONENT_KEYS.forEach(k => { updated[k] = updated[k] / total })
    onWeightsChange(updated)
  }

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
        Scoring weights
      </span>
      <ChevronIcon open={open} />
    </button>
  )

  return (
    <div style={{ marginTop: '24px' }}>
      <Collapsible open={open} onOpenChange={setOpen} trigger={trigger}>
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', padding: '16px', marginTop: '12px' }}>
          {COMPONENT_KEYS.map(key => (
            <div key={key} style={{ marginBottom: '14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--text-secondary)' }}>
                  {LABELS[key]}
                </span>
                <span style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--accent-cyan)' }}>
                  <NumberFlow
                    value={Math.round(weights[key] * 100)}
                    format={{ minimumFractionDigits: 0 }}
                  />%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="1"
                value={Math.round(weights[key] * 100)}
                onChange={e => handleChange(key, e.target.value)}
                style={{ width: '100%' }}
              />
            </div>
          ))}
          <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '10px', color: 'var(--text-muted)', textAlign: 'right', marginTop: '4px' }}>
            weights normalised · total = 100%
          </div>
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

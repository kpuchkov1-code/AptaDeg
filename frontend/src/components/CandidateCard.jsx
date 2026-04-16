import { motion, AnimatePresence } from 'framer-motion'
import NumberFlow from '@number-flow/react'
import ArcDiagram from './ArcDiagram'
import { Tooltip, TooltipProvider } from './ui/Tooltip'

const NUCLEOTIDE_COLORS = {
  A: 'var(--accent-green)',
  U: 'var(--accent-red)',
  G: 'var(--accent-cyan)',
  C: 'var(--accent-amber)',
}

const SCORE_LABELS = {
  fold_stability:       'Fold Stability',
  binding_score:        'Binding Score',
  epitope_quality:      'Epitope Quality',
  lysine_accessibility: 'Lysine Access',
  ternary_feasibility:  'Ternary Geometry',
  hook_penalty:         'Hook Penalty',
}

const SCORE_TOOLTIPS = {
  fold_stability:       'How stably the aptamer folds into its predicted secondary structure. Unstable aptamers will not function in vivo.',
  binding_score:        'Predicted binding affinity to the target protein surface from rDock docking. Proxy for Kd1.',
  epitope_quality:      'Whether the binding site leaves geometric space for E3 ligase approach. High binding affinity to the wrong epitope will not produce degradation.',
  lysine_accessibility: 'Number of surface-exposed lysines accessible for ubiquitination after aptamer binding. Required for proteasomal degradation.',
  ternary_feasibility:  'Probability of forming a productive ternary complex. Scored from PEG linker bridging distance between aptamer 3\' terminus and CRBN pomalidomide pocket (PDB 4CI1). Optimal range: 15–50 Å.',
  hook_penalty:         'Affinity asymmetry between targeting arm and recruiter arm. High asymmetry causes binary complex dominance at therapeutic concentrations.',
}

function scoreColor(v, isHook = false) {
  const effective = isHook ? 1 - v : v
  if (effective > 0.66) return 'var(--accent-green)'
  if (effective > 0.33) return 'var(--accent-amber)'
  return 'var(--accent-red)'
}

function borderColor(d) {
  if (d > 0.75) return 'var(--accent-green)'
  if (d >= 0.5) return 'var(--accent-amber)'
  return 'var(--accent-red)'
}

function ColoredSequence({ seq }) {
  const lines = []
  for (let i = 0; i < seq.length; i += 60) lines.push(seq.slice(i, i + 60))
  return (
    <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '11px', lineHeight: 1.6 }}>
      {lines.map((line, li) => (
        <div key={li}>
          {line.split('').map((nt, ni) => (
            <span key={ni} style={{ color: NUCLEOTIDE_COLORS[nt] ?? 'var(--text-secondary)' }}>{nt}</span>
          ))}
        </div>
      ))}
    </div>
  )
}

function GaugeBar({ label, value, isHook }) {
  const color = scoreColor(value, isHook)
  const tooltip = SCORE_TOOLTIPS[
    Object.keys(SCORE_LABELS).find(k => SCORE_LABELS[k] === label) ?? ''
  ]
  return (
    <Tooltip content={tooltip} side="left">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', cursor: 'crosshair' }}>
        <div style={{ width: '110px', flexShrink: 0, fontFamily: 'DM Sans, sans-serif', fontSize: '11px', color: 'var(--text-secondary)' }}>
          {label}
        </div>
        <div style={{ flex: 1, height: '4px', background: 'var(--bg-secondary)', position: 'relative' }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${value * 100}%` }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            style={{ position: 'absolute', top: 0, left: 0, height: '100%', background: color }}
          />
        </div>
        <div style={{ width: '38px', textAlign: 'right', fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color, flexShrink: 0 }}>
          <NumberFlow value={Math.round(value * 100)} />
        </div>
      </div>
    </Tooltip>
  )
}

// Card variants for staggered entry
const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
}

export default function CandidateCard({ candidate, isSelected, onSelect }) {
  const bc = borderColor(candidate.degradability)

  return (
    <TooltipProvider>
      <motion.div
        layout
        layoutId={`card-${candidate.id}`}
        variants={cardVariants}
        whileHover={{ scale: 1.005 }}
        onClick={() => onSelect(candidate)}
        style={{
          background: 'var(--bg-card)',
          border: `1px solid ${isSelected ? 'var(--accent-cyan)' : 'var(--border)'}`,
          borderLeft: `3px solid ${bc}`,
          cursor: 'crosshair',
          position: 'relative',
          overflow: 'hidden',
          marginBottom: '8px',
          transition: 'border-color 0.2s',
        }}
      >
        {/* Rank + score */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 16px 8px' }}>
          <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '28px', color: 'var(--text-muted)' }}>
            #{candidate.rank}
          </span>
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '28px', color: bc }}>
              <NumberFlow
                value={Math.round(candidate.degradability * 100)}
                format={{ minimumFractionDigits: 0, maximumFractionDigits: 0 }}
              />
            </span>
            <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '9px', color: 'var(--text-muted)' }}>
              DEGRADABILITY
            </div>
          </div>
        </div>

        {/* Sequence */}
        <div style={{ padding: '0 16px 10px' }}>
          <ColoredSequence seq={candidate.sequence} />
        </div>

        {/* Arc diagram */}
        <div style={{ padding: '0 16px 8px' }}>
          <ArcDiagram dotBracket={candidate.dot_bracket} height={56} />
        </div>

        {/* Score bars */}
        <div style={{ padding: '8px 16px 10px', borderTop: '1px solid var(--border)' }}>
          {Object.entries(candidate.scores).map(([key, val]) => (
            <GaugeBar
              key={key}
              label={SCORE_LABELS[key] ?? key}
              value={val}
              isHook={key === 'hook_penalty'}
            />
          ))}
        </div>

        {/* Generation basis metadata */}
        {candidate.generation_basis && (
          <div style={{ padding: '6px 16px 8px', borderTop: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '10px', color: 'var(--text-muted)', lineHeight: 1.7 }}>
              GENERATION BASIS: {candidate.generation_basis}
            </div>
            {candidate.linker_recommendation && (
              <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '10px', color: 'var(--accent-cyan)', marginTop: '2px' }}>
                {candidate.linker_recommendation}
              </div>
            )}
          </div>
        )}

        {/* Verdict */}
        <div style={{ padding: '8px 16px 12px', fontFamily: 'DM Sans, sans-serif', fontStyle: 'italic', fontSize: '12px', color: 'var(--text-secondary)', borderTop: '1px solid var(--border)' }}>
          {candidate.verdict}
        </div>

        {/* Warning banners */}
        <AnimatePresence>
          {candidate.ternary_failure && (
            <motion.div
              key="ternary"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22 }}
              style={{ overflow: 'hidden' }}
            >
              <div style={{ padding: '8px 16px', background: 'rgba(255,68,85,0.15)', borderTop: '1px solid var(--accent-red)', fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--accent-red)' }}>
                ✕  TERNARY FAILURE — linker distance exceeds feasible range ({candidate.linker_angstroms} Å)
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {candidate.steric_clash && !candidate.ternary_failure && (
            <motion.div
              key="clash"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22 }}
              style={{ overflow: 'hidden' }}
            >
              <div style={{ padding: '8px 16px', background: 'rgba(255,68,85,0.15)', borderTop: '1px solid var(--accent-red)', fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--accent-red)' }}>
                ✕  STERIC CLASH — CRBN approach blocked by aptamer pose
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {candidate.hook_risk && (
            <motion.div
              key="hook"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22 }}
              style={{ overflow: 'hidden' }}
            >
              <div style={{ padding: '8px 16px', background: 'rgba(255,170,0,0.15)', borderTop: '1px solid var(--accent-amber)', fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--accent-amber)' }}>
                ⚠  HIGH HOOK EFFECT RISK — arm affinities mismatched
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {candidate.e3_inhibitory && (
            <motion.div
              key="e3"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22 }}
              style={{ overflow: 'hidden' }}
            >
              <div style={{ padding: '8px 16px', background: 'rgba(255,68,85,0.15)', borderTop: '1px solid var(--accent-red)', fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--accent-red)' }}>
                ✕  EXCLUDED — aptamer predicted to inhibit E3 ligase activity
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Source badge */}
        <div style={{ position: 'absolute', top: '16px', right: '80px', fontFamily: 'Fragment Mono, monospace', fontSize: '9px', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
          {candidate.source === 'database' ? 'DB' : 'GEN'}
        </div>
      </motion.div>
    </TooltipProvider>
  )
}

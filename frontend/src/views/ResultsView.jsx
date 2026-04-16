import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Radar } from '@nivo/radar'
import NumberFlow from '@number-flow/react'
import ProteinViewer from '../components/ProteinViewer'

// ─── Nucleotide colour map ────────────────────────────────────────────────────
const NT = {
  A: { bg: 'rgba(0,255,157,0.15)',  color: '#00ff9d', border: 'rgba(0,255,157,0.3)'  },
  U: { bg: 'rgba(255,68,85,0.15)',  color: '#ff4455', border: 'rgba(255,68,85,0.3)'  },
  G: { bg: 'rgba(0,212,255,0.15)',  color: '#00d4ff', border: 'rgba(0,212,255,0.3)'  },
  C: { bg: 'rgba(255,170,0,0.15)',  color: '#ffaa00', border: 'rgba(255,170,0,0.3)'  },
}

// ─── Sparkline ────────────────────────────────────────────────────────────────
function SparkLine({ trajectory = [] }) {
  if (!trajectory || trajectory.length < 2) return null
  const W = 60, H = 20
  const min = Math.min(...trajectory)
  const max = Math.max(...trajectory)
  const range = max - min || 0.001
  const pts = trajectory.map((v, i) => {
    const x = (i / (trajectory.length - 1)) * W
    const y = H - ((v - min) / range) * (H - 4) - 2
    return `${x},${y}`
  })
  const improving = trajectory[trajectory.length - 1] > trajectory[0] + 0.005
  const color = improving ? 'var(--cyan)' : 'var(--amber)'
  return (
    <svg width={W} height={H} style={{ display: 'block' }}>
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {trajectory.map((v, i) => {
        const x = (i / (trajectory.length - 1)) * W
        const y = H - ((v - min) / range) * (H - 4) - 2
        return <circle key={i} cx={x} cy={y} r="2" fill={color} />
      })}
    </svg>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function SequenceDisplay({ sequence }) {
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '1px',
      fontFamily: 'var(--font-mono)',
      fontSize: '11px',
      lineHeight: 1.6,
    }}>
      {sequence.split('').map((nt, i) => {
        const c = NT[nt] || { bg: 'transparent', color: 'var(--text-muted)', border: 'var(--border)' }
        return (
          <span key={i} style={{
            background: c.bg,
            color: c.color,
            border: `1px solid ${c.border}`,
            padding: '0 2px',
            minWidth: '14px',
            textAlign: 'center',
          }}>
            {nt}
          </span>
        )
      })}
    </div>
  )
}

function ScoreBar({ label, value = 0 }) {
  const color = value > 0.7 ? 'var(--green)' : value > 0.4 ? 'var(--amber)' : 'var(--red)'
  const clamped = Math.max(0, Math.min(1, value))
  return (
    <div style={{ marginBottom: '8px' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '4px',
      }}>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: '11px', color: 'var(--text-secondary)' }}>
          {label}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color }}>
          <NumberFlow
            value={clamped}
            format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
          />
        </span>
      </div>
      <div style={{ height: '3px', background: 'var(--border)', position: 'relative' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${clamped * 100}%` }}
          transition={{ duration: 0.8, ease: 'easeOut', delay: 0.1 }}
          style={{ position: 'absolute', left: 0, top: 0, height: '100%', background: color }}
        />
      </div>
    </div>
  )
}

function CandidateCard({ candidate: c, rank, isSelected, onClick }) {
  const score = c.degradability_score ?? 0
  const accent = score > 0.6 ? 'var(--green)' : score > 0.4 ? 'var(--amber)' : 'var(--red)'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: rank * 0.08 }}
      onClick={onClick}
      whileHover={{ scale: 1.003 }}
      style={{
        background: isSelected ? 'var(--bg-elevated)' : 'var(--bg-card)',
        border:     isSelected ? '1px solid var(--cyan)' : '1px solid var(--border)',
        borderLeft: `3px solid ${accent}`,
        padding:    '24px',
        cursor:     'crosshair',
        transition: 'background 0.2s, border-color 0.2s',
      }}
    >
      {/* Rank + degradability */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: '16px',
      }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: '40px',
          fontWeight: 800,
          color: 'var(--text-muted)',
          lineHeight: 1,
        }}>
          {String(rank + 1).padStart(2, '0')}
        </span>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: '40px',
          fontWeight: 800,
          color: accent,
          lineHeight: 1,
        }}>
          <NumberFlow
            value={score}
            format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
          />
        </span>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <SequenceDisplay sequence={c.sequence || ''} />
      </div>

      <ScoreBar label="Fold Stability"    value={c.fold_stability_score} />
      <ScoreBar label="Binding Score"     value={c.binding_score} />
      <ScoreBar label="Epitope Quality"   value={c.epitope_quality_score} />
      <ScoreBar label="Lysine Access"     value={c.lysine_accessibility_score} />
      <ScoreBar label="Ternary Geometry"  value={c.ternary_feasibility_score} />
      <ScoreBar label="Hook Safety"       value={1 - (c.hook_penalty ?? 0.3)} />

      {c.verdict && (
        <p style={{
          fontFamily: 'var(--font-body)',
          fontSize: '12px',
          fontStyle: 'italic',
          color: 'var(--text-secondary)',
          marginTop: '16px',
          lineHeight: 1.5,
        }}>
          {c.verdict}
        </p>
      )}

      {/* Score trajectory sparkline + lineage */}
      {c.score_trajectory && c.score_trajectory.length > 1 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginTop: '12px',
        }}>
          <SparkLine trajectory={c.score_trajectory} />
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            color: 'var(--text-muted)',
          }}>
            {c.score_trajectory.map(v => v.toFixed(2)).join(' → ')}
          </span>
        </div>
      )}

      {c.lineage_summary && (
        <p style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '9px',
          color: 'var(--text-muted)',
          marginTop: '6px',
          letterSpacing: '0.04em',
        }}>
          {c.lineage_summary}
        </p>
      )}

      {c.experimental_hypothesis && (
        <p style={{
          fontFamily: 'var(--font-body)',
          fontSize: '11px',
          fontStyle: 'italic',
          color: 'var(--cyan)',
          marginTop: '8px',
          lineHeight: 1.5,
          borderTop: '1px solid var(--border)',
          paddingTop: '8px',
        }}>
          ↳ {c.experimental_hypothesis}
        </p>
      )}

      {c.linker_display && (
        <p style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: 'var(--text-muted)',
          marginTop: '8px',
        }}>
          LINKER: {c.linker_display}
        </p>
      )}

      {c.hook_result?.high_risk && (
        <div style={{
          marginTop: '12px',
          padding: '8px 12px',
          background: 'rgba(255,170,0,0.10)',
          borderTop: '1px solid var(--amber)',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: 'var(--amber)',
        }}>
          ⚠  HIGH HOOK EFFECT RISK
        </div>
      )}

      {c.ternary_warning && (
        <div style={{
          marginTop: '8px',
          padding: '8px 12px',
          background: 'rgba(255,68,85,0.10)',
          borderTop: '1px solid var(--red)',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: 'var(--red)',
        }}>
          ✕  {c.ternary_warning}
        </div>
      )}
    </motion.div>
  )
}

// ─── Radar theme ──────────────────────────────────────────────────────────────
const radarTheme = {
  background: 'transparent',
  text: { fill: '#7a9bb5', fontSize: 10, fontFamily: 'Fragment Mono, monospace' },
  grid: { line: { stroke: '#1a3050', strokeWidth: 1 } },
}

const LIMITATIONS = [
  'Docking scores are proxies for binding affinity, not true Kd values',
  'rna-tools 3D structures are approximate backbone models, not experimental structures',
  'Hook penalty uses literature Kd₂ for pomalidomide/CRBN (5 nM fixed)',
  'Ternary complex geometry uses rigid-body approximation — linker conformational flexibility not modelled',
  'Epitope/lysine scores use SASA-estimated contact residues, not parsed from docked complex',
  'Degradation model generalisation: 80.8% known targets, 62.3% novel targets (Ribes et al. 2024)',
]

// ─── Main view ────────────────────────────────────────────────────────────────
export default function ResultsView({ results, onReset }) {
  const [selected, setSelected] = useState(0)
  const candidates = results?.candidates || []
  const current    = candidates[selected]

  const radarData = current
    ? [
        { component: 'Fold',    score: current.fold_stability_score        ?? 0.5 },
        { component: 'Binding', score: current.binding_score               ?? 0.5 },
        { component: 'Epitope', score: current.epitope_quality_score       ?? 0.5 },
        { component: 'Lysine',  score: current.lysine_accessibility_score  ?? 0.5 },
        { component: 'Ternary', score: current.ternary_feasibility_score   ?? 0.5 },
      ]
    : []

  return (
    <div style={{ minHeight: '100vh', padding: '40px 48px' }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '8px',
      }}>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: '28px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            letterSpacing: '-0.01em',
          }}>
            {results?.protein_id}
          </div>
          <div style={{
            fontFamily: 'var(--font-body)',
            fontSize: '14px',
            color: 'var(--text-secondary)',
            marginTop: '4px',
          }}>
            {candidates.length} candidates ranked by degradability
          </div>
        </div>
        <button
          onClick={onReset}
          style={{
            background: 'transparent',
            border: '1px solid var(--border)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            padding: '8px 16px',
            cursor: 'crosshair',
            letterSpacing: '0.05em',
          }}
        >
          NEW RUN
        </button>
      </div>

      {/* ── Summary stats bar ──────────────────────────────────────────────── */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        color: 'var(--text-muted)',
        marginBottom: '32px',
        borderBottom: '1px solid var(--border)',
        paddingBottom: '16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '8px',
      }}>
        <span>
          {results?.n_generated} generated
          {'  //  '}{results?.n_stable} stable folds
          {'  //  '}{results?.n_docked} docked
          {'  //  '}{candidates.length} ranked
          {results?.n_literature > 0 && `  //  ${results.n_literature} from literature`}
        </span>
        {results?.total_elapsed && (
          <span style={{ color: 'var(--cyan)' }}>
            total {Math.floor(results.total_elapsed / 60)}m {Math.round(results.total_elapsed % 60)}s
          </span>
        )}
      </div>

      {/* ── Two-column body ────────────────────────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '55% 45%',
        gap: '24px',
        alignItems: 'start',
      }}>

        {/* Left — candidate cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {candidates.map((c, i) => (
            <CandidateCard
              key={c.id || i}
              candidate={c}
              rank={i}
              isSelected={selected === i}
              onClick={() => setSelected(i)}
            />
          ))}

          {/* Limitations */}
          <details style={{ marginTop: '32px' }}>
            <summary style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: 'var(--text-muted)',
              cursor: 'crosshair',
              letterSpacing: '0.05em',
              listStyle: 'none',
              userSelect: 'none',
            }}>
              Known model limitations ▾
            </summary>
            <div style={{
              marginTop: '16px',
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              color: 'var(--text-muted)',
              lineHeight: 2.2,
              borderLeft: '1px solid var(--border)',
              paddingLeft: '16px',
            }}>
              {LIMITATIONS.map((l, i) => <div key={i}>// {l}</div>)}
            </div>
          </details>
        </div>

        {/* Right — sticky detail panel */}
        <div style={{
          position: 'sticky',
          top: '40px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}>

          {/* Protein structure viewer */}
          <ProteinViewer
            proteinId={results?.protein_id}
            selectedCandidate={current}
          />

          {/* Radar chart */}
          <AnimatePresence mode="wait">
            <motion.div
              key={selected}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                padding: '24px',
                height: '300px',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                color: 'var(--text-muted)',
                marginBottom: '8px',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
              }}>
                Degradability Profile
              </div>
              {radarData.length > 0 && (
                <Radar
                  data={radarData}
                  keys={['score']}
                  indexBy="component"
                  maxValue={1}
                  width={300}
                  height={240}
                  margin={{ top: 24, right: 48, bottom: 24, left: 48 }}
                  curve="linearClosed"
                  borderWidth={2}
                  borderColor="var(--cyan)"
                  gridLevels={4}
                  gridShape="linear"
                  gridLabelOffset={12}
                  enableDots
                  dotSize={6}
                  dotColor="var(--cyan)"
                  dotBorderWidth={2}
                  dotBorderColor="var(--bg-primary)"
                  fillOpacity={0.15}
                  colors={['var(--cyan)']}
                  theme={radarTheme}
                  animate
                  motionConfig="gentle"
                />
              )}
            </motion.div>
          </AnimatePresence>

          {/* Metadata panel */}
          {current && (
            <AnimatePresence mode="wait">
              <motion.div
                key={selected + '-meta'}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  padding: '16px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  lineHeight: 2,
                }}
              >
                <div>
                  GENERATION{'  '}
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {current.generation_method || 'biased SELEX'}
                  </span>
                </div>
                <div>
                  SCAFFOLD{'  '}
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {current.scaffold || 'stem-loop'}
                  </span>
                </div>
                <div>
                  MFE{'  '}
                  <span style={{ color: 'var(--cyan)' }}>
                    {current.mfe != null ? `${current.mfe.toFixed(1)} kcal/mol` : 'n/a'}
                  </span>
                </div>
                <div>
                  EST. Kd{'  '}
                  <span style={{ color: 'var(--cyan)' }}>
                    {current.kd_estimate || 'n/a'}
                  </span>
                </div>
                {current.linker_display && (
                  <div>
                    LINKER{'  '}
                    <span style={{ color: 'var(--text-secondary)' }}>
                      {current.linker_display}
                    </span>
                  </div>
                )}
                <div style={{ marginTop: '8px', color: 'var(--text-muted)', fontSize: '9px', lineHeight: 1.6 }}>
                  {current.generation_bias}
                </div>
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  )
}

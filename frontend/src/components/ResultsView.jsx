import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import NumberFlow from '@number-flow/react'
import CandidateCard from './CandidateCard'
import DetailPanel from './DetailPanel'
import ScoringWeights, { DEFAULT_WEIGHTS } from './ScoringWeights'
import Limitations from './Limitations'
import ProteinViewer from './ProteinViewer'
import ExperimentalAptamers from './ExperimentalAptamers'
import { TooltipProvider } from './ui/Tooltip'

function rerank(candidates, weights) {
  return [...candidates]
    .map(c => {
      const s = c.scores
      const degradability =
        weights.fold_stability       * s.fold_stability +
        weights.binding_score        * s.binding_score +
        weights.epitope_quality      * s.epitope_quality +
        weights.lysine_accessibility * s.lysine_accessibility -
        weights.hook_penalty         * s.hook_penalty
      return { ...c, degradability: Math.max(0, Math.min(1, degradability)) }
    })
    .sort((a, b) => b.degradability - a.degradability)
    .map((c, i) => ({ ...c, rank: i + 1 }))
}

// Stagger container — children opt in via cardVariants
const listVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.15 },
  },
}

export default function ResultsView({ candidates, protein, summary, onReset }) {
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS)
  const [selectedCandidate, setSelectedCandidate] = useState(candidates?.[0] ?? null)
  const [pdbData] = useState(null)

  const ranked = rerank(candidates ?? [], weights)

  const handleWeightsChange = useCallback((newWeights) => {
    setWeights(newWeights)
  }, [])

  return (
    <TooltipProvider>
      <div style={{ padding: '40px', minHeight: '100vh' }}>
        {/* Header */}
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
            <div>
              <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '24px', color: 'var(--text-primary)' }}>
                {protein?.name ?? 'Protein Target'}
                <span style={{ color: 'var(--text-muted)', fontSize: '18px', marginLeft: '12px' }}>
                  {protein?.id}
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
              <span style={{ fontFamily: 'DM Sans, sans-serif', fontSize: '13px', color: 'var(--text-secondary)' }}>
                5 candidates ranked by degradability
              </span>
              <button
                onClick={onReset}
                style={{
                  background: 'none',
                  border: '1px solid var(--border)',
                  color: 'var(--text-muted)',
                  fontFamily: 'Fragment Mono, monospace',
                  fontSize: '11px',
                  padding: '6px 12px',
                  cursor: 'crosshair',
                }}
              >
                ← new target
              </button>
            </div>
          </div>

          <div style={{ height: '1px', background: 'var(--border)', marginBottom: '12px' }} />

          {/* Summary stats with NumberFlow */}
          {summary && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5 }}
              style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontFamily: 'Fragment Mono, monospace', fontSize: '12px', color: 'var(--text-secondary)' }}
            >
              <StatCount value={summary.generated} label="generated" />
              <Sep />
              <StatCount value={summary.stable_folds} label="stable folds" />
              <Sep />
              <StatCount value={summary.docked} label="docked" />
              <Sep />
              <StatCount value={summary.ranked} label="ranked" />
              <Sep />
              <span>
                completed in{' '}
                <span style={{ color: 'var(--text-primary)' }}>
                  <NumberFlow value={summary.elapsed_s} />s
                </span>
              </span>
            </motion.div>
          )}
        </div>

        {/* Full-width protein viewer */}
        <div style={{ marginBottom: '24px' }}>
          <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: '8px' }}>
            Target Structure  ·  {protein?.id}
            {selectedCandidate && (
              <span style={{ color: 'var(--accent-amber)', marginLeft: '12px' }}>
                binding site: candidate #{selectedCandidate.rank}
              </span>
            )}
          </div>
          <ProteinViewer
            proteinId={protein?.id}
            selectedCandidate={selectedCandidate}
          />
        </div>

        {/* Two-column layout */}
        <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start' }}>
          {/* Left: candidate list 55% */}
          <div style={{ flex: '0 0 55%', minWidth: 0 }}>
            {/* Stagger container */}
            <motion.div
              variants={listVariants}
              initial="hidden"
              animate="visible"
            >
              {ranked.map(candidate => (
                <CandidateCard
                  key={candidate.id}
                  candidate={candidate}
                  isSelected={selectedCandidate?.id === candidate.id}
                  onSelect={setSelectedCandidate}
                />
              ))}
            </motion.div>

            <ScoringWeights weights={weights} onWeightsChange={handleWeightsChange} />
            <Limitations />
            <ExperimentalAptamers proteinId={protein?.id} />
          </div>

          {/* Right: detail panel 45% sticky */}
          <div style={{ flex: '0 0 calc(45% - 24px)', position: 'sticky', top: '40px', maxHeight: 'calc(100vh - 80px)', overflow: 'hidden' }}>
            <DetailPanel
              candidate={selectedCandidate}
              proteinId={protein?.id}
              pdbData={pdbData}
            />
          </div>
        </div>
      </div>
    </TooltipProvider>
  )
}

function StatCount({ value, label }) {
  return (
    <span>
      <span style={{ color: 'var(--text-primary)' }}>
        <NumberFlow value={value} />
      </span>
      {' '}{label}
    </span>
  )
}

function Sep() {
  return <span style={{ color: 'var(--text-muted)' }}>//</span>
}

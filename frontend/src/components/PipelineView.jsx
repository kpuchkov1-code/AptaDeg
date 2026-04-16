import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import NumberFlow from '@number-flow/react'
import PipelineSteps from './PipelineSteps'
import MolecularViewer from './MolecularViewer'
import { PIPELINE_STEPS, STEP_DESCRIPTIONS, MOCK_CANDIDATES, MOCK_SUMMARY, MOCK_PROTEIN } from '../mockData'

const STEP_DURATIONS = [3200, 2800, 2000, 4500, 5000, 8000, 3000, 2500, 1500]

// Each log line has a unique key so AnimatePresence can track it
let logKeyCounter = 0

export default function PipelineView({ submission, onComplete }) {
  const [activeStepIdx, setActiveStepIdx] = useState(0)
  const [completedStepIds, setCompletedStepIds] = useState([])
  const [elapsedTimes, setElapsedTimes] = useState({})
  const [logLines, setLogLines] = useState([
    { id: logKeyCounter++, text: `> initialising pipeline for target ${submission?.proteinId ?? '...'}` },
  ])
  const [candidateCount, setCandidateCount] = useState(0)
  const [proteinPdb, setProteinPdb] = useState(null)
  const [showViewer, setShowViewer] = useState(false)
  const [pocketSites, setPocketSites] = useState(false)
  const [showDocked, setShowDocked] = useState(false)
  const stepStartRef = useRef(Date.now())
  const finishedRef = useRef(false)

  const addLog = useCallback((text) => {
    setLogLines(prev => {
      const next = [...prev, { id: logKeyCounter++, text }]
      return next.slice(-8) // keep last 8, display 4
    })
  }, [])

  useEffect(() => {
    let cancelled = false

    async function runSteps() {
      try {
        const res = await fetch(`/api/fetch-structure?id=${submission?.proteinId ?? '4OLI'}`)
        if (res.ok) {
          const data = await res.json()
          if (data.pdb) setProteinPdb(data.pdb)
        }
      } catch (_) {}

      for (let i = 0; i < PIPELINE_STEPS.length; i++) {
        if (cancelled) return
        const step = PIPELINE_STEPS[i]
        stepStartRef.current = Date.now()
        setActiveStepIdx(i)
        addLog(`> ${step.label.toLowerCase()}...`)

        if (step.key === 'fetch_structure') {
          setTimeout(() => {
            addLog(`> parsed ${MOCK_PROTEIN.residue_count} residues, ${MOCK_PROTEIN.lysine_count} surface-exposed lysines`)
            setShowViewer(true)
          }, 900)
        }
        if (step.key === 'generate_library') {
          setTimeout(() => { addLog('> querying Aptagen database...'); setCandidateCount(247) }, 500)
        }
        if (step.key === 'fold_filter') {
          addLog('> running ViennaRNA fold filter (MFE < −5.0 kcal/mol)...')
          setTimeout(() => { addLog('> 71 sequences passed stability threshold'); setCandidateCount(71) }, STEP_DURATIONS[i] * 0.6)
        }
        if (step.key === 'predict_3d') {
          addLog('> predicting 3D aptamer structures (rna-tools)...')
          setTimeout(() => setCandidateCount(25), 400)
        }
        if (step.key === 'docking') {
          addLog('> running rDock protein–RNA docking...')
          setTimeout(() => { addLog('> top score: −284.7 (est. Kd ≈ 2.3 nM)'); setShowDocked(true) }, STEP_DURATIONS[i] * 0.7)
        }
        if (step.key === 'identify_sites') {
          setTimeout(() => { setPocketSites(true); addLog('> 3 pockets found, top vol 312 Å³') }, STEP_DURATIONS[i] * 0.5)
        }
        if (step.key === 'epitope_score') {
          addLog('> checking CRBN contact residues Y384 W386 H378 H353...')
          setTimeout(() => addLog('> 0 candidates flagged E3-inhibitory'), 800)
        }
        if (step.key === 'hook_penalty') {
          addLog('> Kd2 anchor: 5 nM (pomalidomide→CRBN, literature)')
          setTimeout(() => addLog('> 1 candidate HIGH HOOK RISK'), 600)
        }

        await sleep(STEP_DURATIONS[i])
        if (cancelled) return

        const elapsed = ((Date.now() - stepStartRef.current) / 1000).toFixed(1)
        setElapsedTimes(prev => ({ ...prev, [PIPELINE_STEPS[i].id]: elapsed }))
        setCompletedStepIds(prev => [...prev, PIPELINE_STEPS[i].id])
      }

      if (!cancelled && !finishedRef.current) {
        finishedRef.current = true
        addLog('> pipeline complete — 5 candidates ranked')
        await sleep(600)
        onComplete({
          candidates: MOCK_CANDIDATES,
          protein: { ...MOCK_PROTEIN, id: submission?.proteinId ?? '4OLI' },
          summary: MOCK_SUMMARY,
        })
      }
    }

    runSteps()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const activeStep = PIPELINE_STEPS[activeStepIdx]
  const allDone = completedStepIds.length === PIPELINE_STEPS.length
  const visibleLogs = logLines.slice(-4)

  return (
    <div style={{ minHeight: '100vh', padding: '40px', display: 'flex', flexDirection: 'column', gap: '28px' }}>
      {/* Header */}
      <div>
        <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
          {submission?.proteinId}  ·  E3: {submission?.e3}  ·  {submission?.cellLine}
        </div>
        <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '20px', color: 'var(--text-primary)' }}>
          Pipeline running
          {!allDone && <motion.span animate={{ opacity: [1, 0, 1] }} transition={{ duration: 1.2, repeat: Infinity }} style={{ color: 'var(--accent-cyan)' }}> ...</motion.span>}
          {allDone && <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ color: 'var(--accent-green)' }}> — complete</motion.span>}
        </div>
      </div>

      {/* Two-column */}
      <div style={{ display: 'flex', gap: '32px', flex: 1 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '24px', minWidth: 0 }}>
          <PipelineSteps
            activeStepId={activeStep?.id}
            completedStepIds={completedStepIds}
            elapsedTimes={elapsedTimes}
          />

          {/* Step description */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeStep?.key}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              style={{ fontFamily: 'DM Sans, sans-serif', fontSize: '14px', color: 'var(--text-secondary)' }}
            >
              {allDone ? 'All steps complete. Loading results...' : (STEP_DESCRIPTIONS[activeStep?.key] ?? '')}
            </motion.div>
          </AnimatePresence>

          {/* Candidate counter */}
          <AnimatePresence>
            {candidateCount > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}
              >
                <span style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '32px', color: 'var(--accent-cyan)' }}>
                  <NumberFlow value={candidateCount} />
                </span>
                <span style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '12px', color: 'var(--text-muted)' }}>
                  candidates in pool
                </span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Log panel */}
          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            padding: '16px',
            minHeight: '96px',
            overflow: 'hidden',
          }}>
            <AnimatePresence initial={false} mode="popLayout">
              {visibleLogs.map(line => (
                <motion.div
                  key={line.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
                  transition={{ duration: 0.18 }}
                  style={{
                    fontFamily: 'Fragment Mono, monospace',
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    lineHeight: '1.7',
                  }}
                >
                  {line.text}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>

        {/* Molecular viewer */}
        <AnimatePresence>
          {showViewer && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6 }}
              style={{
                width: '380px',
                flexShrink: 0,
                background: '#020810',
                border: '1px solid var(--border)',
                position: 'relative',
                minHeight: '340px',
              }}
            >
              <MolecularViewer
                pdbData={proteinPdb}
                proteinId={submission?.proteinId ?? '4OLI'}
                residueCount={MOCK_PROTEIN.residue_count}
                showPockets={pocketSites}
                showDocked={showDocked}
                autoRotate
                rotateSpeed={0.3}
                mode="pipeline"
              />
              <div style={{
                position: 'absolute',
                bottom: '10px',
                left: '12px',
                fontFamily: 'Fragment Mono, monospace',
                fontSize: '10px',
                color: 'var(--text-muted)',
                pointerEvents: 'none',
              }}>
                {submission?.proteinId}  ·  {MOCK_PROTEIN.residue_count} residues
                {showDocked && <span>  ·  <span style={{ color: 'var(--accent-cyan)' }}>aptamer docked</span></span>}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

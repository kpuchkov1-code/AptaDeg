import { motion, AnimatePresence } from 'framer-motion'
import { PIPELINE_STEPS } from '../mockData'

// Framer Motion variants per step state
const nodeVariants = {
  inactive: {
    borderColor: 'var(--border)',
    backgroundColor: '#0a1628',
    transition: { duration: 0.25 },
  },
  active: {
    borderColor: 'var(--accent-cyan)',
    backgroundColor: '#0f1f35',
    transition: { duration: 0.25 },
  },
  complete: {
    borderColor: '#00ff9d',
    backgroundColor: 'rgba(0,255,157,0.08)',
    transition: { duration: 0.3 },
  },
}

const pulseVariants = {
  inactive: { scale: 1, opacity: 0.4 },
  active: {
    scale: [1, 1.15, 1],
    opacity: 1,
    transition: { duration: 1, repeat: Infinity, ease: 'easeInOut' },
  },
  complete: { scale: 1, opacity: 1 },
}

function nodeState(stepId, activeStepId, completedStepIds) {
  if (completedStepIds.includes(stepId)) return 'complete'
  if (stepId === activeStepId) return 'active'
  return 'inactive'
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <polyline points="2,7 5.5,11 12,3" stroke="#00ff9d" strokeWidth="2" strokeLinecap="square" />
    </svg>
  )
}

function DotIcon({ state }) {
  return (
    <motion.div
      variants={pulseVariants}
      style={{
        width: '8px',
        height: '8px',
        background: state === 'active' ? '#00d4ff' : '#3d5a75',
      }}
    />
  )
}

function ConnectorLine({ leftState, rightState }) {
  const filled = leftState === 'complete'
  const filling = leftState === 'complete' && rightState === 'active'

  return (
    <div style={{
      flex: 1,
      height: '1px',
      background: 'var(--border)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {(filled || filling) && (
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: '100%' }}
          transition={{ duration: 0.5, ease: 'easeInOut' }}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            height: '100%',
            background: '#00d4ff',
          }}
        />
      )}
    </div>
  )
}

export default function PipelineSteps({ activeStepId, completedStepIds, elapsedTimes }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', width: '100%' }}>
      {PIPELINE_STEPS.map((step, idx) => {
        const state = nodeState(step.id, activeStepId, completedStepIds)
        const elapsed = elapsedTimes?.[step.id]
        const nextState = idx < PIPELINE_STEPS.length - 1
          ? nodeState(PIPELINE_STEPS[idx + 1].id, activeStepId, completedStepIds)
          : null

        return (
          <div
            key={step.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              flex: idx < PIPELINE_STEPS.length - 1 ? 1 : '0 0 auto',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
              <motion.div
                animate={state}
                variants={nodeVariants}
                style={{
                  width: '40px',
                  height: '40px',
                  border: '1px solid',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <AnimatePresence mode="wait">
                  {state === 'complete' ? (
                    <motion.div
                      key="check"
                      initial={{ opacity: 0, scale: 0.6 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ duration: 0.2 }}
                    >
                      <CheckIcon />
                    </motion.div>
                  ) : (
                    <motion.div
                      key="dot"
                      initial={{ opacity: 0 }}
                      variants={pulseVariants}
                      animate={state}
                    >
                      <DotIcon state={state} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>

              <div style={{ textAlign: 'center' }}>
                <div style={{
                  fontFamily: 'Fragment Mono, monospace',
                  fontSize: '10px',
                  color: state === 'complete' ? '#00ff9d' : state === 'active' ? '#00d4ff' : 'var(--text-muted)',
                  whiteSpace: 'nowrap',
                  transition: 'color 0.25s',
                }}>
                  {step.label}
                </div>
                {elapsed && (
                  <div style={{
                    fontFamily: 'Fragment Mono, monospace',
                    fontSize: '9px',
                    color: 'var(--text-muted)',
                    marginTop: '2px',
                  }}>
                    {elapsed}s
                  </div>
                )}
              </div>
            </div>

            {idx < PIPELINE_STEPS.length - 1 && (
              <div style={{ flex: 1, paddingBottom: '22px', minWidth: '6px' }}>
                <ConnectorLine leftState={state} rightState={nextState} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

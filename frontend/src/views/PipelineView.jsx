import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const STATUS_COLOR = {
  pending:  'var(--text-muted)',
  running:  'var(--cyan)',
  complete: 'var(--green)',
  failed:   'var(--red)',
}

const STATUS_ICON = {
  pending:  '○',
  running:  '●',
  complete: '✓',
  failed:   '✕',
}

export default function PipelineView({ steps, pipelineSteps, log, error, progress = 0 }) {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '48px 24px',
      gap: '48px',
    }}>
      {/* Header + progress % */}
      <div style={{ textAlign: 'center' }}>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: '24px',
          fontWeight: 700,
          color: 'var(--text-secondary)',
          letterSpacing: '-0.01em',
        }}>
          {error ? 'Pipeline Failed' : 'Pipeline Running'}
        </div>
        {!error && (
          <div style={{
            marginTop: '8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--cyan)',
            letterSpacing: '0.08em',
          }}>
            {progress}%
          </div>
        )}
        {/* Progress bar */}
        {!error && (
          <div style={{
            marginTop: '8px',
            width: '200px',
            height: '2px',
            background: 'var(--border)',
            position: 'relative',
            margin: '8px auto 0',
          }}>
            <motion.div
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              style={{
                position: 'absolute', left: 0, top: 0,
                height: '100%', background: 'var(--cyan)',
              }}
            />
          </div>
        )}
      </div>

      {/* Step nodes — two-row layout: icons+connectors / labels */}
      <div style={{
        width: '100%',
        maxWidth: '920px',
        overflowX: 'auto',
        paddingBottom: '8px',
      }}>
        {/* Row 1: icons and connector lines, all perfectly centred */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          width: '100%',
        }}>
          {pipelineSteps.map((step, i) => {
            const status = error && steps[step.id]?.status === 'pending'
              ? 'pending'
              : (steps[step.id]?.status || 'pending')
            const color = STATUS_COLOR[status] || STATUS_COLOR.pending
            const icon  = STATUS_ICON[status]  || '○'
            return (
              <React.Fragment key={step.id}>
                <motion.div
                  animate={status === 'running' ? {
                    boxShadow: [
                      `0 0 0px ${color}`,
                      `0 0 18px ${color}`,
                      `0 0 0px ${color}`,
                    ],
                  } : {}}
                  transition={{ duration: 1.2, repeat: Infinity }}
                  style={{
                    flexShrink: 0,
                    width: '40px', height: '40px',
                    border: `1px solid ${color}`,
                    background: status === 'complete' ? 'rgba(0,255,157,0.08)'
                              : status === 'running'  ? 'rgba(0,212,255,0.08)'
                              : 'var(--bg-secondary)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '16px',
                    color,
                    transition: 'all 0.3s',
                  }}
                >
                  {icon}
                </motion.div>
                {i < pipelineSteps.length - 1 && (
                  <div style={{
                    flex: 1,
                    height: '1px',
                    minWidth: '4px',
                    background: status === 'complete' ? 'var(--cyan)' : 'var(--border)',
                    transition: 'background 0.5s',
                  }} />
                )}
              </React.Fragment>
            )
          })}
        </div>

        {/* Row 2: labels beneath each icon */}
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          width: '100%',
          marginTop: '8px',
        }}>
          {pipelineSteps.map((step, i) => {
            const status = error && steps[step.id]?.status === 'pending'
              ? 'pending'
              : (steps[step.id]?.status || 'pending')
            const color = STATUS_COLOR[status] || STATUS_COLOR.pending
            const elapsed = steps[step.id]?.elapsed
            return (
              <React.Fragment key={step.id}>
                <div style={{
                  flexShrink: 0,
                  width: '40px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '2px',
                }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '8px',
                    color,
                    textAlign: 'center',
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    lineHeight: 1.3,
                  }}>
                    {step.label}
                  </span>
                  {elapsed != null && (
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '8px',
                      color: 'var(--text-muted)',
                    }}>
                      {elapsed}s
                    </span>
                  )}
                </div>
                {i < pipelineSteps.length - 1 && (
                  <div style={{ flex: 1, minWidth: '4px' }} />
                )}
              </React.Fragment>
            )
          })}
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div style={{
          width: '100%',
          maxWidth: '600px',
          padding: '16px',
          background: 'rgba(255,68,85,0.1)',
          border: '1px solid var(--red)',
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          color: 'var(--red)',
          lineHeight: 1.6,
        }}>
          ✕  {error}
        </div>
      )}

      {/* Log stream */}
      <div style={{
        width: '100%',
        maxWidth: '600px',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        padding: '16px',
        height: '160px',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        gap: '2px',
      }}>
        <AnimatePresence initial={false}>
          {log.length === 0 && (
            <motion.div
              key="waiting"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--text-muted)',
                lineHeight: 1.8,
              }}
            >
              &gt; Initialising pipeline...
            </motion.div>
          )}
          {log.map((line, i) => (
            <motion.div
              key={line + i}
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: Math.max(0.1, 1 - i * 0.18), y: 0 }}
              transition={{ duration: 0.2 }}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: i === 0 ? 'var(--text-secondary)' : 'var(--text-muted)',
                lineHeight: 1.8,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {line}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

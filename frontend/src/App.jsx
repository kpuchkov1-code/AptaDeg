import { AnimatePresence, motion } from 'framer-motion'
import { usePipeline } from './hooks/usePipeline'
import LandingView  from './views/LandingView'
import PipelineView from './views/PipelineView'
import ResultsView  from './views/ResultsView'
import './styles/tokens.css'

export default function App() {
  const {
    phase, steps, results, error, log, progress,
    runPipeline, resumePipeline, PIPELINE_STEPS,
  } = usePipeline()

  const handleReset = () => window.location.reload()

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg-primary)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      <AnimatePresence mode="wait">

        {phase === 'idle' && (
          <motion.div
            key="landing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -30 }}
            transition={{ duration: 0.4 }}
            style={{ position: 'absolute', inset: 0 }}
          >
            <LandingView onRun={runPipeline} onResume={resumePipeline} />
          </motion.div>
        )}

        {(phase === 'running' || phase === 'failed') && (
          <motion.div
            key="pipeline"
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            style={{ position: 'absolute', inset: 0 }}
          >
            <PipelineView
              steps={steps}
              pipelineSteps={PIPELINE_STEPS}
              log={log}
              error={error}
              progress={progress}
            />
            {phase === 'failed' && (
              <div style={{ textAlign: 'center', marginTop: '24px' }}>
                <button
                  onClick={handleReset}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--border)',
                    color: 'var(--text-muted)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    padding: '8px 20px',
                    cursor: 'crosshair',
                    letterSpacing: '0.05em',
                  }}
                >
                  TRY AGAIN
                </button>
              </div>
            )}
          </motion.div>
        )}

        {phase === 'complete' && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            style={{ position: 'absolute', inset: 0, overflowY: 'auto' }}
          >
            <ResultsView results={results} onReset={handleReset} />
          </motion.div>
        )}

      </AnimatePresence>
    </div>
  )
}

import { useState, useEffect, useCallback } from 'react'
import { io } from 'socket.io-client'

const SOCKET_URL = 'http://localhost:5000'
const API_URL    = 'http://localhost:5000/api'

export const PIPELINE_STEPS = [
  { id: 'crbn_load',  label: 'CRBN',       pct: 2  },
  { id: 'fetch',      label: 'Fetch',      pct: 5  },
  { id: 'clean',      label: 'Clean',      pct: 8  },
  { id: 'fpocket',    label: 'Pockets',    pct: 12 },
  { id: 'literature', label: 'Literature', pct: 22 },
  { id: 'generate',   label: 'Generate',   pct: 22 },
  { id: 'fold',       label: 'Fold',       pct: 28 },
  { id: 'structures', label: '3D Struct',  pct: 40 },
  { id: 'docking',    label: 'Docking',    pct: 60 },
  { id: 'scoring',    label: 'Scoring',    pct: 65 },
  { id: 'refine_1',   label: 'Refine ①',  pct: 78 },
  { id: 'refine_2',   label: 'Refine ②',  pct: 89 },
  { id: 'refine_3',   label: 'Refine ③',  pct: 97 },
]

export function usePipeline() {
  const [socket,  setSocket]  = useState(null)
  const [runId,   setRunId]   = useState(null)
  const [phase,   setPhase]   = useState('idle')   // idle | running | complete | failed
  const [steps,   setSteps]   = useState({})
  const [results, setResults] = useState(null)
  const [error,   setError]   = useState(null)
  const [log,      setLog]     = useState([])
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const s = io(SOCKET_URL, { transports: ['websocket', 'polling'] })
    setSocket(s)

    s.on('step_update', (data) => {
      if (data.step) {
        setSteps(prev => ({
          ...prev,
          [data.step]: {
            status:   data.status,
            message:  data.message,
            elapsed:  data.elapsed,
            progress: data.progress,
          },
        }))
        // Track highest completed step's progress %
        if (data.status === 'complete' && data.progress != null) {
          setProgress(prev => Math.max(prev, data.progress))
        }
      }
      if (data.message) {
        setLog(prev => [`> ${data.message}`, ...prev].slice(0, 8))
      }
    })

    s.on('pipeline_complete', async (data) => {
      try {
        const res  = await fetch(`${API_URL}/results/${data.run_id}`)
        const json = await res.json()
        setResults(json)
        setPhase('complete')
      } catch (e) {
        setError('Failed to fetch results: ' + e.message)
        setPhase('failed')
      }
    })

    s.on('pipeline_failed', (data) => {
      setError(data.error)
      setPhase('failed')
    })

    return () => s.disconnect()
  }, [])

  const runPipeline = useCallback(async (proteinId, e3Ligase, cellLine) => {
    setPhase('running')
    setSteps({})
    setResults(null)
    setError(null)
    setLog([])
    setProgress(0)

    try {
      const res = await fetch(`${API_URL}/run`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          protein_id: proteinId,
          e3_ligase:  e3Ligase,
          cell_line:  cellLine,
          socket_id:  socket?.id,
        }),
      })
      const { run_id, error: apiError } = await res.json()
      if (apiError) throw new Error(apiError)
      setRunId(run_id)
    } catch (e) {
      setError(e.message)
      setPhase('failed')
    }
  }, [])

  const resumePipeline = useCallback(async (proteinId) => {
    setPhase('running')
    setSteps({})
    setResults(null)
    setError(null)
    setLog([])
    setProgress(60)

    try {
      const res = await fetch(`${API_URL}/resume`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ protein_id: proteinId, socket_id: socket?.id }),
      })
      const { run_id, error: apiError } = await res.json()
      if (apiError) throw new Error(apiError)
      setRunId(run_id)
    } catch (e) {
      setError(e.message)
      setPhase('failed')
    }
  }, [])

  return { phase, steps, results, error, log, progress, runId, runPipeline, resumePipeline, PIPELINE_STEPS }
}

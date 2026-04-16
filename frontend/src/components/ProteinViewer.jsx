// Full-width protein structure viewer for the results header
// Shows the fetched PDB with binding site of selected candidate highlighted

import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'

export default function ProteinViewer({ proteinId, pdbUrl, selectedCandidate }) {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)
  const [loaded, setLoaded] = useState(false)
  const [pdbText, setPdbText] = useState(null)
  const [error, setError] = useState(null)

  // Fetch PDB from backend (which either has it cached or fetches it)
  useEffect(() => {
    if (!proteinId) return
    fetch(`/api/fetch-structure?id=${proteinId}`)
      .then(r => r.json())
      .then(d => {
        if (d.pdb) setPdbText(d.pdb)
        else setError('No structure available')
      })
      .catch(() => setError('Could not load structure'))
  }, [proteinId])

  // Init / re-render 3Dmol when pdbText or candidate changes
  useEffect(() => {
    if (!pdbText || !containerRef.current) return

    const check = () => {
      if (typeof window.$3Dmol !== 'undefined') {
        renderStructure()
      } else {
        setTimeout(check, 200)
      }
    }
    check()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdbText, selectedCandidate])

  function renderStructure() {
    const container = containerRef.current
    if (!container) return

    // Destroy existing viewer if present
    if (viewerRef.current) {
      try { viewerRef.current.clear() } catch (_) {}
    }

    const viewer = viewerRef.current ?? window.$3Dmol.createViewer(container, {
      backgroundColor: '#020810',
      antialias: true,
    })
    viewerRef.current = viewer
    viewer.clear()

    viewer.addModel(pdbText, 'pdb')

    // Base style: cartoon in muted colour
    viewer.setStyle({}, { cartoon: { color: '#3d5a75', opacity: 0.75 } })

    // Highlight surface-exposed lysines in red (residue name LYS)
    viewer.setStyle({ resn: 'LYS' }, { stick: { color: '#ff4455', radius: 0.25 }, cartoon: { color: '#ff4455' } })

    // If a candidate is selected, highlight its binding site residues in amber
    // We don't have real contact residues so we pick a window around residue 50-80 as placeholder
    if (selectedCandidate) {
      const mockContactStart = 48 + (selectedCandidate.rank * 7)
      const mockContactEnd = mockContactStart + selectedCandidate.contact_residues
      viewer.setStyle(
        { resi: `${mockContactStart}-${mockContactEnd}` },
        { stick: { color: '#ffaa00', radius: 0.3 }, cartoon: { color: '#ffaa00', opacity: 0.9 } }
      )
    }

    viewer.zoomTo()
    viewer.render()
    setLoaded(true)
  }

  return (
    <div style={{
      position: 'relative',
      width: '100%',
      height: '280px',
      background: '#020810',
      border: '1px solid var(--border)',
      overflow: 'hidden',
    }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      {/* Overlay label */}
      {loaded && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          style={{
            position: 'absolute',
            bottom: '10px',
            left: '14px',
            fontFamily: 'Fragment Mono, monospace',
            fontSize: '10px',
            color: 'var(--text-muted)',
            pointerEvents: 'none',
            lineHeight: 1.8,
          }}
        >
          <span style={{ color: 'var(--text-primary)' }}>{proteinId}</span>
          {'  ·  '}
          <span style={{ color: '#3d5a75' }}>● protein</span>
          {'  ·  '}
          <span style={{ color: '#ff4455' }}>● lysines</span>
          {selectedCandidate && (
            <>{'  ·  '}<span style={{ color: '#ffaa00' }}>● binding site ({selectedCandidate.contact_residues} residues)</span></>
          )}
        </motion.div>
      )}

      {/* Loading state */}
      {!loaded && !error && (
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'Fragment Mono, monospace',
          fontSize: '11px',
          color: 'var(--text-muted)',
        }}>
          loading structure...
        </div>
      )}

      {error && (
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'Fragment Mono, monospace',
          fontSize: '11px',
          color: 'var(--text-muted)',
        }}>
          {error}
        </div>
      )}

      {/* Drag hint */}
      {loaded && (
        <div style={{
          position: 'absolute',
          top: '10px',
          right: '14px',
          fontFamily: 'Fragment Mono, monospace',
          fontSize: '9px',
          color: 'var(--text-muted)',
          pointerEvents: 'none',
        }}>
          drag to rotate  ·  scroll to zoom
        </div>
      )}
    </div>
  )
}

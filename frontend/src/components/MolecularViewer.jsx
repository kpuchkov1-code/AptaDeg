import { useEffect, useRef, useState } from 'react'

// Wrapper around 3Dmol.js
// 3Dmol is loaded globally via CDN script tag in index.html
export default function MolecularViewer({
  pdbData,
  proteinId,
  residueCount,
  showPockets = false,
  showDocked = false,
  autoRotate = false,
  rotateSpeed = 0.5,
  mode = 'results', // 'pipeline' | 'results'
  height = '100%',
  contactResidues = [],
  accessibleLysines = [],
}) {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)
  const animRef = useRef(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const check3Dmol = () => {
      if (typeof window.$3Dmol !== 'undefined') {
        init3Dmol()
      } else {
        setTimeout(check3Dmol, 200)
      }
    }
    check3Dmol()

    function init3Dmol() {
      if (viewerRef.current) return // already initialised

      const viewer = window.$3Dmol.createViewer(container, {
        backgroundColor: '#020810',
        antialias: true,
      })
      viewerRef.current = viewer

      loadStructure(viewer)
      setReady(true)
    }

    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Update when pdbData / showDocked changes
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadStructure(viewer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdbData, showDocked, showPockets])

  function loadStructure(viewer) {
    viewer.clear()

    if (pdbData) {
      viewer.addModel(pdbData, 'pdb')
    } else {
      // Generate a minimal placeholder sphere when no real PDB available
      viewer.addShape({ type: 'sphere', x: 0, y: 0, z: 0, radius: 1, color: '#3d5a75', opacity: 0.4 })
      renderPlaceholder(viewer)
      return
    }

    const m = viewer.getModel()
    if (!m) return

    if (showDocked) {
      // Cartoon protein + stick aptamer
      viewer.setStyle({}, { cartoon: { color: '#3d5a75', opacity: 0.7 } })
      // Highlight contact residues as sticks
      if (contactResidues.length > 0) {
        viewer.setStyle(
          { resi: contactResidues },
          { stick: { color: '#ffaa00', radius: 0.3 } }
        )
      }
      // Accessible lysines as spheres
      if (accessibleLysines.length > 0) {
        viewer.setStyle(
          { resn: 'LYS', resi: accessibleLysines },
          { sphere: { color: '#ff4455', radius: 0.6 } }
        )
      }
    } else {
      // Surface representation for pipeline view
      viewer.setStyle({}, { surface: { color: '#3d5a75', opacity: 0.85 } })
    }

    if (showPockets) {
      // Show three amber pocket spheres at mock positions
      const pockets = [
        { x: 5, y: 10, z: -3 },
        { x: -8, y: 4, z: 7 },
        { x: 3, y: -6, z: 12 },
      ]
      pockets.forEach((pos, i) => {
        viewer.addShape({
          type: 'sphere',
          ...pos,
          radius: 5,
          color: '#ffaa00',
          opacity: 0.35,
        })
      })
    }

    viewer.zoomTo()
    viewer.render()

    if (autoRotate) {
      startRotation(viewer)
    }
  }

  function renderPlaceholder(viewer) {
    viewer.render()
    if (autoRotate) startRotation(viewer)
  }

  function startRotation(viewer) {
    if (animRef.current) cancelAnimationFrame(animRef.current)
    let angle = 0
    function tick() {
      angle += rotateSpeed
      viewer.rotate(rotateSpeed, { x: 0, y: 1, z: 0 })
      viewer.render()
      animRef.current = requestAnimationFrame(tick)
    }
    animRef.current = requestAnimationFrame(tick)
  }

  function stopRotation() {
    if (animRef.current) {
      cancelAnimationFrame(animRef.current)
      animRef.current = null
    }
  }

  function resumeRotation() {
    if (autoRotate && viewerRef.current) startRotation(viewerRef.current)
  }

  return (
    <div
      ref={containerRef}
      onMouseEnter={stopRotation}
      onMouseLeave={resumeRotation}
      style={{
        width: '100%',
        height: height,
        minHeight: '200px',
        position: 'relative',
        background: '#020810',
      }}
    />
  )
}

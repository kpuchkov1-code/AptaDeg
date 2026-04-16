import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'

const TITLE = 'AptaDeg'

export default function LandingView({ onRun, onResume }) {
  const [typed,    setTyped]    = useState('')
  const [showForm, setShowForm] = useState(false)
  const [proteinId, setProteinId] = useState('')
  const [e3,       setE3]       = useState('CRBN')
  const [cellLine, setCellLine] = useState('HEK293')

  useEffect(() => {
    let i = 0
    const iv = setInterval(() => {
      if (i < TITLE.length) {
        setTyped(TITLE.slice(0, ++i))
      } else {
        clearInterval(iv)
        setTimeout(() => setShowForm(true), 300)
      }
    }, 80)
    return () => clearInterval(iv)
  }, [])

  const inputStyle = {
    width: '100%',
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    color: 'var(--cyan)',
    fontFamily: 'var(--font-mono)',
    fontSize: '14px',
    padding: '14px 16px',
    outline: 'none',
    transition: 'border-color 0.2s',
  }

  const handleFocus = e => { e.target.style.borderColor = 'var(--cyan)' }
  const handleBlur  = e => { e.target.style.borderColor = 'var(--border)' }

  const handleSubmit = () => {
    const id = proteinId.trim()
    if (id) onRun(id, e3, cellLine)
  }

  const handleKey = e => {
    if (e.key === 'Enter') handleSubmit()
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '48px 24px',
    }}>
      {/* Ambient glow */}
      <div style={{
        position: 'fixed',
        bottom: 0, left: '50%',
        transform: 'translateX(-50%)',
        width: '600px', height: '300px',
        background: 'radial-gradient(ellipse at center bottom, rgba(0,212,255,0.05) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Logo */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{ marginBottom: '16px', textAlign: 'center' }}
      >
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(48px, 8vw, 80px)',
          fontWeight: 800,
          color: 'var(--cyan)',
          letterSpacing: '-0.02em',
          lineHeight: 1,
        }}>
          {typed}
          <span style={{
            opacity: typed.length < TITLE.length ? 1 : 0,
            transition: 'opacity 0.1s',
          }}>_</span>
        </div>
      </motion.div>

      {showForm && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{ width: '100%', maxWidth: '480px' }}
        >
          <p style={{
            fontFamily: 'var(--font-body)',
            color: 'var(--text-secondary)',
            fontSize: '14px',
            textAlign: 'center',
            marginBottom: '48px',
            letterSpacing: '0.02em',
          }}>
            RNA aptamer candidate generation for targeted protein degradation
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <input
              style={inputStyle}
              placeholder="Enter PDB code or UniProt ID  e.g. 6G6K"
              value={proteinId}
              onChange={e => setProteinId(e.target.value.toUpperCase())}
              onFocus={handleFocus}
              onBlur={handleBlur}
              onKeyDown={handleKey}
              autoFocus
            />

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              <select
                style={{ ...inputStyle, cursor: 'crosshair' }}
                value={e3}
                onChange={e => setE3(e.target.value)}
                onFocus={handleFocus}
                onBlur={handleBlur}
              >
                <option>CRBN</option>
                <option>VHL</option>
                <option>MDM2</option>
              </select>

              <select
                style={{ ...inputStyle, cursor: 'crosshair' }}
                value={cellLine}
                onChange={e => setCellLine(e.target.value)}
                onFocus={handleFocus}
                onBlur={handleBlur}
              >
                <option>HEK293</option>
                <option>HCT116</option>
                <option>MCF7</option>
                <option>PC3</option>
              </select>
            </div>

            <motion.button
              whileHover={{ backgroundColor: 'var(--green)' }}
              whileTap={{ scale: 0.98 }}
              transition={{ duration: 0.15 }}
              onClick={handleSubmit}
              style={{
                marginTop: '8px',
                width: '100%',
                background: 'var(--cyan)',
                color: 'var(--bg-primary)',
                border: 'none',
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '13px',
                letterSpacing: '0.1em',
                padding: '16px',
                cursor: 'crosshair',
                textTransform: 'uppercase',
              }}
            >
              Generate Aptamer Candidates
            </motion.button>

            {onResume && proteinId.trim() && (
              <motion.button
                whileHover={{ borderColor: 'var(--cyan)', color: 'var(--cyan)' }}
                whileTap={{ scale: 0.98 }}
                transition={{ duration: 0.15 }}
                onClick={() => onResume(proteinId.trim())}
                style={{
                  width: '100%',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                  fontFamily: 'var(--font-display)',
                  fontWeight: 600,
                  fontSize: '12px',
                  letterSpacing: '0.1em',
                  padding: '13px',
                  cursor: 'crosshair',
                  textTransform: 'uppercase',
                }}
              >
                Load Cached Results
              </motion.button>
            )}
          </div>

          <p style={{
            marginTop: '48px',
            textAlign: 'center',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--text-muted)',
            letterSpacing: '0.05em',
          }}>
            Binding affinity ≠ degradability{'  //  '}This tool scores what others ignore
          </p>
        </motion.div>
      )}
    </div>
  )
}

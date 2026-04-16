// DIAGNOSTIC v2
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ProteinInput } from './ui/Command'
import { Select } from './ui/Select'
import { TooltipProvider } from './ui/Tooltip'

const TITLE_CHARS = 'AptaDeg'.split('')

const E3_OPTIONS = [
  { value: 'CRBN', label: 'E3 Ligase: CRBN (cereblon)' },
  { value: 'VHL',  label: 'E3 Ligase: VHL (von Hippel-Lindau)' },
  { value: 'MDM2', label: 'E3 Ligase: MDM2 (mouse double minute 2)' },
]

const CELL_OPTIONS = [
  { value: 'HEK293', label: 'Cell line: HEK293' },
  { value: 'HCT116', label: 'Cell line: HCT116' },
  { value: 'MCF7',   label: 'Cell line: MCF7' },
  { value: 'PC3',    label: 'Cell line: PC3' },
]

// Framer Motion variants
const containerVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.08 },
  },
}

const charVariants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.06 } },
}

export default function LandingView({ onSubmit }) {
  const [titleDone, setTitleDone] = useState(false)
  const [proteinId, setProteinId] = useState('')
  const [e3, setE3] = useState('CRBN')
  const [cellLine, setCellLine] = useState('HEK293')
  const [hoverRun, setHoverRun] = useState(false)

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (!proteinId.trim()) return
    onSubmit({ proteinId: proteinId.trim().toUpperCase(), e3, cellLine })
  }

  return (
    <TooltipProvider>
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 24px',
        position: 'relative',
        overflow: 'hidden',
      }}>
        {/* Radial glow */}
        <div style={{
          position: 'absolute',
          bottom: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          width: '900px',
          height: '500px',
          background: 'radial-gradient(ellipse at bottom, rgba(0,212,255,0.04) 0%, transparent 65%)',
          pointerEvents: 'none',
        }} />

        <div style={{ width: '100%', maxWidth: '560px', zIndex: 1 }}>
          {/* Staggered character title */}
          <div style={{ marginBottom: '10px' }}>
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              onAnimationComplete={() => setTitleDone(true)}
              style={{
                fontFamily: 'Syne, sans-serif',
                fontWeight: 800,
                fontSize: '52px',
                color: 'var(--accent-cyan)',
                letterSpacing: '-0.02em',
                display: 'flex',
              }}
            >
              {TITLE_CHARS.map((ch, i) => (
                <motion.span key={i} variants={charVariants}>{ch}</motion.span>
              ))}
            </motion.div>
          </div>

          {/* Subtitle */}
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: titleDone ? 1 : 0 }}
            transition={{ duration: 0.4 }}
            style={{
              fontFamily: 'DM Sans, sans-serif',
              color: 'var(--text-secondary)',
              fontSize: '14px',
              marginBottom: '40px',
              marginTop: '0',
            }}
          >
            RNA aptamer candidate generation for targeted protein degradation
          </motion.p>

          {/* Form */}
          <motion.form
            onSubmit={handleSubmit}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: titleDone ? 1 : 0, y: titleDone ? 0 : 24 }}
            transition={{ duration: 0.2, delay: 0.15 }}
          >
            <div style={{ marginBottom: '8px' }}>
              <ProteinInput
                value={proteinId}
                onChange={setProteinId}
                onSubmit={handleSubmit}
              />
            </div>

            <div style={{ marginBottom: '8px' }}>
              <Select
                value={e3}
                onValueChange={setE3}
                options={E3_OPTIONS}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <Select
                value={cellLine}
                onValueChange={setCellLine}
                options={CELL_OPTIONS}
              />
            </div>

            <motion.button
              type="submit"
              onHoverStart={() => setHoverRun(true)}
              onHoverEnd={() => setHoverRun(false)}
              animate={{ scale: hoverRun ? 1.02 : 1 }}
              transition={{ duration: 0.15 }}
              style={{
                width: '100%',
                background: hoverRun ? 'var(--accent-green)' : 'var(--accent-cyan)',
                color: 'var(--bg-primary)',
                fontFamily: 'Syne, sans-serif',
                fontWeight: 700,
                fontSize: '13px',
                letterSpacing: '0.15em',
                padding: '14px',
                border: 'none',
                textTransform: 'uppercase',
                cursor: 'crosshair',
                transition: 'background 200ms',
              }}
            >
              Generate Aptamer Candidates
            </motion.button>
          </motion.form>
        </div>

        {/* Tagline */}
        <div style={{
          position: 'absolute',
          bottom: '24px',
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'Fragment Mono, monospace',
          fontSize: '11px',
          color: 'var(--text-muted)',
          whiteSpace: 'nowrap',
          letterSpacing: '0.02em',
        }}>
          Binding affinity ≠ degradability  //  This tool scores what others ignore
        </div>
      </div>
    </TooltipProvider>
  )
}

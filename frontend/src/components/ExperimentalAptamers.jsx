import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

export default function ExperimentalAptamers({ proteinId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(true)
  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => {
    if (!proteinId) return
    setLoading(true)
    setError(null)
    setData(null)

    fetch(`/api/experimental-aptamers?id=${proteinId}`)
      .then(r => r.json())
      .then(d => {
        setData(d)
        setLoading(false)
      })
      .catch(() => {
        setError('Could not fetch experimental data')
        setLoading(false)
      })
  }, [proteinId])

  return (
    <div style={{ marginTop: '32px' }}>
      {/* Section header */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'crosshair',
          padding: '0',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          width: '100%',
        }}
      >
        <div style={{ height: '1px', flex: 1, background: 'var(--border)' }} />
        <span style={{
          fontFamily: 'Syne, sans-serif',
          fontWeight: 700,
          fontSize: '13px',
          color: 'var(--text-secondary)',
          whiteSpace: 'nowrap',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}>
          Experimentally Validated Aptamers
        </span>
        <div style={{ height: '1px', flex: 1, background: 'var(--border)' }} />
        <ChevronIcon open={open} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: 'easeInOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ marginTop: '16px' }}>
              {/* Source legend */}
              <div style={{
                display: 'flex',
                gap: '16px',
                marginBottom: '12px',
                fontFamily: 'Fragment Mono, monospace',
                fontSize: '10px',
                color: 'var(--text-muted)',
              }}>
                <span>Sources:</span>
                <SourceBadge label="PubMed" color="var(--accent-cyan)" />
                <SourceBadge label="Aptagen DB" color="var(--accent-green)" />
                <SourceBadge label="seed CSV" color="var(--accent-amber)" />
              </div>

              {/* States */}
              {loading && <LoadingState />}
              {error && <ErrorState message={error} />}
              {data && data.aptamers?.length === 0 && <EmptyState proteinId={proteinId} />}

              {data && data.aptamers?.length > 0 && (
                <div>
                  <div style={{
                    fontFamily: 'Fragment Mono, monospace',
                    fontSize: '10px',
                    color: 'var(--text-muted)',
                    marginBottom: '10px',
                  }}>
                    {data.aptamers.length} aptamers found  ·  {data.pubmed_hits ?? 0} PubMed results searched
                  </div>

                  {data.aptamers.map((apt, i) => (
                    <AptamerRow
                      key={i}
                      apt={apt}
                      index={i}
                      expanded={expandedId === i}
                      onToggle={() => setExpandedId(expandedId === i ? null : i)}
                    />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function AptamerRow({ apt, index, expanded, onToggle }) {
  const sourceColor = {
    pubmed: 'var(--accent-cyan)',
    aptagen: 'var(--accent-green)',
    csv: 'var(--accent-amber)',
    seed: 'var(--accent-amber)',
  }[apt.source] ?? 'var(--text-muted)'

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderLeft: `3px solid ${sourceColor}`,
        marginBottom: '6px',
        overflow: 'hidden',
      }}
    >
      {/* Row header — always visible */}
      <div
        onClick={onToggle}
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto auto auto auto',
          gap: '12px',
          padding: '12px 14px',
          cursor: 'crosshair',
          alignItems: 'center',
        }}
      >
        <div style={{
          fontFamily: 'Fragment Mono, monospace',
          fontSize: '11px',
          color: 'var(--text-secondary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {apt.name ?? apt.sequence?.slice(0, 20) + '…'}
        </div>

        {apt.kd && (
          <div style={{
            fontFamily: 'Fragment Mono, monospace',
            fontSize: '11px',
            color: 'var(--accent-cyan)',
            whiteSpace: 'nowrap',
          }}>
            Kd {apt.kd}
          </div>
        )}

        {apt.length && (
          <div style={{
            fontFamily: 'Fragment Mono, monospace',
            fontSize: '10px',
            color: 'var(--text-muted)',
            whiteSpace: 'nowrap',
          }}>
            {apt.length} nt
          </div>
        )}

        <div style={{
          fontFamily: 'Fragment Mono, monospace',
          fontSize: '9px',
          color: sourceColor,
          border: `1px solid ${sourceColor}`,
          padding: '2px 6px',
          whiteSpace: 'nowrap',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}>
          {apt.source}
        </div>

        <ChevronIcon open={expanded} size={10} />
      </div>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              borderTop: '1px solid var(--border)',
              padding: '12px 14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}>
              {apt.sequence && (
                <div>
                  <Label>Sequence</Label>
                  <ColoredSeq seq={apt.sequence} />
                </div>
              )}

              <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
                {apt.selection_method && <Field label="Selection" value={apt.selection_method} />}
                {apt.cell_line && <Field label="Cell line" value={apt.cell_line} />}
                {apt.year && <Field label="Year" value={apt.year} />}
                {apt.protein_target && <Field label="Target" value={apt.protein_target} />}
              </div>

              {apt.abstract_snippet && (
                <div>
                  <Label>Abstract excerpt</Label>
                  <div style={{
                    fontFamily: 'DM Sans, sans-serif',
                    fontSize: '11px',
                    color: 'var(--text-secondary)',
                    fontStyle: 'italic',
                    lineHeight: 1.6,
                    borderLeft: '2px solid var(--border)',
                    paddingLeft: '10px',
                    marginTop: '4px',
                  }}>
                    "{apt.abstract_snippet}"
                  </div>
                </div>
              )}

              {apt.pmid && (
                <div style={{
                  fontFamily: 'Fragment Mono, monospace',
                  fontSize: '10px',
                  color: 'var(--accent-cyan)',
                }}>
                  PubMed: PMID {apt.pmid}
                  {apt.doi && <span style={{ color: 'var(--text-muted)', marginLeft: '12px' }}>DOI: {apt.doi}</span>}
                </div>
              )}

              {apt.title && (
                <div style={{
                  fontFamily: 'DM Sans, sans-serif',
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                }}>
                  {apt.title}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ── small helpers ─────────────────────────────────────────────────────────────

const NT_COLORS = { A: 'var(--accent-green)', U: 'var(--accent-red)', G: 'var(--accent-cyan)', C: 'var(--accent-amber)' }

function ColoredSeq({ seq }) {
  return (
    <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '11px', lineHeight: 1.6, marginTop: '4px', wordBreak: 'break-all' }}>
      {seq.split('').map((nt, i) => (
        <span key={i} style={{ color: NT_COLORS[nt.toUpperCase()] ?? 'var(--text-secondary)' }}>{nt}</span>
      ))}
    </div>
  )
}

function Label({ children }) {
  return (
    <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '9px', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: '2px' }}>
      {children}
    </div>
  )
}

function Field({ label, value }) {
  return (
    <div>
      <Label>{label}</Label>
      <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--text-secondary)' }}>{value}</div>
    </div>
  )
}

function SourceBadge({ label, color }) {
  return (
    <span style={{ color, border: `1px solid ${color}`, padding: '1px 5px', fontSize: '9px', letterSpacing: '0.05em' }}>
      {label}
    </span>
  )
}

function LoadingState() {
  return (
    <div style={{ padding: '20px 0', fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--text-muted)' }}>
      <motion.span animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.2, repeat: Infinity }}>
        searching PubMed and Aptagen database...
      </motion.span>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div style={{ padding: '16px', border: '1px solid var(--border)', fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--accent-red)' }}>
      {message}
    </div>
  )
}

function EmptyState({ proteinId }) {
  return (
    <div style={{ padding: '20px', border: '1px solid var(--border)', fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center', lineHeight: 2 }}>
      No experimentally validated aptamers found for {proteinId}<br />
      <span style={{ fontSize: '10px' }}>Try a well-studied target: BRD4, EGFR, VEGF, thrombin, MUC1</span>
    </div>
  )
}

function ChevronIcon({ open, size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12"
      style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s', flexShrink: 0 }}>
      <polyline points="2,4 6,8 10,4" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="square" />
    </svg>
  )
}

import { motion, AnimatePresence } from 'framer-motion'
import { ResponsiveRadar } from '@nivo/radar'
import MolecularViewer from './MolecularViewer'

const RADAR_LABELS = {
  fold_stability:       'Fold',
  binding_score:        'Binding',
  epitope_quality:      'Epitope',
  lysine_accessibility: 'Lysines',
  ternary_feasibility:  'Ternary',
  hook_penalty:         'Hook',
}

const radarTheme = {
  background: 'transparent',
  text: {
    fontFamily: 'Fragment Mono, monospace',
    fontSize: 10,
    fill: '#7a9bb5',
  },
  grid: {
    line: {
      stroke: '#1a3050',
      strokeWidth: 1,
    },
  },
  dots: {
    text: { fill: '#7a9bb5' },
  },
  axis: {
    ticks: { text: { fill: '#7a9bb5', fontFamily: 'Fragment Mono, monospace', fontSize: 10 } },
  },
}

function buildRadarData(scores) {
  return Object.entries(scores).map(([key, val]) => ({
    component: RADAR_LABELS[key] ?? key,
    score: key === 'hook_penalty' ? parseFloat((1 - val).toFixed(3)) : parseFloat(val.toFixed(3)),
  }))
}

export default function DetailPanel({ candidate, proteinId, pdbData }) {
  if (!candidate) {
    return (
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px',
        minHeight: '400px',
      }}>
        <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center', lineHeight: 2 }}>
          hover a candidate<br />to view details
        </div>
      </div>
    )
  }

  const radarData = buildRadarData(candidate.scores)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0', height: '100%' }}>
      {/* Mini protein viewer */}
      <div style={{ height: '200px', background: '#020810', border: '1px solid var(--border)', position: 'relative' }}>
        <MolecularViewer
          pdbData={pdbData}
          proteinId={proteinId}
          height="200px"
          autoRotate={false}
          showDocked={true}
          mode="results"
        />
        <div style={{
          position: 'absolute',
          bottom: '8px',
          left: '10px',
          fontFamily: 'Fragment Mono, monospace',
          fontSize: '10px',
          color: 'var(--text-muted)',
          pointerEvents: 'none',
        }}>
          BINDING SITE  ·  {candidate.contact_residues} CONTACT RESIDUES  ·  {candidate.accessible_lysines} ACCESSIBLE LYSINES
        </div>
        <div style={{
          position: 'absolute',
          top: '8px',
          right: '10px',
          fontFamily: 'Fragment Mono, monospace',
          fontSize: '10px',
          color: 'var(--text-muted)',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          pointerEvents: 'none',
        }}>
          <LegendDot color="#3d5a75" label="Protein" />
          <LegendDot color="#00d4ff" label="Aptamer" />
          <LegendDot color="#ff4455" label="Lysines" />
          <LegendDot color="#ffaa00" label="Binding site" />
        </div>
      </div>

      {/* Radar chart */}
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderTop: 'none', padding: '16px', flex: 1 }}>
        <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '10px', color: 'var(--text-secondary)', marginBottom: '8px', letterSpacing: '0.06em' }}>
          DEGRADABILITY PROFILE  ·  {candidate.id}
        </div>

        {/* Nivo radar with fade transition on candidate change */}
        <AnimatePresence mode="wait">
          <motion.div
            key={candidate.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            style={{ height: '220px' }}
          >
            <ResponsiveRadar
              data={radarData}
              keys={['score']}
              indexBy="component"
              maxValue={1}
              margin={{ top: 24, right: 48, bottom: 24, left: 48 }}
              curve="linearClosed"
              borderWidth={2}
              borderColor="#00d4ff"
              gridLevels={4}
              gridShape="linear"
              gridLabelOffset={16}
              enableDots={true}
              dotSize={8}
              dotColor="#00d4ff"
              dotBorderWidth={2}
              dotBorderColor="#050c14"
              enableDotLabel={false}
              fillOpacity={0.25}
              blendMode="normal"
              animate={true}
              motionConfig="gentle"
              theme={radarTheme}
              colors={['#00d4ff']}
            />
          </motion.div>
        </AnimatePresence>

        {/* Stats row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '12px', marginTop: '8px' }}>
          <StatItem label="Est. Kd" value={candidate.kd_estimate} color="var(--accent-cyan)" />
          <StatItem label="Linker" value={candidate.peg_units ? `PEG-${candidate.peg_units}` : 'N/A'} color={candidate.ternary_failure ? 'var(--accent-red)' : 'var(--accent-cyan)'} />
          <StatItem label="Sequence" value={`${candidate.sequence.length} nt`} color="var(--text-secondary)" />
        </div>
      </div>
    </div>
  )
}

function LegendDot({ color, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
      <div style={{ width: '6px', height: '6px', background: color, flexShrink: 0 }} />
      <span>{label}</span>
    </div>
  )
}

function StatItem({ label, value, color }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '2px' }}>{label}</div>
      <div style={{ fontFamily: 'Fragment Mono, monospace', fontSize: '12px', color }}>{value}</div>
    </div>
  )
}

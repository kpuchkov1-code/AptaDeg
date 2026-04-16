// Renders a dot-bracket secondary structure as an SVG arc diagram
// Backbone is drawn as a horizontal line; base pairs as arcs above it

export default function ArcDiagram({ dotBracket, height = 60 }) {
  if (!dotBracket || dotBracket.length === 0) return null

  const n = dotBracket.length
  const padding = 8
  const nodeWidth = Math.max(4, Math.min(8, (400 - padding * 2) / n))
  const width = n * nodeWidth + padding * 2
  const baseline = height - 10

  // Parse dot-bracket into pairs
  const pairs = parsePairs(dotBracket)

  // Draw backbone
  const backboneStart = padding
  const backboneEnd = padding + n * nodeWidth

  const arcs = pairs.map(([i, j]) => {
    const xi = padding + i * nodeWidth + nodeWidth / 2
    const xj = padding + j * nodeWidth + nodeWidth / 2
    const midX = (xi + xj) / 2
    const arcHeight = Math.min(((xj - xi) / 2) * 0.7, baseline - 8)
    const cy = baseline - arcHeight
    return { xi, xj, midX, cy, arcHeight }
  })

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: 'block', maxWidth: '100%' }}
    >
      {/* Backbone */}
      <line
        x1={backboneStart}
        y1={baseline}
        x2={backboneEnd}
        y2={baseline}
        stroke="var(--text-muted)"
        strokeWidth="1"
      />

      {/* Arcs */}
      {arcs.map(({ xi, xj, cy }, idx) => (
        <path
          key={idx}
          d={`M ${xi} ${baseline} Q ${(xi + xj) / 2} ${cy} ${xj} ${baseline}`}
          fill="none"
          stroke="rgba(0,212,255,0.6)"
          strokeWidth="1"
        />
      ))}

      {/* Node dots at backbone */}
      {Array.from({ length: n }, (_, i) => (
        <circle
          key={i}
          cx={padding + i * nodeWidth + nodeWidth / 2}
          cy={baseline}
          r="1"
          fill="var(--text-muted)"
        />
      ))}
    </svg>
  )
}

function parsePairs(dotBracket) {
  const stack = []
  const pairs = []
  for (let i = 0; i < dotBracket.length; i++) {
    const c = dotBracket[i]
    if (c === '(') {
      stack.push(i)
    } else if (c === ')') {
      if (stack.length > 0) {
        pairs.push([stack.pop(), i])
      }
    }
  }
  return pairs
}

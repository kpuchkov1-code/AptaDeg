// Radix UI Select wrapped with our design system
import * as SelectPrimitive from '@radix-ui/react-select'

const triggerStyle = {
  background: 'var(--bg-secondary)',
  border: '2px solid var(--border)',
  color: 'var(--accent-cyan)',
  fontFamily: 'Fragment Mono, monospace',
  fontSize: '14px',
  padding: '12px 16px',
  width: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  cursor: 'crosshair',
  outline: 'none',
  borderRadius: '0',
}

const contentStyle = {
  background: 'var(--bg-secondary)',
  border: '2px solid var(--border)',
  borderRadius: '0',
  overflow: 'hidden',
  zIndex: 8000,
  minWidth: 'var(--radix-select-trigger-width)',
  boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
}

const itemStyle = {
  fontFamily: 'Fragment Mono, monospace',
  fontSize: '14px',
  color: 'var(--text-secondary)',
  padding: '10px 16px',
  cursor: 'crosshair',
  outline: 'none',
  userSelect: 'none',
}

export function Select({ value, onValueChange, options, placeholder }) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger style={triggerStyle}>
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>

      <SelectPrimitive.Portal>
        <SelectPrimitive.Content position="popper" style={contentStyle}>
          <SelectPrimitive.Viewport>
            {options.map(opt => (
              <SelectPrimitive.Item
                key={opt.value}
                value={opt.value}
                style={itemStyle}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'var(--bg-card)'
                  e.currentTarget.style.color = 'var(--accent-cyan)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = 'var(--text-secondary)'
                }}
              >
                <SelectPrimitive.ItemText>{opt.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}

function ChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <polyline points="2,4 6,8 10,4" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="square" />
    </svg>
  )
}

// Radix UI Tooltip wrapped with our design system
import * as TooltipPrimitive from '@radix-ui/react-tooltip'

export function TooltipProvider({ children }) {
  return (
    <TooltipPrimitive.Provider delayDuration={300}>
      {children}
    </TooltipPrimitive.Provider>
  )
}

export function Tooltip({ children, content, side = 'top', align = 'center' }) {
  if (!content) return children

  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>
        {children}
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          align={align}
          sideOffset={6}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            fontFamily: 'DM Sans, sans-serif',
            fontSize: '12px',
            maxWidth: '220px',
            padding: '12px 16px',
            borderRadius: '0',
            lineHeight: '1.5',
            zIndex: 9000,
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          }}
        >
          {content}
          <TooltipPrimitive.Arrow
            style={{ fill: 'var(--border)' }}
          />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}

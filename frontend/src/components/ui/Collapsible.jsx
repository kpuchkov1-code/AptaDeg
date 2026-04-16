// Radix UI Collapsible — uses Root for a11y/keyboard state, Framer Motion for animation
import * as CollapsiblePrimitive from '@radix-ui/react-collapsible'
import { motion, AnimatePresence } from 'framer-motion'

export function Collapsible({ open, onOpenChange, trigger, children }) {
  return (
    <CollapsiblePrimitive.Root open={open} onOpenChange={onOpenChange}>
      <CollapsiblePrimitive.Trigger asChild>
        {trigger}
      </CollapsiblePrimitive.Trigger>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: 'hidden' }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </CollapsiblePrimitive.Root>
  )
}

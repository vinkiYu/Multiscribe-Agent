import { Root, Trigger, Portal, Content, CheckboxItem, ItemIndicator } from '@radix-ui/react-dropdown-menu'
import { Check, ChevronDown } from 'lucide-react'
import type { ReactElement, ReactNode } from 'react'

type CheckItem = {
  value: string
  label: string
  checked: boolean
}

type Props = {
  triggerLabel: ReactNode
  items: CheckItem[]
  onCheckedChange: (value: string, checked: boolean) => void
  disabled?: boolean
  ariaLabel?: string
}

export function MultiSelectDropdown({ triggerLabel, items, onCheckedChange, disabled, ariaLabel }: Props): ReactElement {
  return (
    <Root>
      <Trigger asChild>
        <button type="button" className="neo-dropdown-trigger" disabled={disabled} aria-label={ariaLabel}>
          {triggerLabel}
          <ChevronDown size={14} aria-hidden="true" />
        </button>
      </Trigger>
      <Portal>
        <Content className="neo-dropdown-content" sideOffset={4} align="start">
          {items.map((item) => (
            <CheckboxItem
              key={item.value}
              className="neo-dropdown-item"
              checked={item.checked}
              onCheckedChange={(checked) => onCheckedChange(item.value, checked)}
              onSelect={(event) => event.preventDefault()}
            >
              <ItemIndicator className="neo-dropdown-indicator">
                <Check size={14} aria-hidden="true" />
              </ItemIndicator>
              <span>{item.label}</span>
            </CheckboxItem>
          ))}
        </Content>
      </Portal>
    </Root>
  )
}

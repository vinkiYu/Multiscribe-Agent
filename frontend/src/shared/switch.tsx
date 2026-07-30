import { Root, Thumb } from '@radix-ui/react-switch'
import type { ReactElement, ReactNode } from 'react'

type Props = {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: ReactNode
  disabled?: boolean
  id?: string
}

export function Switch({ checked, onCheckedChange, label, disabled, id }: Props): ReactElement {
  return (
    <div className="switch-row">
      <Root
        id={id}
        className="neo-switch"
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
      >
        <Thumb className="neo-switch-thumb" />
      </Root>
      <label className="neo-switch-label" htmlFor={id}>{label}</label>
    </div>
  )
}

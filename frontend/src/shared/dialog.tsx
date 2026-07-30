/* The Modal namespace is a stable design-system export, not a page component. */
/* eslint-disable react-refresh/only-export-components */
import * as Dialog from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'

interface ModalProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: ReactNode
}

function ModalRoot({ open, onOpenChange, children }: ModalProps): ReactNode {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}>{children}</Dialog.Root>
}

export const Modal = {
  Root: ModalRoot,
  Trigger: Dialog.Trigger,
  Overlay: Dialog.Overlay,
  Content: Dialog.Content,
  Title: Dialog.Title,
  Description: Dialog.Description,
  Close: Dialog.Close,
}

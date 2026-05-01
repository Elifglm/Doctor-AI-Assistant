import { create } from 'zustand'

export type ConfirmVariant = 'default' | 'danger'

export interface ConfirmOptions {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: ConfirmVariant
}

interface ConfirmState {
  open: boolean
  options: ConfirmOptions | null
  resolver: ((accepted: boolean) => void) | null
  request: (options: ConfirmOptions) => Promise<boolean>
  resolve: (accepted: boolean) => void
}

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  open: false,
  options: null,
  resolver: null,
  request: (options) => {
    return new Promise<boolean>((resolve) => {
      set({ open: true, options, resolver: resolve })
    })
  },
  resolve: (accepted) => {
    const { resolver } = get()
    resolver?.(accepted)
    set({ open: false, options: null, resolver: null })
  },
}))

export function confirm(options: ConfirmOptions): Promise<boolean> {
  return useConfirmStore.getState().request(options)
}

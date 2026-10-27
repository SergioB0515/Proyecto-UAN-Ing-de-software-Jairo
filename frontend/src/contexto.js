import { inject } from 'vue'

export const CLAVE_CONTEXTO = Symbol('contribuyente')

export function useContribuyente() {
  const contexto = inject(CLAVE_CONTEXTO)
  if (!contexto) throw new Error('useContribuyente se usa dentro de ContribuyenteView')
  return contexto
}

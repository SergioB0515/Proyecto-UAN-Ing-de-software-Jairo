/**
 * Contexto del contribuyente abierto: lo provee ContribuyenteView y lo
 * consumen sus vistas hijas (resumen, patrimonio, exógena…), para que el
 * contribuyente y el periodo seleccionado se carguen una sola vez.
 */
import { inject } from 'vue'

export const CLAVE_CONTEXTO = Symbol('contribuyente')

export function useContribuyente() {
  const contexto = inject(CLAVE_CONTEXTO)
  if (!contexto) throw new Error('useContribuyente se usa dentro de ContribuyenteView')
  return contexto
}

/** Formato de cifras y fechas en convención colombiana. */

const pesos = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
})
const numero = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 })

export function dinero(valor) {
  if (valor === null || valor === undefined) return '—'
  return pesos.format(valor)
}

export function cantidad(valor) {
  if (valor === null || valor === undefined) return '—'
  return numero.format(valor)
}

export function fecha(valor) {
  if (!valor) return '—'
  // Las fechas 'YYYY-MM-DD' se interpretan como locales, no como UTC.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(valor) ? new Date(`${valor}T00:00:00`) : new Date(valor)
  return d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
}

export const ETIQUETAS_TIPO_CONTRIBUYENTE = {
  ASALARIADO: 'Asalariado',
  INDEPENDIENTE: 'Independiente',
  MIXTO: 'Mixto',
}

export const ETIQUETAS_TIPO_ACTIVO = {
  CUENTA: 'Cuenta bancaria',
  VEHICULO: 'Vehículo',
  INMUEBLE: 'Inmueble',
  INVERSION: 'Inversión',
  INVENTARIO: 'Inventario (cierre)',
}

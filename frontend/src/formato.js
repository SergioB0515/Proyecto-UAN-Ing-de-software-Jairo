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

export const ETIQUETAS_CATEGORIA_ADJUNTO = {
  RECIBO: 'Recibo',
  FACTURA: 'Factura',
  TRANSFERENCIA: 'Transferencia',
  CAPTURA: 'Captura de pantalla',
  CERTIFICADO: 'Certificado',
  DECLARACION: 'Declaración',
  CONTRATO: 'Contrato o escritura',
  OTRO: 'Otro',
}

export const ETIQUETAS_TIPO_ENTIDAD = {
  CONTRIBUYENTE: 'Contribuyente',
  PERIODO_FISCAL: 'Año gravable',
  ACTIVO: 'Activo',
  FUENTE_INGRESO: 'Ingreso',
  DOCUMENTO_SOPORTE: 'Documento soporte',
  MOVIMIENTO: 'Movimiento',
  PROVEEDOR: 'Proveedor',
}

export function tamano(bytes) {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function fechaHora(valor) {
  if (!valor) return '—'
  return new Date(valor).toLocaleString('es-CO', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

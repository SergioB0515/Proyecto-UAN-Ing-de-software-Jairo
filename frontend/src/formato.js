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
  REQUERIMIENTO: 'Soporte pedido',
}

// Los cuatro estados que el contribuyente puede marcar. En su idioma, no en
// el del formulario: quien contesta esto no es contador.
export const ETIQUETAS_ESTADO_REQUERIMIENTO = {
  PENDIENTE: 'Pendiente',
  NO_APLICA: 'No aplica',
  NO_LO_TENGO: 'No lo tengo',
  NO_ENTIENDO: 'No entiendo',
}

export const AYUDA_ESTADO_REQUERIMIENTO = {
  PENDIENTE: 'Todavía lo estoy buscando.',
  NO_APLICA: 'Esto no es mío o no me corresponde.',
  NO_LO_TENGO: 'Es mío pero no tengo el papel.',
  NO_ENTIENDO: 'No sé qué me están pidiendo.',
}

export const ETIQUETAS_TIPO_ADICIONAL = {
  DEPENDIENTE: 'Dependientes económicos',
  INTERESES_VIVIENDA: 'Intereses del crédito de vivienda',
  MEDICINA_PREPAGADA: 'Medicina prepagada o póliza de salud',
  AHORRO_AFC: 'Ahorro en cuenta AFC o AVC',
  APORTES_VOLUNTARIOS_PENSION: 'Aportes voluntarios a pensión',
  ACTIVO: 'Bien o activo en Colombia',
  DEUDA: 'Deuda a 31 de diciembre',
  BIEN_EXTERIOR: 'Bien o inversión en el exterior',
}

// Las cuatro columnas de la conciliación, en palabras.
export const ETIQUETAS_ESTADO_CONCILIACION = {
  COINCIDE: 'Coincide',
  DISCREPANCIA: 'Hay diferencia',
  NO_DECLARADO: 'Solo en la exógena',
  NO_REPORTADO_POR_TERCERO: 'Solo en lo declarado',
}

export const ETIQUETAS_FUENTE_VALOR_FINAL = {
  EXOGENA: 'Valor de la exógena',
  DECLARADO: 'Valor declarado',
  MANUAL: 'Valor fijado a mano',
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

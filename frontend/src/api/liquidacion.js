import { cliente, descargarArchivo, enviar, obtener } from './cliente'

const base = (cid, pid) => `/liquidacion/contribuyentes/${cid}/periodos-fiscales/${pid}`

export const listarCedulas = () => obtener('/liquidacion/cedulas')

export const obtenerHoja = (cid, pid) => obtener(`${base(cid, pid)}/hoja`)

export const actualizarHoja = async (cid, pid, cambios) => {
  const { data } = await cliente.patch(`${base(cid, pid)}/hoja`, cambios)
  return data
}

export const listarDeducciones = (cid, pid) => obtener(`${base(cid, pid)}/deducciones`)

export const crearDeduccion = (cid, pid, datos) =>
  enviar(`${base(cid, pid)}/deducciones`, datos)

export const eliminarDeduccion = (cid, pid, id) =>
  cliente.delete(`${base(cid, pid)}/deducciones/${id}`)

export const listarIngresos = (cid, pid) => obtener(`${base(cid, pid)}/ingresos`)

export const clasificarIngresos = async (cid, pid, clasificaciones) => {
  const { data } = await cliente.put(`${base(cid, pid)}/ingresos`, clasificaciones)
  return data
}

export const liquidar = (cid, pid) => obtener(base(cid, pid))

export const exportarLiquidacion = (cid, pid, formato) =>
  descargarArchivo(`${base(cid, pid)}/exportar`, { formato }, `liquidacion.${formato}`)

// --- Parte empresarial -----------------------------------------------------

export const listarCategoriasDepreciacion = (anioGravable) =>
  obtener('/liquidacion/categorias-depreciacion', { anio_gravable: anioGravable })

export const listarDepreciacion = (cid, pid) => obtener(`${base(cid, pid)}/depreciacion`)

export const guardarDepreciacion = async (cid, pid, filas) => {
  const { data } = await cliente.put(`${base(cid, pid)}/depreciacion`, filas)
  return data
}

export const eliminarDepreciacion = (cid, pid, activoId) =>
  cliente.delete(`${base(cid, pid)}/depreciacion/${activoId}`)

export const listarPerdidas = (cid, anioGravable) =>
  obtener(`/liquidacion/contribuyentes/${cid}/perdidas`, { anio_gravable: anioGravable })

export const crearPerdida = (cid, anioGravable, datos) =>
  enviar(`/liquidacion/contribuyentes/${cid}/perdidas?anio_gravable=${anioGravable}`, datos)

export const eliminarPerdida = (cid, perdidaId) =>
  cliente.delete(`/liquidacion/contribuyentes/${cid}/perdidas/${perdidaId}`)

export const listarPagosEfectivo = (cid, pid) => obtener(`${base(cid, pid)}/pagos-efectivo`)

export const crearPagoEfectivo = (cid, pid, datos) =>
  enviar(`${base(cid, pid)}/pagos-efectivo`, datos)

export const eliminarPagoEfectivo = (cid, pid, pagoId) =>
  cliente.delete(`${base(cid, pid)}/pagos-efectivo/${pagoId}`)

export const listarPlantillas = (cid, pid) =>
  obtener(`${base(cid, pid)}/plantillas-deducciones`)

export const crearDeduccionDesdePlantilla = (cid, pid, codigo, valor) =>
  enviar(
    `${base(cid, pid)}/deducciones/desde-plantilla` +
      `?codigo=${encodeURIComponent(codigo)}&valor=${encodeURIComponent(valor)}`,
  )

export const copiarHojaDelAnterior = (cid, pid) =>
  enviar(`${base(cid, pid)}/hoja/copiar-del-anterior`)

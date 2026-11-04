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

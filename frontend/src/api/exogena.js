import { cliente, obtener } from './cliente'

export async function importarExogena(contribuyenteId, periodoId, archivo) {
  const form = new FormData()
  form.append('archivo', archivo)
  const { data } = await cliente.post(
    `/contribuyentes/${contribuyenteId}/periodos-fiscales/${periodoId}/exogena`,
    form,
  )
  return data
}

export const listarReportesExogena = (contribuyenteId) =>
  obtener(`/contribuyentes/${contribuyenteId}/reportes-exogena`)

export const listarTopes = (contribuyenteId, reporteId) =>
  obtener(`/contribuyentes/${contribuyenteId}/reportes-exogena/${reporteId}/topes`)

export const listarRegistros = (contribuyenteId, reporteId, filtros = {}) =>
  obtener(`/contribuyentes/${contribuyenteId}/reportes-exogena/${reporteId}/registros`, filtros)

import { cliente, enviar, obtener } from './cliente'

export const listarUmbrales = () => obtener('/parametros/umbrales')
export const guardarUmbral = (datos) => enviar('/parametros/umbrales', datos)

export const verificarObligacion = (contribuyenteId, periodoId) =>
  obtener(`/parametros/contribuyentes/${contribuyenteId}/periodos-fiscales/${periodoId}/obligacion`)

export const listarPlazos = (anio) => obtener(`/parametros/plazos/${anio}`)
export const cargarCalendarioOficial = (anio) => enviar(`/parametros/plazos/${anio}/calendario-oficial`)
export async function reemplazarPlazos(anio, plazos) {
  const { data } = await cliente.put(`/parametros/plazos/${anio}`, plazos)
  return data
}

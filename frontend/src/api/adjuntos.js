import { cliente, descargarArchivo, obtener, obtenerBlob } from './cliente'

const base = (id) => `/contribuyentes/${id}/adjuntos`

export async function subirAdjunto(contribuyenteId, { entidadTipo, entidadId, categoria, descripcion, archivo }) {
  const form = new FormData()
  form.append('entidad_tipo', entidadTipo)
  form.append('entidad_id', entidadId)
  form.append('categoria', categoria || 'OTRO')
  if (descripcion?.trim()) form.append('descripcion', descripcion.trim())
  form.append('archivo', archivo, archivo.name)
  const { data } = await cliente.post(base(contribuyenteId), form)
  return data
}

export const listarAdjuntos = (contribuyenteId, filtros = {}) => obtener(base(contribuyenteId), filtros)

export const resumenAdjuntos = (contribuyenteId) => obtener(`${base(contribuyenteId)}/resumen`)

export async function actualizarAdjunto(contribuyenteId, adjuntoId, cambios) {
  const { data } = await cliente.patch(`${base(contribuyenteId)}/${adjuntoId}`, cambios)
  return data
}

export const eliminarAdjunto = (contribuyenteId, adjuntoId) =>
  cliente.delete(`${base(contribuyenteId)}/${adjuntoId}`)

export const obtenerArchivoAdjunto = (contribuyenteId, adjuntoId) =>
  obtenerBlob(`${base(contribuyenteId)}/${adjuntoId}/archivo`)

export const descargarAdjunto = (contribuyenteId, adjunto) =>
  descargarArchivo(`${base(contribuyenteId)}/${adjunto.id}/archivo`, { descargar: true }, adjunto.nombre_original)

export const descargarSoportesDelAnio = (contribuyenteId, periodoId, anio) =>
  descargarArchivo(
    `/contribuyentes/${contribuyenteId}/periodos-fiscales/${periodoId}/soportes/zip`,
    undefined,
    `soportes_${anio}.zip`,
  )

import { cliente, enviar, obtener } from './cliente'

const periodo = (cid, pid) => `/contribuyentes/${cid}/periodos-fiscales/${pid}`

export const obtenerResumen = (cid, pid) => obtener(`${periodo(cid, pid)}/resumen`)
export const cerrarPeriodo = (cid, pid) => enviar(`${periodo(cid, pid)}/cerrar`)
export const reabrirPeriodo = (cid, pid) => enviar(`${periodo(cid, pid)}/reabrir`)

/** Descarga un reporte (HU-16) y lo entrega al navegador como archivo. */
export async function descargarReporte(cid, pid, tipo, formato) {
  const respuesta = await cliente.get(`${periodo(cid, pid)}/reportes/${tipo}`, {
    params: { formato },
    responseType: 'blob',
  }).catch(async (error) => {
    // Con responseType blob, el JSON del error también llega como Blob.
    if (error.response?.data instanceof Blob) {
      try {
        error.response.data = JSON.parse(await error.response.data.text())
      } catch {
        /* se deja tal cual */
      }
    }
    throw error
  })
  const disposicion = respuesta.headers['content-disposition'] || ''
  const nombre = /filename="([^"]+)"/.exec(disposicion)?.[1] || `${tipo}.${formato}`
  const url = URL.createObjectURL(respuesta.data)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  enlace.click()
  URL.revokeObjectURL(url)
}

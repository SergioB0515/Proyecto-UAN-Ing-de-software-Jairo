import axios from 'axios'

import { cerrarSesion, sesion } from '../sesion'

export const cliente = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000',
})

cliente.interceptors.request.use((config) => {
  if (sesion.token) config.headers.Authorization = `Bearer ${sesion.token}`
  return config
})

cliente.interceptors.response.use(
  (respuesta) => respuesta,
  async (error) => {
    const esLogin = error.config?.url?.includes('/contadores/login')
    if (error.response?.status === 401 && !esLogin) {
      cerrarSesion()
      const { default: router } = await import('../router')
      router.push({ name: 'login', query: { expirada: '1' } })
    }
    return Promise.reject(error)
  },
)

export function mensajeDeError(error) {
  if (!error.response) {
    return 'No hay conexión con el servidor. Verifica que el backend esté corriendo.'
  }
  const detalle = error.response.data?.detail
  if (typeof detalle === 'string') return detalle
  if (Array.isArray(detalle)) {
    return detalle
      .map((d) => {
        if (d.msg?.startsWith('Value error, ')) return d.msg.slice('Value error, '.length)
        const campo = d.loc?.filter((p) => p !== 'body').join('.')
        return campo ? `${campo}: ${d.msg}` : d.msg
      })
      .join(' · ')
  }
  return `Error ${error.response.status} del servidor.`
}

export async function obtener(url, params) {
  const { data } = await cliente.get(url, { params })
  return data
}

export async function enviar(url, cuerpo) {
  const { data } = await cliente.post(url, cuerpo)
  return data
}

async function pedirBlob(url, params) {
  return cliente.get(url, { params, responseType: 'blob' }).catch(async (error) => {
    if (error.response?.data instanceof Blob) {
      try {
        error.response.data = JSON.parse(await error.response.data.text())
      } catch {}
    }
    throw error
  })
}

export async function obtenerBlob(url, params) {
  const respuesta = await pedirBlob(url, params)
  return respuesta.data
}

export async function descargarArchivo(url, params, nombrePorDefecto) {
  const respuesta = await pedirBlob(url, params)
  const disposicion = respuesta.headers['content-disposition'] || ''
  const nombre = /filename="([^"]+)"/.exec(disposicion)?.[1] || nombrePorDefecto
  const enlace = document.createElement('a')
  enlace.href = URL.createObjectURL(respuesta.data)
  enlace.download = nombre
  enlace.click()
  URL.revokeObjectURL(enlace.href)
}

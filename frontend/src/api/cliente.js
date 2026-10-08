/**
 * Cliente HTTP base. Toda petición al backend pasa por aquí: agrega el
 * token JWT y, si el backend responde 401, cierra la sesión y manda al
 * login. Las vistas nunca arman URLs ni tocan el token directamente.
 */
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
      // Import diferido para evitar un ciclo router -> vistas -> api -> router.
      const { default: router } = await import('../router')
      router.push({ name: 'login', query: { expirada: '1' } })
    }
    return Promise.reject(error)
  },
)

/** Convierte cualquier error del backend en un texto para mostrar. */
export function mensajeDeError(error) {
  if (!error.response) {
    return 'No hay conexión con el servidor. Verifica que el backend esté corriendo.'
  }
  const detalle = error.response.data?.detail
  if (typeof detalle === 'string') return detalle
  if (Array.isArray(detalle)) {
    // 422 de validación de FastAPI: [{loc: [...], msg: '...'}]
    return detalle
      .map((d) => {
        const campo = d.loc?.filter((p) => p !== 'body').join('.')
        return campo ? `${campo}: ${d.msg}` : d.msg
      })
      .join(' · ')
  }
  return `Error ${error.response.status} del servidor.`
}

/** GET que devuelve directamente el cuerpo. */
export async function obtener(url, params) {
  const { data } = await cliente.get(url, { params })
  return data
}

export async function enviar(url, cuerpo) {
  const { data } = await cliente.post(url, cuerpo)
  return data
}

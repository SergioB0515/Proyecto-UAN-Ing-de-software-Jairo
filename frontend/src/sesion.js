import { reactive } from 'vue'

const CLAVE = 'renta.token'

function leerToken() {
  try {
    return localStorage.getItem(CLAVE)
  } catch {
    return null
  }
}

export const sesion = reactive({
  token: leerToken(),
  contador: null,
})

export function guardarToken(token) {
  sesion.token = token
  try {
    localStorage.setItem(CLAVE, token)
  } catch {}
}

export function cerrarSesion() {
  sesion.token = null
  sesion.contador = null
  try {
    localStorage.removeItem(CLAVE)
  } catch {}
}

/**
 * Estado de la sesión del contador. El token se guarda en localStorage
 * para sobrevivir a una recarga; al arrancar, el router lo valida contra
 * GET /contadores/yo antes de dejar entrar (ver router/index.js).
 */
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
  } catch {
    /* modo privado: la sesión vive solo en memoria */
  }
}

export function cerrarSesion() {
  sesion.token = null
  sesion.contador = null
  try {
    localStorage.removeItem(CLAVE)
  } catch {
    /* nada que limpiar */
  }
}

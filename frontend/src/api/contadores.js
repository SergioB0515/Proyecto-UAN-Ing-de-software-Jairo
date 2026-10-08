import { cliente, obtener } from './cliente'

export async function iniciarSesion(email, contrasena) {
  // El login es OAuth2 estándar: form-data con "username" y "password".
  const form = new URLSearchParams({ username: email, password: contrasena })
  const { data } = await cliente.post('/contadores/login', form)
  return data.access_token
}

export async function registrarContador(datos) {
  const { data } = await cliente.post('/contadores/registro', datos)
  return data
}

export const obtenerContadorActual = () => obtener('/contadores/yo')

export async function cambiarContrasena(contrasenaActual, contrasenaNueva) {
  await cliente.put('/contadores/yo/contrasena', {
    contrasena_actual: contrasenaActual,
    contrasena_nueva: contrasenaNueva,
  })
}

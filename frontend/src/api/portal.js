import axios from 'axios'

import { cliente, enviar, mensajeDeError, obtener } from './cliente'

// ---------------------------------------------------------------------------
// Portal del contribuyente
//
// Instancia de axios APARTE, sin interceptores. Dos razones, las dos
// importantes:
//
// 1. `cliente` le pega el `Authorization: Bearer <token del contador>` a toda
//    petición. Si el contador abriera el enlace de un cliente desde su propio
//    navegador, ese encabezado viajaría a una ruta pública. Aquí no hay
//    encabezado que mandar: el alcance lo da el token de la URL.
// 2. `cliente` redirige al login ante cualquier 401. En el portal no hay login
//    al que mandar a nadie, y un 410 de enlace vencido tiene que llegarle a la
//    vista para que muestre «pídale otro a su contador».
// ---------------------------------------------------------------------------

const clientePortal = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000',
})

const raiz = (token) => `/carga/${encodeURIComponent(token)}`

export { mensajeDeError }

export async function abrirPortal(token) {
  const { data } = await clientePortal.get(raiz(token))
  return data
}

export async function aceptarPolitica(token, datos) {
  const { data } = await clientePortal.post(`${raiz(token)}/politica`, datos)
  return data
}

export async function cargarExogena(token, archivo) {
  const cuerpo = new FormData()
  cuerpo.append('archivo', archivo)
  const { data } = await clientePortal.post(`${raiz(token)}/exogena`, cuerpo)
  return data
}

export async function responderRequerimiento(token, requerimientoId, cambios) {
  const { data } = await clientePortal.patch(
    `${raiz(token)}/requerimientos/${requerimientoId}`,
    cambios,
  )
  return data
}

export async function subirSoporte(token, requerimientoId, archivo, descripcion) {
  const cuerpo = new FormData()
  cuerpo.append('archivo', archivo)
  if (descripcion) cuerpo.append('descripcion', descripcion)
  const { data } = await clientePortal.post(
    `${raiz(token)}/requerimientos/${requerimientoId}/archivos`,
    cuerpo,
  )
  return data
}

export async function parametrosAdicionalesPortal(token) {
  const { data } = await clientePortal.get(`${raiz(token)}/adicionales/parametros`)
  return data
}

export async function agregarAdicionalPortal(token, datos) {
  const { data } = await clientePortal.post(`${raiz(token)}/adicionales`, datos)
  return data
}

export async function eliminarAdicionalPortal(token, adicionalId) {
  await clientePortal.delete(`${raiz(token)}/adicionales/${adicionalId}`)
}

// ---------------------------------------------------------------------------
// Lado del contador (con sesión)
// ---------------------------------------------------------------------------

const periodo = (cid, pid) => `/contribuyentes/${cid}/periodos-fiscales/${pid}`

export const listarEnlaces = (cid) => obtener(`/contribuyentes/${cid}/enlaces-carga`)

export const generarEnlace = (cid, datos) =>
  enviar(`/contribuyentes/${cid}/enlaces-carga`, datos)

export const revocarEnlace = (cid, enlaceId) =>
  enviar(`/contribuyentes/${cid}/enlaces-carga/${enlaceId}/revocar`)

export const listarRequerimientos = (cid, pid) => obtener(`${periodo(cid, pid)}/requerimientos`)

export const resumenRequerimientos = (cid, pid) =>
  obtener(`${periodo(cid, pid)}/requerimientos/resumen`)

export const sincronizarRequerimientos = (cid, pid) =>
  enviar(`${periodo(cid, pid)}/requerimientos/sincronizar`)

export async function marcarRevisado(cid, pid, requerimientoId, revisado = true) {
  const { data } = await cliente.patch(
    `${periodo(cid, pid)}/requerimientos/${requerimientoId}/revision`,
    null,
    { params: { revisado } },
  )
  return data
}

export const listarAdicionales = (cid, pid) => obtener(`${periodo(cid, pid)}/adicionales`)

export const parametrosAdicionales = (cid, pid) =>
  obtener(`${periodo(cid, pid)}/adicionales/parametros`)

export const crearAdicional = (cid, pid, datos) =>
  enviar(`${periodo(cid, pid)}/adicionales`, datos)

export async function eliminarAdicional(cid, pid, adicionalId) {
  await cliente.delete(`${periodo(cid, pid)}/adicionales/${adicionalId}`)
}

// Valor final de cada renglón de la conciliación.
export const listarDecisiones = (cid, pid) =>
  obtener(`${periodo(cid, pid)}/conciliacion/decisiones`)

export async function fijarDecision(cid, pid, datos) {
  const { data } = await cliente.put(`${periodo(cid, pid)}/conciliacion/decisiones`, datos)
  return data
}

export async function borrarDecision(cid, pid, claveItem) {
  await cliente.delete(
    `${periodo(cid, pid)}/conciliacion/decisiones/${encodeURIComponent(claveItem)}`,
  )
}

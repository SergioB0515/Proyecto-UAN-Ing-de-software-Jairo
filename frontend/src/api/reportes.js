import { descargarArchivo, enviar, obtener } from './cliente'

const periodo = (cid, pid) => `/contribuyentes/${cid}/periodos-fiscales/${pid}`

export const obtenerResumen = (cid, pid) => obtener(`${periodo(cid, pid)}/resumen`)
export const cerrarPeriodo = (cid, pid) => enviar(`${periodo(cid, pid)}/cerrar`)
export const reabrirPeriodo = (cid, pid) => enviar(`${periodo(cid, pid)}/reabrir`)

export const descargarReporte = (cid, pid, tipo, formato) =>
  descargarArchivo(`${periodo(cid, pid)}/reportes/${tipo}`, { formato }, `${tipo}.${formato}`)

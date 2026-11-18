import { cliente, descargarArchivo, enviar, obtener } from './cliente'

const periodo = (cid, pid) => `/contribuyentes/${cid}/periodos-fiscales/${pid}`

export const obtenerGestion = (cid, pid, fechaPago) =>
  obtener(`${periodo(cid, pid)}/gestion`, fechaPago ? { fecha_pago: fechaPago } : undefined)

export const actualizarSeguimiento = async (cid, pid, cambios) =>
  (await cliente.patch(`${periodo(cid, pid)}/gestion/seguimiento`, cambios)).data

export const registrarPresentacion = (cid, pid, datos) =>
  enviar(`${periodo(cid, pid)}/gestion/presentaciones`, datos)

export const registrarDeclaracionAnterior = (cid, datos) =>
  enviar(`/contribuyentes/${cid}/declaraciones-anteriores`, datos)

export const traerDelAnioAnterior = (cid, pid) =>
  enviar(`${periodo(cid, pid)}/gestion/traer-del-anio-anterior`, {})

export const obtenerDocumentos = (cid, pid) => obtener(`${periodo(cid, pid)}/documentos`)

export const actualizarDocumento = async (cid, pid, clave, cambios) =>
  (await cliente.patch(`${periodo(cid, pid)}/documentos/${encodeURIComponent(clave)}`, cambios)).data

export const agregarDocumento = (cid, pid, datos) => enviar(`${periodo(cid, pid)}/documentos`, datos)

export const descargarInforme = (cid, pid) =>
  descargarArchivo(`${periodo(cid, pid)}/informe-cliente`, {}, 'informe_renta.pdf')

export const listarTasas = () => obtener('/tasas-interes-moratorio')
export const guardarTasa = async (datos) => (await cliente.put('/tasas-interes-moratorio', datos)).data

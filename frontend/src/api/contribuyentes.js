import { cliente, enviar, obtener } from './cliente'

const base = (id) => `/contribuyentes/${id}`

export const listarContribuyentes = () => obtener('/contribuyentes')
export const crearContribuyente = (datos) => enviar('/contribuyentes', datos)
export const obtenerContribuyente = (id) => obtener(base(id))

export const listarPeriodos = (id) => obtener(`${base(id)}/periodos-fiscales`)
export const crearPeriodo = (id, anio) =>
  enviar(`${base(id)}/periodos-fiscales`, { anio_gravable: anio })

export const obtenerPatrimonio = (id, periodoId) =>
  obtener(`${base(id)}/patrimonio`, { periodo_fiscal_id: periodoId })

export const listarActivos = (id, periodoId) =>
  obtener(`${base(id)}/activos`, { periodo_fiscal_id: periodoId })
export const crearActivo = (id, datos) => enviar(`${base(id)}/activos`, datos)

export const listarFuentesIngreso = (id, periodoId) =>
  obtener(`${base(id)}/fuentes-ingreso`, { periodo_fiscal_id: periodoId })
export const crearFuenteIngreso = (id, datos) => enviar(`${base(id)}/fuentes-ingreso`, datos)

// Corrección de datos (solo en periodos abiertos; el backend responde 409 si no).
async function parchar(url, cambios) {
  const { data } = await cliente.patch(url, cambios)
  return data
}
export const actualizarContribuyente = (id, cambios) => parchar(base(id), cambios)
export const eliminarContribuyente = (id) => cliente.delete(base(id))
export const actualizarActivo = (id, activoId, cambios) => parchar(`${base(id)}/activos/${activoId}`, cambios)
export const eliminarActivo = (id, activoId) => cliente.delete(`${base(id)}/activos/${activoId}`)
export const actualizarFuenteIngreso = (id, fuenteId, cambios) =>
  parchar(`${base(id)}/fuentes-ingreso/${fuenteId}`, cambios)
export const eliminarFuenteIngreso = (id, fuenteId) => cliente.delete(`${base(id)}/fuentes-ingreso/${fuenteId}`)

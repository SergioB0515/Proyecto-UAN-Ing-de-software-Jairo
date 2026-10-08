import { cliente, enviar, obtener } from './cliente'

const base = (cid) => `/contribuyentes/${cid}`

export const listarCategorias = (cid) => obtener(`${base(cid)}/categorias`)
export const crearCategoria = (cid, datos) => enviar(`${base(cid)}/categorias`, datos)
export const eliminarCategoria = (cid, categoriaId) =>
  cliente.delete(`${base(cid)}/categorias/${categoriaId}`)

export const listarProductos = (cid) => obtener(`${base(cid)}/productos`)
export const crearProducto = (cid, datos) => enviar(`${base(cid)}/productos`, datos)
export async function actualizarProducto(cid, productoId, cambios) {
  const { data } = await cliente.patch(`${base(cid)}/productos/${productoId}`, cambios)
  return data
}

export const listarProveedores = (cid) => obtener(`${base(cid)}/proveedores`)
export const crearProveedor = (cid, datos) => enviar(`${base(cid)}/proveedores`, datos)

export const listarDocumentosSoporte = (cid) => obtener(`${base(cid)}/documentos-soporte`)
export const crearDocumentoSoporte = (cid, datos) => enviar(`${base(cid)}/documentos-soporte`, datos)

export const listarMovimientos = (cid, filtros = {}) => obtener(`${base(cid)}/movimientos`, filtros)
export const registrarMovimiento = (cid, datos) => enviar(`${base(cid)}/movimientos`, datos)

export const obtenerKardexPeriodo = (cid, pid) =>
  obtener(`${base(cid)}/periodos-fiscales/${pid}/kardex`)
export const obtenerCostoVentas = (cid, pid) =>
  obtener(`${base(cid)}/periodos-fiscales/${pid}/costo-ventas`)

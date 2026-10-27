import { descargarArchivo, obtener } from './cliente'

export const obtenerPanelCartera = (filtros = {}) => obtener('/cartera', filtros)

export const exportarCartera = (filtros, formato) =>
  descargarArchivo('/cartera/exportar', { ...filtros, formato }, `cartera.${formato}`)

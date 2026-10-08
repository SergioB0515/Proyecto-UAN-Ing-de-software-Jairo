import { obtener } from './cliente'

export const obtenerPanelCartera = (filtros = {}) => obtener('/cartera', filtros)

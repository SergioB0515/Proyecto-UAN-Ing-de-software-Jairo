import { obtener } from './cliente'

export const listarEventos = (filtros = {}) => obtener('/auditoria', filtros)
export const listarAccesos = () => obtener('/auditoria/accesos')

import { obtener } from './cliente'

const periodo = (cid, pid) => `/contribuyentes/${cid}/periodos-fiscales/${pid}`

export const conciliar = (cid, pid) => obtener(`${periodo(cid, pid)}/conciliacion`)
export const obtenerBorradorRenglones = (cid, pid) =>
  obtener(`${periodo(cid, pid)}/borrador-renglones`)

import { enviar, obtener } from './cliente'

export const listarUmbrales = () => obtener('/parametros/umbrales')
export const guardarUmbral = (datos) => enviar('/parametros/umbrales', datos)

export const verificarObligacion = (contribuyenteId, periodoId) =>
  obtener(`/parametros/contribuyentes/${contribuyenteId}/periodos-fiscales/${periodoId}/obligacion`)

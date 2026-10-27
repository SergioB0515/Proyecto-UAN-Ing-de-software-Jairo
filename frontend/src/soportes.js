import { reactive } from 'vue'

import { mensajeDeError } from './api/cliente'
import { resumenAdjuntos } from './api/adjuntos'

export function useConteoAdjuntos(contribuyenteId) {
  const conteos = reactive({})
  const clave = (tipo, id) => `${tipo}:${id}`

  async function cargar() {
    try {
      const filas = await resumenAdjuntos(contribuyenteId)
      for (const llave of Object.keys(conteos)) delete conteos[llave]
      for (const fila of filas) conteos[clave(fila.entidad_tipo, fila.entidad_id)] = fila.total
    } catch (error) {
      console.error(mensajeDeError(error))
    }
  }

  const total = (tipo, id) => conteos[clave(tipo, id)] ?? 0

  function fijar(tipo, id, cantidad) {
    conteos[clave(tipo, id)] = cantidad
  }

  return { cargar, total, fijar }
}

export function esImagenOPdf(tipoMime) {
  return tipoMime === 'application/pdf' || tipoMime?.startsWith('image/')
}

export function nombreDeCaptura(archivo) {
  const ahora = new Date()
  const parte = (n) => String(n).padStart(2, '0')
  const marca = `${ahora.getFullYear()}${parte(ahora.getMonth() + 1)}${parte(ahora.getDate())}-${parte(ahora.getHours())}${parte(ahora.getMinutes())}${parte(ahora.getSeconds())}`
  const extension = (archivo.type.split('/')[1] || 'png').replace('jpeg', 'jpg')
  return `captura-${marca}.${extension}`
}

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { descargarAdjunto, obtenerArchivoAdjunto } from '../api/adjuntos'
import { tamano } from '../formato'
import MensajeError from './MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  adjuntos: { type: Array, required: true },
  indice: { type: Number, required: true },
})
const emit = defineEmits(['cerrar', 'cambiar'])

const url = ref('')
const cargando = ref(false)
const error = ref('')
const botonCerrar = ref(null)
const anterior = document.activeElement

function actual() {
  return props.adjuntos[props.indice]
}

function liberar() {
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = ''
}

let solicitud = 0

async function cargar() {
  const mia = ++solicitud
  liberar()
  error.value = ''
  const adjunto = actual()
  if (!adjunto) return
  cargando.value = true
  try {
    const blob = await obtenerArchivoAdjunto(props.contribuyenteId, adjunto.id)
    if (mia !== solicitud) return
    url.value = URL.createObjectURL(new Blob([blob], { type: adjunto.tipo_mime }))
  } catch (e) {
    if (mia === solicitud) error.value = mensajeDeError(e)
  } finally {
    if (mia === solicitud) cargando.value = false
  }
}

function ir(paso) {
  const siguiente = props.indice + paso
  if (siguiente >= 0 && siguiente < props.adjuntos.length) emit('cambiar', siguiente)
}

function alTeclear(evento) {
  if (evento.key === 'Escape') emit('cerrar')
  else if (evento.key === 'ArrowLeft') ir(-1)
  else if (evento.key === 'ArrowRight') ir(1)
}

watch(() => props.indice, cargar)

onMounted(async () => {
  document.addEventListener('keydown', alTeclear)
  document.body.style.overflow = 'hidden'
  await nextTick()
  botonCerrar.value?.focus()
  cargar()
})

onBeforeUnmount(() => {
  solicitud++
  document.removeEventListener('keydown', alTeclear)
  document.body.style.overflow = ''
  liberar()
  anterior?.focus?.()
})
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex flex-col bg-tinta/80 p-3 sm:p-6" role="dialog" aria-modal="true" aria-label="Vista previa del soporte" @click.self="emit('cerrar')">
      <div class="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col overflow-hidden rounded-md bg-white shadow-xl">
        <header class="flex flex-wrap items-center justify-between gap-3 border-b border-papel-linea px-4 py-3">
          <div class="min-w-0">
            <p class="truncate font-semibold">{{ actual()?.nombre_original }}</p>
            <p class="truncate text-sm text-tinta-suave">
              {{ actual()?.etiqueta_entidad }} · {{ tamano(actual()?.tamano_bytes) }} · {{ indice + 1 }} de {{ adjuntos.length }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button type="button" class="boton-secundario" :disabled="indice === 0" aria-label="Soporte anterior" @click="ir(-1)">←</button>
            <button type="button" class="boton-secundario" :disabled="indice === adjuntos.length - 1" aria-label="Soporte siguiente" @click="ir(1)">→</button>
            <button type="button" class="boton-secundario" @click="descargarAdjunto(contribuyenteId, actual())">Descargar</button>
            <button ref="botonCerrar" type="button" class="boton" @click="emit('cerrar')">Cerrar</button>
          </div>
        </header>
        <div class="relative min-h-0 flex-1 overflow-auto bg-papel-hondo">
          <p v-if="cargando" class="p-6 text-sm text-tinta-suave" role="status">Cargando…</p>
          <div v-else-if="error" class="p-6"><MensajeError :mensaje="error" /></div>
          <iframe
            v-else-if="url && actual()?.tipo_mime === 'application/pdf'"
            :src="url"
            :title="actual().nombre_original"
            class="h-full min-h-[60vh] w-full border-0"
            @load="botonCerrar?.focus()"
          ></iframe>
          <img
            v-else-if="url"
            :src="url"
            :alt="actual().descripcion || actual().nombre_original"
            class="mx-auto max-h-full max-w-full object-contain"
          />
        </div>
        <p v-if="actual()?.descripcion" class="border-t border-papel-linea px-4 py-2 text-sm text-tinta-suave">
          {{ actual().descripcion }}
        </p>
      </div>
    </div>
  </Teleport>
</template>

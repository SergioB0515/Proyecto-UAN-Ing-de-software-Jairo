<script setup>
import { reactive } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { actualizarPeriodo } from '../api/contribuyentes'
import { fecha } from '../formato'
import EstadoVencimiento from './EstadoVencimiento.vue'
import MensajeError from './MensajeError.vue'

const props = defineProps({
  vencimiento: { type: Object, required: true },
  contribuyenteId: { type: Number, required: true },
  periodoId: { type: Number, required: true },
})
const emit = defineEmits(['actualizado'])

function hoyIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const form = reactive({
  modo: null,
  valor: '',
  error: '',
  guardando: false,
})

function abrir(modo) {
  Object.assign(form, {
    modo,
    valor: modo === 'presentada' ? hoyIso() : props.vencimiento.origen === 'MANUAL' ? props.vencimiento.fecha : '',
    error: '',
  })
}

async function guardar(cambios) {
  form.error = ''
  form.guardando = true
  try {
    await actualizarPeriodo(props.contribuyenteId, props.periodoId, cambios)
    form.modo = null
    emit('actualizado')
  } catch (e) {
    form.error = mensajeDeError(e)
  } finally {
    form.guardando = false
  }
}

function enviar() {
  const campo = form.modo === 'presentada' ? 'fecha_presentacion' : 'fecha_vencimiento_manual'
  guardar({ [campo]: form.valor || null })
}
</script>

<template>
  <div class="space-y-3">
    <EstadoVencimiento :vencimiento="vencimiento" />
    <p v-if="vencimiento.estado === 'SIN_FECHA'" class="text-sm text-tinta-suave">
      Sin calendario de vencimientos para este año.
      <RouterLink :to="{ name: 'umbrales' }" class="enlace">Cárgalo en Parámetros DIAN</RouterLink>
      o registra una fecha especial.
    </p>
    <p v-else-if="vencimiento.origen === 'CALENDARIO'" class="text-xs text-tinta-tenue">
      Según el calendario DIAN para NIT terminados en {{ vencimiento.ultimos_digitos }}.
    </p>

    <div v-if="!form.modo" class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
      <button v-if="vencimiento.estado !== 'PRESENTADA'" type="button" class="enlace" @click="abrir('presentada')">
        Marcar como presentada
      </button>
      <button v-else type="button" class="text-tinta-suave underline hover:text-tinta" @click="guardar({ fecha_presentacion: null })">
        Desmarcar presentada
      </button>
      <button type="button" class="text-tinta-suave underline hover:text-tinta" @click="abrir('manual')">
        {{ vencimiento.origen === 'MANUAL' ? 'Cambiar fecha especial' : 'Fecha límite especial' }}
      </button>
      <button
        v-if="vencimiento.origen === 'MANUAL'"
        type="button"
        class="text-tinta-suave underline hover:text-tinta"
        @click="guardar({ fecha_vencimiento_manual: null })"
      >
        Volver al calendario
      </button>
    </div>

    <form v-else class="flex flex-wrap items-end gap-2" @submit.prevent="enviar">
      <div>
        <label class="etiqueta" for="seg-fecha">
          {{ form.modo === 'presentada' ? 'Fecha de presentación' : 'Fecha límite especial' }}
        </label>
        <input id="seg-fecha" v-model="form.valor" type="date" class="campo" required />
      </div>
      <button type="submit" class="boton" :disabled="form.guardando">Guardar</button>
      <button type="button" class="boton-secundario" @click="form.modo = null">Cancelar</button>
      <p v-if="form.modo === 'manual'" class="basis-full text-xs text-tinta-tenue">
        Para prórrogas o plazos especiales que la DIAN fije por fuera del calendario general.
        <template v-if="vencimiento.fecha">Fecha límite actual: {{ fecha(vencimiento.fecha) }}.</template>
      </p>
    </form>
    <MensajeError :mensaje="form.error" />
  </div>
</template>

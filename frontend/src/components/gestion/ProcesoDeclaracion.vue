<script setup>
// Las siete etapas de una declaración. Las automáticas se calculan; las de
// criterio (revisar, aprobar, pagar) las marca el contador con su fecha.
import { reactive } from 'vue'

import { fecha } from '../../formato'

const props = defineProps({ gestion: { type: Object, required: true } })
const emit = defineEmits(['marcar'])

const CAMPO = {
  CRUCE: 'cruce_revisado_en',
  LIQUIDACION: 'liquidacion_revisada_en',
  APROBACION: 'aprobada_cliente_en',
  PAGO: 'pagada_en',
}
const editando = reactive({ clave: null, valor: '' })

function hoyIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function abrir(clave) {
  editando.clave = clave
  editando.valor = props.gestion.seguimiento[CAMPO[clave]] || hoyIso()
}

function guardar(clave, valor) {
  emit('marcar', { [CAMPO[clave]]: valor })
  editando.clave = null
}
</script>

<template>
  <section class="hoja p-5">
    <div class="flex items-baseline justify-between">
      <h2>Proceso</h2>
      <span class="text-sm text-tinta-suave">{{ gestion.proceso.hechas }} de {{ gestion.proceso.total }}</span>
    </div>
    <div class="mt-2 h-1.5 rounded bg-papel-hondo">
      <div class="h-1.5 rounded bg-libro" :style="{ width: `${(gestion.proceso.hechas / gestion.proceso.total) * 100}%` }" />
    </div>
    <ol class="mt-4 space-y-3">
      <li v-for="(e, i) in gestion.proceso.etapas" :key="e.clave" class="flex gap-3">
        <span
          class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
          :class="e.hecha ? 'bg-libro text-white' : e.clave === gestion.proceso.etapa_actual ? 'border-2 border-libro text-libro' : 'border border-papel-linea text-tinta-tenue'"
        >{{ e.hecha ? '✓' : i + 1 }}</span>
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium" :class="{ 'text-tinta-suave': e.hecha }">{{ e.nombre }}</p>
          <p v-if="e.fecha || e.detalle" class="text-xs text-tinta-suave">
            {{ e.fecha ? fecha(e.fecha) : '' }}{{ e.fecha && e.detalle ? ' · ' : '' }}{{ e.detalle }}
          </p>
          <p v-if="e.automatica && !e.hecha" class="text-xs text-tinta-tenue">Se marca sola</p>
          <template v-if="!e.automatica">
            <div v-if="editando.clave === e.clave" class="mt-1 flex flex-wrap items-center gap-2">
              <input v-model="editando.valor" type="date" class="campo w-auto py-1" />
              <button type="button" class="boton px-3 py-1" @click="guardar(e.clave, editando.valor)">Guardar</button>
              <button type="button" class="text-xs underline" @click="editando.clave = null">Cancelar</button>
            </div>
            <div v-else class="mt-0.5 flex gap-3 text-xs">
              <button type="button" class="text-libro underline" @click="abrir(e.clave)">
                {{ gestion.seguimiento[CAMPO[e.clave]] ? 'Cambiar fecha' : 'Marcar hecha' }}
              </button>
              <button v-if="gestion.seguimiento[CAMPO[e.clave]]" type="button" class="text-tinta-suave underline" @click="guardar(e.clave, null)">
                Desmarcar
              </button>
            </div>
          </template>
        </div>
      </li>
    </ol>
  </section>
</template>

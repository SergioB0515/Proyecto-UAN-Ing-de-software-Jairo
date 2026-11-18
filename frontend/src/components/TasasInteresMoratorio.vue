<script setup>
// Tasa de interés moratorio por mes (art. 635 ET). Mes sin tasa: no se calcula.
import { computed, onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { guardarTasa, listarTasas } from '../api/gestion'
import MensajeError from './MensajeError.vue'

const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
const tasas = ref([])
const error = ref('')
const aviso = ref('')
const hoy = new Date()
const form = reactive({ anio: hoy.getFullYear(), mes: hoy.getMonth() + 1, tasa_efectiva_anual: '', fuente: '' })
const visibles = computed(() => tasas.value.slice(0, 24))

async function cargar() {
  try {
    tasas.value = await listarTasas()
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function guardar() {
  error.value = ''
  try {
    await guardarTasa({ ...form })
    aviso.value = `Tasa de ${MESES[form.mes - 1].toLowerCase()} de ${form.anio} guardada.`
    form.tasa_efectiva_anual = ''
    await cargar()
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

onMounted(cargar)
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-baseline justify-between gap-3">
      <div>
        <h2>Tasa de interés moratorio</h2>
        <p class="text-sm text-tinta-suave">
          Efectiva anual de cada mes (art. 635 ET). Las publicadas por la DIAN vienen cargadas; agregue
          aquí cada mes nuevo cuando la DIAN lo publique, o corrija uno.
        </p>
      </div>
    </div>
    <MensajeError :mensaje="error" />
    <p v-if="aviso" class="text-sm text-libro" role="status">{{ aviso }}</p>

    <form class="flex flex-wrap items-end gap-2" @submit.prevent="guardar">
      <label><span class="etiqueta">Año</span><input v-model.number="form.anio" type="number" min="2000" max="2100" class="campo w-24" /></label>
      <label><span class="etiqueta">Mes</span>
        <select v-model.number="form.mes" class="campo w-36"><option v-for="(m, i) in MESES" :key="m" :value="i + 1">{{ m }}</option></select></label>
      <label><span class="etiqueta">Tasa % E.A.</span><input v-model="form.tasa_efectiva_anual" type="number" step="0.01" min="0" max="99" class="campo w-28" required /></label>
      <label class="min-w-48 flex-1"><span class="etiqueta">Fuente</span><input v-model="form.fuente" class="campo" placeholder="Resolución o publicación" /></label>
      <button class="boton">Guardar</button>
    </form>

    <div v-if="tasas.length" class="hoja overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr><th class="text-left">Mes</th><th class="cifra">Tasa E.A.</th><th class="text-left">Fuente</th></tr></thead>
        <tbody>
          <tr v-for="t in visibles" :key="`${t.anio}-${t.mes}`">
            <td>{{ MESES[t.mes - 1] }} {{ t.anio }}</td>
            <td class="cifra">{{ Number(t.tasa_efectiva_anual).toLocaleString('es-CO', { minimumFractionDigits: 2 }) }} %</td>
            <td class="text-xs text-tinta-suave">{{ t.fuente }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="text-sm text-tinta-suave">No hay tasas cargadas.</p>
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listarEventos } from '../api/auditoria'
import { mensajeDeError } from '../api/cliente'
import { listarContribuyentes } from '../api/contribuyentes'
import Cargando from '../components/Cargando.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import MensajeError from '../components/MensajeError.vue'

const route = useRoute()
const router = useRouter()
const eventos = ref(null)
const contribuyentes = ref([])
const error = ref('')
// El filtro vive en la URL para poder enlazar «Actividad de este contribuyente».
const filtro = ref(route.query.contribuyente ? Number(route.query.contribuyente) : null)

function fechaHora(valor) {
  return new Date(valor).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' })
}

async function cargar() {
  error.value = ''
  try {
    eventos.value = await listarEventos({ contribuyente_id: filtro.value ?? undefined, limite: 200 })
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

watch(filtro, (valor) => {
  router.replace({ query: valor ? { contribuyente: valor } : {} })
  cargar()
})

onMounted(async () => {
  cargar()
  try {
    contribuyentes.value = await listarContribuyentes()
  } catch {
    /* el filtro es opcional */
  }
})
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1>Actividad</h1>
        <p class="max-w-prose text-tinta-suave">
          Cada cambio que hiciste en los datos y cada reporte descargado, con fecha y dirección IP.
        </p>
      </div>
      <div>
        <label class="etiqueta" for="filtro">Contribuyente</label>
        <select id="filtro" v-model="filtro" class="campo w-64">
          <option :value="null">Todos</option>
          <option v-for="c in contribuyentes" :key="c.id" :value="c.id">{{ c.nombre }}</option>
        </select>
      </div>
    </header>

    <MensajeError :mensaje="error" />
    <Cargando v-if="eventos === null && !error" />
    <EstadoVacio v-else-if="eventos && !eventos.length" titulo="Sin actividad registrada">
      Aquí aparecerá lo que registres, edites, importes, cierres o descargues.
    </EstadoVacio>
    <div v-else-if="eventos" class="hoja overflow-x-auto">
      <table>
        <thead>
          <tr><th>Fecha</th><th>Acción</th><th>Contribuyente</th><th>Dirección IP</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in eventos" :key="e.id">
            <td class="whitespace-nowrap">{{ fechaHora(e.fecha) }}</td>
            <td>{{ e.descripcion }}</td>
            <td>
              <RouterLink
                v-if="e.nombre_contribuyente"
                :to="{ name: 'resumen', params: { id: e.contribuyente_id } }"
                class="enlace"
              >
                {{ e.nombre_contribuyente }}
              </RouterLink>
              <span v-else-if="e.contribuyente_id" class="text-tinta-tenue">Eliminado</span>
              <span v-else class="text-tinta-tenue">—</span>
            </td>
            <td class="text-tinta-suave">{{ e.ip ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

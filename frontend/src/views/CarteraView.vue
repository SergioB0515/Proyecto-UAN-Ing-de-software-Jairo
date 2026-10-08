<script setup>
import { onMounted, ref, watch } from 'vue'

import { obtenerPanelCartera } from '../api/cartera'
import { mensajeDeError } from '../api/cliente'
import Cargando from '../components/Cargando.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import MensajeError from '../components/MensajeError.vue'
import { ETIQUETAS_TIPO_CONTRIBUYENTE } from '../formato'

const anio = ref('')
const orden = ref('alertas')
const panel = ref(null)
const cargando = ref(true)
const error = ref('')

async function cargar() {
  cargando.value = true
  error.value = ''
  try {
    panel.value = await obtenerPanelCartera({
      anio_gravable: anio.value || undefined,
      orden: orden.value,
    })
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    cargando.value = false
  }
}

onMounted(cargar)
watch(orden, cargar)
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1>Cartera</h1>
        <p class="text-tinta-suave">Quién debe declarar y quién tiene ingresos o bienes sin declarar.</p>
      </div>
      <form class="flex flex-wrap items-end gap-3" @submit.prevent="cargar">
        <div>
          <label class="etiqueta" for="anio">Año gravable</label>
          <input id="anio" v-model="anio" type="number" min="2000" max="2100" placeholder="Más reciente" class="campo w-36" />
        </div>
        <div>
          <label class="etiqueta" for="orden">Ordenar por</label>
          <select id="orden" v-model="orden" class="campo w-40">
            <option value="alertas">Alertas</option>
            <option value="nombre">Nombre</option>
          </select>
        </div>
        <button type="submit" class="boton-secundario">Ver año</button>
      </form>
    </header>

    <MensajeError :mensaje="error" />
    <Cargando v-if="cargando && !panel" />

    <template v-else-if="panel">
      <dl class="grid divide-y divide-papel-linea sm:grid-cols-3 sm:divide-x sm:divide-y-0 rounded-md border border-papel-linea bg-white">
        <div class="px-5 py-4">
          <dt class="text-sm text-tinta-suave">Contribuyentes</dt>
          <dd class="cifra text-left text-2xl font-semibold">{{ panel.total_contribuyentes }}</dd>
        </div>
        <div class="px-5 py-4">
          <dt class="text-sm text-tinta-suave">Obligados a declarar</dt>
          <dd class="cifra text-left text-2xl font-semibold">{{ panel.total_obligados }}</dd>
        </div>
        <div class="px-5 py-4">
          <dt class="text-sm text-tinta-suave">Conceptos sin declarar</dt>
          <dd
            class="cifra text-left text-2xl font-semibold"
            :class="panel.total_alertas ? 'text-estado-nodeclarado' : ''"
          >
            {{ panel.total_alertas }}
          </dd>
        </div>
      </dl>

      <EstadoVacio v-if="!panel.contribuyentes.length" titulo="Aún no hay contribuyentes en tu cartera">
        <RouterLink :to="{ name: 'contribuyentes' }" class="enlace">Registra el primero</RouterLink>
        para empezar a conciliar su información exógena.
      </EstadoVacio>

      <div v-else class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Contribuyente</th>
              <th>Año</th>
              <th>¿Obligado?</th>
              <th class="cifra">Sin declarar</th>
              <th>Pendiente</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="fila in panel.contribuyentes" :key="fila.contribuyente_id">
              <td>
                <RouterLink
                  :to="{
                    name: 'resumen',
                    params: { id: fila.contribuyente_id },
                    query: fila.periodo_fiscal_id ? { periodo: fila.periodo_fiscal_id } : {},
                  }"
                  class="enlace"
                >
                  {{ fila.nombre }}
                </RouterLink>
                <p class="text-xs text-tinta-tenue">
                  NIT {{ fila.rut }}, {{ ETIQUETAS_TIPO_CONTRIBUYENTE[fila.tipo_contribuyente].toLowerCase() }}
                </p>
              </td>
              <td>
                <template v-if="fila.anio_gravable">
                  {{ fila.anio_gravable }}
                  <span v-if="fila.estado_periodo === 'CERRADO'" class="text-xs text-tinta-tenue">(cerrado)</span>
                </template>
                <span v-else class="text-tinta-tenue">—</span>
              </td>
              <td>
                <span v-if="fila.obligado === true" class="font-semibold">Sí</span>
                <span v-else-if="fila.obligado === false">No</span>
                <span v-else class="text-tinta-tenue">Sin datos</span>
              </td>
              <td class="cifra">
                <span
                  v-if="fila.alertas_no_declarado !== null"
                  :class="fila.alertas_no_declarado ? 'font-semibold text-estado-nodeclarado' : 'text-tinta-tenue'"
                >
                  {{ fila.alertas_no_declarado }}
                </span>
                <span v-else class="text-tinta-tenue">—</span>
              </td>
              <td class="text-tinta-suave">
                <p v-for="aviso in fila.avisos" :key="aviso" class="text-xs">{{ aviso }}</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

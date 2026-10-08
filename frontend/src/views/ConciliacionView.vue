<script setup>
import { computed, onMounted, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { conciliar } from '../api/conciliacion'
import Cargando from '../components/Cargando.vue'
import EstadoConciliacion from '../components/EstadoConciliacion.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import MensajeError from '../components/MensajeError.vue'
import { useContribuyente } from '../contexto'
import { dinero } from '../formato'

const { contribuyente, periodo } = useContribuyente()
const resultado = ref(null)
const sinExogena = ref(false)
const error = ref('')
const filtro = ref(null)

// Orden de lectura: primero lo que exige acción del contador.
const ORDEN = ['NO_DECLARADO', 'DISCREPANCIA', 'NO_REPORTADO_POR_TERCERO', 'COINCIDE']
const EXPLICACION = {
  NO_DECLARADO: 'Un tercero lo reportó a la DIAN y no está entre los activos o ingresos registrados.',
  DISCREPANCIA: 'Está registrado, pero el valor no coincide con lo reportado (tolerancia: $1.000 o 0,5 %).',
  NO_REPORTADO_POR_TERCERO: 'Está registrado, pero ningún tercero lo reportó, o no tiene cruce con la exógena.',
  COINCIDE: 'Registrado y reportado por el mismo valor.',
}

const items = computed(() => {
  if (!resultado.value) return []
  return [...resultado.value.items]
    .filter((i) => !filtro.value || i.estado === filtro.value)
    .sort((a, b) => ORDEN.indexOf(a.estado) - ORDEN.indexOf(b.estado))
})

function origenTexto(item) {
  const origen = { FuenteIngreso: 'Ingreso', Activo: 'Activo' }[item.origen] ?? 'Solo en la exógena'
  return item.concepto_code ? `${origen}, concepto ${item.concepto_code}` : origen
}

const FONDO_FILA = {
  NO_DECLARADO: 'bg-estado-nodeclarado-claro/50',
  DISCREPANCIA: 'bg-estado-discrepancia-claro/60',
}

onMounted(async () => {
  try {
    resultado.value = await conciliar(contribuyente.value.id, periodo.value.id)
  } catch (e) {
    if (e.response?.status === 404) sinExogena.value = true
    else error.value = mensajeDeError(e)
  }
})
</script>

<template>
  <MensajeError :mensaje="error" />
  <EstadoVacio v-if="sinExogena" :titulo="`Falta la exógena de ${periodo.anio_gravable}`">
    La conciliación cruza lo registrado contra el archivo de la DIAN.
    <RouterLink :to="{ name: 'exogena', query: $route.query }" class="enlace">Importa la exógena</RouterLink> primero.
  </EstadoVacio>
  <Cargando v-else-if="!resultado && !error" />

  <div v-else-if="resultado" class="space-y-5">
    <div class="flex flex-wrap gap-2" role="group" aria-label="Filtrar por estado">
      <button
        type="button"
        class="rounded-full border px-3 py-1 text-sm"
        :class="filtro === null ? 'border-tinta bg-tinta text-white' : 'border-papel-linea bg-white'"
        :aria-pressed="filtro === null"
        @click="filtro = null"
      >
        Todos ({{ resultado.items.length }})
      </button>
      <button
        v-for="estado in ORDEN"
        :key="estado"
        type="button"
        class="flex items-center gap-2 rounded-full border bg-white py-1 pl-1 pr-3 text-sm"
        :class="filtro === estado ? 'border-tinta' : 'border-papel-linea'"
        :aria-pressed="filtro === estado"
        @click="filtro = filtro === estado ? null : estado"
      >
        <EstadoConciliacion :estado="estado" />
        <span class="cifra font-semibold">{{ resultado.resumen[estado] }}</span>
      </button>
    </div>
    <p v-if="filtro" class="text-sm text-tinta-suave">{{ EXPLICACION[filtro] }}</p>

    <!-- Libro de dos columnas: lo declarado frente a lo reportado por terceros. -->
    <div class="hoja overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Concepto</th>
            <th>Reportado por</th>
            <th class="cifra border-l border-papel-linea">Declarado</th>
            <th class="cifra">Exógena</th>
            <th class="cifra">Diferencia</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!items.length">
            <td colspan="6" class="py-6 text-center text-tinta-suave">Nada en este estado.</td>
          </tr>
          <tr v-for="(item, i) in items" :key="i" :class="FONDO_FILA[item.estado]">
            <td>
              {{ item.concepto }}
              <p class="text-xs text-tinta-tenue">
                {{ origenTexto(item) }}
              </p>
            </td>
            <td>
              <template v-if="item.nombre_reportante">
                {{ item.nombre_reportante }}
                <p class="text-xs text-tinta-tenue">NIT {{ item.nit_reportante }}</p>
              </template>
              <span v-else class="text-tinta-tenue">—</span>
            </td>
            <td class="cifra border-l border-papel-linea">{{ dinero(item.valor_declarado) }}</td>
            <td class="cifra">{{ dinero(item.valor_exogena) }}</td>
            <td class="cifra" :class="item.estado === 'DISCREPANCIA' ? 'font-semibold text-estado-discrepancia' : 'text-tinta-suave'">
              <template v-if="item.diferencia !== null">{{ item.diferencia > 0 ? '+' : '' }}{{ dinero(item.diferencia) }}</template>
              <template v-else>—</template>
            </td>
            <td><EstadoConciliacion :estado="item.estado" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="max-w-prose text-xs text-tinta-suave">
      Diferencia = exógena − declarado: positiva cuando la DIAN ve más de lo declarado. No se cruzan las
      retenciones, los consumos con tarjeta ni lo que reporta el propio contribuyente o la DIAN.
    </p>
  </div>
</template>

<script setup>
// El cruce de la liquidación contra lo que la DIAN ya sabe: los cinco topes de
// la exógena reconstruidos desde su detalle, y lo que se va a declarar frente a
// lo que reportaron los terceros.
import { computed, onMounted, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { obtenerCruceDian } from '../api/conciliacion'
import { dinero } from '../formato'
import MensajeError from './MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  periodoId: { type: Number, required: true },
})

const cruce = ref(null)
const error = ref('')
const topeAbierto = ref(null)

const SEVERIDAD = {
  ALTA: { texto: 'Riesgo', clase: 'bg-estado-nodeclarado-claro text-estado-nodeclarado' },
  MEDIA: { texto: 'Revisar', clase: 'bg-estado-discrepancia-claro text-estado-discrepancia' },
  OPORTUNIDAD: { texto: 'A favor', clase: 'bg-libro-claro text-libro-oscuro' },
  OK: { texto: 'Cubre', clase: 'bg-papel-hondo text-tinta-suave' },
  SIN_DATO: { texto: 'Sin dato', clase: 'bg-estado-noreportado-claro text-estado-noreportado' },
}
const ORDEN = ['ALTA', 'MEDIA', 'OPORTUNIDAD', 'SIN_DATO', 'OK']

const comparaciones = computed(() =>
  [...(cruce.value?.comparaciones ?? [])].sort(
    (a, b) => ORDEN.indexOf(a.severidad) - ORDEN.indexOf(b.severidad),
  ),
)

const titular = computed(() => {
  const r = cruce.value?.resumen ?? {}
  if (r.ALTA) {
    return `${r.ALTA} cifra(s) del borrador quedan por debajo de lo que la DIAN ya tiene reportado.`
  }
  if (r.MEDIA) return `Sin faltantes frente a la DIAN; ${r.MEDIA} punto(s) para revisar.`
  return 'Lo que se va a declarar cubre lo que la DIAN tiene reportado.'
})

async function cargar() {
  try {
    cruce.value = await obtenerCruceDian(props.contribuyenteId, props.periodoId)
  } catch (e) {
    // Sin exógena no hay cruce; la vista que lo contiene ya lo explica.
    if (e.response?.status !== 404) error.value = mensajeDeError(e)
  }
}

defineExpose({ cargar })
onMounted(cargar)
</script>

<template>
  <MensajeError :mensaje="error" />
  <section v-if="cruce" class="hoja p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2>Cruce con la DIAN</h2>
        <p class="mt-1 max-w-prose text-sm" :class="cruce.resumen.ALTA ? 'font-semibold text-estado-nodeclarado' : 'text-tinta-suave'">
          {{ titular }}
        </p>
      </div>
      <span
        v-if="cruce.obligado_a_declarar !== null"
        class="rounded px-3 py-1 text-sm font-medium"
        :class="cruce.obligado_a_declarar ? 'bg-estado-discrepancia-claro text-estado-discrepancia' : 'bg-papel-hondo text-tinta-suave'"
      >
        {{ cruce.obligado_a_declarar ? 'Obligado a declarar según los topes' : 'Ningún tope obliga a declarar' }}
      </span>
    </div>

    <!-- Lo que se va a declarar frente a lo reportado -->
    <div class="mt-4 overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Lo que se compara</th>
            <th class="text-right">La DIAN tiene</th>
            <th class="text-right">El borrador declara</th>
            <th class="text-right">Diferencia</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in comparaciones" :key="c.clave">
            <td>
              <span class="mr-2 rounded px-2 py-0.5 text-xs font-medium" :class="SEVERIDAD[c.severidad].clase">
                {{ SEVERIDAD[c.severidad].texto }}
              </span>
              <span class="font-medium">{{ c.titulo }}</span>
              <span class="ml-1 text-xs text-tinta-tenue">casilla(s) {{ c.casillas }}</span>
              <p class="mt-1 max-w-2xl text-sm text-tinta-suave">{{ c.mensaje }}</p>
            </td>
            <td class="cifra">{{ dinero(c.valor_dian) }}</td>
            <td class="cifra">{{ dinero(c.valor_declarado) }}</td>
            <td class="cifra" :class="c.severidad === 'ALTA' ? 'font-semibold text-estado-nodeclarado' : ''">
              {{ dinero(c.diferencia) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Los cinco topes, reconstruidos desde el detalle -->
    <h3 class="mt-6 text-base font-semibold">Los cinco topes del archivo</h3>
    <p class="mt-1 max-w-prose text-sm text-tinta-suave">
      Son las cifras consolidadas con las que la DIAN decide a quién revisar. Cada una
      se reconstruye aquí desde el detalle del mismo archivo: si no cuadra, el archivo
      se leyó mal.
    </p>
    <div class="mt-3 overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Tope</th>
            <th class="text-right">Reporta el archivo</th>
            <th class="text-right">Desde el detalle</th>
            <th class="text-right">Umbral para declarar</th>
            <th><span class="sr-only">Detalle</span></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="t in cruce.topes" :key="t.numero">
            <tr>
              <td>
                {{ t.numero }}. {{ t.nombre }}
                <span
                  class="ml-2 rounded px-2 py-0.5 text-xs font-medium"
                  :class="t.cuadra ? 'bg-libro-claro text-libro-oscuro' : 'bg-estado-discrepancia-claro text-estado-discrepancia'"
                >
                  {{ t.cuadra ? 'Cuadra' : 'No cuadra' }}
                </span>
              </td>
              <td class="cifra">{{ dinero(t.valor_tope) }}</td>
              <td class="cifra">{{ dinero(t.valor_esperado) }}</td>
              <td class="cifra">
                {{ dinero(t.umbral) }}
                <span v-if="t.supera_umbral" class="ml-1 text-xs font-medium text-estado-discrepancia">lo supera</span>
              </td>
              <td class="text-right">
                <button
                  type="button"
                  class="enlace text-sm"
                  :aria-expanded="topeAbierto === t.numero"
                  @click="topeAbierto = topeAbierto === t.numero ? null : t.numero"
                >
                  {{ topeAbierto === t.numero ? 'Ocultar' : `Ver ${t.registros.length} registro(s)` }}
                </button>
              </td>
            </tr>
            <tr v-if="topeAbierto === t.numero">
              <td colspan="5" class="bg-papel">
                <p class="text-sm text-tinta-suave">{{ t.explicacion }}</p>
                <ul class="mt-2 space-y-1 text-sm">
                  <li v-for="(r, i) in t.registros" :key="i" class="flex flex-wrap justify-between gap-2">
                    <span>
                      {{ r.detalle }}
                      <span v-if="r.reportante" class="text-xs text-tinta-tenue">— {{ r.reportante }}</span>
                      <span v-if="Number(r.participacion) < 1" class="text-xs text-tinta-tenue">
                        ({{ Math.round(Number(r.participacion) * 100) }} % de {{ dinero(r.valor) }})
                      </span>
                    </span>
                    <span class="cifra">{{ dinero(r.valor_propio) }}</span>
                  </li>
                </ul>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div v-if="cruce.pendientes.length" class="mt-6">
      <h3 class="text-base font-semibold">Sin renglón asignado por la DIAN</h3>
      <ul class="mt-2 space-y-1 text-sm">
        <li v-for="(r, i) in cruce.pendientes" :key="i" class="flex flex-wrap justify-between gap-2">
          <span>
            {{ r.detalle }}
            <span class="text-xs text-tinta-tenue">— puede ir en {{ r.renglones_posibles.join(', ') }}</span>
          </span>
          <span class="cifra">{{ dinero(r.valor) }}</span>
        </li>
      </ul>
    </div>

    <ul v-if="cruce.diagnosticos.length" class="mt-4 list-disc space-y-1 pl-5 text-sm text-tinta-suave">
      <li v-for="(d, i) in cruce.diagnosticos" :key="i">{{ d }}</li>
    </ul>
    <p class="mt-4 max-w-prose text-xs text-tinta-tenue">{{ cruce.advertencia }}</p>
  </section>
</template>

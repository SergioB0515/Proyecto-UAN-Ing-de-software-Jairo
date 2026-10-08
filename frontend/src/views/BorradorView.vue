<script setup>
import { onMounted, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { obtenerBorradorRenglones } from '../api/conciliacion'
import Cargando from '../components/Cargando.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import MensajeError from '../components/MensajeError.vue'
import { useContribuyente } from '../contexto'
import { dinero } from '../formato'

const { contribuyente, periodo } = useContribuyente()
const borrador = ref(null)
const sinExogena = ref(false)
const error = ref('')

const numero = (renglon) => renglon.replace(/\D/g, '') || renglon

onMounted(async () => {
  try {
    borrador.value = await obtenerBorradorRenglones(contribuyente.value.id, periodo.value.id)
  } catch (e) {
    if (e.response?.status === 404) sinExogena.value = true
    else error.value = mensajeDeError(e)
  }
})
</script>

<template>
  <MensajeError :mensaje="error" />
  <EstadoVacio v-if="sinExogena" :titulo="`Falta la exógena de ${periodo.anio_gravable}`">
    El borrador sale de la columna «Uso declaración sugerida» del archivo de la DIAN.
    <RouterLink :to="{ name: 'exogena', query: $route.query }" class="enlace">Importa la exógena</RouterLink> primero.
  </EstadoVacio>
  <Cargando v-else-if="!borrador && !error" />

  <div v-else-if="borrador" class="space-y-5">
    <p class="max-w-prose rounded border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro px-4 py-3 text-sm">
      {{ borrador.advertencia }}
    </p>

    <EstadoVacio v-if="!borrador.renglones.length" titulo="La exógena no sugiere ningún renglón">
      Ningún registro del archivo trae un renglón sugerido.
    </EstadoVacio>

    <!-- Casillas al estilo del formulario 210: número de renglón y valor. -->
    <section v-else class="hoja max-w-3xl p-5 sm:p-6">
      <h2>Formulario 210, año gravable {{ periodo.anio_gravable }}</h2>
      <p class="text-sm text-tinta-suave">{{ contribuyente.nombre }}, NIT {{ contribuyente.rut }}</p>
      <ol class="mt-5 grid gap-x-8 gap-y-3 sm:grid-cols-2">
        <li v-for="r in borrador.renglones" :key="r.renglon" class="flex items-stretch">
          <span
            class="flex w-12 shrink-0 items-center justify-center rounded-l bg-tinta text-sm font-semibold text-white"
            :aria-label="`Renglón ${numero(r.renglon)}`"
          >
            {{ numero(r.renglon) }}
          </span>
          <span class="flex flex-1 flex-col justify-center rounded-r border border-l-0 border-papel-linea px-3 py-2">
            <span class="cifra text-base font-semibold">{{ dinero(r.valor_total) }}</span>
            <span class="text-right text-xs text-tinta-tenue">
              {{ r.cantidad_registros }} {{ r.cantidad_registros === 1 ? 'registro' : 'registros' }}
            </span>
          </span>
        </li>
      </ol>
      <p class="mt-5 text-xs text-tinta-suave">
        Una fila de la exógena con varios renglones sugeridos suma en cada uno de ellos, así que estos
        valores no se deben sumar entre sí.
      </p>
    </section>
  </div>
</template>

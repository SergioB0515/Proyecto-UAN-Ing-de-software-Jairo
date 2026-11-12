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

    <div v-if="borrador.diagnosticos?.length" class="space-y-2">
      <p
        v-for="(d, i) in borrador.diagnosticos"
        :key="i"
        role="alert"
        class="max-w-prose rounded border-l-4 border-estado-nodeclarado bg-estado-nodeclarado-claro px-4 py-3 text-sm"
      >
        {{ d }}
      </p>
    </div>

    <!-- Cuadre contra los topes del propio archivo. La DIAN informa el
         detalle y también el consolidado, así que el borrador se puede
         verificar solo. -->
    <section v-if="borrador.cuadres?.length" class="hoja max-w-3xl p-5">
      <h2>Cuadre contra los topes del archivo</h2>
      <p class="mt-1 text-sm text-tinta-suave">
        El mismo archivo de la DIAN trae el detalle y el consolidado. Si no coinciden,
        algún registro se contó de más o falta alguno.
      </p>
      <table class="mt-4">
        <thead>
          <tr>
            <th>Tope del archivo</th>
            <th class="text-right">Reporta</th>
            <th class="text-right">Borrador</th>
            <th class="text-right">Diferencia</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in borrador.cuadres" :key="c.etiqueta">
            <td>
              {{ c.etiqueta }}
              <span
                class="ml-2 rounded px-2 py-0.5 text-xs font-medium"
                :class="c.cuadra ? 'bg-libro-claro text-libro-oscuro' : 'bg-estado-discrepancia-claro text-estado-discrepancia'"
              >
                {{ c.cuadra ? 'Cuadra' : 'No cuadra' }}
              </span>
            </td>
            <td class="cifra">{{ dinero(c.valor_tope) }}</td>
            <td class="cifra">{{ dinero(c.valor_borrador) }}</td>
            <td class="cifra" :class="c.cuadra ? '' : 'font-semibold text-estado-discrepancia'">
              {{ dinero(c.diferencia) }}
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Registros que la DIAN no asignó a un renglón concreto. -->
    <section v-if="borrador.sin_asignar?.length" class="hoja max-w-3xl p-5">
      <h2>Sin renglón asignado</h2>
      <p class="mt-1 max-w-prose text-sm text-tinta-suave">
        En estos registros la DIAN no asigna un renglón: ofrece varios posibles y deja
        la decisión al declarante. <strong>No se sumaron a ninguno</strong>, porque
        repartirlos en todos contaría el mismo valor varias veces.
      </p>
      <table class="mt-4">
        <thead>
          <tr>
            <th>Detalle</th>
            <th class="text-right">Valor</th>
            <th>Renglones posibles</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in borrador.sin_asignar" :key="i">
            <td>
              {{ r.detalle }}
              <p class="max-w-md text-xs text-tinta-tenue">{{ r.uso_sugerido }}</p>
            </td>
            <td class="cifra">{{ dinero(r.valor) }}</td>
            <td>
              <span
                v-for="ren in r.renglones_posibles"
                :key="ren"
                class="mr-1 inline-block rounded bg-papel-hondo px-2 py-0.5 text-xs font-medium"
              >
                {{ ren }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <EstadoVacio v-if="!borrador.renglones.length" titulo="La exógena no sugiere ningún renglón">
      Ningún registro del archivo trae un renglón sugerido.
    </EstadoVacio>

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
            <span v-if="r.nombre_oficial" class="text-xs text-tinta-suave">{{ r.nombre_oficial }}</span>
            <span class="cifra text-base font-semibold">{{ dinero(r.valor_total) }}</span>
            <span class="text-right text-xs text-tinta-tenue">
              {{ r.cantidad_registros }} {{ r.cantidad_registros === 1 ? 'registro' : 'registros' }}
            </span>
          </span>
        </li>
      </ol>
      <p class="mt-5 text-xs text-tinta-suave">
        Una fila con varios renglones asignados suma en cada uno, así que estos valores no se
        deben sumar entre sí. Las filas en las que la DIAN no asigna renglón se listan aparte.
      </p>
    </section>
  </div>
</template>

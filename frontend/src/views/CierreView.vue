<script setup>
import { computed, onMounted, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { cerrarPeriodo, descargarReporte, obtenerResumen, reabrirPeriodo } from '../api/reportes'
import MensajeError from '../components/MensajeError.vue'
import { useContribuyente } from '../contexto'
import { dinero, fecha } from '../formato'

const { contribuyente, periodo, manejaInventario, recargarPeriodos } = useContribuyente()
const cid = contribuyente.value.id
const cerrado = computed(() => periodo.value.estado === 'CERRADO')

const cierre = ref(null)
const confirmando = ref(false)
const procesando = ref(false)
const error = ref('')
const errorDescarga = ref('')
const descargando = ref('')

const REPORTES = computed(() => [
  { tipo: 'resumen', titulo: 'Resumen del contribuyente', detalle: 'Patrimonio, ingresos, obligación y conciliación.' },
  { tipo: 'conciliacion', titulo: 'Conciliación con la exógena', detalle: 'Cada concepto con su estado y diferencia.' },
  { tipo: 'borrador-renglones', titulo: 'Borrador por renglón', detalle: 'Valores sugeridos para el formulario 210.' },
  ...(manejaInventario.value
    ? [
        { tipo: 'kardex', titulo: 'Kardex', detalle: 'Movimientos valorizados por producto.' },
        { tipo: 'saldo-inventario', titulo: 'Saldo de inventario', detalle: 'Costo de ventas e inventario final.' },
      ]
    : []),
])

async function cargarCierre() {
  const resumen = await obtenerResumen(cid, periodo.value.id)
  cierre.value = resumen.cierre
}

async function ejecutar(accion) {
  error.value = ''
  procesando.value = true
  try {
    await accion(cid, periodo.value.id)
    await recargarPeriodos()
    await cargarCierre()
    confirmando.value = false
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    procesando.value = false
  }
}

async function descargar(tipo, formato) {
  errorDescarga.value = ''
  descargando.value = `${tipo}-${formato}`
  try {
    await descargarReporte(cid, periodo.value.id, tipo, formato)
  } catch (e) {
    errorDescarga.value = mensajeDeError(e)
  } finally {
    descargando.value = ''
  }
}

onMounted(() => cargarCierre().catch((e) => (error.value = mensajeDeError(e))))
</script>

<template>
  <div class="grid gap-8 lg:grid-cols-[22rem_1fr]">
    <section class="hoja h-fit space-y-4 p-5">
      <h2>Año gravable {{ periodo.anio_gravable }}</h2>
      <p class="text-sm">
        Estado:
        <span class="font-semibold" :class="cerrado ? 'text-tinta' : 'text-libro'">{{ cerrado ? 'Cerrado' : 'Abierto' }}</span>
      </p>

      <template v-if="cerrado && cierre">
        <dl class="space-y-1 text-sm">
          <div class="flex justify-between"><dt class="text-tinta-suave">Cerrado el</dt><dd>{{ fecha(cierre.fecha_cierre) }}</dd></div>
          <template v-if="cierre.activo_inventario_id">
            <div class="flex justify-between"><dt class="text-tinta-suave">Inventario final</dt><dd class="cifra">{{ dinero(cierre.valor_inventario) }}</dd></div>
            <div class="flex justify-between"><dt class="text-tinta-suave">Costo de ventas</dt><dd class="cifra">{{ dinero(cierre.costo_ventas) }}</dd></div>
          </template>
        </dl>
      </template>

      <p class="text-sm text-tinta-suave">
        <template v-if="!cerrado">
          Cerrar el año bloquea nuevos movimientos, activos, ingresos y exógena.
          <template v-if="manejaInventario">El inventario final queda registrado como activo del patrimonio.</template>
          Los años anteriores deben estar cerrados.
        </template>
        <template v-else>
          Reabrir deshace el cierre para corregir datos. Solo se puede reabrir el último año cerrado.
        </template>
      </p>

      <div v-if="!confirmando">
        <button v-if="!cerrado" type="button" class="boton" @click="confirmando = true">Cerrar año {{ periodo.anio_gravable }}</button>
        <button v-else type="button" class="boton-peligro" @click="confirmando = true">Reabrir año {{ periodo.anio_gravable }}</button>
      </div>
      <div v-else class="space-y-3 rounded bg-papel-hondo p-3">
        <p class="text-sm font-medium">
          {{ cerrado ? `¿Reabrir ${periodo.anio_gravable}? Se borrará el inventario que registró el cierre.` : `¿Cerrar ${periodo.anio_gravable}?` }}
        </p>
        <div class="flex gap-2">
          <button
            type="button"
            :class="cerrado ? 'boton-peligro' : 'boton'"
            :disabled="procesando"
            @click="ejecutar(cerrado ? reabrirPeriodo : cerrarPeriodo)"
          >
            {{ cerrado ? 'Sí, reabrir' : 'Sí, cerrar' }}
          </button>
          <button type="button" class="boton-secundario" @click="confirmando = false">Cancelar</button>
        </div>
      </div>
      <MensajeError :mensaje="error" />
    </section>

    <section class="space-y-3">
      <h2>Reportes de {{ periodo.anio_gravable }}</h2>
      <MensajeError :mensaje="errorDescarga" />
      <ul class="hoja divide-y divide-papel-hondo">
        <li v-for="r in REPORTES" :key="r.tipo" class="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div>
            <p class="font-medium">{{ r.titulo }}</p>
            <p class="text-sm text-tinta-suave">{{ r.detalle }}</p>
          </div>
          <div class="flex gap-2">
            <button
              v-for="formato in ['xlsx', 'pdf']"
              :key="formato"
              type="button"
              class="boton-secundario px-3 py-1.5"
              :disabled="descargando === `${r.tipo}-${formato}`"
              @click="descargar(r.tipo, formato)"
            >
              {{ formato === 'xlsx' ? 'Excel' : 'PDF' }}
            </button>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

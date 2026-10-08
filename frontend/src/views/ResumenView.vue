<script setup>
import { onMounted, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { obtenerResumen } from '../api/reportes'
import Cargando from '../components/Cargando.vue'
import EstadoConciliacion from '../components/EstadoConciliacion.vue'
import MensajeError from '../components/MensajeError.vue'
import TablaObligacion from '../components/TablaObligacion.vue'
import { useContribuyente } from '../contexto'
import { ETIQUETAS_TIPO_ACTIVO, dinero, fecha } from '../formato'

const { contribuyente, periodo } = useContribuyente()
const resumen = ref(null)
const error = ref('')

onMounted(async () => {
  try {
    resumen.value = await obtenerResumen(contribuyente.value.id, periodo.value.id)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
})
</script>

<template>
  <MensajeError :mensaje="error" />
  <Cargando v-if="!resumen && !error" />

  <div v-if="resumen" class="space-y-6">
    <ul v-if="resumen.avisos.length" class="space-y-1 rounded border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro px-4 py-3 text-sm">
      <li v-for="aviso in resumen.avisos" :key="aviso">{{ aviso }}</li>
    </ul>

    <p v-if="resumen.cierre" class="text-sm text-tinta-suave">
      Periodo cerrado el {{ fecha(resumen.cierre.fecha_cierre) }}.
    </p>

    <div class="grid gap-6 lg:grid-cols-2">
      <section class="hoja p-5">
        <h2>Patrimonio al 31 de diciembre</h2>
        <p class="cifra mt-2 text-left text-3xl font-semibold">{{ dinero(resumen.patrimonio.patrimonio_liquido) }}</p>
        <table v-if="Object.keys(resumen.patrimonio.por_tipo).length" class="mt-4">
          <tbody>
            <tr v-for="(valor, tipo) in resumen.patrimonio.por_tipo" :key="tipo">
              <td class="px-0">{{ ETIQUETAS_TIPO_ACTIVO[tipo] ?? tipo }}</td>
              <td class="cifra px-0">{{ dinero(valor) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="mt-3 text-sm text-tinta-suave">
          Sin activos en este año.
          <RouterLink :to="{ name: 'patrimonio', query: $route.query }" class="enlace">Registrar activos</RouterLink>
        </p>
      </section>

      <section class="hoja p-5">
        <h2>Ingresos del año</h2>
        <p class="cifra mt-2 text-left text-3xl font-semibold">{{ dinero(resumen.ingresos.total_ingresos) }}</p>
        <table class="mt-4">
          <tbody>
            <tr>
              <td class="px-0">Fuentes de ingreso</td>
              <td class="cifra px-0">{{ resumen.ingresos.cantidad_fuentes }}</td>
            </tr>
            <tr>
              <td class="px-0">Retenciones en la fuente</td>
              <td class="cifra px-0">{{ dinero(resumen.ingresos.total_retenciones) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="resumen.inventario" class="hoja p-5">
        <h2>Inventario y costo de ventas</h2>
        <table class="mt-3">
          <tbody>
            <tr>
              <td class="px-0">Ventas</td>
              <td class="cifra px-0">{{ dinero(resumen.inventario.total_ingresos_ventas) }}</td>
            </tr>
            <tr>
              <td class="px-0">Costo de ventas</td>
              <td class="cifra px-0">{{ dinero(resumen.inventario.total_costo_ventas) }}</td>
            </tr>
            <tr>
              <td class="px-0 font-semibold">Utilidad bruta</td>
              <td class="cifra px-0 font-semibold">{{ dinero(resumen.inventario.total_utilidad_bruta) }}</td>
            </tr>
            <tr>
              <td class="px-0">Inventario final ({{ resumen.inventario.cantidad_productos }} {{ resumen.inventario.cantidad_productos === 1 ? 'producto' : 'productos' }})</td>
              <td class="cifra px-0">{{ dinero(resumen.inventario.inventario_final) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="hoja p-5">
        <h2>Conciliación con la exógena</h2>
        <ul v-if="resumen.conciliacion" class="mt-3 space-y-2">
          <li v-for="(n, estado) in resumen.conciliacion" :key="estado" class="flex items-center justify-between">
            <EstadoConciliacion :estado="estado" />
            <span class="cifra font-semibold">{{ n }}</span>
          </li>
        </ul>
        <p v-else class="mt-3 text-sm text-tinta-suave">
          Se calcula al importar la exógena.
          <RouterLink :to="{ name: 'exogena', query: $route.query }" class="enlace">Importar exógena</RouterLink>
        </p>
        <RouterLink v-if="resumen.conciliacion" :to="{ name: 'conciliacion', query: $route.query }" class="enlace mt-4 inline-block text-sm">
          Ver el detalle de la conciliación
        </RouterLink>
      </section>
    </div>

    <section v-if="resumen.obligacion" class="hoja p-5">
      <h2 class="sr-only">Obligación de declarar</h2>
      <TablaObligacion :obligacion="resumen.obligacion" />
    </section>
  </div>
</template>

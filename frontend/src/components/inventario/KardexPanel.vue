<script setup>
import { onMounted, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { obtenerCostoVentas, obtenerKardexPeriodo } from '../../api/inventario'
import { cantidad, dinero, fecha } from '../../formato'
import Cargando from '../Cargando.vue'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  periodo: { type: Object, required: true },
})

const costo = ref(null)
const kardex = ref([])
const error = ref('')

onMounted(async () => {
  try {
    ;[costo.value, kardex.value] = await Promise.all([
      obtenerCostoVentas(props.contribuyenteId, props.periodo.id),
      obtenerKardexPeriodo(props.contribuyenteId, props.periodo.id),
    ])
  } catch (e) {
    error.value = mensajeDeError(e)
  }
})
</script>

<template>
  <MensajeError :mensaje="error" />
  <Cargando v-if="!costo && !error" />
  <div v-else-if="costo" class="space-y-8">
    <section class="space-y-3">
      <h2>Costo de ventas {{ periodo.anio_gravable }}</h2>
      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Producto</th>
              <th class="cifra">Vendido</th>
              <th class="cifra">Ventas</th>
              <th class="cifra">Costo de ventas</th>
              <th class="cifra">Utilidad bruta</th>
              <th class="cifra">Inventario final</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!costo.productos.length"><td colspan="6" class="py-6 text-center text-tinta-suave">Sin movimientos este año.</td></tr>
            <tr v-for="p in costo.productos" :key="p.producto_id">
              <td>{{ p.codigo }}, {{ p.nombre }}</td>
              <td class="cifra">{{ cantidad(p.cantidad_vendida) }}</td>
              <td class="cifra">{{ dinero(p.ingresos_ventas) }}</td>
              <td class="cifra">{{ dinero(p.costo_ventas) }}</td>
              <td class="cifra">{{ dinero(p.utilidad_bruta) }}</td>
              <td class="cifra">{{ dinero(p.saldo_final_valor) }}</td>
            </tr>
          </tbody>
          <tfoot v-if="costo.productos.length">
            <tr class="font-semibold">
              <td class="border-0">Total</td>
              <td class="border-0"></td>
              <td class="cifra border-0">{{ dinero(costo.total_ingresos_ventas) }}</td>
              <td class="cifra border-0">{{ dinero(costo.total_costo_ventas) }}</td>
              <td class="cifra border-0">{{ dinero(costo.total_utilidad_bruta) }}</td>
              <td class="cifra border-0">{{ dinero(costo.total_inventario_final) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <section v-for="k in kardex" :key="k.producto_id" class="space-y-2">
      <h3>Kardex: {{ k.codigo }}, {{ k.nombre }} <span class="font-normal text-tinta-suave">({{ k.metodo_costeo === 'PEPS' ? 'PEPS' : 'promedio ponderado' }})</span></h3>
      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Movimiento</th>
              <th class="cifra">Cantidad</th>
              <th class="cifra">Costo unitario</th>
              <th class="cifra">Costo total</th>
              <th class="cifra border-l border-papel-linea">Saldo (unidades)</th>
              <th class="cifra">Saldo ($)</th>
            </tr>
          </thead>
          <tbody>
            <tr class="text-tinta-suave">
              <td colspan="5">Saldo inicial</td>
              <td class="cifra border-l border-papel-linea">{{ cantidad(k.saldo_inicial_cantidad) }}</td>
              <td class="cifra">{{ dinero(k.saldo_inicial_valor) }}</td>
            </tr>
            <tr v-for="l in k.lineas" :key="l.movimiento_id">
              <td>{{ fecha(l.fecha) }}</td>
              <td>{{ l.tipo === 'ENTRADA' ? 'Compra' : 'Venta' }}</td>
              <td class="cifra">{{ l.tipo === 'SALIDA' ? '−' : '' }}{{ cantidad(l.cantidad) }}</td>
              <td class="cifra">{{ dinero(l.costo_unitario) }}</td>
              <td class="cifra">{{ dinero(l.costo_total) }}</td>
              <td class="cifra border-l border-papel-linea">{{ cantidad(l.saldo_cantidad) }}</td>
              <td class="cifra">{{ dinero(l.saldo_valor) }}</td>
            </tr>
            <tr class="font-semibold">
              <td colspan="5">Saldo final</td>
              <td class="cifra border-l border-papel-linea">{{ cantidad(k.saldo_final_cantidad) }}</td>
              <td class="cifra">{{ dinero(k.saldo_final_valor) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

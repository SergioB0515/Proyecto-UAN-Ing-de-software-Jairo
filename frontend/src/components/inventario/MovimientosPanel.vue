<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { listarMovimientos, registrarMovimiento } from '../../api/inventario'
import { cantidad, dinero, fecha } from '../../formato'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  periodo: { type: Object, required: true },
  productos: { type: Array, required: true },
  proveedores: { type: Array, required: true },
  documentos: { type: Array, required: true },
})
const emit = defineEmits(['cambio'])

const movimientos = ref([])
const error = ref('')
const cerrado = computed(() => props.periodo.estado === 'CERRADO')
const productosActivos = computed(() => props.productos.filter((p) => p.activo))
const porId = (lista) => Object.fromEntries(lista.map((x) => [x.id, x]))
const productoPorId = computed(() => porId(props.productos))
const documentoPorId = computed(() => porId(props.documentos))

function vacio() {
  return {
    tipo: 'ENTRADA',
    producto_id: null,
    documento_soporte_id: null,
    proveedor_id: null,
    fecha: `${props.periodo.anio_gravable}-01-01`,
    cantidad: null,
    valor_unitario: null,
  }
}
const form = reactive({ datos: vacio(), error: '', guardando: false })
const faltanDatos = computed(() => !productosActivos.value.length || !props.documentos.length)

async function cargar() {
  try {
    movimientos.value = await listarMovimientos(props.contribuyenteId, { periodo_fiscal_id: props.periodo.id })
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function registrar() {
  form.error = ''
  form.guardando = true
  try {
    await registrarMovimiento(props.contribuyenteId, {
      ...form.datos,
      periodo_fiscal_id: props.periodo.id,
      proveedor_id: form.datos.tipo === 'ENTRADA' ? form.datos.proveedor_id : null,
    })
    const tipo = form.datos.tipo
    form.datos = { ...vacio(), tipo }
    await cargar()
    emit('cambio') // las existencias del producto cambiaron
  } catch (e) {
    form.error = mensajeDeError(e)
  } finally {
    form.guardando = false
  }
}

onMounted(cargar)
</script>

<template>
  <div class="space-y-6">
    <p v-if="cerrado" class="rounded bg-papel-hondo px-4 py-3 text-sm">
      El año {{ periodo.anio_gravable }} está cerrado y no admite movimientos.
    </p>
    <p v-else-if="faltanDatos" class="rounded bg-papel-hondo px-4 py-3 text-sm">
      Para registrar movimientos necesitas al menos un producto activo y un documento soporte
      (pestañas «Productos» y «Proveedores y documentos»).
    </p>

    <form v-else class="hoja space-y-4 p-5" @submit.prevent="registrar">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2>Registrar movimiento</h2>
        <div class="inline-flex rounded border border-papel-linea p-0.5" role="radiogroup" aria-label="Tipo de movimiento">
          <label
            v-for="t in ['ENTRADA', 'SALIDA']"
            :key="t"
            class="cursor-pointer rounded px-3 py-1 text-sm"
            :class="form.datos.tipo === t ? 'bg-tinta text-white' : 'text-tinta-suave'"
          >
            <input v-model="form.datos.tipo" type="radio" :value="t" class="sr-only" />
            {{ t === 'ENTRADA' ? 'Compra (entrada)' : 'Venta (salida)' }}
          </label>
        </div>
      </div>
      <div class="grid gap-4 sm:grid-cols-3">
        <div>
          <label class="etiqueta" for="m-producto">Producto</label>
          <select id="m-producto" v-model="form.datos.producto_id" class="campo" required>
            <option :value="null" disabled>Elige un producto</option>
            <option v-for="p in productosActivos" :key="p.id" :value="p.id">
              {{ p.codigo }}, {{ p.nombre }} ({{ cantidad(p.stock_actual) }} en existencia)
            </option>
          </select>
        </div>
        <div>
          <label class="etiqueta" for="m-doc">Documento soporte</label>
          <select id="m-doc" v-model="form.datos.documento_soporte_id" class="campo" required>
            <option :value="null" disabled>Elige un documento</option>
            <option v-for="d in documentos" :key="d.id" :value="d.id">{{ d.tipo.toLowerCase().replace('_', ' ') }} {{ d.numero }}</option>
          </select>
        </div>
        <div v-if="form.datos.tipo === 'ENTRADA'">
          <label class="etiqueta" for="m-prov">Proveedor</label>
          <select id="m-prov" v-model="form.datos.proveedor_id" class="campo">
            <option :value="null">Sin proveedor</option>
            <option v-for="p in proveedores" :key="p.id" :value="p.id">{{ p.nombre }}</option>
          </select>
        </div>
        <div>
          <label class="etiqueta" for="m-fecha">Fecha</label>
          <input
            id="m-fecha"
            v-model="form.datos.fecha"
            type="date"
            class="campo"
            required
            :min="`${periodo.anio_gravable}-01-01`"
            :max="`${periodo.anio_gravable}-12-31`"
          />
        </div>
        <div>
          <label class="etiqueta" for="m-cant">Cantidad</label>
          <input id="m-cant" v-model.number="form.datos.cantidad" type="number" min="0" step="any" class="campo" required />
        </div>
        <div>
          <label class="etiqueta" for="m-valor">
            {{ form.datos.tipo === 'ENTRADA' ? 'Costo unitario de compra' : 'Precio unitario de venta' }}
          </label>
          <input id="m-valor" v-model.number="form.datos.valor_unitario" type="number" min="0" step="any" class="campo" required />
        </div>
      </div>
      <p v-if="form.datos.tipo === 'SALIDA'" class="text-xs text-tinta-tenue">
        El costo de la venta lo calcula el método de costeo del producto (PEPS o promedio ponderado).
      </p>
      <MensajeError :mensaje="form.error" />
      <button type="submit" class="boton" :disabled="form.guardando">
        Registrar {{ form.datos.tipo === 'ENTRADA' ? 'compra' : 'venta' }}
      </button>
    </form>

    <section class="space-y-3">
      <h2>Movimientos de {{ periodo.anio_gravable }}</h2>
      <MensajeError :mensaje="error" />
      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Tipo</th>
              <th>Producto</th>
              <th>Documento</th>
              <th class="cifra">Cantidad</th>
              <th class="cifra">Valor unitario</th>
              <th class="cifra">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!movimientos.length"><td colspan="7" class="py-6 text-center text-tinta-suave">Sin movimientos este año.</td></tr>
            <tr v-for="m in movimientos" :key="m.id">
              <td>{{ fecha(m.fecha) }}</td>
              <td>{{ m.tipo === 'ENTRADA' ? 'Compra' : 'Venta' }}</td>
              <td>{{ productoPorId[m.producto_id]?.nombre }}</td>
              <td class="text-tinta-suave">{{ documentoPorId[m.documento_soporte_id]?.numero }}</td>
              <td class="cifra">{{ m.tipo === 'SALIDA' ? '−' : '' }}{{ cantidad(m.cantidad) }}</td>
              <td class="cifra">{{ dinero(m.valor_unitario) }}</td>
              <td class="cifra">{{ dinero(m.valor_total) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup>
// Venta de inmuebles: costo fiscal (arts. 69, 72 y 73), utilidad y si va como
// ganancia ocasional (dos años o más) o como renta ordinaria (art. 300).
import { onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { crearVentaInmueble, eliminarVentaInmueble, listarVentasInmuebles } from '../../api/liquidacion'
import { dinero, fecha } from '../../formato'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  periodoFiscalId: { type: Number, required: true },
  anioGravable: { type: Number, required: true },
})
const emit = defineEmits(['cambio'])

const ventas = ref([])
const error = ref('')
const vacia = () => ({
  abierto: false,
  descripcion: '',
  tipo: 'URBANO',
  fecha_adquisicion: '',
  fecha_venta: '',
  valor_venta: '',
  costo_adquisicion: '',
  mejoras_y_valorizacion: '',
  avaluo_catastral_anterior: '',
  es_casa_de_habitacion: false,
  porcentaje_participacion: 100,
  retencion: '',
  factor_manual: '',
})
const form = reactive(vacia())
const TIPOS = { URBANO: 'Urbano', RURAL_AGROPECUARIO: 'Rural agropecuario', RURAL: 'Rural' }

async function cargar() {
  try {
    ventas.value = await listarVentasInmuebles(props.contribuyenteId, props.periodoFiscalId)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function guardar() {
  error.value = ''
  const n = (v) => (v === '' || v === null ? null : v)
  const { abierto, ...datos } = form
  try {
    await crearVentaInmueble(props.contribuyenteId, props.periodoFiscalId, {
      ...datos,
      mejoras_y_valorizacion: datos.mejoras_y_valorizacion || 0,
      retencion: datos.retencion || 0,
      avaluo_catastral_anterior: n(datos.avaluo_catastral_anterior),
      factor_manual: n(datos.factor_manual),
    })
    Object.assign(form, vacia())
    await cargar()
    emit('cambio')
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function eliminar(id) {
  error.value = ''
  try {
    await eliminarVentaInmueble(props.contribuyenteId, props.periodoFiscalId, id)
    await cargar()
    emit('cambio')
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

onMounted(cargar)
</script>

<template>
  <section class="hoja p-5">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2>Venta de inmuebles</h2>
      <button v-if="!form.abierto" type="button" class="boton-secundario" @click="form.abierto = true">Registrar una venta</button>
    </div>
    <p class="mt-1 max-w-prose text-sm text-tinta-suave">
      El costo fiscal es el mayor entre el costo de compra reajustado con la tabla del art. 73 (más mejoras) y el
      avalúo catastral del año anterior (art. 72). Si se tuvo dos años o más, la utilidad es ganancia ocasional; si
      no, renta ordinaria.
    </p>
    <MensajeError :mensaje="error" />

    <form v-if="form.abierto" class="mt-4 space-y-3" @submit.prevent="guardar">
      <div class="grid gap-3 sm:grid-cols-3">
        <label class="sm:col-span-2"><span class="etiqueta">Inmueble</span><input v-model="form.descripcion" class="campo" required minlength="3" placeholder="Apartamento, matrícula 50C-…" /></label>
        <label><span class="etiqueta">Tipo</span>
          <select v-model="form.tipo" class="campo"><option v-for="(t, v) in TIPOS" :key="v" :value="v">{{ t }}</option></select></label>
        <label><span class="etiqueta">Fecha de compra</span><input v-model="form.fecha_adquisicion" type="date" class="campo" required /></label>
        <label><span class="etiqueta">Fecha de venta</span><input v-model="form.fecha_venta" type="date" class="campo" required /></label>
        <label><span class="etiqueta">Participación %</span><input v-model.number="form.porcentaje_participacion" type="number" min="0.01" max="100" step="0.01" class="campo" required /></label>
        <label><span class="etiqueta">Valor de venta</span><input v-model.number="form.valor_venta" type="number" min="0" step="1000" class="campo" required /></label>
        <label><span class="etiqueta">Costo de compra</span><input v-model.number="form.costo_adquisicion" type="number" min="0" step="1000" class="campo" required /></label>
        <label><span class="etiqueta">Mejoras y valorización</span><input v-model.number="form.mejoras_y_valorizacion" type="number" min="0" step="1000" class="campo" /></label>
        <label><span class="etiqueta">Avalúo catastral del año anterior</span><input v-model.number="form.avaluo_catastral_anterior" type="number" min="0" step="1000" class="campo" /></label>
        <label><span class="etiqueta">Retención de la notaría</span><input v-model.number="form.retencion" type="number" min="0" step="1000" class="campo" /></label>
        <label><span class="etiqueta">Multiplicador art. 73 (solo sin tabla)</span><input v-model="form.factor_manual" type="number" min="0" step="0.01" class="campo" :placeholder="anioGravable === 2025 ? 'Cargado para 2025' : 'Del decreto del año'" /></label>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="form.es_casa_de_habitacion" type="checkbox" />
        Era su casa o apartamento de habitación (exención de hasta 5.000 UVT, art. 311-1)
      </label>
      <div class="flex gap-2">
        <button class="boton">Guardar</button>
        <button type="button" class="boton-secundario" @click="Object.assign(form, vacia())">Cancelar</button>
      </div>
    </form>

    <ul v-if="ventas.length" class="mt-4 space-y-3">
      <li v-for="v in ventas" :key="v.id" class="rounded border border-papel-linea p-4 text-sm">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <p class="font-medium">{{ v.descripcion }}</p>
          <span class="rounded px-2 py-0.5 text-xs" :class="v.es_ganancia_ocasional ? 'bg-libro-claro' : 'bg-estado-discrepancia-claro'">
            {{ v.es_ganancia_ocasional ? 'Ganancia ocasional' : 'Renta ordinaria' }}
          </span>
        </div>
        <p class="text-xs text-tinta-suave">Compra {{ fecha(v.fecha_adquisicion) }} · venta {{ fecha(v.fecha_venta) }} · {{ TIPOS[v.tipo].toLowerCase() }}</p>
        <dl class="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
          <div class="flex justify-between"><dt class="text-tinta-suave">Valor de venta</dt><dd class="cifra">{{ dinero(v.valor_venta) }}</dd></div>
          <div class="flex justify-between"><dt class="text-tinta-suave">Costo fiscal ({{ v.metodo_costo === 'ART_72' ? 'avalúo, art. 72' : 'reajustado, art. 73' }})</dt><dd class="cifra">{{ dinero(v.costo_fiscal) }}</dd></div>
          <div class="flex justify-between"><dt class="text-tinta-suave">{{ v.perdida > 0 ? 'Pérdida' : 'Utilidad' }}</dt><dd class="cifra">{{ dinero(v.perdida > 0 ? v.perdida : v.utilidad) }}</dd></div>
          <div v-if="v.exenta > 0" class="flex justify-between"><dt class="text-tinta-suave">Exenta (art. 311-1)</dt><dd class="cifra">{{ dinero(v.exenta) }}</dd></div>
        </dl>
        <p class="mt-2 text-xs text-tinta-suave">{{ v.formula }}</p>
        <p v-for="a in v.avisos" :key="a" class="mt-1 text-xs">{{ a }}</p>
        <button type="button" class="mt-2 text-xs text-estado-nodeclarado underline" @click="eliminar(v.id)">Eliminar</button>
      </li>
    </ul>
  </section>
</template>

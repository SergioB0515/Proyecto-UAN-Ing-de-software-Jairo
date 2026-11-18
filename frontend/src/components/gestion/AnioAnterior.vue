<script setup>
// La declaración del año anterior: registrarla si no se hizo en la app,
// compararla casilla por casilla y traer a la hoja lo que esta declaración
// toma de ella.
import { computed, reactive, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { registrarDeclaracionAnterior, traerDelAnioAnterior } from '../../api/gestion'
import { dinero, fecha } from '../../formato'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  gestion: { type: Object, required: true },
  contribuyenteId: { type: Number, required: true },
  periodoId: { type: Number, required: true },
})
const emit = defineEmits(['cambio'])

const CASILLAS = [
  [29, 'Patrimonio bruto'],
  [30, 'Deudas'],
  [31, 'Patrimonio líquido'],
  [32, 'Ingresos brutos rentas de trabajo'],
  [43, 'Ingresos rentas de trabajo sin vínculo laboral'],
  [58, 'Ingresos brutos rentas de capital'],
  [74, 'Ingresos brutos rentas no laborales'],
  [111, 'Renta líquida gravable'],
  [126, 'Impuesto neto de renta'],
  [127, 'Impuesto de ganancias ocasionales'],
  [132, 'Retenciones'],
  [133, 'Anticipo del año siguiente'],
  [136, 'Total saldo a pagar'],
  [137, 'Total saldo a favor'],
]
const anio = computed(() => props.gestion.anio_gravable - 1)
const form = reactive({ abierto: false, fecha_presentacion: '', numero_formulario: '', valores: {} })
const error = ref('')
const cambios = ref(null)

async function registrar() {
  error.value = ''
  const casillas = Object.fromEntries(
    Object.entries(form.valores).filter(([, v]) => v !== '' && v !== null && v !== undefined),
  )
  try {
    await registrarDeclaracionAnterior(props.contribuyenteId, {
      anio_gravable: anio.value,
      fecha_presentacion: form.fecha_presentacion,
      numero_formulario: form.numero_formulario || null,
      casillas,
    })
    form.abierto = false
    emit('cambio')
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function traer() {
  error.value = ''
  try {
    cambios.value = await traerDelAnioAnterior(props.contribuyenteId, props.periodoId)
    emit('cambio')
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

const porcentaje = (v) => (v === null || v === undefined ? '—' : `${Number(v) > 0 ? '+' : ''}${Number(v).toLocaleString('es-CO')} %`)
</script>

<template>
  <section class="hoja p-5">
    <h2>Frente al año {{ anio }}</h2>
    <MensajeError :mensaje="error" />

    <template v-if="!gestion.declaracion_anterior">
      <p class="mt-1 text-sm text-tinta-suave">
        No hay declaración de {{ anio }} registrada. Con ella se comparan las cifras, se valida el
        anticipo y el saldo a favor que se traen, y se calcula el beneficio de auditoría.
      </p>
      <button v-if="!form.abierto" type="button" class="boton mt-3" @click="form.abierto = true">
        Registrar la declaración de {{ anio }}
      </button>
      <form v-else class="mt-4 space-y-3" @submit.prevent="registrar">
        <div class="grid gap-3 sm:grid-cols-2">
          <label><span class="etiqueta">Fecha de presentación</span>
            <input v-model="form.fecha_presentacion" type="date" class="campo" required /></label>
          <label><span class="etiqueta">Número de formulario (opcional)</span>
            <input v-model="form.numero_formulario" class="campo" /></label>
        </div>
        <p class="text-sm text-tinta-suave">Copie las casillas de la declaración presentada. Las vacías no se guardan.</p>
        <div class="grid gap-x-4 gap-y-2 sm:grid-cols-2">
          <label v-for="[n, nombre] in CASILLAS" :key="n" class="flex items-center gap-2 text-sm">
            <span class="w-8 shrink-0 text-right text-xs text-tinta-tenue">{{ n }}</span>
            <span class="w-44 shrink-0">{{ nombre }}</span>
            <input v-model.number="form.valores[n]" type="number" min="0" step="1000" class="campo py-1" />
          </label>
        </div>
        <div class="flex gap-2">
          <button class="boton">Guardar</button>
          <button type="button" class="boton-secundario" @click="form.abierto = false">Cancelar</button>
        </div>
      </form>
    </template>

    <template v-else>
      <p class="mt-1 text-sm text-tinta-suave">
        {{ gestion.comparativo.origen_anterior }} · presentada el {{ fecha(gestion.declaracion_anterior.fecha_presentacion) }}
        <template v-if="gestion.declaracion_anterior.numero_formulario"> · formulario {{ gestion.declaracion_anterior.numero_formulario }}</template>
      </p>

      <ul v-if="gestion.comparativo.coherencias.length" class="mt-4 space-y-2">
        <li
          v-for="c in gestion.comparativo.coherencias"
          :key="c.descripcion"
          class="rounded p-3 text-sm"
          :class="c.cuadra ? 'bg-papel-hondo' : 'bg-estado-discrepancia-claro'"
        >
          <p class="font-medium">{{ c.cuadra ? '✓' : '!' }} {{ c.descripcion }}: {{ dinero(c.registrado) }}
            <template v-if="!c.cuadra">— debería ser {{ dinero(c.esperado) }}</template></p>
          <p v-if="!c.cuadra" class="text-tinta-suave">{{ c.explicacion }}</p>
        </li>
      </ul>
      <div class="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" class="boton-secundario" @click="traer">Traer anticipo, saldo a favor e impuesto a la hoja</button>
        <span v-if="cambios" class="text-sm text-tinta-suave">{{ cambios.length ? `Actualizado: ${cambios.join('; ')}` : 'La hoja ya tenía esos valores.' }}</span>
      </div>

      <div class="mt-4 overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="text-left text-tinta-suave">
            <tr><th class="py-2 pr-2 font-medium">Casilla</th><th class="text-right font-medium">{{ anio }}</th>
              <th class="text-right font-medium">{{ gestion.anio_gravable }}</th><th class="text-right font-medium">Variación</th></tr>
          </thead>
          <tbody class="divide-y divide-papel-hondo">
            <tr v-for="f in gestion.comparativo.filas" :key="f.casilla" :class="{ 'bg-estado-discrepancia-claro': f.revisar }">
              <td class="py-2 pr-2"><span class="text-xs text-tinta-tenue">{{ f.casilla }}</span> {{ f.nombre }}</td>
              <td class="cifra text-right">{{ dinero(f.anterior) }}</td>
              <td class="cifra text-right">{{ dinero(f.actual) }}</td>
              <td class="cifra text-right" :title="f.revisar ? 'Variación mayor al 30 %: revise la causa' : ''">
                <template v-if="f.variacion_porcentaje !== null">{{ porcentaje(f.variacion_porcentaje) }}</template>
                <span v-else-if="f.diferencia === null" class="text-tinta-tenue" title="Esa casilla no se copió de la declaración anterior">Sin dato</span>
                <template v-else>—</template>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="mt-2 text-xs text-tinta-tenue">Resaltadas: variaciones de más del 30 % y de más de 20 UVT. No son errores; son las que la DIAN mira primero.</p>
      </div>
    </template>
  </section>
</template>

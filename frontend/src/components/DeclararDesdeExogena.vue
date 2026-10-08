<script setup>
// Formulario corto para declarar un concepto que la exógena reporta y no
// está registrado: llega prellenado con el detalle, el valor y el código de
// concepto, y crea un activo o una fuente de ingreso del periodo.
import { reactive } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { crearActivo, crearFuenteIngreso } from '../api/contribuyentes'
import { ETIQUETAS_TIPO_ACTIVO } from '../formato'
import MensajeError from './MensajeError.vue'

const props = defineProps({
  item: { type: Object, required: true },
  contribuyenteId: { type: Number, required: true },
  periodoId: { type: Number, required: true },
})
const emit = defineEmits(['declarado', 'cancelar'])

const detalle = (props.item.concepto || '')
  .replace(/\(Concepto:\s*\d+\)/i, '')
  .replace(/\s+/g, ' ')
  .trim()
const texto = detalle.toLowerCase()

// Sugerencia inicial a partir del detalle de la DIAN; el contador la cambia si no aplica.
const pareceIngreso = /ingreso|venta|salario|honorario|pago|arrend|rendimiento|dividend|pensi/.test(texto)
function tipoActivoSugerido() {
  if (/aval[uú]o|inmueble|predio|catastr/.test(texto)) return 'INMUEBLE'
  if (/veh[ií]culo|automotor|placa/.test(texto)) return 'VEHICULO'
  if (/cdt|inversi|acci[oó]n|fondo|t[ií]tulo/.test(texto)) return 'INVERSION'
  return 'CUENTA'
}

const form = reactive({
  clase: pareceIngreso ? 'fuente' : 'activo',
  descripcion: detalle.slice(0, 200),
  tipo: tipoActivoSugerido(),
  valor: props.item.valor_exogena,
  retencion: 0,
  error: '',
  guardando: false,
})

// El vínculo hace que, al recalcular, este registro se cruce con el de la exógena.
function vinculo() {
  return props.item.concepto_code
    ? { vinculo_codigo_concepto: props.item.concepto_code, vinculo_palabra_clave: null }
    : { vinculo_codigo_concepto: null, vinculo_palabra_clave: detalle.slice(0, 200) }
}

async function guardar() {
  form.error = ''
  form.guardando = true
  try {
    if (form.clase === 'activo') {
      await crearActivo(props.contribuyenteId, {
        periodo_fiscal_id: props.periodoId,
        descripcion: form.descripcion,
        tipo: form.tipo,
        valor: form.valor,
        ...vinculo(),
      })
    } else {
      await crearFuenteIngreso(props.contribuyenteId, {
        periodo_fiscal_id: props.periodoId,
        concepto: form.descripcion,
        valor_anual: form.valor,
        retencion_fuente: form.retencion || 0,
        ...vinculo(),
      })
    }
    emit('declarado')
  } catch (e) {
    form.error = mensajeDeError(e)
  } finally {
    form.guardando = false
  }
}
</script>

<template>
  <form class="space-y-3 rounded border border-papel-linea bg-white p-4" @submit.prevent="guardar">
    <div class="flex flex-wrap items-center gap-4 text-sm" role="radiogroup" aria-label="Registrar como">
      <span class="font-medium">Registrar como</span>
      <label class="flex items-center gap-2"><input v-model="form.clase" type="radio" value="activo" class="accent-libro" /> Activo</label>
      <label class="flex items-center gap-2"><input v-model="form.clase" type="radio" value="fuente" class="accent-libro" /> Ingreso</label>
    </div>
    <div class="grid gap-3 sm:grid-cols-4">
      <div class="sm:col-span-2">
        <label class="etiqueta" :for="`d-desc-${item.registro_exogena_id}`">{{ form.clase === 'activo' ? 'Descripción' : 'Concepto' }}</label>
        <input :id="`d-desc-${item.registro_exogena_id}`" v-model="form.descripcion" class="campo" required maxlength="200" />
      </div>
      <div v-if="form.clase === 'activo'">
        <label class="etiqueta" :for="`d-tipo-${item.registro_exogena_id}`">Tipo</label>
        <select :id="`d-tipo-${item.registro_exogena_id}`" v-model="form.tipo" class="campo">
          <option v-for="t in ['CUENTA', 'VEHICULO', 'INMUEBLE', 'INVERSION']" :key="t" :value="t">{{ ETIQUETAS_TIPO_ACTIVO[t] }}</option>
        </select>
      </div>
      <div v-else>
        <label class="etiqueta" :for="`d-ret-${item.registro_exogena_id}`">Retención</label>
        <input :id="`d-ret-${item.registro_exogena_id}`" v-model.number="form.retencion" type="number" min="0" step="any" class="campo" />
      </div>
      <div>
        <label class="etiqueta" :for="`d-valor-${item.registro_exogena_id}`">Valor (COP)</label>
        <input :id="`d-valor-${item.registro_exogena_id}`" v-model.number="form.valor" type="number" min="1" step="any" class="campo" required />
      </div>
    </div>
    <p class="text-xs text-tinta-tenue">
      Queda vinculado al {{ item.concepto_code ? `concepto ${item.concepto_code}` : 'detalle de la exógena' }} para que la
      conciliación lo cruce.
    </p>
    <MensajeError :mensaje="form.error" />
    <div class="flex gap-2">
      <button type="submit" class="boton" :disabled="form.guardando">
        Registrar {{ form.clase === 'activo' ? 'activo' : 'ingreso' }}
      </button>
      <button type="button" class="boton-secundario" @click="emit('cancelar')">Cancelar</button>
    </div>
  </form>
</template>

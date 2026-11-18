<script setup>
// Documentos que hay que pedirle al cliente, sugeridos desde la exógena y las
// deducciones, con su estado y el mensaje listo para enviar.
import { onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { actualizarDocumento, agregarDocumento, obtenerDocumentos } from '../../api/gestion'
import { fecha } from '../../formato'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  periodoId: { type: Number, required: true },
})
const emit = defineEmits(['cambio'])

const solicitud = ref(null)
const error = ref('')
const copiado = ref(false)
const nuevo = reactive({ abierto: false, descripcion: '', tercero: '' })

const ESTADOS = { PENDIENTE: 'Pendiente', RECIBIDO: 'Recibido', NO_APLICA: 'No aplica' }

async function cargar() {
  try {
    solicitud.value = await obtenerDocumentos(props.contribuyenteId, props.periodoId)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function cambiarEstado(doc, estado) {
  error.value = ''
  try {
    solicitud.value = await actualizarDocumento(props.contribuyenteId, props.periodoId, doc.clave, { estado })
    emit('cambio')
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function agregar() {
  error.value = ''
  try {
    solicitud.value = await agregarDocumento(props.contribuyenteId, props.periodoId, {
      descripcion: nuevo.descripcion,
      tercero: nuevo.tercero,
    })
    Object.assign(nuevo, { abierto: false, descripcion: '', tercero: '' })
    emit('cambio')
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function copiar() {
  try {
    await navigator.clipboard.writeText(solicitud.value.mensaje)
    copiado.value = true
    setTimeout(() => (copiado.value = false), 2000)
  } catch {
    error.value = 'No se pudo copiar: seleccione el texto y cópielo a mano.'
  }
}

onMounted(cargar)
defineExpose({ cargar })
</script>

<template>
  <section class="hoja p-5">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2>Documentos del cliente</h2>
      <span v-if="solicitud" class="text-sm text-tinta-suave">
        {{ solicitud.recibidos }} recibidos · {{ solicitud.pendientes }} pendientes
      </span>
    </div>
    <p class="mt-1 text-sm text-tinta-suave">
      Sugeridos a partir de la exógena y de las deducciones solicitadas: un certificado por tercero.
    </p>
    <MensajeError :mensaje="error" />

    <ul v-if="solicitud" class="mt-4 divide-y divide-papel-hondo">
      <li v-for="d in solicitud.documentos" :key="d.clave" class="flex flex-wrap items-start justify-between gap-3 py-3">
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium" :class="{ 'text-tinta-suave line-through': d.estado === 'NO_APLICA' }">{{ d.descripcion }}</p>
          <p class="text-xs text-tinta-suave">
            <template v-if="d.tercero">{{ d.tercero }}<template v-if="d.nit"> · NIT {{ d.nit }}</template> · </template>
            {{ d.motivo }}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <span v-if="d.actualizado_en" class="text-xs text-tinta-tenue">{{ fecha(d.actualizado_en) }}</span>
          <select :value="d.estado" class="campo w-auto py-1" :aria-label="`Estado de ${d.descripcion}`" @change="cambiarEstado(d, $event.target.value)">
            <option v-for="(texto, valor) in ESTADOS" :key="valor" :value="valor">{{ texto }}</option>
          </select>
        </div>
      </li>
    </ul>

    <div class="mt-3">
      <button v-if="!nuevo.abierto" type="button" class="text-sm text-libro underline" @click="nuevo.abierto = true">
        Agregar otro documento
      </button>
      <form v-else class="grid gap-2 sm:grid-cols-[1fr_14rem_auto]" @submit.prevent="agregar">
        <input v-model="nuevo.descripcion" class="campo" placeholder="Documento" required minlength="3" />
        <input v-model="nuevo.tercero" class="campo" placeholder="Quién lo expide (opcional)" />
        <button class="boton">Agregar</button>
      </form>
    </div>

    <div v-if="solicitud?.mensaje" class="mt-5">
      <div class="flex items-center justify-between">
        <p class="etiqueta mb-0">Mensaje para el cliente</p>
        <button type="button" class="boton-secundario px-3 py-1" @click="copiar">{{ copiado ? 'Copiado' : 'Copiar' }}</button>
      </div>
      <textarea class="campo mt-1 h-48 font-mono text-xs" readonly :value="solicitud.mensaje" />
    </div>
  </section>
</template>

<script setup>
// Documentos para el cliente: sugeridos, estado, lo que él contestó y el
// mensaje para pedírselos. Es la misma lista que el contribuyente ve en su
// enlace de carga, no una copia.
import { computed, onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { actualizarDocumento, agregarDocumento, obtenerDocumentos } from '../../api/gestion'
import { ETIQUETAS_ESTADO_DOCUMENTO, dinero, fecha } from '../../formato'
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

const COLORES = {
  PENDIENTE: 'bg-estado-noreportado-claro text-estado-noreportado',
  RECIBIDO: 'bg-libro-claro text-estado-coincide',
  NO_APLICA: 'bg-papel-hondo text-tinta-suave',
  NO_LO_TENGO: 'bg-estado-discrepancia-claro text-estado-discrepancia',
  NO_ENTIENDO: 'bg-estado-nodeclarado-claro text-estado-nodeclarado',
}

// Lo que el contribuyente contestó y el contador tiene que atender.
const atencion = computed(() => {
  const s = solicitud.value
  if (!s) return []
  const avisos = []
  if (s.no_entiendo) avisos.push(`${s.no_entiendo} con «no entiendo»: esperan tu explicación.`)
  if (s.no_lo_tengo) avisos.push(`${s.no_lo_tengo} que el cliente dice no tener.`)
  if (s.sin_reconocer)
    avisos.push(`${s.sin_reconocer} concepto(s) de la exógena que la aplicación no clasificó.`)
  return avisos
})

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
    solicitud.value = await actualizarDocumento(
      props.contribuyenteId,
      props.periodoId,
      doc.clave,
      { estado },
    )
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
      Sugeridos a partir de la exógena, de las deducciones solicitadas y de lo que el cliente
      registró en su enlace: un certificado por tercero. Es la misma lista que él ve.
    </p>
    <MensajeError :mensaje="error" />

    <ul v-if="atencion.length" class="mt-3 space-y-1">
      <li
        v-for="aviso in atencion"
        :key="aviso"
        class="rounded bg-estado-discrepancia-claro px-3 py-2 text-sm"
      >
        {{ aviso }}
      </li>
    </ul>

    <ul v-if="solicitud" class="mt-4 divide-y divide-papel-hondo">
      <li v-for="d in solicitud.documentos" :key="d.clave" class="py-3">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <p
              class="text-sm font-medium"
              :class="{ 'text-tinta-suave line-through': d.estado === 'NO_APLICA' }"
            >
              {{ d.descripcion }}
              <span
                v-if="!d.reconocido"
                class="ml-1 rounded-full bg-estado-discrepancia-claro px-2 py-0.5 text-xs font-semibold text-estado-discrepancia"
              >
                sin clasificar
              </span>
            </p>
            <p class="text-xs text-tinta-suave">
              <template v-if="d.tercero"
                >{{ d.tercero }}<template v-if="d.nit"> · NIT {{ d.nit }}</template> ·
              </template>
              {{ d.motivo }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <span
              class="whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold"
              :class="COLORES[d.estado]"
            >
              {{ ETIQUETAS_ESTADO_DOCUMENTO[d.estado] }}
            </span>
            <span v-if="d.actualizado_en" class="text-xs text-tinta-tenue">
              {{ fecha(d.actualizado_en) }}
            </span>
            <select
              :value="d.estado"
              class="campo w-auto py-1"
              :aria-label="`Estado de ${d.descripcion}`"
              @change="cambiarEstado(d, $event.target.value)"
            >
              <option
                v-for="(texto, valor) in ETIQUETAS_ESTADO_DOCUMENTO"
                :key="valor"
                :value="valor"
              >
                {{ texto }}
              </option>
            </select>
          </div>
        </div>

        <!-- Lo que puso el cliente desde su enlace. -->
        <div
          v-if="d.respondido_por_contribuyente || d.nota || d.valor_informado || d.archivos.length"
          class="mt-2 space-y-1 rounded bg-papel-hondo/50 px-3 py-2 text-sm"
        >
          <p v-if="d.respondido_por_contribuyente" class="text-xs text-tinta-tenue">
            Lo contestó el contribuyente desde su enlace.
          </p>
          <p v-if="d.nota">Nota: «{{ d.nota }}»</p>
          <p v-if="d.valor_informado">
            Valor que informó: <span class="cifra">{{ dinero(Number(d.valor_informado)) }}</span>
          </p>
          <div v-if="d.archivos.length">
            <p class="font-medium">Soportes cargados</p>
            <ul class="mt-0.5 text-tinta-suave">
              <li v-for="a in d.archivos" :key="a.id">{{ a.nombre_original }}</li>
            </ul>
            <p class="text-xs text-tinta-tenue">Se abren desde la pestaña «Soportes».</p>
          </div>
        </div>
      </li>
    </ul>

    <div class="mt-3">
      <button
        v-if="!nuevo.abierto"
        type="button"
        class="text-sm text-libro underline"
        @click="nuevo.abierto = true"
      >
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
        <button type="button" class="boton-secundario px-3 py-1" @click="copiar">
          {{ copiado ? 'Copiado' : 'Copiar' }}
        </button>
      </div>
      <p class="mb-1 text-xs text-tinta-tenue">
        Si prefieres que los cargue él mismo, usa el enlace de arriba en vez de este mensaje.
      </p>
      <textarea class="campo mt-1 h-48 font-mono text-xs" readonly :value="solicitud.mensaje" />
    </div>
  </section>
</template>

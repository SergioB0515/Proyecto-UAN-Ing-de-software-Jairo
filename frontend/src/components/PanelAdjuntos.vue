<script>
let panelActivo = null
</script>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import {
  actualizarAdjunto,
  descargarAdjunto,
  eliminarAdjunto,
  listarAdjuntos,
  subirAdjunto,
} from '../api/adjuntos'
import { mensajeDeError } from '../api/cliente'
import { ETIQUETAS_CATEGORIA_ADJUNTO, fechaHora, tamano } from '../formato'
import { nombreDeCaptura } from '../soportes'
import IconoArchivo from './IconoArchivo.vue'
import MensajeError from './MensajeError.vue'
import VistaPreviaAdjunto from './VistaPreviaAdjunto.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  entidadTipo: { type: String, required: true },
  entidadId: { type: Number, required: true },
  titulo: { type: String, default: '' },
  ayuda: { type: String, default: '' },
  categoriaInicial: { type: String, default: 'OTRO' },
  puedeEliminar: { type: Boolean, default: true },
})
const emit = defineEmits(['cambio'])

const adjuntos = ref([])
const cargando = ref(true)
const error = ref('')
const subidas = ref([])
const arrastrando = ref(false)
const categoria = ref(props.categoriaInicial)
const descripcion = ref('')
const indicePrevia = ref(null)
const confirmandoId = ref(null)
const edicion = reactive({ id: null, categoria: 'OTRO', descripcion: '', guardando: false, error: '' })
const selector = ref(null)
const raiz = ref(null)
const yo = Symbol('panel-adjuntos')
let encima = false
let contadorSubidas = 0

const previsualizables = computed(() => adjuntos.value.filter((a) => a.previsualizable))
const idDescripcion = `desc-adjunto-${props.entidadTipo}-${props.entidadId}`
const idCategoria = `cat-adjunto-${props.entidadTipo}-${props.entidadId}`

async function cargar() {
  try {
    adjuntos.value = await listarAdjuntos(props.contribuyenteId, {
      entidad_tipo: props.entidadTipo,
      entidad_id: props.entidadId,
    })
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    cargando.value = false
  }
}

function alEntrarElRaton() {
  encima = true
  panelActivo = yo
}

function alSalirElRaton() {
  encima = false
  if (panelActivo === yo && !raiz.value?.contains(document.activeElement)) panelActivo = null
}

function alEnfocar() {
  panelActivo = yo
}

function alDesenfocar(evento) {
  if (panelActivo === yo && !encima && !raiz.value?.contains(evento.relatedTarget)) panelActivo = null
}

function avisarCambio() {
  emit('cambio', adjuntos.value.length)
}

async function agregarArchivos(archivos) {
  for (const archivo of archivos) {
    const registro = reactive({
      id: ++contadorSubidas,
      nombre: archivo.name,
      estado: 'subiendo',
      mensaje: '',
    })
    subidas.value.push(registro)
    try {
      const creado = await subirAdjunto(props.contribuyenteId, {
        entidadTipo: props.entidadTipo,
        entidadId: props.entidadId,
        categoria: categoria.value,
        descripcion: descripcion.value,
        archivo,
      })
      adjuntos.value.unshift(creado)
      registro.estado = 'ok'
      avisarCambio()
      setTimeout(() => descartarSubida(registro.id), 3500)
    } catch (e) {
      registro.estado = 'error'
      registro.mensaje = mensajeDeError(e)
    }
  }
  descripcion.value = ''
}

function descartarSubida(id) {
  subidas.value = subidas.value.filter((s) => s.id !== id)
}

function alElegir(evento) {
  agregarArchivos([...evento.target.files])
  evento.target.value = ''
}

function alSoltar(evento) {
  arrastrando.value = false
  agregarArchivos([...(evento.dataTransfer?.files ?? [])])
}

function alPegar(evento) {
  if (panelActivo !== yo) return
  const archivos = [...(evento.clipboardData?.files ?? [])]
  if (!archivos.length) return
  evento.preventDefault()
  agregarArchivos(
    archivos.map((a) => (/^image\/(png|jpeg|webp|gif)$/.test(a.type) && (!a.name || /^image\.\w+$/.test(a.name))
      ? new File([a], nombreDeCaptura(a), { type: a.type })
      : a)),
  )
}

function abrirPrevia(adjunto) {
  const indice = previsualizables.value.findIndex((a) => a.id === adjunto.id)
  if (indice >= 0) indicePrevia.value = indice
  else descargarAdjunto(props.contribuyenteId, adjunto).catch((e) => (error.value = mensajeDeError(e)))
}

function abrirEdicion(adjunto) {
  Object.assign(edicion, {
    id: adjunto.id,
    categoria: adjunto.categoria,
    descripcion: adjunto.descripcion ?? '',
    guardando: false,
    error: '',
  })
}

async function guardarEdicion() {
  edicion.guardando = true
  edicion.error = ''
  try {
    const actualizado = await actualizarAdjunto(props.contribuyenteId, edicion.id, {
      categoria: edicion.categoria,
      descripcion: edicion.descripcion,
    })
    adjuntos.value = adjuntos.value.map((a) => (a.id === actualizado.id ? actualizado : a))
    edicion.id = null
  } catch (e) {
    edicion.error = mensajeDeError(e)
  } finally {
    edicion.guardando = false
  }
}

async function eliminar(adjunto) {
  error.value = ''
  confirmandoId.value = null
  try {
    await eliminarAdjunto(props.contribuyenteId, adjunto.id)
    adjuntos.value = adjuntos.value.filter((a) => a.id !== adjunto.id)
    if (edicion.id === adjunto.id) edicion.id = null
    avisarCambio()
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function bajar(adjunto) {
  try {
    await descargarAdjunto(props.contribuyenteId, adjunto)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

onMounted(() => {
  cargar()
  document.addEventListener('paste', alPegar)
})
onBeforeUnmount(() => {
  document.removeEventListener('paste', alPegar)
  if (panelActivo === yo) panelActivo = null
})
</script>

<template>
  <section
    ref="raiz"
    class="space-y-3"
    :aria-label="titulo || 'Soportes'"
    @mouseenter="alEntrarElRaton"
    @mouseleave="alSalirElRaton"
    @focusin="alEnfocar"
    @focusout="alDesenfocar"
  >
    <header v-if="titulo || ayuda">
      <h3 v-if="titulo">{{ titulo }}</h3>
      <p v-if="ayuda" class="text-sm text-tinta-suave">{{ ayuda }}</p>
    </header>

    <div
      class="rounded-md border-2 border-dashed px-4 py-4 text-center text-sm transition-colors"
      :class="arrastrando ? 'border-libro bg-libro-claro' : 'border-papel-linea bg-white/60'"
      @dragenter.prevent="arrastrando = true"
      @dragover.prevent="arrastrando = true"
      @dragleave.prevent="arrastrando = false"
      @drop.prevent="alSoltar"
    >
      <div class="flex flex-wrap items-end justify-center gap-3 text-left">
        <div>
          <label class="etiqueta" :for="idCategoria">Tipo de soporte</label>
          <select :id="idCategoria" v-model="categoria" class="campo w-48">
            <option v-for="(texto, valor) in ETIQUETAS_CATEGORIA_ADJUNTO" :key="valor" :value="valor">{{ texto }}</option>
          </select>
        </div>
        <div class="min-w-[12rem] flex-1">
          <label class="etiqueta" :for="idDescripcion">Nota (opcional)</label>
          <input :id="idDescripcion" v-model="descripcion" class="campo" maxlength="300" placeholder="Ej. Pago del predial, abril" />
        </div>
        <button type="button" class="boton" @click="selector.click()">Elegir archivos</button>
        <input ref="selector" type="file" multiple class="sr-only" tabindex="-1" accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.xlsx,.docx,.csv,.txt,image/*,application/pdf" @change="alElegir" />
      </div>
      <p class="mt-3 text-tinta-suave">
        o suéltalos aquí. También puedes <strong class="font-medium text-tinta">pegar una captura con Ctrl+V</strong>
        mientras el cursor esté sobre este recuadro. Se admiten PDF, imágenes, Excel, Word, CSV y TXT.
      </p>
    </div>

    <ul v-if="subidas.length" class="space-y-1 text-sm" aria-live="polite">
      <li
        v-for="s in subidas"
        :key="s.id"
        class="flex items-center justify-between gap-3 rounded px-3 py-2"
        :class="s.estado === 'error' ? 'bg-estado-nodeclarado-claro text-estado-nodeclarado' : s.estado === 'ok' ? 'bg-libro-claro' : 'bg-papel-hondo'"
      >
        <span class="min-w-0 truncate">
          <span class="font-medium">{{ s.nombre }}</span>
          <span v-if="s.estado === 'subiendo'"> · subiendo…</span>
          <span v-else-if="s.estado === 'ok'"> · adjuntado</span>
          <span v-else> · {{ s.mensaje }}</span>
        </span>
        <button v-if="s.estado === 'error'" type="button" class="shrink-0 underline" @click="descartarSubida(s.id)">Descartar</button>
      </li>
    </ul>

    <MensajeError :mensaje="error" />

    <p v-if="cargando" class="text-sm text-tinta-suave" role="status">Cargando soportes…</p>
    <p v-else-if="!adjuntos.length" class="text-sm text-tinta-suave">Todavía no hay soportes adjuntos.</p>

    <ul v-else class="divide-y divide-papel-hondo rounded-md border border-papel-linea bg-white">
      <li v-for="a in adjuntos" :key="a.id" class="px-3 py-2">
        <div class="flex flex-wrap items-center gap-3">
          <IconoArchivo :tipo-mime="a.tipo_mime" />
          <div class="min-w-0 flex-1">
            <button type="button" class="block max-w-full truncate text-left font-medium text-libro hover:underline" @click="abrirPrevia(a)">
              {{ a.nombre_original }}
            </button>
            <p class="truncate text-xs text-tinta-suave">
              {{ ETIQUETAS_CATEGORIA_ADJUNTO[a.categoria] }} · {{ tamano(a.tamano_bytes) }} · {{ fechaHora(a.creado_en) }}
              <span v-if="a.descripcion"> · {{ a.descripcion }}</span>
            </p>
          </div>
          <span
            v-if="confirmandoId !== a.id"
            class="flex gap-3 whitespace-nowrap text-sm"
          >
            <button v-if="a.previsualizable" type="button" class="text-tinta-suave underline hover:text-tinta" :aria-label="`Ver ${a.nombre_original}`" @click="abrirPrevia(a)">Ver</button>
            <button type="button" class="text-tinta-suave underline hover:text-tinta" :aria-label="`Descargar ${a.nombre_original}`" @click="bajar(a)">Descargar</button>
            <button type="button" class="text-tinta-suave underline hover:text-tinta" :aria-label="`Editar ${a.nombre_original}`" @click="abrirEdicion(a)">Editar</button>
            <button
              v-if="puedeEliminar"
              type="button"
              class="text-tinta-suave underline hover:text-estado-nodeclarado"
              :aria-label="`Eliminar ${a.nombre_original}`"
              @click="confirmandoId = a.id"
            >
              Eliminar
            </button>
          </span>
          <span v-else class="flex items-center gap-3 whitespace-nowrap text-sm" role="group" :aria-label="`Confirmar eliminación de ${a.nombre_original}`">
            <span class="font-medium">¿Eliminar?</span>
            <button type="button" class="font-semibold text-estado-nodeclarado underline" @click="eliminar(a)">Sí, eliminar</button>
            <button type="button" class="text-tinta-suave underline" @click="confirmandoId = null">No</button>
          </span>
        </div>

        <form v-if="edicion.id === a.id" class="mt-3 grid gap-3 sm:grid-cols-[12rem_1fr_auto]" @submit.prevent="guardarEdicion">
          <div>
            <label class="etiqueta" :for="`ed-cat-${a.id}`">Tipo de soporte</label>
            <select :id="`ed-cat-${a.id}`" v-model="edicion.categoria" class="campo">
              <option v-for="(texto, valor) in ETIQUETAS_CATEGORIA_ADJUNTO" :key="valor" :value="valor">{{ texto }}</option>
            </select>
          </div>
          <div>
            <label class="etiqueta" :for="`ed-desc-${a.id}`">Nota</label>
            <input :id="`ed-desc-${a.id}`" v-model="edicion.descripcion" class="campo" maxlength="300" />
          </div>
          <div class="flex items-end gap-2">
            <button type="submit" class="boton" :disabled="edicion.guardando">Guardar</button>
            <button type="button" class="boton-secundario" @click="edicion.id = null">Cancelar</button>
          </div>
          <MensajeError :mensaje="edicion.error" class="sm:col-span-3" />
        </form>
      </li>
    </ul>

    <VistaPreviaAdjunto
      v-if="indicePrevia !== null"
      :contribuyente-id="contribuyenteId"
      :adjuntos="previsualizables"
      :indice="indicePrevia"
      @cambiar="indicePrevia = $event"
      @cerrar="indicePrevia = null"
    />
  </section>
</template>

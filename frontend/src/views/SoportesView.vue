<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'

import { descargarAdjunto, descargarSoportesDelAnio, listarAdjuntos } from '../api/adjuntos'
import { mensajeDeError } from '../api/cliente'
import Cargando from '../components/Cargando.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import IconoArchivo from '../components/IconoArchivo.vue'
import MensajeError from '../components/MensajeError.vue'
import PanelAdjuntos from '../components/PanelAdjuntos.vue'
import VistaPreviaAdjunto from '../components/VistaPreviaAdjunto.vue'
import { useContribuyente } from '../contexto'
import { ETIQUETAS_CATEGORIA_ADJUNTO, ETIQUETAS_TIPO_ENTIDAD, fechaHora, tamano } from '../formato'

const { contribuyente, periodo, manejaInventario } = useContribuyente()
const cid = contribuyente.value.id

const filtros = reactive({ ambito: 'anio', tipo: '', categoria: '', texto: '' })
const adjuntos = ref([])
const cargando = ref(true)
const error = ref('')
const indicePrevia = ref(null)
const zip = reactive({ descargando: false, error: '' })
let temporizador = null
let solicitud = 0

const tiposDisponibles = computed(() =>
  Object.entries(ETIQUETAS_TIPO_ENTIDAD).filter(
    ([tipo]) => manejaInventario.value || !['DOCUMENTO_SOPORTE', 'MOVIMIENTO', 'PROVEEDOR'].includes(tipo),
  ),
)
const previsualizables = computed(() => adjuntos.value.filter((a) => a.previsualizable))
const hayFiltros = computed(() => filtros.tipo || filtros.categoria || filtros.texto.trim())

async function cargar() {
  const mia = ++solicitud
  try {
    const resultado = await listarAdjuntos(cid, {
      periodo_fiscal_id: filtros.ambito === 'anio' ? periodo.value.id : undefined,
      incluir_generales: filtros.ambito === 'anio' ? true : undefined,
      entidad_tipo: filtros.tipo || undefined,
      categoria: filtros.categoria || undefined,
      q: filtros.texto.trim() || undefined,
    })
    if (mia !== solicitud) return
    adjuntos.value = resultado
    error.value = ''
  } catch (e) {
    if (mia === solicitud) error.value = mensajeDeError(e)
  } finally {
    if (mia === solicitud) cargando.value = false
  }
}

function programarCarga() {
  clearTimeout(temporizador)
  temporizador = setTimeout(cargar, 250)
}

function abrirPrevia(adjunto) {
  const indice = previsualizables.value.findIndex((a) => a.id === adjunto.id)
  if (indice >= 0) indicePrevia.value = indice
  else bajar(adjunto)
}

async function bajar(adjunto) {
  try {
    await descargarAdjunto(cid, adjunto)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function bajarZip() {
  zip.error = ''
  zip.descargando = true
  try {
    await descargarSoportesDelAnio(cid, periodo.value.id, periodo.value.anio_gravable)
  } catch (e) {
    zip.error = mensajeDeError(e)
  } finally {
    zip.descargando = false
  }
}

function limpiarFiltros() {
  Object.assign(filtros, { tipo: '', categoria: '', texto: '' })
}

watch(() => [filtros.ambito, filtros.tipo, filtros.categoria], cargar)
watch(() => filtros.texto, programarCarga)
cargar()
onBeforeUnmount(() => clearTimeout(temporizador))
</script>

<template>
  <div class="space-y-10">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2>Soportes de {{ periodo.anio_gravable }}</h2>
        <p class="max-w-prose text-sm text-tinta-suave">
          Recibos, capturas y PDF de transferencias. Cada soporte se adjunta al objeto que respalda (un activo, un
          ingreso, un movimiento…) desde su propia fila; aquí están todos juntos.
        </p>
      </div>
      <button type="button" class="boton-secundario" :disabled="zip.descargando" @click="bajarZip">
        {{ zip.descargando ? 'Preparando ZIP…' : `Descargar soportes de ${periodo.anio_gravable} (ZIP)` }}
      </button>
    </header>
    <MensajeError :mensaje="zip.error" />

    <div class="grid gap-8 lg:grid-cols-2">
      <PanelAdjuntos
        :contribuyente-id="cid"
        entidad-tipo="CONTRIBUYENTE"
        :entidad-id="cid"
        titulo="Documentos del contribuyente"
        ayuda="RUT, cédula, poderes y todo lo que no depende de un año."
        categoria-inicial="CERTIFICADO"
        @cambio="cargar"
      />
      <PanelAdjuntos
        :contribuyente-id="cid"
        entidad-tipo="PERIODO_FISCAL"
        :entidad-id="periodo.id"
        :titulo="`Declaración y certificados de ${periodo.anio_gravable}`"
        ayuda="Declaración presentada, recibo de pago, certificados de ingresos y retenciones."
        categoria-inicial="DECLARACION"
        @cambio="cargar"
      />
    </div>

    <section class="space-y-3">
      <h2>Todos los soportes</h2>
      <div class="flex flex-wrap items-end gap-3">
        <div>
          <label class="etiqueta" for="s-ambito">Mostrar</label>
          <select id="s-ambito" v-model="filtros.ambito" class="campo w-52">
            <option value="anio">Solo {{ periodo.anio_gravable }} y generales</option>
            <option value="todos">De todos los años</option>
          </select>
        </div>
        <div>
          <label class="etiqueta" for="s-tipo">Objeto</label>
          <select id="s-tipo" v-model="filtros.tipo" class="campo w-48">
            <option value="">Todos</option>
            <option v-for="[tipo, texto] in tiposDisponibles" :key="tipo" :value="tipo">{{ texto }}</option>
          </select>
        </div>
        <div>
          <label class="etiqueta" for="s-cat">Tipo de soporte</label>
          <select id="s-cat" v-model="filtros.categoria" class="campo w-52">
            <option value="">Todos</option>
            <option v-for="(texto, valor) in ETIQUETAS_CATEGORIA_ADJUNTO" :key="valor" :value="valor">{{ texto }}</option>
          </select>
        </div>
        <div class="min-w-[14rem] flex-1">
          <label class="etiqueta" for="s-texto">Buscar</label>
          <input id="s-texto" v-model="filtros.texto" type="search" class="campo" placeholder="Nombre del archivo o nota" />
        </div>
        <button v-if="hayFiltros" type="button" class="boton-secundario" @click="limpiarFiltros">Quitar filtros</button>
      </div>

      <MensajeError :mensaje="error" />
      <Cargando v-if="cargando" />
      <EstadoVacio v-else-if="!adjuntos.length" :titulo="hayFiltros ? 'Ningún soporte coincide con los filtros' : 'Todavía no hay soportes'">
        <template v-if="hayFiltros">Prueba con otra búsqueda o quita los filtros.</template>
        <template v-else>
          Adjunta el primero arriba, o desde la fila de un activo, un ingreso o un movimiento.
        </template>
      </EstadoVacio>

      <div v-else class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Archivo</th>
              <th>Objeto</th>
              <th>Tipo de soporte</th>
              <th class="cifra">Tamaño</th>
              <th>Cargado</th>
              <th><span class="sr-only">Acciones</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in adjuntos" :key="a.id">
              <td>
                <div class="flex items-center gap-3">
                  <IconoArchivo :tipo-mime="a.tipo_mime" />
                  <div class="min-w-0">
                    <button type="button" class="block max-w-[22rem] truncate text-left font-medium text-libro hover:underline" @click="abrirPrevia(a)">
                      {{ a.nombre_original }}
                    </button>
                    <p v-if="a.descripcion" class="max-w-[22rem] truncate text-xs text-tinta-suave">{{ a.descripcion }}</p>
                  </div>
                </div>
              </td>
              <td>
                <span class="block text-xs uppercase tracking-wide text-tinta-tenue">{{ ETIQUETAS_TIPO_ENTIDAD[a.entidad_tipo] }}</span>
                <span class="block max-w-[18rem] truncate">{{ a.etiqueta_entidad }}</span>
              </td>
              <td>{{ ETIQUETAS_CATEGORIA_ADJUNTO[a.categoria] }}</td>
              <td class="cifra">{{ tamano(a.tamano_bytes) }}</td>
              <td class="whitespace-nowrap text-tinta-suave">{{ fechaHora(a.creado_en) }}</td>
              <td class="whitespace-nowrap text-right text-sm">
                <button v-if="a.previsualizable" type="button" class="mr-3 text-tinta-suave underline hover:text-tinta" :aria-label="`Ver ${a.nombre_original}`" @click="abrirPrevia(a)">Ver</button>
                <button type="button" class="text-tinta-suave underline hover:text-tinta" :aria-label="`Descargar ${a.nombre_original}`" @click="bajar(a)">Descargar</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="adjuntos.length" class="text-sm text-tinta-suave">{{ adjuntos.length }} soporte(s).</p>
    </section>

    <VistaPreviaAdjunto
      v-if="indicePrevia !== null"
      :contribuyente-id="cid"
      :adjuntos="previsualizables"
      :indice="indicePrevia"
      @cambiar="indicePrevia = $event"
      @cerrar="indicePrevia = null"
    />
  </div>
</template>

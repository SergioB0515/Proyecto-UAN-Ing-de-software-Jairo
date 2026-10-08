<script setup>
import { computed, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { mensajeDeError } from '../api/cliente'
import {
  actualizarContribuyente,
  crearPeriodo,
  eliminarContribuyente,
  listarPeriodos,
  obtenerContribuyente,
} from '../api/contribuyentes'
import Cargando from '../components/Cargando.vue'
import MensajeError from '../components/MensajeError.vue'
import { CLAVE_CONTEXTO } from '../contexto'
import { ETIQUETAS_TIPO_CONTRIBUYENTE } from '../formato'

const props = defineProps({ id: { type: Number, required: true } })
const route = useRoute()
const router = useRouter()

const contribuyente = ref(null)
const periodos = ref([])
const error = ref('')
const nuevoAnio = ref(new Date().getFullYear() - 1)
const errorPeriodo = ref('')
const creandoPeriodo = ref(false)

const manejaInventario = computed(() => contribuyente.value && contribuyente.value.tipo_contribuyente !== 'ASALARIADO')

// El periodo vive en la URL (?periodo=ID) para que cada pantalla se pueda
// enlazar y recargar; sin él, se toma el año más reciente.
const periodo = computed(() => {
  if (!periodos.value.length) return null
  const elegido = periodos.value.find((p) => p.id === Number(route.query.periodo))
  return elegido ?? periodos.value[periodos.value.length - 1]
})

async function cargar() {
  error.value = ''
  try {
    const [c, p] = await Promise.all([obtenerContribuyente(props.id), listarPeriodos(props.id)])
    contribuyente.value = c
    periodos.value = p
    if (p.length) nuevoAnio.value = p[p.length - 1].anio_gravable + 1
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function recargarPeriodos() {
  periodos.value = await listarPeriodos(props.id)
  if (periodos.value.length) nuevoAnio.value = periodos.value[periodos.value.length - 1].anio_gravable + 1
}

function elegirPeriodo(id) {
  router.replace({ query: { ...route.query, periodo: id } })
}

async function agregarPeriodo() {
  errorPeriodo.value = ''
  creandoPeriodo.value = true
  try {
    const creado = await crearPeriodo(props.id, Number(nuevoAnio.value))
    await recargarPeriodos()
    elegirPeriodo(creado.id)
  } catch (e) {
    errorPeriodo.value = mensajeDeError(e)
  } finally {
    creandoPeriodo.value = false
  }
}

// Corrección de datos del contribuyente y eliminación de un registro hecho por error.
const edicion = reactive({ abierta: false, datos: {}, error: '', guardando: false, confirmandoEliminar: false })

function abrirEdicion() {
  const { nombre, rut, tipo_contribuyente, regimen_tributario } = contribuyente.value
  Object.assign(edicion, {
    abierta: true,
    datos: { nombre, rut, tipo_contribuyente, regimen_tributario },
    error: '',
    confirmandoEliminar: false,
  })
}

async function guardarEdicion() {
  edicion.error = ''
  edicion.guardando = true
  try {
    contribuyente.value = await actualizarContribuyente(props.id, { ...edicion.datos })
    edicion.abierta = false
  } catch (e) {
    edicion.error = mensajeDeError(e)
  } finally {
    edicion.guardando = false
  }
}

async function eliminar() {
  edicion.error = ''
  try {
    await eliminarContribuyente(props.id)
    router.push({ name: 'contribuyentes' })
  } catch (e) {
    edicion.error = mensajeDeError(e)
    edicion.confirmandoEliminar = false
  }
}

watch(() => props.id, cargar, { immediate: true })

provide(CLAVE_CONTEXTO, { contribuyente, periodos, periodo, manejaInventario, recargarPeriodos })

const pestanas = computed(() => [
  { nombre: 'resumen', texto: 'Resumen' },
  { nombre: 'patrimonio', texto: 'Patrimonio e ingresos' },
  { nombre: 'exogena', texto: 'Exógena' },
  { nombre: 'conciliacion', texto: 'Conciliación' },
  { nombre: 'borrador', texto: 'Borrador por renglón' },
  ...(manejaInventario.value ? [{ nombre: 'inventario', texto: 'Inventario' }] : []),
  { nombre: 'cierre', texto: 'Cierre y reportes' },
])
</script>

<template>
  <div class="mx-auto max-w-6xl">
    <MensajeError :mensaje="error" />
    <Cargando v-if="!contribuyente && !error" />

    <template v-if="contribuyente">
      <header class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <RouterLink :to="{ name: 'contribuyentes' }" class="text-sm text-tinta-suave hover:text-tinta">
            Contribuyentes
          </RouterLink>
          <h1 class="mt-1">{{ contribuyente.nombre }}</h1>
          <p class="flex flex-wrap gap-x-4 text-sm text-tinta-suave">
            <span>NIT {{ contribuyente.rut }}</span>
            <span>{{ ETIQUETAS_TIPO_CONTRIBUYENTE[contribuyente.tipo_contribuyente] }}</span>
            <span>Régimen {{ contribuyente.regimen_tributario.toLowerCase() }}</span>
            <button v-if="!edicion.abierta" type="button" class="underline hover:text-tinta" @click="abrirEdicion">
              Editar datos
            </button>
            <RouterLink :to="{ name: 'actividad', query: { contribuyente: id } }" class="underline hover:text-tinta">
              Ver actividad
            </RouterLink>
          </p>
        </div>

        <div class="flex flex-wrap items-end gap-3">
          <div v-if="periodos.length">
            <label class="etiqueta" for="periodo">Año gravable</label>
            <select id="periodo" class="campo w-44" :value="periodo?.id" @change="elegirPeriodo(Number($event.target.value))">
              <option v-for="p in periodos" :key="p.id" :value="p.id">
                {{ p.anio_gravable }}{{ p.estado === 'CERRADO' ? ' (cerrado)' : '' }}
              </option>
            </select>
          </div>
          <form class="flex items-end gap-2" @submit.prevent="agregarPeriodo">
            <div>
              <label class="etiqueta" for="nuevo-anio">{{ periodos.length ? 'Otro año' : 'Primer año gravable' }}</label>
              <input id="nuevo-anio" v-model="nuevoAnio" type="number" min="2000" max="2100" class="campo w-28" required />
            </div>
            <button type="submit" class="boton-secundario" :disabled="creandoPeriodo">Abrir año</button>
          </form>
        </div>
      </header>
      <MensajeError :mensaje="errorPeriodo" class="mt-3" />

      <form v-if="edicion.abierta" class="hoja mt-4 space-y-4 p-5" @submit.prevent="guardarEdicion">
        <h2>Datos del contribuyente</h2>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div class="sm:col-span-2">
            <label class="etiqueta" for="e-nombre">Nombre o razón social</label>
            <input id="e-nombre" v-model="edicion.datos.nombre" class="campo" required maxlength="200" />
          </div>
          <div>
            <label class="etiqueta" for="e-rut">NIT o cédula (RUT)</label>
            <input id="e-rut" v-model="edicion.datos.rut" class="campo" required maxlength="20" />
          </div>
          <div>
            <label class="etiqueta" for="e-regimen">Régimen tributario</label>
            <input id="e-regimen" v-model="edicion.datos.regimen_tributario" class="campo" maxlength="60" />
          </div>
          <div>
            <label class="etiqueta" for="e-tipo">Tipo</label>
            <select id="e-tipo" v-model="edicion.datos.tipo_contribuyente" class="campo">
              <option v-for="(texto, tipo) in ETIQUETAS_TIPO_CONTRIBUYENTE" :key="tipo" :value="tipo">{{ texto }}</option>
            </select>
          </div>
        </div>
        <MensajeError :mensaje="edicion.error" />
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex gap-3">
            <button type="submit" class="boton" :disabled="edicion.guardando">Guardar cambios</button>
            <button type="button" class="boton-secundario" @click="edicion.abierta = false">Cancelar</button>
          </div>
          <div v-if="!edicion.confirmandoEliminar">
            <button type="button" class="boton-peligro" @click="edicion.confirmandoEliminar = true">Eliminar contribuyente</button>
          </div>
          <div v-else class="flex flex-wrap items-center gap-3 text-sm">
            <span>Solo se puede si no tiene años gravables ni inventario. ¿Eliminar?</span>
            <button type="button" class="boton-peligro" @click="eliminar">Sí, eliminar</button>
            <button type="button" class="boton-secundario" @click="edicion.confirmandoEliminar = false">No</button>
          </div>
        </div>
      </form>

      <nav class="mt-6 flex gap-1 overflow-x-auto border-b border-papel-linea" aria-label="Secciones del contribuyente">
        <RouterLink
          v-for="p in pestanas"
          :key="p.nombre"
          :to="{ name: p.nombre, params: { id }, query: route.query }"
          class="-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm"
          :class="route.name === p.nombre ? 'border-libro font-semibold text-tinta' : 'border-transparent text-tinta-suave hover:text-tinta'"
        >
          {{ p.texto }}
        </RouterLink>
      </nav>

      <div class="pt-6">
        <div v-if="!periodo" class="hoja max-w-xl p-6">
          <h2>Abre el año gravable que vas a declarar</h2>
          <p class="mt-1 text-sm text-tinta-suave">
            El patrimonio, los ingresos, la exógena y el inventario se registran por año. Usa
            «Abrir año» arriba; normalmente es el año anterior al actual.
          </p>
        </div>
        <RouterView v-else :key="`${id}-${periodo.id}`" />
      </div>
    </template>
  </div>
</template>

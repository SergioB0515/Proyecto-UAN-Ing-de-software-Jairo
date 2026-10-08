<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { mensajeDeError } from '../api/cliente'
import { crearContribuyente, listarContribuyentes } from '../api/contribuyentes'
import Cargando from '../components/Cargando.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import MensajeError from '../components/MensajeError.vue'
import { ETIQUETAS_TIPO_CONTRIBUYENTE, fecha } from '../formato'

const router = useRouter()
const contribuyentes = ref([])
const cargando = ref(true)
const error = ref('')
const mostrarFormulario = ref(false)
const errorFormulario = ref('')
const guardando = ref(false)
const filtro = ref('')

const nuevo = reactive({
  nombre: '',
  rut: '',
  tipo_contribuyente: 'ASALARIADO',
  regimen_tributario: 'Ordinario',
})

const DESCRIPCION_TIPO = {
  ASALARIADO: 'Solo patrimonio e ingresos.',
  INDEPENDIENTE: 'Maneja inventario de mercancía.',
  MIXTO: 'Asalariado que además tiene negocio con inventario.',
}

async function cargar() {
  try {
    contribuyentes.value = await listarContribuyentes()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    cargando.value = false
  }
}

async function guardar() {
  errorFormulario.value = ''
  guardando.value = true
  try {
    const creado = await crearContribuyente({ ...nuevo })
    router.push({ name: 'resumen', params: { id: creado.id } })
  } catch (e) {
    errorFormulario.value = mensajeDeError(e)
  } finally {
    guardando.value = false
  }
}

function coincide(c) {
  const texto = filtro.value.trim().toLowerCase()
  return !texto || c.nombre.toLowerCase().includes(texto) || c.rut.includes(texto)
}

onMounted(cargar)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1>Contribuyentes</h1>
        <p class="text-tinta-suave">Los clientes a los que les preparas la declaración.</p>
      </div>
      <button v-if="!mostrarFormulario" type="button" class="boton" @click="mostrarFormulario = true">
        Registrar contribuyente
      </button>
    </header>

    <form v-if="mostrarFormulario" class="hoja space-y-4 p-5" @submit.prevent="guardar">
      <h2>Nuevo contribuyente</h2>
      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label class="etiqueta" for="c-nombre">Nombre o razón social</label>
          <input id="c-nombre" v-model="nuevo.nombre" class="campo" required maxlength="200" />
        </div>
        <div>
          <label class="etiqueta" for="c-rut">NIT o cédula (RUT)</label>
          <input id="c-rut" v-model="nuevo.rut" class="campo" required maxlength="20" inputmode="numeric" />
        </div>
        <div>
          <label class="etiqueta" for="c-regimen">Régimen tributario</label>
          <input id="c-regimen" v-model="nuevo.regimen_tributario" class="campo" maxlength="60" />
        </div>
      </div>
      <fieldset>
        <legend class="etiqueta">Tipo de contribuyente</legend>
        <div class="grid gap-2 sm:grid-cols-3">
          <label
            v-for="(texto, tipo) in ETIQUETAS_TIPO_CONTRIBUYENTE"
            :key="tipo"
            class="flex cursor-pointer gap-3 rounded border p-3 text-sm"
            :class="nuevo.tipo_contribuyente === tipo ? 'border-libro bg-libro-claro' : 'border-papel-linea bg-white'"
          >
            <input v-model="nuevo.tipo_contribuyente" type="radio" :value="tipo" class="mt-1 accent-libro" />
            <span>
              <span class="block font-medium">{{ texto }}</span>
              <span class="text-tinta-suave">{{ DESCRIPCION_TIPO[tipo] }}</span>
            </span>
          </label>
        </div>
      </fieldset>
      <MensajeError :mensaje="errorFormulario" />
      <div class="flex gap-3">
        <button type="submit" class="boton" :disabled="guardando">Registrar contribuyente</button>
        <button type="button" class="boton-secundario" @click="mostrarFormulario = false">Cancelar</button>
      </div>
    </form>

    <MensajeError :mensaje="error" />
    <Cargando v-if="cargando" />

    <EstadoVacio v-else-if="!contribuyentes.length" titulo="Todavía no tienes contribuyentes registrados">
      Registra uno con su NIT y tipo para empezar a cargar su patrimonio, ingresos y exógena.
    </EstadoVacio>

    <template v-else>
      <div class="max-w-xs">
        <label class="sr-only" for="buscar">Buscar</label>
        <input id="buscar" v-model="filtro" class="campo" placeholder="Buscar por nombre o NIT" />
      </div>
      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>NIT</th>
              <th>Tipo</th>
              <th>Régimen</th>
              <th>Registrado</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in contribuyentes.filter(coincide)" :key="c.id">
              <td>
                <RouterLink :to="{ name: 'resumen', params: { id: c.id } }" class="enlace">{{ c.nombre }}</RouterLink>
              </td>
              <td class="cifra text-left">{{ c.rut }}</td>
              <td>{{ ETIQUETAS_TIPO_CONTRIBUYENTE[c.tipo_contribuyente] }}</td>
              <td>{{ c.regimen_tributario }}</td>
              <td class="text-tinta-suave">{{ fecha(c.creado_en) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

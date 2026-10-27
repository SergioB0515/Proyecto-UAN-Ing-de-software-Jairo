<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { cargarCalendarioOficial, listarPlazos, reemplazarPlazos } from '../api/parametros'
import { fecha } from '../formato'
import MensajeError from './MensajeError.vue'

const anio = ref(new Date().getFullYear() - 1)
const anioMostrado = ref(null)
const plazos = ref([])
const error = ref('')
const aviso = ref('')
const editor = reactive({ abierto: false, texto: '', error: '' })

const dd = (n) => String(n % 100).padStart(2, '0')
const rango = (p) => (p.digitos_desde === p.digitos_hasta ? dd(p.digitos_desde) : `${dd(p.digitos_desde)}–${dd(p.digitos_hasta)}`)
const columnas = computed(() => {
  const mitad = Math.ceil(plazos.value.length / 2)
  return [plazos.value.slice(0, mitad), plazos.value.slice(mitad)]
})

async function ver() {
  error.value = ''
  aviso.value = ''
  editor.abierto = false
  try {
    plazos.value = await listarPlazos(anio.value)
    anioMostrado.value = anio.value
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function cargarOficial() {
  error.value = ''
  try {
    plazos.value = await cargarCalendarioOficial(anioMostrado.value)
    aviso.value = `Calendario oficial de ${anioMostrado.value} cargado. Confírmalo en dian.gov.co si la DIAN publica cambios.`
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

function abrirEditor() {
  editor.texto = plazos.value.map((p) => `${dd(p.digitos_desde)}-${dd(p.digitos_hasta)} ${p.fecha}`).join('\n')
  editor.error = ''
  editor.abierto = true
}

function interpretar(texto) {
  const plazosLeidos = []
  texto.split('\n').forEach((linea, i) => {
    if (!linea.trim()) return
    const m = /^\s*(\d{1,2})\s*[-–]\s*(\d{1,2})[\s;,\t]+(\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{4})\s*$/.exec(linea)
    if (!m) throw new Error(`Línea ${i + 1}: usa el formato «01-02 2027-08-12».`)
    const aNumero = (s) => (Number(s) === 0 ? 100 : Number(s))
    let iso = m[3]
    if (iso.includes('/')) {
      const [d, mes, a] = iso.split('/')
      iso = `${a}-${mes.padStart(2, '0')}-${d.padStart(2, '0')}`
    }
    plazosLeidos.push({ digitos_desde: aNumero(m[1]), digitos_hasta: aNumero(m[2]), fecha: iso })
  })
  return plazosLeidos
}

async function guardarEditor() {
  editor.error = ''
  try {
    plazos.value = await reemplazarPlazos(anioMostrado.value, interpretar(editor.texto))
    editor.abierto = false
    aviso.value = `Calendario de ${anioMostrado.value} guardado.`
  } catch (e) {
    editor.error = e.response ? mensajeDeError(e) : e.message
  }
}

onMounted(ver)
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2>Calendario de vencimientos</h2>
        <p class="max-w-prose text-sm text-tinta-suave">
          Fecha límite para declarar renta según los dos últimos dígitos del NIT, sin el dígito de verificación.
          Con él, la cartera muestra qué declaraciones vencen pronto.
        </p>
      </div>
      <form class="flex items-end gap-2" @submit.prevent="ver">
        <div>
          <label class="etiqueta" for="cal-anio">Año gravable</label>
          <input id="cal-anio" v-model.number="anio" type="number" min="2000" max="2100" class="campo w-28" required />
        </div>
        <button type="submit" class="boton-secundario">Ver</button>
      </form>
    </div>

    <MensajeError :mensaje="error" />
    <p v-if="aviso" class="rounded bg-libro-claro px-4 py-3 text-sm" role="status">{{ aviso }}</p>

    <div v-if="anioMostrado && !plazos.length && !editor.abierto" class="hoja space-y-3 p-5">
      <p class="font-medium">No hay calendario registrado para el año gravable {{ anioMostrado }}.</p>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="boton" @click="cargarOficial">Cargar el calendario oficial de {{ anioMostrado }}</button>
        <button type="button" class="boton-secundario" @click="abrirEditor">Registrarlo a mano</button>
      </div>
    </div>

    <form v-if="editor.abierto" class="hoja space-y-3 p-5" @submit.prevent="guardarEditor">
      <label class="etiqueta" for="cal-texto">
        Calendario {{ anioMostrado }}: una línea por rango, con los dígitos y la fecha
      </label>
      <textarea
        id="cal-texto"
        v-model="editor.texto"
        rows="12"
        class="campo font-[ui-monospace,monospace]"
        placeholder="01-02 2027-08-12&#10;03-04 2027-08-13&#10;…&#10;99-00 2027-10-26"
      ></textarea>
      <MensajeError :mensaje="editor.error" />
      <div class="flex gap-2">
        <button type="submit" class="boton">Guardar calendario</button>
        <button type="button" class="boton-secundario" @click="editor.abierto = false">Cancelar</button>
      </div>
    </form>

    <template v-if="plazos.length && !editor.abierto">
      <div class="hoja grid gap-x-8 p-2 sm:grid-cols-2">
        <table v-for="(columna, i) in columnas" :key="i">
          <thead>
            <tr><th>Últimos dígitos</th><th>Fecha límite</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in columna" :key="p.digitos_desde">
              <td class="cifra text-left">{{ rango(p) }}</td>
              <td>{{ fecha(p.fecha) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="boton-secundario" @click="abrirEditor">Corregir fechas</button>
        <button type="button" class="boton-secundario" @click="cargarOficial">Volver a cargar el oficial</button>
      </div>
    </template>
  </section>
</template>

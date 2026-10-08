<script setup>
import { onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { guardarUmbral, listarUmbrales } from '../api/parametros'
import MensajeError from '../components/MensajeError.vue'
import { cantidad, dinero } from '../formato'

const umbrales = ref([])
const error = ref('')
const errorFormulario = ref('')
const guardado = ref('')

const CAMPOS = [
  { clave: 'tope_ingresos_uvt', texto: 'Ingresos brutos' },
  { clave: 'tope_patrimonio_uvt', texto: 'Patrimonio bruto' },
  { clave: 'tope_consumo_tc_uvt', texto: 'Consumos con tarjeta' },
  { clave: 'tope_compras_uvt', texto: 'Compras y consumos' },
  { clave: 'tope_movimiento_uvt', texto: 'Consignaciones e inversiones' },
]

const form = reactive({
  anio_gravable: new Date().getFullYear() - 1,
  valor_uvt: null,
  tope_ingresos_uvt: null,
  tope_patrimonio_uvt: null,
  tope_consumo_tc_uvt: null,
  tope_compras_uvt: null,
  tope_movimiento_uvt: null,
})

async function cargar() {
  try {
    umbrales.value = await listarUmbrales()
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

function editar(u) {
  Object.assign(form, u)
  guardado.value = ''
}

async function guardar() {
  errorFormulario.value = ''
  guardado.value = ''
  try {
    const u = await guardarUmbral({ ...form })
    guardado.value = `Umbral de ${u.anio_gravable} guardado.`
    await cargar()
  } catch (e) {
    errorFormulario.value = mensajeDeError(e)
  }
}

onMounted(cargar)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <header>
      <h1>Umbrales de declaración</h1>
      <p class="max-w-prose text-tinta-suave">
        El valor de la UVT y los topes (en UVT) que obligan a una persona natural a declarar renta en cada año
        gravable. Se comparan contra los topes de la exógena. Son comunes a toda la aplicación.
      </p>
    </header>

    <MensajeError :mensaje="error" />

    <div class="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Año</th>
              <th class="cifra">UVT</th>
              <th v-for="c in CAMPOS" :key="c.clave" class="cifra">{{ c.texto }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!umbrales.length">
              <td :colspan="CAMPOS.length + 3" class="py-6 text-center text-tinta-suave">
                Sin umbrales. Sin ellos no se puede saber quién está obligado a declarar.
              </td>
            </tr>
            <tr v-for="u in umbrales" :key="u.anio_gravable">
              <td class="font-semibold">{{ u.anio_gravable }}</td>
              <td class="cifra">{{ dinero(u.valor_uvt) }}</td>
              <td v-for="c in CAMPOS" :key="c.clave" class="cifra">
                {{ cantidad(u[c.clave]) }}
                <p class="text-xs text-tinta-tenue">{{ dinero(u[c.clave] * u.valor_uvt) }}</p>
              </td>
              <td><button type="button" class="enlace text-sm" @click="editar(u)">Editar</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      <form class="hoja h-fit space-y-3 p-5" @submit.prevent="guardar">
        <h2>Registrar o corregir un año</h2>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="etiqueta" for="u-anio">Año gravable</label>
            <input id="u-anio" v-model.number="form.anio_gravable" type="number" min="2000" max="2100" class="campo" required />
          </div>
          <div>
            <label class="etiqueta" for="u-uvt">Valor UVT ($)</label>
            <input id="u-uvt" v-model.number="form.valor_uvt" type="number" min="1" step="any" class="campo" required />
          </div>
          <div v-for="c in CAMPOS" :key="c.clave">
            <label class="etiqueta" :for="`u-${c.clave}`">{{ c.texto }} (UVT)</label>
            <input :id="`u-${c.clave}`" v-model.number="form[c.clave]" type="number" min="1" step="any" class="campo" required />
          </div>
        </div>
        <p class="text-xs text-tinta-tenue">Si el año ya existe, se reemplaza.</p>
        <MensajeError :mensaje="errorFormulario" />
        <p v-if="guardado" class="text-sm text-libro" role="status">{{ guardado }}</p>
        <button type="submit" class="boton">Guardar umbral</button>
      </form>
    </div>
  </div>
</template>

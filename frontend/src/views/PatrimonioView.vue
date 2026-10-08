<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import {
  actualizarActivo,
  copiarActivosAnioAnterior,
  actualizarFuenteIngreso,
  crearActivo,
  crearFuenteIngreso,
  eliminarActivo,
  eliminarFuenteIngreso,
  listarActivos,
  listarFuentesIngreso,
} from '../api/contribuyentes'
import AccionesFila from '../components/AccionesFila.vue'
import CamposVinculoDian from '../components/CamposVinculoDian.vue'
import Cargando from '../components/Cargando.vue'
import MensajeError from '../components/MensajeError.vue'
import { useContribuyente } from '../contexto'
import { ETIQUETAS_TIPO_ACTIVO, dinero } from '../formato'

const { contribuyente, periodo, periodos } = useContribuyente()
const cid = contribuyente.value.id
const pid = periodo.value.id
const cerrado = computed(() => periodo.value.estado === 'CERRADO')

const activos = ref([])
const fuentes = ref([])
const cargando = ref(true)
const error = ref('')
const errorLista = ref('')

const totalActivos = computed(() => activos.value.reduce((s, a) => s + a.valor, 0))
const totalIngresos = computed(() => fuentes.value.reduce((s, f) => s + f.valor_anual, 0))
const totalRetenciones = computed(() => fuentes.value.reduce((s, f) => s + f.retencion_fuente, 0))

const TIPOS_REGISTRABLES = ['CUENTA', 'VEHICULO', 'INMUEBLE', 'INVERSION']

function activoVacio() {
  return { descripcion: '', tipo: 'CUENTA', valor: null, vinculo_codigo_concepto: '', vinculo_palabra_clave: '' }
}
function fuenteVacia() {
  return { concepto: '', valor_anual: null, retencion_fuente: 0, vinculo_codigo_concepto: '', vinculo_palabra_clave: '' }
}

// Un mismo formulario sirve para crear y para editar: `editandoId` dice cuál.
const formActivo = reactive({ abierto: false, editandoId: null, datos: activoVacio(), error: '', guardando: false })
const formFuente = reactive({ abierto: false, editandoId: null, datos: fuenteVacia(), error: '', guardando: false })

const OPERACIONES = {
  activo: { form: formActivo, lista: activos, vacio: activoVacio, crear: crearActivo, actualizar: actualizarActivo, eliminar: eliminarActivo },
  fuente: { form: formFuente, lista: fuentes, vacio: fuenteVacia, crear: crearFuenteIngreso, actualizar: actualizarFuenteIngreso, eliminar: eliminarFuenteIngreso },
}

// Los vínculos vacíos se mandan como null, no como cadena vacía.
function limpiar(datos) {
  return {
    ...datos,
    vinculo_codigo_concepto: datos.vinculo_codigo_concepto?.trim() || null,
    vinculo_palabra_clave: datos.vinculo_palabra_clave?.trim() || null,
  }
}

function abrirNuevo(clase) {
  const { form, vacio } = OPERACIONES[clase]
  Object.assign(form, { abierto: true, editandoId: null, datos: vacio(), error: '' })
}

function abrirEdicion(clase, item) {
  const { form, vacio } = OPERACIONES[clase]
  const datos = vacio()
  for (const campo of Object.keys(datos)) datos[campo] = item[campo] ?? ''
  Object.assign(form, { abierto: true, editandoId: item.id, datos, error: '' })
}

function cerrarFormulario(clase) {
  Object.assign(OPERACIONES[clase].form, { abierto: false, editandoId: null, error: '' })
}

async function guardar(clase) {
  const { form, lista, crear, actualizar } = OPERACIONES[clase]
  form.error = ''
  form.guardando = true
  try {
    if (form.editandoId) {
      const actualizado = await actualizar(cid, form.editandoId, limpiar(form.datos))
      lista.value = lista.value.map((x) => (x.id === actualizado.id ? actualizado : x))
    } else {
      lista.value.push(await crear(cid, { ...limpiar(form.datos), periodo_fiscal_id: pid }))
    }
    cerrarFormulario(clase)
  } catch (e) {
    form.error = mensajeDeError(e)
  } finally {
    form.guardando = false
  }
}

async function eliminar(clase, item) {
  const { lista, eliminar: borrar, form } = OPERACIONES[clase]
  errorLista.value = ''
  try {
    await borrar(cid, item.id)
    lista.value = lista.value.filter((x) => x.id !== item.id)
    if (form.editandoId === item.id) cerrarFormulario(clase)
  } catch (e) {
    errorLista.value = mensajeDeError(e)
  }
}

// Copiar activos del año anterior: solo si existe uno y este año está abierto.
const anioAnterior = computed(() =>
  periodos.value
    .map((p) => p.anio_gravable)
    .filter((a) => a < periodo.value.anio_gravable)
    .reduce((max, a) => Math.max(max, a), 0) || null,
)
const copia = reactive({ copiando: false, mensaje: '', error: '' })

async function copiarAnioAnterior() {
  Object.assign(copia, { copiando: true, mensaje: '', error: '' })
  try {
    const creados = await copiarActivosAnioAnterior(cid, pid)
    activos.value.push(...creados)
    copia.mensaje = creados.length
      ? `Se copiaron ${creados.length} activo(s) de ${anioAnterior.value}. Actualiza sus valores al 31 de diciembre de ${periodo.value.anio_gravable}.`
      : `Los activos de ${anioAnterior.value} ya estaban en este año; no se copió nada.`
  } catch (e) {
    copia.error = mensajeDeError(e)
  } finally {
    copia.copiando = false
  }
}

function vinculo(item) {
  if (item.vinculo_codigo_concepto) return `Concepto ${item.vinculo_codigo_concepto}`
  if (item.vinculo_palabra_clave) return `«${item.vinculo_palabra_clave}»`
  return '—'
}

onMounted(async () => {
  try {
    ;[activos.value, fuentes.value] = await Promise.all([listarActivos(cid, pid), listarFuentesIngreso(cid, pid)])
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    cargando.value = false
  }
})
</script>

<template>
  <MensajeError :mensaje="error" />
  <Cargando v-if="cargando" />

  <div v-else class="space-y-10">
    <p v-if="cerrado" class="rounded bg-papel-hondo px-4 py-3 text-sm">
      El año {{ periodo.anio_gravable }} está cerrado: puedes consultarlo, pero para registrar o corregir
      datos hay que reabrirlo en «Cierre y reportes».
    </p>
    <MensajeError :mensaje="errorLista" />

    <section class="space-y-3">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2>Activos al 31 de diciembre de {{ periodo.anio_gravable }}</h2>
          <p class="text-sm text-tinta-suave">Suman el patrimonio líquido del año.</p>
        </div>
        <div v-if="!formActivo.abierto && !cerrado" class="flex flex-wrap gap-2">
          <button
            v-if="anioAnterior"
            type="button"
            class="boton-secundario"
            :disabled="copia.copiando"
            @click="copiarAnioAnterior"
          >
            Copiar activos de {{ anioAnterior }}
          </button>
          <button type="button" class="boton" @click="abrirNuevo('activo')">Agregar activo</button>
        </div>
      </div>
      <p v-if="copia.mensaje" class="rounded bg-libro-claro px-4 py-3 text-sm" role="status">{{ copia.mensaje }}</p>
      <MensajeError :mensaje="copia.error" />

      <form v-if="formActivo.abierto" class="hoja space-y-4 p-5" @submit.prevent="guardar('activo')">
        <h3>{{ formActivo.editandoId ? 'Corregir activo' : 'Nuevo activo' }}</h3>
        <div class="grid gap-4 sm:grid-cols-3">
          <div class="sm:col-span-3">
            <label class="etiqueta" for="a-desc">Descripción</label>
            <input id="a-desc" v-model="formActivo.datos.descripcion" class="campo" required maxlength="200" placeholder="Ej. Apartamento en Chapinero" />
          </div>
          <div>
            <label class="etiqueta" for="a-tipo">Tipo</label>
            <select id="a-tipo" v-model="formActivo.datos.tipo" class="campo">
              <option v-for="t in TIPOS_REGISTRABLES" :key="t" :value="t">{{ ETIQUETAS_TIPO_ACTIVO[t] }}</option>
            </select>
          </div>
          <div>
            <label class="etiqueta" for="a-valor">Valor (COP)</label>
            <input id="a-valor" v-model.number="formActivo.datos.valor" type="number" min="1" step="any" class="campo" required />
          </div>
        </div>
        <CamposVinculoDian
          v-model:codigo="formActivo.datos.vinculo_codigo_concepto"
          v-model:palabra="formActivo.datos.vinculo_palabra_clave"
          prefijo="a"
        />
        <MensajeError :mensaje="formActivo.error" />
        <div class="flex gap-3">
          <button type="submit" class="boton" :disabled="formActivo.guardando">
            {{ formActivo.editandoId ? 'Guardar cambios' : 'Guardar activo' }}
          </button>
          <button type="button" class="boton-secundario" @click="cerrarFormulario('activo')">Cancelar</button>
        </div>
      </form>

      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Descripción</th>
              <th>Tipo</th>
              <th>Cruce con exógena</th>
              <th class="cifra">Valor</th>
              <th v-if="!cerrado"><span class="sr-only">Acciones</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!activos.length">
              <td :colspan="cerrado ? 4 : 5" class="py-6 text-center text-tinta-suave">Sin activos registrados en {{ periodo.anio_gravable }}.</td>
            </tr>
            <tr v-for="a in activos" :key="a.id" :class="formActivo.editandoId === a.id ? 'bg-libro-claro/60' : ''">
              <td>{{ a.descripcion }}</td>
              <td>{{ ETIQUETAS_TIPO_ACTIVO[a.tipo] }}</td>
              <td class="text-tinta-suave">{{ vinculo(a) }}</td>
              <td class="cifra">{{ dinero(a.valor) }}</td>
              <td v-if="!cerrado" class="text-right">
                <AccionesFila
                  v-if="a.tipo !== 'INVENTARIO'"
                  :etiqueta="a.descripcion"
                  @editar="abrirEdicion('activo', a)"
                  @eliminar="eliminar('activo', a)"
                />
              </td>
            </tr>
          </tbody>
          <tfoot v-if="activos.length">
            <tr>
              <td colspan="3" class="border-0 font-semibold">Patrimonio líquido</td>
              <td class="cifra border-0 font-semibold">{{ dinero(totalActivos) }}</td>
              <td v-if="!cerrado" class="border-0"></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <section class="space-y-3">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2>Ingresos de {{ periodo.anio_gravable }}</h2>
          <p class="text-sm text-tinta-suave">Salario, honorarios, ventas, arriendos… con su retención en la fuente.</p>
        </div>
        <button v-if="!formFuente.abierto && !cerrado" type="button" class="boton" @click="abrirNuevo('fuente')">
          Agregar ingreso
        </button>
      </div>

      <form v-if="formFuente.abierto" class="hoja space-y-4 p-5" @submit.prevent="guardar('fuente')">
        <h3>{{ formFuente.editandoId ? 'Corregir ingreso' : 'Nuevo ingreso' }}</h3>
        <div class="grid gap-4 sm:grid-cols-3">
          <div class="sm:col-span-3">
            <label class="etiqueta" for="f-concepto">Concepto</label>
            <input id="f-concepto" v-model="formFuente.datos.concepto" class="campo" required maxlength="200" placeholder="Ej. Salario Empresa XYZ" />
          </div>
          <div>
            <label class="etiqueta" for="f-valor">Valor anual (COP)</label>
            <input id="f-valor" v-model.number="formFuente.datos.valor_anual" type="number" min="1" step="any" class="campo" required />
          </div>
          <div>
            <label class="etiqueta" for="f-ret">Retención en la fuente</label>
            <input id="f-ret" v-model.number="formFuente.datos.retencion_fuente" type="number" min="0" step="any" class="campo" />
          </div>
        </div>
        <CamposVinculoDian
          v-model:codigo="formFuente.datos.vinculo_codigo_concepto"
          v-model:palabra="formFuente.datos.vinculo_palabra_clave"
          prefijo="f"
        />
        <MensajeError :mensaje="formFuente.error" />
        <div class="flex gap-3">
          <button type="submit" class="boton" :disabled="formFuente.guardando">
            {{ formFuente.editandoId ? 'Guardar cambios' : 'Guardar ingreso' }}
          </button>
          <button type="button" class="boton-secundario" @click="cerrarFormulario('fuente')">Cancelar</button>
        </div>
      </form>

      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Concepto</th>
              <th>Cruce con exógena</th>
              <th class="cifra">Retención</th>
              <th class="cifra">Valor anual</th>
              <th v-if="!cerrado"><span class="sr-only">Acciones</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!fuentes.length">
              <td :colspan="cerrado ? 4 : 5" class="py-6 text-center text-tinta-suave">Sin ingresos registrados en {{ periodo.anio_gravable }}.</td>
            </tr>
            <tr v-for="f in fuentes" :key="f.id" :class="formFuente.editandoId === f.id ? 'bg-libro-claro/60' : ''">
              <td>{{ f.concepto }}</td>
              <td class="text-tinta-suave">{{ vinculo(f) }}</td>
              <td class="cifra">{{ dinero(f.retencion_fuente) }}</td>
              <td class="cifra">{{ dinero(f.valor_anual) }}</td>
              <td v-if="!cerrado" class="text-right">
                <AccionesFila :etiqueta="f.concepto" @editar="abrirEdicion('fuente', f)" @eliminar="eliminar('fuente', f)" />
              </td>
            </tr>
          </tbody>
          <tfoot v-if="fuentes.length">
            <tr>
              <td colspan="2" class="border-0 font-semibold">Total</td>
              <td class="cifra border-0 font-semibold">{{ dinero(totalRetenciones) }}</td>
              <td class="cifra border-0 font-semibold">{{ dinero(totalIngresos) }}</td>
              <td v-if="!cerrado" class="border-0"></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  </div>
</template>

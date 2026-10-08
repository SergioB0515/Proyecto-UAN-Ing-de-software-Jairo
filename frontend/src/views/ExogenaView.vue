<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { importarExogena, listarRegistros, listarReportesExogena, listarTopes } from '../api/exogena'
import { verificarObligacion } from '../api/parametros'
import Cargando from '../components/Cargando.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import MensajeError from '../components/MensajeError.vue'
import TablaObligacion from '../components/TablaObligacion.vue'
import { useContribuyente } from '../contexto'
import { dinero, fecha } from '../formato'

const { contribuyente, periodo } = useContribuyente()
const cid = contribuyente.value.id
const pid = periodo.value.id
const cerrado = computed(() => periodo.value.estado === 'CERRADO')

const reportes = ref([])
const reporte = computed(() => reportes.value[0] ?? null) // el más reciente
const topes = ref([])
const registros = ref([])
const obligacion = ref(null)
const errorObligacion = ref('')
const filtros = reactive({ concepto_code: '', nit_reportante: '' })
const cargando = ref(true)
const error = ref('')

const archivo = ref(null)
const campoArchivo = ref(null)
const importando = ref(false)
const resultadoImportacion = ref(null)
const errorImportacion = ref('')

async function cargarReporte() {
  if (!reporte.value) return
  const [t, r] = await Promise.all([listarTopes(cid, reporte.value.id), listarRegistros(cid, reporte.value.id)])
  topes.value = t
  registros.value = r
  errorObligacion.value = ''
  obligacion.value = null
  try {
    obligacion.value = await verificarObligacion(cid, pid)
  } catch (e) {
    errorObligacion.value = mensajeDeError(e)
  }
}

async function cargar() {
  error.value = ''
  try {
    const todos = await listarReportesExogena(cid)
    reportes.value = todos.filter((r) => r.periodo_fiscal_id === pid)
    await cargarReporte()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    cargando.value = false
  }
}

async function filtrar() {
  registros.value = await listarRegistros(cid, reporte.value.id, {
    concepto_code: filtros.concepto_code.trim() || undefined,
    nit_reportante: filtros.nit_reportante.trim() || undefined,
  })
}

async function importar() {
  if (!archivo.value) return
  errorImportacion.value = ''
  resultadoImportacion.value = null
  importando.value = true
  try {
    resultadoImportacion.value = await importarExogena(cid, pid, archivo.value)
    archivo.value = null
    if (campoArchivo.value) campoArchivo.value.value = ''
    await cargar()
  } catch (e) {
    errorImportacion.value = mensajeDeError(e)
  } finally {
    importando.value = false
  }
}

function reportanteTexto(r) {
  let texto = `NIT ${r.nit_reportante}`
  if (r.es_auto_reportado) texto += ', reportado por el mismo contribuyente'
  if (r.es_dian) texto += ', DIAN'
  return texto
}

function elegirArchivo(evento) {
  archivo.value = evento.target.files?.[0] ?? null
}

onMounted(cargar)
</script>

<template>
  <MensajeError :mensaje="error" />
  <Cargando v-if="cargando" />

  <div v-else class="space-y-8">
    <section v-if="!cerrado" class="hoja p-5">
      <h2>{{ reporte ? 'Importar una versión más reciente' : `Importar la exógena de ${periodo.anio_gravable}` }}</h2>
      <p class="mt-1 max-w-prose text-sm text-tinta-suave">
        El archivo Excel que se descarga en el portal de la DIAN («Información exógena» del contribuyente).
        Si importas otro, la conciliación usa siempre el más reciente.
      </p>
      <form class="mt-4 flex flex-wrap items-center gap-3" @submit.prevent="importar">
        <label class="sr-only" for="archivo">Archivo de exógena</label>
        <input
          id="archivo"
          ref="campoArchivo"
          type="file"
          accept=".xlsx,.xls"
          class="text-sm file:mr-3 file:rounded file:border file:border-papel-linea file:bg-white file:px-3 file:py-2 file:text-sm file:font-medium"
          @change="elegirArchivo"
        />
        <button type="submit" class="boton" :disabled="!archivo || importando">
          {{ importando ? 'Importando…' : 'Importar archivo' }}
        </button>
      </form>
      <MensajeError :mensaje="errorImportacion" class="mt-3" />
      <div v-if="resultadoImportacion" class="mt-4 rounded bg-libro-claro px-4 py-3 text-sm" role="status">
        <p class="font-medium">
          Importado: {{ resultadoImportacion.cantidad_registros }} registros y {{ resultadoImportacion.cantidad_topes }} topes
          <template v-if="resultadoImportacion.consultante?.nombre">
            de {{ resultadoImportacion.consultante.nombre }}
          </template>.
        </p>
        <template v-if="resultadoImportacion.errores.length">
          <p class="mt-2">Estas filas no se pudieron leer y no se importaron:</p>
          <ul class="mt-1 list-inside list-disc">
            <li v-for="e in resultadoImportacion.errores" :key="e.fila">Fila {{ e.fila }}: {{ e.motivo }}</li>
          </ul>
        </template>
      </div>
    </section>

    <EstadoVacio v-if="!reporte" :titulo="`Aún no hay exógena importada para ${periodo.anio_gravable}`">
      <template v-if="cerrado">El año está cerrado; reábrelo para importar.</template>
      <template v-else>Con el archivo importado se calculan la obligación de declarar, la conciliación y el borrador.</template>
    </EstadoVacio>

    <template v-else>
      <p class="text-sm text-tinta-suave">
        Archivo en uso: <span class="font-medium text-tinta">{{ reporte.nombre_archivo_original }}</span>,
        importado el {{ fecha(reporte.fecha_importacion) }}.
        <template v-if="reportes.length > 1">Hay {{ reportes.length - 1 }} versión(es) anterior(es).</template>
      </p>

      <div class="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <section class="hoja p-5">
          <h2>Topes reportados</h2>
          <p class="text-sm text-tinta-suave">Valores que la DIAN calcula para comparar con los umbrales de declaración.</p>
          <table class="mt-3">
            <tbody>
              <tr v-for="t in topes" :key="t.id">
                <td class="px-0">{{ t.etiqueta }}</td>
                <td class="cifra px-0">{{ dinero(t.valor) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="hoja p-5">
          <h2 class="mb-2">¿Debe declarar?</h2>
          <TablaObligacion v-if="obligacion" :obligacion="obligacion" />
          <div v-else class="text-sm">
            <p class="text-tinta-suave">{{ errorObligacion }}</p>
            <RouterLink :to="{ name: 'umbrales' }" class="enlace mt-2 inline-block">
              Configurar los umbrales de {{ periodo.anio_gravable }}
            </RouterLink>
          </div>
        </section>
      </div>

      <section class="space-y-3">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <h2>Lo que reportaron terceros ({{ registros.length }})</h2>
          <form class="flex flex-wrap items-end gap-2" @submit.prevent="filtrar">
            <div>
              <label class="etiqueta" for="f-concepto">Concepto</label>
              <input id="f-concepto" v-model="filtros.concepto_code" class="campo w-28" placeholder="1476" />
            </div>
            <div>
              <label class="etiqueta" for="f-nit">NIT reportante</label>
              <input id="f-nit" v-model="filtros.nit_reportante" class="campo w-40" />
            </div>
            <button type="submit" class="boton-secundario">Filtrar</button>
          </form>
        </div>
        <div class="hoja overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Reportante</th>
                <th>Detalle</th>
                <th>Concepto</th>
                <th>Renglón sugerido</th>
                <th class="cifra">Valor</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!registros.length">
                <td colspan="5" class="py-6 text-center text-tinta-suave">Ningún registro con esos filtros.</td>
              </tr>
              <tr v-for="r in registros" :key="r.id">
                <td>
                  {{ r.nombre_reportante }}
                  <p class="text-xs text-tinta-tenue">{{ reportanteTexto(r) }}</p>
                </td>
                <td class="max-w-sm">{{ r.detalle }}</td>
                <td>{{ r.concepto_code ?? '—' }}</td>
                <td>{{ r.renglones_sugeridos ?? '—' }}</td>
                <td class="cifra">{{ dinero(r.valor) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

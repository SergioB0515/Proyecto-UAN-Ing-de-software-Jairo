<script setup>
/**
 * «Lo que falta» del contribuyente, desde el lado del contador.
 *
 * Tres cosas en una pantalla, porque son la misma conversación: el enlace que
 * se le mandó, los documentos que contestó y lo que registró en adicionales.
 */
import { computed, onMounted, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import {
  crearAdicional,
  eliminarAdicional,
  listarAdicionales,
  listarRequerimientos,
  marcarRevisado,
  parametrosAdicionales,
  sincronizarRequerimientos,
} from '../api/portal'
import Cargando from '../components/Cargando.vue'
import MensajeError from '../components/MensajeError.vue'
import PanelEnlaceCarga from '../components/PanelEnlaceCarga.vue'
import { useContribuyente } from '../contexto'
import {
  ETIQUETAS_ESTADO_REQUERIMIENTO,
  ETIQUETAS_TIPO_ADICIONAL,
  dinero,
  fechaHora,
} from '../formato'

const { contribuyente, periodo } = useContribuyente()

const requerimientos = ref(null)
const adicionales = ref([])
const parametros = ref(null)
const error = ref('')
const sincronizando = ref(false)
const filtro = ref('faltantes')

const cerrado = computed(() => periodo.value.estado === 'CERRADO')

const COLORES_ESTADO = {
  PENDIENTE: 'bg-estado-noreportado-claro text-estado-noreportado',
  NO_APLICA: 'bg-papel-hondo text-tinta-suave',
  NO_LO_TENGO: 'bg-estado-discrepancia-claro text-estado-discrepancia',
  NO_ENTIENDO: 'bg-estado-nodeclarado-claro text-estado-nodeclarado',
}

const conSoporte = computed(() => (requerimientos.value ?? []).filter((r) => r.requiere_soporte))

const resumen = computed(() => {
  const lista = conSoporte.value
  return {
    total: lista.length,
    resueltos: lista.filter((r) => r.resuelto).length,
    pendientes: lista.filter((r) => r.estado === 'PENDIENTE' && !r.archivos.length).length,
    no_entiendo: lista.filter((r) => r.estado === 'NO_ENTIENDO').length,
    no_lo_tengo: lista.filter((r) => r.estado === 'NO_LO_TENGO').length,
    sin_reconocer: (requerimientos.value ?? []).filter(
      (r) => !r.concepto_reconocido && !r.revisado_por_contador,
    ).length,
  }
})

const visibles = computed(() => {
  const lista = requerimientos.value ?? []
  if (filtro.value === 'todos') return lista
  if (filtro.value === 'sin_clasificar')
    return lista.filter((r) => !r.concepto_reconocido && !r.revisado_por_contador)
  if (filtro.value === 'no_entiendo') return lista.filter((r) => r.estado === 'NO_ENTIENDO')
  return conSoporte.value.filter((r) => !r.resuelto)
})

async function cargar() {
  error.value = ''
  try {
    const [r, a] = await Promise.all([
      listarRequerimientos(contribuyente.value.id, periodo.value.id),
      listarAdicionales(contribuyente.value.id, periodo.value.id),
    ])
    requerimientos.value = r
    adicionales.value = a
    try {
      parametros.value = await parametrosAdicionales(contribuyente.value.id, periodo.value.id)
    } catch {
      parametros.value = null
    }
  } catch (e) {
    error.value = mensajeDeError(e)
    requerimientos.value = []
  }
}

async function sincronizar() {
  error.value = ''
  sincronizando.value = true
  try {
    requerimientos.value = await sincronizarRequerimientos(
      contribuyente.value.id,
      periodo.value.id,
    )
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    sincronizando.value = false
  }
}

async function revisar(requerimiento) {
  error.value = ''
  try {
    await marcarRevisado(
      contribuyente.value.id,
      periodo.value.id,
      requerimiento.id,
      !requerimiento.revisado_por_contador,
    )
    await cargar()
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

// --- Adicionales, desde el lado del contador ------------------------------

const nuevo = ref({ tipo: '', descripcion: '', valor: '', cantidad: '', pais: '' })
const errorAdicional = ref('')
const agregando = ref(false)

const conceptoElegido = computed(
  () => parametros.value?.conceptos.find((c) => c.tipo === nuevo.value.tipo) ?? null,
)

function numero(texto) {
  const limpio = String(texto ?? '').replace(/[^\d]/g, '')
  return limpio === '' ? 0 : Number(limpio)
}

async function agregar() {
  errorAdicional.value = ''
  agregando.value = true
  try {
    await crearAdicional(contribuyente.value.id, periodo.value.id, {
      tipo: nuevo.value.tipo,
      descripcion: nuevo.value.descripcion,
      valor: numero(nuevo.value.valor),
      cantidad: nuevo.value.cantidad === '' ? null : Number(nuevo.value.cantidad),
      pais: nuevo.value.pais || null,
    })
    nuevo.value = { tipo: '', descripcion: '', valor: '', cantidad: '', pais: '' }
    await cargar()
  } catch (e) {
    errorAdicional.value = mensajeDeError(e)
  } finally {
    agregando.value = false
  }
}

async function quitar(adicional) {
  errorAdicional.value = ''
  try {
    await eliminarAdicional(contribuyente.value.id, periodo.value.id, adicional.id)
    await cargar()
  } catch (e) {
    errorAdicional.value = mensajeDeError(e)
  }
}

onMounted(cargar)
</script>

<template>
  <div class="space-y-6">
    <PanelEnlaceCarga
      :contribuyente-id="contribuyente.id"
      :periodo-id="periodo.id"
      :anio-gravable="periodo.anio_gravable"
      :cerrado="cerrado"
    />

    <MensajeError :mensaje="error" />
    <Cargando v-if="requerimientos === null && !error" />

    <template v-else>
      <section class="hoja p-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>Documentos pedidos</h2>
            <p class="mt-1 text-sm text-tinta-suave">
              {{ resumen.resueltos }} de {{ resumen.total }} resueltos.
            </p>
          </div>
          <button type="button" class="boton-secundario" :disabled="sincronizando" @click="sincronizar">
            Regenerar desde la exógena
          </button>
        </div>

        <div class="mt-4 grid gap-3 sm:grid-cols-4">
          <div
            v-for="d in [
              { clave: 'faltantes', texto: 'Sin resolver', valor: resumen.total - resumen.resueltos },
              { clave: 'no_entiendo', texto: '«No entiendo»', valor: resumen.no_entiendo },
              { clave: 'sin_clasificar', texto: 'Sin clasificar', valor: resumen.sin_reconocer },
              { clave: 'todos', texto: 'Todos', valor: (requerimientos ?? []).length },
            ]"
            :key="d.clave"
          >
            <button
              type="button"
              class="w-full rounded border px-3 py-2 text-left"
              :class="filtro === d.clave ? 'border-tinta bg-papel-hondo/60' : 'border-papel-linea bg-white'"
              :aria-pressed="filtro === d.clave"
              @click="filtro = d.clave"
            >
              <span class="block text-xs text-tinta-suave">{{ d.texto }}</span>
              <span class="cifra block text-xl font-semibold">{{ d.valor }}</span>
            </button>
          </div>
        </div>
      </section>

      <div v-if="!visibles.length" class="hoja p-6 text-center text-sm text-tinta-suave">
        Nada en este grupo.
      </div>

      <article v-for="r in visibles" :key="r.id" class="hoja space-y-3 p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="leading-snug">{{ r.titulo }}</h3>
            <p class="mt-0.5 text-xs text-tinta-tenue">
              <span v-if="r.nombre_reportante">
                {{ r.nombre_reportante }} · NIT {{ r.nit_reportante }}
              </span>
              <span v-else>Dato adicional</span>
              <span v-if="r.concepto_code"> · concepto {{ r.concepto_code }}</span>
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <span v-if="r.valor_exogena !== null" class="cifra text-sm">
              {{ dinero(r.valor_exogena) }}
            </span>
            <span
              class="whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold"
              :class="COLORES_ESTADO[r.estado]"
            >
              {{ ETIQUETAS_ESTADO_REQUERIMIENTO[r.estado] }}
            </span>
          </div>
        </div>

        <p v-if="r.detalle_original" class="text-sm text-tinta-suave">
          Detalle del archivo: «{{ r.detalle_original }}»
        </p>

        <p
          v-if="r.motivo_revision"
          class="rounded border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro px-3 py-2 text-sm"
        >
          {{ r.motivo_revision }}
        </p>

        <p v-if="r.nota_contribuyente" class="rounded bg-papel-hondo/60 px-3 py-2 text-sm">
          Nota del contribuyente: «{{ r.nota_contribuyente }}»
        </p>

        <p v-if="r.valor_informado !== null" class="text-sm">
          Valor que informó: <span class="cifra">{{ dinero(Number(r.valor_informado)) }}</span>
        </p>

        <div v-if="r.archivos.length" class="text-sm">
          <p class="font-medium">Soportes cargados</p>
          <p class="text-xs text-tinta-tenue">
            Se abren y se descargan desde la pestaña «Soportes».
          </p>
          <ul class="mt-1 space-y-0.5">
            <li v-for="a in r.archivos" :key="a.id" class="flex flex-wrap gap-x-3 text-tinta-suave">
              <span>{{ a.nombre_original }}</span>
              <span class="text-xs text-tinta-tenue">{{ fechaHora(a.creado_en) }}</span>
            </li>
          </ul>
        </div>

        <div class="flex flex-wrap items-center gap-3 text-sm">
          <span class="text-xs text-tinta-tenue">
            Última respuesta: {{ fechaHora(r.actualizado_en) }}
          </span>
          <button
            v-if="!r.concepto_reconocido || r.revisado_por_contador"
            type="button"
            class="text-sm font-medium text-libro underline"
            @click="revisar(r)"
          >
            {{ r.revisado_por_contador ? 'Quitar la marca de revisado' : 'Marcar como revisado' }}
          </button>
        </div>
      </article>

      <!-- Adicionales -->
      <section class="hoja space-y-4 p-5">
        <div>
          <h2>Adicionales</h2>
          <p class="mt-1 max-w-prose text-sm text-tinta-suave">
            Lo que la exógena nunca contiene. Los topes se validan contra la tabla de parámetros
            del año gravable {{ periodo.anio_gravable }}, no contra cifras escritas en el código.
          </p>
        </div>

        <form v-if="parametros && !cerrado" class="grid gap-3 sm:grid-cols-5" @submit.prevent="agregar">
          <div class="sm:col-span-2">
            <label class="etiqueta" for="r-tipo">Concepto</label>
            <select id="r-tipo" v-model="nuevo.tipo" class="campo" required>
              <option value="" disabled>Elige…</option>
              <option v-for="c in parametros.conceptos" :key="c.tipo" :value="c.tipo">
                {{ ETIQUETAS_TIPO_ADICIONAL[c.tipo] ?? c.etiqueta }}
              </option>
            </select>
          </div>
          <div class="sm:col-span-2">
            <label class="etiqueta" for="r-desc">Descripción</label>
            <input id="r-desc" v-model="nuevo.descripcion" class="campo" required maxlength="300" />
          </div>
          <div v-if="conceptoElegido?.pide_cantidad">
            <label class="etiqueta" for="r-cant">Cantidad</label>
            <input
              id="r-cant"
              v-model="nuevo.cantidad"
              type="number"
              min="1"
              :max="conceptoElegido.cantidad_maxima ?? 20"
              class="campo"
              required
            />
          </div>
          <div v-else>
            <label class="etiqueta" for="r-valor">Valor</label>
            <input id="r-valor" v-model="nuevo.valor" class="campo" inputmode="numeric" />
          </div>
          <div v-if="conceptoElegido?.pide_pais" class="sm:col-span-2">
            <label class="etiqueta" for="r-pais">País</label>
            <input id="r-pais" v-model="nuevo.pais" class="campo" required maxlength="60" />
          </div>
          <div class="sm:col-span-5 flex flex-wrap items-center gap-3">
            <button type="submit" class="boton" :disabled="agregando || !nuevo.tipo">Agregar</button>
            <p v-if="conceptoElegido" class="text-xs text-tinta-suave">
              <template v-if="conceptoElegido.tope_anual_en_pesos">
                Tope del año: {{ dinero(Number(conceptoElegido.tope_anual_en_pesos)) }}
                <span v-if="conceptoElegido.es_tope_mensual">(tope mensual anualizado)</span>
                <span v-if="conceptoElegido.grupo_tope_compartido">— compartido</span>
                · {{ conceptoElegido.fuente_legal }}
              </template>
              <template v-else>Sin tope legal propio.</template>
            </p>
          </div>
          <p v-if="conceptoElegido?.advertencia" class="sm:col-span-5 text-xs text-tinta-suave">
            {{ conceptoElegido.advertencia }}
          </p>
        </form>
        <p
          v-else-if="!parametros"
          class="rounded border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro px-4 py-3 text-sm"
        >
          La aplicación no trae los parámetros tributarios de {{ periodo.anio_gravable }}, así que
          no se puede validar este formulario contra ningún tope. Cárgalos antes de capturar
          adicionales.
        </p>

        <MensajeError :mensaje="errorAdicional" />

        <div v-if="adicionales.length" class="overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Concepto</th>
                <th>Descripción</th>
                <th class="cifra">Valor</th>
                <th>Cantidad</th>
                <th>País</th>
                <th>Lo registró</th>
                <th><span class="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in adicionales" :key="a.id">
                <td>{{ ETIQUETAS_TIPO_ADICIONAL[a.tipo] ?? a.tipo }}</td>
                <td>{{ a.descripcion }}</td>
                <td class="cifra">{{ Number(a.valor) > 0 ? dinero(Number(a.valor)) : '—' }}</td>
                <td>{{ a.cantidad ?? '—' }}</td>
                <td>{{ a.pais ?? '—' }}</td>
                <td class="text-sm">
                  {{ a.capturado_en_portal ? 'El contribuyente' : 'Tú' }}
                </td>
                <td class="text-right">
                  <button
                    v-if="!cerrado"
                    type="button"
                    class="text-sm text-estado-nodeclarado underline"
                    @click="quitar(a)"
                  >
                    Quitar
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="text-sm text-tinta-suave">Todavía no hay adicionales registrados.</p>
      </section>
    </template>
  </div>
</template>

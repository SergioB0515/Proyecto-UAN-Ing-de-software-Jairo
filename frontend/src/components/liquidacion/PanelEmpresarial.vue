<script setup>
/**
 * Depreciación, pérdidas fiscales y pagos en efectivo.
 *
 * Va aparte de LiquidacionView porque solo le sirve a contribuyentes con
 * negocio: un asalariado no deprecia activos ni compensa pérdidas, y meterle
 * tres secciones vacías en la pantalla le estorba. La vista decide si lo
 * muestra; este componente solo sabe pintarlo.
 */
import { computed, onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import {
  crearPagoEfectivo,
  crearPerdida,
  eliminarDepreciacion,
  eliminarPagoEfectivo,
  eliminarPerdida,
  guardarDepreciacion,
  listarCategoriasDepreciacion,
  listarDepreciacion,
  listarPagosEfectivo,
  listarPerdidas,
} from '../../api/liquidacion'
import { dinero } from '../../formato'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  periodoFiscalId: { type: Number, required: true },
  anioGravable: { type: Number, required: true },
  activos: { type: Array, default: () => [] },
})
const emit = defineEmits(['cambio'])

const error = ref('')
const categorias = ref([])
const depreciacion = ref([])
const perdidas = ref([])
const pagos = ref([])
const guardando = reactive({ depreciacion: false, perdida: false, pago: false })

const nuevaFila = reactive({ activo_id: '', categoria: '', vida_util_anios: 10 })
const nuevaPerdida = reactive({ anio_origen: props.anioGravable - 1, tipo_renta: 'NO_LABORAL', valor: '' })
const nuevoPago = reactive({ descripcion: '', valor: '' })

const TIPOS_PERDIDA = [
  { valor: 'CAPITAL', etiqueta: 'Rentas de capital' },
  { valor: 'NO_LABORAL', etiqueta: 'Rentas no laborales' },
  { valor: 'TRABAJO_SIN_VINCULO', etiqueta: 'Trabajo sin vínculo laboral' },
]

const yaDepreciados = computed(() => new Set(depreciacion.value.map((d) => d.activo_id)))
const activosDisponibles = computed(() =>
  props.activos.filter((a) => !yaDepreciados.value.has(a.id)),
)
const totalDepreciacion = computed(() =>
  depreciacion.value.reduce((s, d) => s + Number(d.depreciacion_del_periodo), 0),
)

async function cargar() {
  error.value = ''
  try {
    const [c, d, p, e] = await Promise.all([
      listarCategoriasDepreciacion(props.anioGravable),
      listarDepreciacion(props.contribuyenteId, props.periodoFiscalId),
      listarPerdidas(props.contribuyenteId, props.anioGravable),
      listarPagosEfectivo(props.contribuyenteId, props.periodoFiscalId),
    ])
    categorias.value = c
    depreciacion.value = d
    perdidas.value = p
    pagos.value = e
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function accion(clave, fn) {
  guardando[clave] = true
  error.value = ''
  try {
    await fn()
    await cargar()
    emit('cambio')
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    guardando[clave] = false
  }
}

const agregarDepreciacion = () =>
  accion('depreciacion', async () => {
    const filas = depreciacion.value.map((d) => ({
      activo_id: d.activo_id,
      categoria: d.categoria,
      vida_util_anios: d.vida_util_anios,
      valor_residual: d.valor_residual,
      depreciacion_acumulada: d.depreciacion_acumulada,
      meses_en_el_periodo: d.meses_en_el_periodo,
    }))
    filas.push({
      activo_id: Number(nuevaFila.activo_id),
      categoria: nuevaFila.categoria,
      vida_util_anios: Number(nuevaFila.vida_util_anios),
    })
    await guardarDepreciacion(props.contribuyenteId, props.periodoFiscalId, filas)
    Object.assign(nuevaFila, { activo_id: '', categoria: '', vida_util_anios: 10 })
  })

const guardarCambiosDepreciacion = () =>
  accion('depreciacion', () =>
    guardarDepreciacion(
      props.contribuyenteId,
      props.periodoFiscalId,
      depreciacion.value.map((d) => ({
        activo_id: d.activo_id,
        categoria: d.categoria,
        vida_util_anios: Number(d.vida_util_anios),
        valor_residual: d.valor_residual,
        depreciacion_acumulada: d.depreciacion_acumulada,
        meses_en_el_periodo: Number(d.meses_en_el_periodo),
      })),
    ),
  )

const quitarDepreciacion = (activoId) =>
  accion('depreciacion', () =>
    eliminarDepreciacion(props.contribuyenteId, props.periodoFiscalId, activoId),
  )

const agregarPerdida = () =>
  accion('perdida', async () => {
    await crearPerdida(props.contribuyenteId, props.anioGravable, {
      anio_origen: Number(nuevaPerdida.anio_origen),
      tipo_renta: nuevaPerdida.tipo_renta,
      valor: nuevaPerdida.valor,
    })
    nuevaPerdida.valor = ''
  })

const quitarPerdida = (id) =>
  accion('perdida', () => eliminarPerdida(props.contribuyenteId, id))

const agregarPago = () =>
  accion('pago', async () => {
    await crearPagoEfectivo(props.contribuyenteId, props.periodoFiscalId, {
      descripcion: nuevoPago.descripcion,
      valor: nuevoPago.valor,
    })
    Object.assign(nuevoPago, { descripcion: '', valor: '' })
  })

const quitarPago = (id) =>
  accion('pago', () => eliminarPagoEfectivo(props.contribuyenteId, props.periodoFiscalId, id))

onMounted(cargar)
</script>

<template>
  <div class="space-y-6">
    <MensajeError :mensaje="error" />

    <!-- Depreciación --------------------------------------------------- -->
    <section class="hoja p-5">
      <h2>Depreciación de activos fijos</h2>
      <p class="mt-1 max-w-prose text-sm text-tinta-suave">
        El art. 137 fija tasas anuales máximas, no vidas útiles obligatorias: puede
        registrar la vida útil que use en su contabilidad y la aplicación recorta la
        deducción al tope fiscal, avisándole cuando lo hace.
      </p>

<div v-if="depreciacion.length" class="mt-4 overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Activo</th>
            <th class="text-right">Costo fiscal</th>
            <th>Categoría (art. 137)</th>
            <th class="text-right">Vida útil</th>
            <th class="text-right">Valor residual</th>
            <th class="text-right">Depr. acumulada</th>
            <th class="text-right">Meses</th>
            <th class="text-right">Deduce este año</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in depreciacion" :key="d.activo_id">
            <td>
              {{ d.descripcion }}
              <p class="max-w-xs text-xs text-tinta-tenue">{{ d.formula }}</p>
            </td>
            <td class="cifra">{{ dinero(d.costo_fiscal) }}</td>
            <td>
              <select v-model="d.categoria" class="campo w-56" :aria-label="`Categoría de ${d.descripcion}`">
                <option v-for="c in categorias" :key="c.valor" :value="c.valor">{{ c.etiqueta }}</option>
              </select>
            </td>
            <td><input v-model="d.vida_util_anios" type="number" min="1" max="100" class="campo w-20 text-right" /></td>
            <td><input v-model="d.valor_residual" type="number" min="0" step="0.01" class="campo w-32 text-right" /></td>
            <td><input v-model="d.depreciacion_acumulada" type="number" min="0" step="0.01" class="campo w-32 text-right" /></td>
            <td><input v-model="d.meses_en_el_periodo" type="number" min="0" max="12" class="campo w-16 text-right" /></td>
            <td class="cifra font-semibold">{{ dinero(d.depreciacion_del_periodo) }}</td>
            <td>
              <button type="button" class="text-sm underline hover:text-estado-nodeclarado" @click="quitarDepreciacion(d.activo_id)">
                Quitar
              </button>
            </td>
          </tr>
          <tr>
            <td colspan="7" class="text-right font-semibold">Total deducible</td>
            <td class="cifra font-semibold">{{ dinero(totalDepreciacion) }}</td>
            <td></td>
          </tr>
        </tbody>
      </table>
      </div>

      <div v-if="depreciacion.length" class="mt-3">
        <button type="button" class="boton-secundario" :disabled="guardando.depreciacion" @click="guardarCambiosDepreciacion">
          Guardar cambios y recalcular
        </button>
      </div>

      <form class="mt-4 flex flex-wrap items-end gap-3" @submit.prevent="agregarDepreciacion">
        <div>
          <label class="etiqueta" for="dep-activo">Activo a depreciar</label>
          <select id="dep-activo" v-model="nuevaFila.activo_id" class="campo w-64" required>
            <option value="" disabled>Elija un activo</option>
            <option v-for="a in activosDisponibles" :key="a.id" :value="a.id">
              {{ a.descripcion }} — {{ dinero(a.valor) }}
            </option>
          </select>
        </div>
        <div>
          <label class="etiqueta" for="dep-categoria">Categoría</label>
          <select id="dep-categoria" v-model="nuevaFila.categoria" class="campo w-64" required>
            <option value="" disabled>Elija la categoría</option>
            <option v-for="c in categorias" :key="c.valor" :value="c.valor">
              {{ c.etiqueta }} — máx. {{ (Number(c.tasa_maxima_anual) * 100).toFixed(2) }} % anual
            </option>
          </select>
        </div>
        <div>
          <label class="etiqueta" for="dep-vida">Vida útil (años)</label>
          <input id="dep-vida" v-model="nuevaFila.vida_util_anios" type="number" min="1" max="100" class="campo w-28" required />
        </div>
        <button type="submit" class="boton" :disabled="guardando.depreciacion || !activosDisponibles.length">
          Agregar
        </button>
      </form>
      <p v-if="!activosDisponibles.length && !depreciacion.length" class="mt-2 text-sm text-tinta-suave">
        No hay activos registrados en este año gravable.
      </p>
    </section>

    <!-- Pérdidas fiscales ---------------------------------------------- -->
    <section class="hoja p-5">
      <h2>Pérdidas fiscales de años anteriores</h2>
      <p class="mt-1 max-w-prose text-sm text-tinta-suave">
        Solo se compensan contra rentas del mismo tipo (art. 330) y caducan a los doce
        periodos gravables (art. 147). Las rentas de trabajo con vínculo laboral no
        admiten compensación.
      </p>

      <table v-if="perdidas.length" class="mt-4">
        <thead>
          <tr>
            <th>Año de origen</th>
            <th>Tipo de renta</th>
            <th class="text-right">Valor</th>
            <th class="text-right">Saldo por compensar</th>
            <th>Estado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in perdidas" :key="p.id" :class="p.vigente ? '' : 'opacity-60'">
            <td>{{ p.anio_origen }}</td>
            <td>{{ TIPOS_PERDIDA.find((t) => t.valor === p.tipo_renta)?.etiqueta ?? p.tipo_renta }}</td>
            <td class="cifra">{{ dinero(p.valor) }}</td>
            <td class="cifra">{{ dinero(p.saldo_por_compensar) }}</td>
            <td>
              <span
                class="rounded px-2 py-0.5 text-xs font-medium"
                :class="p.vigente ? 'bg-libro-claro text-libro-oscuro' : 'bg-estado-nodeclarado-claro text-estado-nodeclarado'"
              >
                {{ p.vigente ? 'Vigente' : 'Caducada' }}
              </span>
            </td>
            <td>
              <button type="button" class="text-sm underline hover:text-estado-nodeclarado" @click="quitarPerdida(p.id)">
                Quitar
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <form class="mt-4 flex flex-wrap items-end gap-3" @submit.prevent="agregarPerdida">
        <div>
          <label class="etiqueta" for="per-anio">Año de origen</label>
          <input id="per-anio" v-model="nuevaPerdida.anio_origen" type="number" min="2000" max="2100" class="campo w-28" required />
        </div>
        <div>
          <label class="etiqueta" for="per-tipo">Tipo de renta</label>
          <select id="per-tipo" v-model="nuevaPerdida.tipo_renta" class="campo w-64">
            <option v-for="t in TIPOS_PERDIDA" :key="t.valor" :value="t.valor">{{ t.etiqueta }}</option>
          </select>
        </div>
        <div>
          <label class="etiqueta" for="per-valor">Valor de la pérdida</label>
          <input id="per-valor" v-model="nuevaPerdida.valor" type="number" min="0" step="0.01" class="campo w-44" required />
        </div>
        <button type="submit" class="boton" :disabled="guardando.perdida">Agregar</button>
      </form>
    </section>

    <!-- Pagos en efectivo ----------------------------------------------- -->
    <section class="hoja p-5">
      <h2>Pagos individuales en efectivo</h2>
      <p class="mt-1 max-w-prose text-sm text-tinta-suave">
        El art. 771-5 par. 2 no acepta operaciones en efectivo por encima de 100 UVT.
        Registre aquí las que superen ese valor: la aplicación las marca para que las
        revise. Los totales del año van en la hoja de liquidación.
      </p>

      <table v-if="pagos.length" class="mt-4">
        <thead>
          <tr>
            <th>Descripción</th>
            <th class="text-right">Valor</th>
            <th>Estado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in pagos" :key="p.id">
            <td>{{ p.descripcion }}</td>
            <td class="cifra">{{ dinero(p.valor) }}</td>
            <td>
              <span
                v-if="p.supera_limite_individual"
                class="rounded bg-estado-nodeclarado-claro px-2 py-0.5 text-xs font-medium text-estado-nodeclarado"
              >
                Supera 100 UVT
              </span>
              <span v-else class="text-xs text-tinta-suave">Dentro del límite</span>
            </td>
            <td>
              <button type="button" class="text-sm underline hover:text-estado-nodeclarado" @click="quitarPago(p.id)">
                Quitar
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <form class="mt-4 flex flex-wrap items-end gap-3" @submit.prevent="agregarPago">
        <div class="min-w-64 flex-1">
          <label class="etiqueta" for="pag-desc">Descripción</label>
          <input id="pag-desc" v-model="nuevoPago.descripcion" class="campo" maxlength="200" required />
        </div>
        <div>
          <label class="etiqueta" for="pag-valor">Valor</label>
          <input id="pag-valor" v-model="nuevoPago.valor" type="number" min="0" step="0.01" class="campo w-44" required />
        </div>
        <button type="submit" class="boton" :disabled="guardando.pago">Agregar</button>
      </form>
    </section>
  </div>
</template>

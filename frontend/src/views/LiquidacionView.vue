<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import {
  actualizarHoja,
  clasificarIngresos,
  crearDeduccion,
  eliminarDeduccion,
  exportarLiquidacion,
  liquidar,
  listarCedulas,
  listarDeducciones,
  listarIngresos,
  obtenerHoja,
} from '../api/liquidacion'
import Cargando from '../components/Cargando.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import MensajeError from '../components/MensajeError.vue'
import { useContribuyente } from '../contexto'
import { dinero } from '../formato'

const { contribuyente, periodo } = useContribuyente()
const cid = computed(() => contribuyente.value.id)
const pid = computed(() => periodo.value.id)

const cargando = ref(true)
const error = ref('')
const anioNoSoportado = ref('')

const cedulas = ref([])
const ingresos = ref([])
const hoja = ref(null)
const deducciones = ref([])
const resultado = ref(null)

const guardando = reactive({ ingresos: false, hoja: false, deduccion: false })
const nuevaDeduccion = reactive({
  nombre: '',
  valor: '',
  sujeto_a_limite_general: true,
  fuente_legal: '',
})
const renglonAbierto = ref(null)

// Los renglones del motor se agrupan aquí por prefijo. El contador lee la
// liquidación por bloques —patrimonio, cédula general, impuesto, saldo—, no
// como una lista plana de treinta filas.
const BLOQUES = [
  { titulo: 'Patrimonio', prefijos: ['PAT-'] },
  { titulo: 'Cédula general', prefijos: ['CG-', 'DED-'] },
  { titulo: 'Pensiones', prefijos: ['PEN-'] },
  { titulo: 'Dividendos', prefijos: ['DIV-'] },
  { titulo: 'Base e impuesto', prefijos: ['RENTA-PRESUNTIVA', 'BASE-', 'IMP-RENTA'] },
  { titulo: 'Ganancias ocasionales', prefijos: ['GO-'] },
  { titulo: 'Impuesto a cargo y descuentos', prefijos: ['TOTAL-', 'DESC-', 'IMP-NETO'] },
  { titulo: 'Retenciones, anticipo y saldo', prefijos: ['RETENCIONES', 'ANTICIPO-', 'SALDO-'] },
]

const bloques = computed(() => {
  if (!resultado.value) return []
  const usados = new Set()
  const grupos = BLOQUES.map(({ titulo, prefijos }) => {
    const renglones = resultado.value.renglones.filter(
      (r) => !usados.has(r.codigo) && prefijos.some((p) => r.codigo.startsWith(p)),
    )
    renglones.forEach((r) => usados.add(r.codigo))
    return { titulo, renglones }
  }).filter((g) => g.renglones.length)
  // Cualquier renglón nuevo del motor aparece aquí en vez de desaparecer
  // silenciosamente de la pantalla.
  const sobrantes = resultado.value.renglones.filter((r) => !usados.has(r.codigo))
  if (sobrantes.length) grupos.push({ titulo: 'Otros renglones', renglones: sobrantes })
  return grupos
})

const DESTACADOS = new Set(['CG-RENTA-LIQUIDA', 'BASE-GRAVABLE', 'IMP-NETO', 'SALDO-A-PAGAR', 'SALDO-A-FAVOR'])

const sinClasificar = computed(() => ingresos.value.filter((i) => i.cedula === 'SIN_CLASIFICAR'))

// Secciones de la hoja. Se declaran como datos para que agregar un campo sea
// una línea aquí y no otro bloque de plantilla.
const SECCIONES_HOJA = [
  {
    titulo: 'Patrimonio',
    ayuda: 'El patrimonio bruto sale de los activos registrados. Las deudas se capturan aquí.',
    campos: [{ clave: 'deudas', etiqueta: 'Deudas a 31 de diciembre' }],
  },
  {
    titulo: 'Rentas de trabajo',
    ayuda: 'Los aportes obligatorios se restan como ingresos no constitutivos (arts. 55 y 56 ET).',
    campos: [
      { clave: 'aportes_obligatorios_salud', etiqueta: 'Aportes obligatorios a salud' },
      { clave: 'aportes_obligatorios_pension', etiqueta: 'Aportes obligatorios a pensión' },
      { clave: 'otros_ingresos_no_constitutivos', etiqueta: 'Otros ingresos no constitutivos' },
    ],
  },
  {
    titulo: 'Honorarios sin vínculo laboral',
    ayuda:
      'El art. 336 num. 4 obliga a elegir: o se restan costos y gastos, o se toma la renta exenta del 25 %. No las dos.',
    campos: [
      { clave: 'opta_por_costos_y_gastos', etiqueta: 'Optar por costos y gastos', tipo: 'checkbox' },
      { clave: 'costos_y_gastos_sin_vinculo_laboral', etiqueta: 'Costos y gastos imputables' },
    ],
  },
  {
    titulo: 'Deducciones fuera del límite del 40 %',
    ayuda: 'Dependientes (72 UVT cada uno, hasta cuatro) y 1 % de compras con factura electrónica (tope 240 UVT).',
    campos: [
      { clave: 'numero_dependientes', etiqueta: 'Número de dependientes', tipo: 'entero', max: 20 },
      { clave: 'compras_con_factura_electronica', etiqueta: 'Compras con factura electrónica' },
    ],
  },
  {
    titulo: 'Pensiones',
    ayuda: 'Exentas hasta 1.000 UVT mensuales (art. 206 num. 5).',
    campos: [
      { clave: 'ingresos_pensiones', etiqueta: 'Ingresos por pensiones' },
      { clave: 'incrngo_pensiones', etiqueta: 'Ingresos no constitutivos' },
      { clave: 'meses_pension_causados', etiqueta: 'Meses causados', tipo: 'entero', max: 12 },
    ],
  },
  {
    titulo: 'Dividendos',
    ayuda: 'Tomados del certificado que expide la sociedad, incluida la retención.',
    campos: [
      { clave: 'dividendos_no_gravados', etiqueta: 'Dividendos no gravados' },
      { clave: 'dividendos_gravados', etiqueta: 'Dividendos gravados' },
      { clave: 'retencion_dividendos', etiqueta: 'Retención practicada' },
    ],
  },
  {
    titulo: 'Ganancias ocasionales',
    ayuda: 'Tarifa propia del 15 %; loterías, rifas y apuestas al 20 %.',
    campos: [
      { clave: 'go_ingresos', etiqueta: 'Ingresos por ganancia ocasional' },
      { clave: 'go_costos', etiqueta: 'Costos' },
      { clave: 'go_ganancia_exenta', etiqueta: 'Ganancia exenta' },
      { clave: 'go_loterias_rifas_apuestas', etiqueta: 'Loterías, rifas y apuestas' },
      { clave: 'go_retenciones', etiqueta: 'Retenciones' },
    ],
  },
  {
    titulo: 'Cierre de la liquidación',
    ayuda: 'El anticipo del año siguiente depende de cuántos años lleva declarando (art. 807 ET).',
    campos: [
      { clave: 'renta_presuntiva', etiqueta: 'Renta presuntiva' },
      { clave: 'otros_descuentos_tributarios', etiqueta: 'Otros descuentos tributarios' },
      { clave: 'anticipo_pagado_anio_anterior', etiqueta: 'Anticipo pagado el año anterior' },
      { clave: 'saldo_a_favor_anio_anterior', etiqueta: 'Saldo a favor del año anterior' },
      { clave: 'anios_declarando', etiqueta: 'Años declarando', tipo: 'entero', max: 99 },
    ],
  },
]

async function recalcular() {
  anioNoSoportado.value = ''
  try {
    resultado.value = await liquidar(cid.value, pid.value)
  } catch (e) {
    resultado.value = null
    if (e.response?.status === 422) anioNoSoportado.value = mensajeDeError(e)
    else error.value = mensajeDeError(e)
  }
}

async function cargar() {
  cargando.value = true
  error.value = ''
  try {
    const [c, i, h, d] = await Promise.all([
      listarCedulas(),
      listarIngresos(cid.value, pid.value),
      obtenerHoja(cid.value, pid.value),
      listarDeducciones(cid.value, pid.value),
    ])
    cedulas.value = c
    ingresos.value = i
    hoja.value = h
    deducciones.value = d
    await recalcular()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    cargando.value = false
  }
}

async function guardarClasificacion() {
  guardando.ingresos = true
  error.value = ''
  try {
    ingresos.value = await clasificarIngresos(
      cid.value,
      pid.value,
      ingresos.value.map((i) => ({ fuente_ingreso_id: i.fuente_ingreso_id, cedula: i.cedula })),
    )
    await recalcular()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    guardando.ingresos = false
  }
}

async function guardarHoja() {
  guardando.hoja = true
  error.value = ''
  try {
    const cambios = {}
    for (const seccion of SECCIONES_HOJA) {
      for (const campo of seccion.campos) cambios[campo.clave] = hoja.value[campo.clave]
    }
    hoja.value = await actualizarHoja(cid.value, pid.value, cambios)
    await recalcular()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    guardando.hoja = false
  }
}

async function agregarDeduccion() {
  guardando.deduccion = true
  error.value = ''
  try {
    await crearDeduccion(cid.value, pid.value, {
      nombre: nuevaDeduccion.nombre,
      valor: nuevaDeduccion.valor,
      sujeto_a_limite_general: nuevaDeduccion.sujeto_a_limite_general,
      fuente_legal: nuevaDeduccion.fuente_legal,
    })
    Object.assign(nuevaDeduccion, { nombre: '', valor: '', sujeto_a_limite_general: true, fuente_legal: '' })
    deducciones.value = await listarDeducciones(cid.value, pid.value)
    await recalcular()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    guardando.deduccion = false
  }
}

async function quitarDeduccion(id) {
  error.value = ''
  try {
    await eliminarDeduccion(cid.value, pid.value, id)
    deducciones.value = await listarDeducciones(cid.value, pid.value)
    await recalcular()
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

const etiquetaCedula = (valor) => cedulas.value.find((c) => c.valor === valor)?.etiqueta ?? valor

onMounted(cargar)
</script>

<template>
  <MensajeError :mensaje="error" />
  <Cargando v-if="cargando" />

  <div v-else class="space-y-6">
    <EstadoVacio v-if="anioNoSoportado" :titulo="`No hay parámetros tributarios de ${periodo.anio_gravable}`">
      {{ anioNoSoportado }}
    </EstadoVacio>

    <!-- 1. Clasificación por cédula ------------------------------------- -->
    <section class="hoja p-5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2>Clasificación de ingresos por cédula</h2>
          <p class="mt-1 max-w-prose text-sm text-tinta-suave">
            La cédula determina qué se puede restar: en rentas de capital y no laborales se restan
            costos y gastos, en rentas de trabajo con vínculo laboral no, y la exención del 25 % solo
            aplica a estas últimas. La app sugiere; usted confirma.
          </p>
        </div>
        <button type="button" class="boton" :disabled="guardando.ingresos || !ingresos.length" @click="guardarClasificacion">
          Confirmar clasificación
        </button>
      </div>

      <p
        v-if="sinClasificar.length"
        role="alert"
        class="mt-4 rounded border-l-4 border-estado-nodeclarado bg-estado-nodeclarado-claro px-4 py-3 text-sm"
      >
        {{ sinClasificar.length }}
        {{ sinClasificar.length === 1 ? 'ingreso queda' : 'ingresos quedan' }} sin clasificar y
        <strong>no entran en la liquidación</strong>. Asígneles una cédula para que el borrador esté completo.
      </p>

      <EstadoVacio v-if="!ingresos.length" class="mt-4" titulo="No hay fuentes de ingreso registradas">
        Registra los ingresos en
        <RouterLink :to="{ name: 'patrimonio', query: $route.query }" class="enlace">Patrimonio e ingresos</RouterLink>.
      </EstadoVacio>

      <table v-else class="mt-4">
        <thead>
          <tr>
            <th>Concepto</th>
            <th class="text-right">Valor anual</th>
            <th class="text-right">Retención</th>
            <th>Cédula</th>
            <th>Origen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="i in ingresos" :key="i.fuente_ingreso_id">
            <td>{{ i.concepto }}</td>
            <td class="cifra">{{ dinero(i.valor_anual) }}</td>
            <td class="cifra">{{ dinero(i.retencion_fuente) }}</td>
            <td>
              <select v-model="i.cedula" class="campo w-64" :aria-label="`Cédula de ${i.concepto}`">
                <option v-for="c in cedulas" :key="c.valor" :value="c.valor">{{ c.etiqueta }}</option>
              </select>
              <p class="mt-1 max-w-sm text-xs text-tinta-tenue">
                {{ cedulas.find((c) => c.valor === i.cedula)?.implicacion }}
              </p>
            </td>
            <td>
              <span
                class="rounded px-2 py-0.5 text-xs font-medium"
                :class="
                  i.origen_clasificacion === 'MANUAL'
                    ? 'bg-libro-claro text-libro-oscuro'
                    : 'bg-estado-noreportado-claro text-estado-noreportado'
                "
              >
                {{ i.origen_clasificacion === 'MANUAL' ? 'Confirmada' : 'Sugerida' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 2. Hoja de liquidación ------------------------------------------- -->
    <section class="hoja p-5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2>Hoja de liquidación</h2>
          <p class="mt-1 max-w-prose text-sm text-tinta-suave">
            Datos que no están en la exógena ni en el resto de la aplicación. Quedan auditados con
            quién los guardó y cuándo.
          </p>
        </div>
        <button type="button" class="boton" :disabled="guardando.hoja" @click="guardarHoja">
          Guardar y recalcular
        </button>
      </div>

      <div class="mt-5 grid items-start gap-6 lg:grid-cols-2">
        <fieldset v-for="seccion in SECCIONES_HOJA" :key="seccion.titulo" class="rounded border border-papel-linea p-4">
          <legend class="px-1 text-sm font-semibold">{{ seccion.titulo }}</legend>
          <p class="mb-3 text-xs text-tinta-suave">{{ seccion.ayuda }}</p>
          <div class="space-y-3">
            <div v-for="campo in seccion.campos" :key="campo.clave">
              <label v-if="campo.tipo === 'checkbox'" class="flex items-center gap-2 text-sm">
                <input v-model="hoja[campo.clave]" type="checkbox" class="rounded border-papel-linea" />
                {{ campo.etiqueta }}
              </label>
              <template v-else>
                <label class="etiqueta" :for="`h-${campo.clave}`">{{ campo.etiqueta }}</label>
                <input
                  :id="`h-${campo.clave}`"
                  v-model="hoja[campo.clave]"
                  type="number"
                  min="0"
                  :max="campo.max"
                  :step="campo.tipo === 'entero' ? 1 : 0.01"
                  class="campo"
                />
              </template>
            </div>
          </div>
        </fieldset>
      </div>
    </section>

    <!-- 3. Deducciones y rentas exentas solicitadas ---------------------- -->
    <section class="hoja p-5">
      <h2>Deducciones y rentas exentas solicitadas</h2>
      <p class="mt-1 max-w-prose text-sm text-tinta-suave">
        Marque si cada concepto está sujeto al límite del 40 % con tope de 1.340 UVT (art. 336
        num. 3). Confundir eso es el error de liquidación más común y cambia el impuesto.
      </p>

      <table v-if="deducciones.length" class="mt-4">
        <thead>
          <tr>
            <th>Concepto</th>
            <th class="text-right">Valor</th>
            <th>Límite del 40 %</th>
            <th>Fuente legal</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in deducciones" :key="d.id">
            <td>{{ d.nombre }}</td>
            <td class="cifra">{{ dinero(d.valor) }}</td>
            <td>{{ d.sujeto_a_limite_general ? 'Sujeto' : 'No sujeto' }}</td>
            <td class="text-xs text-tinta-suave">{{ d.fuente_legal || '—' }}</td>
            <td>
              <button type="button" class="text-sm underline hover:text-estado-nodeclarado" @click="quitarDeduccion(d.id)">
                Quitar
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <form class="mt-4 grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-5" @submit.prevent="agregarDeduccion">
        <div class="lg:col-span-2">
          <label class="etiqueta" for="d-nombre">Concepto</label>
          <input id="d-nombre" v-model="nuevaDeduccion.nombre" class="campo" required maxlength="200" />
        </div>
        <div>
          <label class="etiqueta" for="d-valor">Valor</label>
          <input id="d-valor" v-model="nuevaDeduccion.valor" type="number" min="0" step="0.01" class="campo" required />
        </div>
        <div>
          <label class="etiqueta" for="d-fuente">Fuente legal</label>
          <input id="d-fuente" v-model="nuevaDeduccion.fuente_legal" class="campo" placeholder="Art. 119 ET" maxlength="200" />
        </div>
        <div class="space-y-2">
          <label class="flex items-center gap-2 text-sm">
            <input v-model="nuevaDeduccion.sujeto_a_limite_general" type="checkbox" class="rounded border-papel-linea" />
            Sujeto al límite
          </label>
          <button type="submit" class="boton w-full" :disabled="guardando.deduccion">Agregar</button>
        </div>
      </form>
    </section>

    <!-- 4. Borrador de la liquidación ------------------------------------ -->
    <template v-if="resultado">
      <section class="hoja p-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>Borrador de la liquidación — año gravable {{ resultado.anio_gravable }}</h2>
            <p class="mt-1 text-sm text-tinta-suave">
              {{ contribuyente.nombre }}, NIT {{ contribuyente.rut }} ·
              UVT {{ dinero(resultado.parametros.uvt) }} · régimen
              {{ resultado.parametros.regimen.replaceAll('_', ' ').toLowerCase() }}
            </p>
            <p class="text-xs text-tinta-tenue">{{ resultado.parametros.fuente_uvt }}</p>
          </div>
          <div class="flex gap-2">
            <button type="button" class="boton-secundario" @click="exportarLiquidacion(cid, pid, 'xlsx')">
              Excel
            </button>
            <button type="button" class="boton-secundario" @click="exportarLiquidacion(cid, pid, 'pdf')">
              PDF
            </button>
          </div>
        </div>

        <p class="mt-4 max-w-prose rounded border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro px-4 py-3 text-sm">
          {{ resultado.advertencia }}
        </p>

        <div v-if="resultado.diagnosticos.length" class="mt-4 space-y-2">
          <h3>Diagnósticos</h3>
          <p
            v-for="(d, n) in resultado.diagnosticos"
            :key="n"
            class="rounded border-l-4 border-estado-nodeclarado bg-estado-nodeclarado-claro px-4 py-2 text-sm"
          >
            {{ d }}
          </p>
        </div>

        <div v-for="bloque in bloques" :key="bloque.titulo" class="mt-6">
          <h3 class="mb-2">{{ bloque.titulo }}</h3>
          <table>
            <thead>
              <tr>
                <th>Concepto</th>
                <th class="text-right">Valor calculado</th>
                <th class="text-right">Valor a declarar</th>
                <th class="w-24">Rastro</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="r in bloque.renglones" :key="r.codigo">
                <tr :class="DESTACADOS.has(r.codigo) ? 'bg-libro-claro/60 font-semibold' : ''">
                  <td>
                    {{ r.nombre }}
                    <span class="ml-1 text-xs font-normal text-tinta-tenue">{{ r.codigo }}</span>
                  </td>
                  <td class="cifra">{{ dinero(r.valor) }}</td>
                  <td class="cifra">{{ dinero(r.valor_declarable) }}</td>
                  <td>
                    <button
                      type="button"
                      class="text-sm underline hover:text-libro"
                      :aria-expanded="renglonAbierto === r.codigo"
                      @click="renglonAbierto = renglonAbierto === r.codigo ? null : r.codigo"
                    >
                      {{ renglonAbierto === r.codigo ? 'Ocultar' : 'Ver' }}
                    </button>
                  </td>
                </tr>
                <tr v-if="renglonAbierto === r.codigo">
                  <td colspan="4" class="bg-papel-hondo/60 text-sm">
                    <p v-if="r.formula"><span class="font-medium">Cómo se calculó:</span> {{ r.formula }}</p>
                    <p v-if="r.fuente_legal" class="mt-1 text-tinta-suave">
                      <span class="font-medium">Norma:</span> {{ r.fuente_legal }}
                    </p>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <div class="mt-6 border-t border-papel-linea pt-4">
          <h3>Notas</h3>
          <ul class="mt-2 list-disc space-y-1 pl-5 text-sm text-tinta-suave">
            <li v-for="(n, i) in resultado.notas" :key="i">{{ n }}</li>
          </ul>
        </div>
      </section>
    </template>
  </div>
</template>

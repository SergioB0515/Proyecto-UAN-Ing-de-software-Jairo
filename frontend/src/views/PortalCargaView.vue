<script setup>
/**
 * Portal de carga del contribuyente.
 *
 * Lo abre quien recibe el enlace, sin cuenta y casi siempre desde el celular.
 * De ahí las decisiones de esta pantalla:
 *
 * - No usa `cliente` de axios: usa `clientePortal`, sin el encabezado de
 *   sesión del contador ni la redirección al login (ver api/portal.js).
 * - Los cuatro estados son botones grandes, no un `select`: se contestan con
 *   el pulgar.
 * - El valor es opcional y el estado no, igual que en el servidor. El
 *   formulario no deja «guardar» sin estado, pero sí sin valor.
 * - Nada de esta pantalla muestra la liquidación: no hay de dónde sacarla.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  abrirPortal,
  aceptarPolitica,
  agregarAdicionalPortal,
  cargarExogena,
  eliminarAdicionalPortal,
  mensajeDeError,
  parametrosAdicionalesPortal,
  responderRequerimiento,
  subirSoporte,
} from '../api/portal'
import {
  AYUDA_ESTADO_REQUERIMIENTO,
  ETIQUETAS_ESTADO_REQUERIMIENTO,
  ETIQUETAS_TIPO_ADICIONAL,
  dinero,
  fecha,
} from '../formato'

const route = useRoute()
const token = String(route.params.token || '')

const sesion = ref(null)
const parametros = ref(null)
const cargando = ref(true)
const error = ref('')
const enlaceInvalido = ref('')
const seccion = ref('documentos')

const ESTADOS = Object.keys(ETIQUETAS_ESTADO_REQUERIMIENTO)

async function cargar() {
  error.value = ''
  try {
    sesion.value = await abrirPortal(token)
    if (sesion.value.autorizacion) await cargarParametros()
  } catch (e) {
    if (e.response?.status === 404) {
      enlaceInvalido.value =
        'Este enlace no existe. Verifica que copiaste la dirección completa, o pídele a tu contador que te la reenvíe.'
    } else if (e.response?.status === 410) {
      enlaceInvalido.value = mensajeDeError(e)
    } else {
      error.value = mensajeDeError(e)
    }
  } finally {
    cargando.value = false
  }
}

async function cargarParametros() {
  try {
    parametros.value = await parametrosAdicionalesPortal(token)
  } catch {
    // El año gravable puede no tener parámetros cargados. En ese caso la
    // pestaña de adicionales no se abre, y el resto del portal sigue sirviendo.
    parametros.value = null
  }
}

// --- Política -------------------------------------------------------------

const autorizacion = ref({ nombre: '', documento: '', acepto: false })
const aceptando = ref(false)

async function aceptar() {
  error.value = ''
  aceptando.value = true
  try {
    await aceptarPolitica(token, {
      version_politica: sesion.value.politica.version,
      nombre_quien_acepta: autorizacion.value.nombre,
      documento_quien_acepta: autorizacion.value.documento || null,
      acepto: autorizacion.value.acepto,
    })
    await cargar()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    aceptando.value = false
  }
}

// --- Exógena --------------------------------------------------------------

const subiendoExogena = ref(false)
const avisoExogena = ref('')

async function alElegirExogena(evento) {
  const archivo = evento.target.files?.[0]
  if (!archivo) return
  error.value = ''
  avisoExogena.value = ''
  subiendoExogena.value = true
  try {
    const resultado = await cargarExogena(token, archivo)
    avisoExogena.value =
      `Listo. Leímos ${resultado.cantidad_registros} ` +
      `renglón${resultado.cantidad_registros === 1 ? '' : 'es'} del archivo` +
      (resultado.fecha_corte ? `, con corte al ${fecha(resultado.fecha_corte)}` : '') +
      '. Abajo está la lista de documentos que necesitamos.'
    await cargar()
    seccion.value = 'documentos'
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    subiendoExogena.value = false
    evento.target.value = ''
  }
}

// --- Requerimientos -------------------------------------------------------

const guardando = ref(null)
const valores = ref({})
const notas = ref({})

const requerimientos = computed(() =>
  (sesion.value?.requerimientos ?? []).filter((r) => r.requiere_soporte),
)
const informativos = computed(() =>
  (sesion.value?.requerimientos ?? []).filter((r) => !r.requiere_soporte),
)
const pendientes = computed(() => requerimientos.value.filter((r) => !r.resuelto))
const listos = computed(() => requerimientos.value.filter((r) => r.resuelto))

function numero(texto) {
  const limpio = String(texto ?? '').replace(/[^\d]/g, '')
  return limpio === '' ? null : Number(limpio)
}

async function marcar(requerimiento, estado) {
  error.value = ''
  guardando.value = requerimiento.id
  try {
    await responderRequerimiento(token, requerimiento.id, {
      estado,
      valor_informado: numero(valores.value[requerimiento.id] ?? requerimiento.valor_informado),
      nota_contribuyente: notas.value[requerimiento.id] ?? requerimiento.nota_contribuyente,
    })
    await cargar()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    guardando.value = null
  }
}

async function alElegirSoporte(requerimiento, evento) {
  const archivo = evento.target.files?.[0]
  if (!archivo) return
  error.value = ''
  guardando.value = requerimiento.id
  try {
    await subirSoporte(token, requerimiento.id, archivo)
    await cargar()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    guardando.value = null
    evento.target.value = ''
  }
}

// --- Adicionales ----------------------------------------------------------

const nuevo = ref({ tipo: '', descripcion: '', valor: '', cantidad: '', pais: '' })
const agregando = ref(false)
const errorAdicional = ref('')

const conceptoElegido = computed(
  () => parametros.value?.conceptos.find((c) => c.tipo === nuevo.value.tipo) ?? null,
)

async function agregar() {
  errorAdicional.value = ''
  agregando.value = true
  try {
    await agregarAdicionalPortal(token, {
      tipo: nuevo.value.tipo,
      descripcion: nuevo.value.descripcion,
      valor: numero(nuevo.value.valor) ?? 0,
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
    await eliminarAdicionalPortal(token, adicional.id)
    await cargar()
  } catch (e) {
    errorAdicional.value = mensajeDeError(e)
  }
}

onMounted(cargar)
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-6 pb-24">
    <!-- Enlace que ya no sirve: el mensaje dice qué hacer, no solo que falló. -->
    <div v-if="enlaceInvalido" class="hoja p-6 text-center">
      <h1 class="text-xl">Este enlace no está disponible</h1>
      <p class="mt-3 text-sm text-tinta-suave">{{ enlaceInvalido }}</p>
      <p class="mt-3 text-sm text-tinta-suave">
        Si ya habías cargado documentos, no se perdieron: siguen guardados con tu contador.
      </p>
    </div>

    <p v-else-if="cargando" class="py-10 text-center text-sm text-tinta-suave" role="status">
      Abriendo…
    </p>

    <template v-else-if="sesion">
      <header class="mb-6">
        <h1 class="text-xl">Documentos para tu declaración de renta</h1>
        <p class="mt-1 text-sm text-tinta-suave">
          Año gravable {{ sesion.anio_gravable }} · {{ sesion.contribuyente_nombre }}
          <span class="text-tinta-tenue">({{ sesion.documento_enmascarado }})</span>
        </p>
        <p class="text-sm text-tinta-suave">
          Te lo pide {{ sesion.contador_nombre }}. El enlace sirve hasta el
          {{ fecha(sesion.expira_en) }}.
        </p>
      </header>

      <p
        v-if="error"
        role="alert"
        class="mb-4 rounded border-l-4 border-estado-nodeclarado bg-estado-nodeclarado-claro px-4 py-3 text-sm text-estado-nodeclarado"
      >
        {{ error }}
      </p>

      <!-- Paso 1: la autorización. Sin esto no se escribe nada. -->
      <form v-if="!sesion.autorizacion" class="hoja space-y-4 p-5" @submit.prevent="aceptar">
        <h2>{{ sesion.politica.titulo }}</h2>
        <p class="text-sm text-tinta-suave">{{ sesion.politica.texto }}</p>
        <div class="rounded bg-papel-hondo/60 p-4 text-sm">
          <p class="font-medium">¿Para qué se usan tus datos?</p>
          <ul class="mt-2 list-disc space-y-1 pl-5 text-tinta-suave">
            <li v-for="(finalidad, i) in sesion.politica.finalidades" :key="i">{{ finalidad }}</li>
          </ul>
          <p class="mt-3 font-medium">¿Quién responde por ellos?</p>
          <p class="text-tinta-suave">{{ sesion.politica.responsable }}</p>
          <p class="mt-3 font-medium">Tus derechos</p>
          <p class="text-tinta-suave">{{ sesion.politica.derechos }}</p>
          <p class="mt-3 text-xs text-tinta-tenue">
            Versión {{ sesion.politica.version }}, vigente desde
            {{ fecha(sesion.politica.vigente_desde) }}. Queda registrado que aceptaste esta
            versión, con la fecha.
          </p>
        </div>
        <div>
          <label class="etiqueta" for="p-nombre">Tu nombre completo</label>
          <input id="p-nombre" v-model="autorizacion.nombre" class="campo" required minlength="3" />
        </div>
        <div>
          <label class="etiqueta" for="p-doc">Tu número de documento (opcional)</label>
          <input id="p-doc" v-model="autorizacion.documento" class="campo" inputmode="numeric" />
        </div>
        <label class="flex items-start gap-3 text-sm">
          <input v-model="autorizacion.acepto" type="checkbox" class="mt-1 h-5 w-5" required />
          <span>Autorizo el tratamiento de mis datos para los fines descritos arriba.</span>
        </label>
        <button type="submit" class="boton w-full py-3" :disabled="aceptando || !autorizacion.acepto">
          Autorizar y continuar
        </button>
      </form>

      <template v-else>
        <nav class="mb-5 flex gap-1 border-b border-papel-linea" aria-label="Secciones">
          <button
            v-for="s in [
              { id: 'archivo', texto: 'Tu archivo DIAN' },
              { id: 'documentos', texto: `Documentos (${pendientes.length})` },
              { id: 'adicionales', texto: 'Adicionales' },
            ]"
            :key="s.id"
            type="button"
            class="-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm"
            :class="
              seccion === s.id
                ? 'border-libro font-semibold text-tinta'
                : 'border-transparent text-tinta-suave'
            "
            :aria-current="seccion === s.id ? 'page' : undefined"
            @click="seccion = s.id"
          >
            {{ s.texto }}
          </button>
        </nav>

        <!-- Archivo de la DIAN -->
        <section v-if="seccion === 'archivo'" class="hoja space-y-4 p-5">
          <h2>El archivo de la DIAN</h2>
          <p class="text-sm text-tinta-suave">
            Entra al portal de la DIAN (MUISCA), abre «Consulta de información reportada por
            terceros» del año {{ sesion.anio_gravable }}, descarga el Excel y cárgalo aquí. Con
            eso armamos la lista de documentos que te vamos a pedir.
          </p>
          <p v-if="sesion.exogena_cargada" class="rounded bg-libro-claro px-4 py-3 text-sm">
            Ya tenemos tu archivo<span v-if="sesion.fecha_corte_exogena">
              , con fecha de corte {{ fecha(sesion.fecha_corte_exogena) }}</span
            >. Si descargas uno más nuevo, cárgalo: no se borra nada de lo que ya hiciste.
          </p>
          <p v-if="avisoExogena" class="rounded bg-libro-claro px-4 py-3 text-sm" role="status">
            {{ avisoExogena }}
          </p>
          <label class="boton w-full cursor-pointer py-3">
            <input
              type="file"
              accept=".xlsx,.xls"
              class="sr-only"
              :disabled="subiendoExogena"
              @change="alElegirExogena"
            />
            {{ subiendoExogena ? 'Cargando…' : 'Elegir el Excel de la DIAN' }}
          </label>
        </section>

        <!-- Documentos pedidos -->
        <section v-else-if="seccion === 'documentos'" class="space-y-4">
          <div v-if="!requerimientos.length" class="hoja p-6 text-center text-sm text-tinta-suave">
            <p class="font-medium text-tinta">Todavía no hay documentos que pedirte</p>
            <p class="mt-1">
              Carga primero el Excel de la DIAN en la pestaña «Tu archivo DIAN» y la lista aparece
              aquí.
            </p>
          </div>

          <template v-else>
            <p class="text-sm text-tinta-suave">
              {{ listos.length }} de {{ requerimientos.length }} resueltos.
              <span v-if="pendientes.length">Faltan {{ pendientes.length }}.</span>
            </p>

            <article
              v-for="r in [...pendientes, ...listos]"
              :key="r.id"
              class="hoja space-y-3 p-4"
              :class="r.resuelto ? 'opacity-70' : ''"
            >
              <div class="flex items-start justify-between gap-3">
                <h3 class="leading-snug">{{ r.titulo }}</h3>
                <span v-if="r.valor_exogena !== null" class="cifra text-sm text-tinta-suave">
                  {{ dinero(r.valor_exogena) }}
                </span>
              </div>
              <p class="text-sm text-tinta-suave">{{ r.explicacion }}</p>

              <div v-if="r.archivos.length" class="rounded bg-libro-claro px-3 py-2 text-sm">
                <p class="font-medium">Ya cargaste:</p>
                <ul class="mt-1 space-y-0.5 text-tinta-suave">
                  <li v-for="a in r.archivos" :key="a.id">{{ a.nombre_original }}</li>
                </ul>
              </div>

              <div class="grid gap-3 sm:grid-cols-2">
                <div>
                  <label class="etiqueta" :for="`valor-${r.id}`">Valor (opcional)</label>
                  <input
                    :id="`valor-${r.id}`"
                    :value="valores[r.id] ?? r.valor_informado ?? ''"
                    class="campo"
                    inputmode="numeric"
                    placeholder="Si lo sabes"
                    @input="valores[r.id] = $event.target.value"
                  />
                </div>
                <div>
                  <label class="etiqueta" :for="`nota-${r.id}`">Nota para tu contador</label>
                  <input
                    :id="`nota-${r.id}`"
                    :value="notas[r.id] ?? r.nota_contribuyente ?? ''"
                    class="campo"
                    maxlength="500"
                    @input="notas[r.id] = $event.target.value"
                  />
                </div>
              </div>

              <label class="boton-secundario w-full cursor-pointer py-3">
                <input
                  type="file"
                  accept="image/*,.pdf,.png,.jpg,.jpeg"
                  class="sr-only"
                  :disabled="guardando === r.id"
                  @change="alElegirSoporte(r, $event)"
                />
                Tomar foto o elegir archivo
              </label>

              <fieldset>
                <legend class="etiqueta">¿Cómo va este documento?</legend>
                <div class="grid grid-cols-2 gap-2">
                  <button
                    v-for="estado in ESTADOS"
                    :key="estado"
                    type="button"
                    class="rounded border px-3 py-3 text-left text-sm transition-colors"
                    :class="
                      r.estado === estado
                        ? 'border-libro bg-libro-claro font-semibold'
                        : 'border-papel-linea bg-white'
                    "
                    :aria-pressed="r.estado === estado"
                    :disabled="guardando === r.id"
                    @click="marcar(r, estado)"
                  >
                    {{ ETIQUETAS_ESTADO_REQUERIMIENTO[estado] }}
                    <span class="block text-xs font-normal text-tinta-suave">
                      {{ AYUDA_ESTADO_REQUERIMIENTO[estado] }}
                    </span>
                  </button>
                </div>
              </fieldset>
            </article>

            <details v-if="informativos.length" class="hoja p-4">
              <summary class="cursor-pointer text-sm font-medium">
                {{ informativos.length }} renglón{{ informativos.length === 1 ? '' : 'es' }} que no
                necesitan documento
              </summary>
              <ul class="mt-3 space-y-2 text-sm text-tinta-suave">
                <li v-for="r in informativos" :key="r.id">
                  <span class="text-tinta">{{ r.titulo }}</span>
                  <span v-if="r.valor_exogena !== null" class="cifra">
                    — {{ dinero(r.valor_exogena) }}</span
                  >
                </li>
              </ul>
            </details>
          </template>
        </section>

        <!-- Adicionales -->
        <section v-else class="space-y-4">
          <div class="hoja space-y-4 p-5">
            <h2>Lo que el archivo de la DIAN no trae</h2>
            <p class="text-sm text-tinta-suave">
              Hay cosas que nadie le reporta a la DIAN y que solo tú sabes: tus dependientes, lo
              que pagaste de medicina prepagada, tus deudas, lo que tengas en el exterior. Si no
              se registran aquí, no entran a tu declaración.
            </p>

            <p
              v-if="!parametros"
              class="rounded border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro px-4 py-3 text-sm"
            >
              Esta sección no está disponible para el año {{ sesion.anio_gravable }}. Habla con tu
              contador.
            </p>

            <form v-else class="space-y-3" @submit.prevent="agregar">
              <div>
                <label class="etiqueta" for="a-tipo">¿Qué quieres agregar?</label>
                <select id="a-tipo" v-model="nuevo.tipo" class="campo" required>
                  <option value="" disabled>Elige una opción…</option>
                  <option v-for="c in parametros.conceptos" :key="c.tipo" :value="c.tipo">
                    {{ ETIQUETAS_TIPO_ADICIONAL[c.tipo] ?? c.etiqueta }}
                  </option>
                </select>
              </div>

              <p v-if="conceptoElegido?.tope_anual_en_pesos" class="text-sm text-tinta-suave">
                Máximo del año: {{ dinero(Number(conceptoElegido.tope_anual_en_pesos)) }}
                <span v-if="conceptoElegido.grupo_tope_compartido">
                  (compartido con el otro concepto del mismo grupo)</span
                >.
                <span class="text-tinta-tenue">{{ conceptoElegido.fuente_legal }}</span>
              </p>

              <div>
                <label class="etiqueta" for="a-desc">¿Cuál? Descríbelo en tus palabras</label>
                <input
                  id="a-desc"
                  v-model="nuevo.descripcion"
                  class="campo"
                  required
                  maxlength="300"
                  placeholder="Ej.: crédito de vivienda con el Banco…"
                />
              </div>

              <div v-if="conceptoElegido?.pide_cantidad">
                <label class="etiqueta" for="a-cant">¿Cuántas personas?</label>
                <input
                  id="a-cant"
                  v-model="nuevo.cantidad"
                  type="number"
                  min="1"
                  :max="conceptoElegido.cantidad_maxima ?? 20"
                  class="campo"
                  required
                />
              </div>
              <div v-else-if="conceptoElegido">
                <label class="etiqueta" for="a-valor">Valor del año</label>
                <input
                  id="a-valor"
                  v-model="nuevo.valor"
                  class="campo"
                  inputmode="numeric"
                  required
                />
              </div>

              <div v-if="conceptoElegido?.pide_pais">
                <label class="etiqueta" for="a-pais">¿En qué país?</label>
                <input id="a-pais" v-model="nuevo.pais" class="campo" required maxlength="60" />
              </div>

              <p
                v-if="errorAdicional"
                role="alert"
                class="rounded border-l-4 border-estado-nodeclarado bg-estado-nodeclarado-claro px-4 py-3 text-sm text-estado-nodeclarado"
              >
                {{ errorAdicional }}
              </p>

              <button type="submit" class="boton w-full py-3" :disabled="agregando || !nuevo.tipo">
                Agregar
              </button>
            </form>
          </div>

          <div v-if="sesion.adicionales.length" class="hoja divide-y divide-papel-hondo">
            <div
              v-for="a in sesion.adicionales"
              :key="a.id"
              class="flex items-start justify-between gap-3 p-4"
            >
              <div>
                <p class="text-sm font-medium">{{ a.descripcion }}</p>
                <p class="text-xs text-tinta-suave">
                  {{ ETIQUETAS_TIPO_ADICIONAL[a.tipo] ?? a.tipo }}
                  <span v-if="a.cantidad"> · {{ a.cantidad }} persona(s)</span>
                  <span v-if="a.pais"> · {{ a.pais }}</span>
                </p>
              </div>
              <div class="flex shrink-0 items-center gap-3">
                <span v-if="Number(a.valor) > 0" class="cifra text-sm">
                  {{ dinero(Number(a.valor)) }}
                </span>
                <button type="button" class="text-sm text-estado-nodeclarado underline" @click="quitar(a)">
                  Quitar
                </button>
              </div>
            </div>
          </div>
        </section>
      </template>

      <footer class="mt-8 text-center text-xs text-tinta-tenue">
        Esta página solo recibe información. No muestra el cálculo de tu impuesto: eso lo prepara
        y lo revisa {{ sesion.contador_nombre }}.
      </footer>
    </template>
  </div>
</template>

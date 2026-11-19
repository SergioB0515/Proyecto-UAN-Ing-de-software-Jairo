<script setup>
/**
 * Portal de carga del contribuyente.
 *
 * Lo abre quien recibe el enlace, sin cuenta y casi siempre desde el celular.
 * De ahí las decisiones de esta pantalla:
 *
 * - No usa `cliente` de axios: usa `clientePortal`, sin el encabezado de
 *   sesión del contador ni la redirección al login (ver api/portal.js).
 * - Las respuestas son botones grandes, no un `select`: se contestan con el
 *   pulgar.
 * - Subir el archivo ES recibir el documento, así que no se pide marcar nada
 *   después de cargarlo.
 * - La lista de documentos es la MISMA que ve el contador. No hay dos
 *   bandejas de «lo que falta».
 *
 * Cómo se reparte el peso visual
 * ------------------------------
 * Cada documento tiene, por debajo, seis cosas que se pueden hacer: subir un
 * archivo, marcar cuatro estados, anotar un valor y escribir una nota. Si se
 * muestran todas a la vez, una lista de veinte documentos son ciento veinte
 * controles y nadie la termina.
 *
 * Entonces el caso normal —«lo tengo, acá está la foto»— se muestra como un
 * botón y nada más, y el resto aparece solo si hace falta. Lo cargado se
 * reserva para lo que el contribuyente no sabe: los documentos que marcó
 * «no sé qué me están pidiendo» se abren solos, con la explicación y el
 * espacio para contar qué tiene, porque ahí es donde la pantalla tiene que
 * ayudar y no solo recibir.
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
  responderDocumento,
  subirSoporte,
} from '../api/portal'
import {
  ETIQUETAS_TIPO_ADICIONAL,
  RESPUESTAS_CONTRIBUYENTE,
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
const primeraCarga = ref(true)

const RESPUESTAS = Object.keys(RESPUESTAS_CONTRIBUYENTE)

/**
 * Qué implica cada respuesta, en una línea.
 *
 * Elegir entre cuatro opciones parecidas sin saber qué pasa después es la
 * parte difícil de esta pantalla. Esta copia es local al portal: el contador
 * ve las mismas claves con otras palabras, las de `formato.js`.
 */
const CONSECUENCIA_RESPUESTA = {
  PENDIENTE: 'Te lo seguimos pidiendo. Puedes volver a este enlace cuando lo tengas.',
  NO_APLICA: 'Tu contador revisa por qué te lo reportaron y lo aclara con la DIAN.',
  NO_LO_TENGO: 'Tu contador ve que existe y busca cómo respaldarlo de otra forma.',
  NO_ENTIENDO: 'Le queda marcado a tu contador para que te lo explique o lo resuelva él.',
}

async function cargar() {
  error.value = ''
  try {
    sesion.value = await abrirPortal(token)
    if (sesion.value.autorizacion) await cargarParametros()
    // Si todavía no hay archivo de la DIAN, no tiene sentido abrir en una
    // lista vacía: la primera cosa que hay que hacer es cargarlo.
    if (primeraCarga.value && sesion.value.autorizacion && !sesion.value.exogena_cargada) {
      seccion.value = 'archivo'
    }
    primeraCarga.value = false
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

const primerNombre = computed(() => {
  const partes = String(sesion.value?.contribuyente_nombre ?? '').trim().split(/\s+/)
  return partes[0] ?? ''
})

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
      documento_quien_acepta: autorizacion.value.documento,
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
      `. Te pedimos ${resultado.documentos_pedidos} documento` +
      `${resultado.documentos_pedidos === 1 ? '' : 's'}.`
    await cargar()
    seccion.value = 'documentos'
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    subiendoExogena.value = false
    evento.target.value = ''
  }
}

// --- Documentos -----------------------------------------------------------

const guardando = ref(null)
const valores = ref({})
const notas = ref({})
const abiertos = ref({})
const mostrarListos = ref(false)

const documentos = computed(() => sesion.value?.documentos ?? [])
const listos = computed(() => documentos.value.filter((d) => d.resuelto))
// Lo que no se entiende va primero y aparte: es lo único de esta lista que el
// contribuyente no puede resolver solo.
const sinEntender = computed(() =>
  documentos.value.filter((d) => !d.resuelto && d.estado === 'NO_ENTIENDO'),
)
const porHacer = computed(() =>
  documentos.value.filter((d) => !d.resuelto && d.estado !== 'NO_ENTIENDO'),
)
const faltan = computed(() => sinEntender.value.length + porHacer.value.length)
const porcentaje = computed(() =>
  documentos.value.length ? Math.round((listos.value.length / documentos.value.length) * 100) : 0,
)

/**
 * Parte la descripción en un título corto y el detalle que lo precisa.
 *
 * Las descripciones están redactadas para el contador, que necesita toda la
 * precisión en el mismo renglón de su tabla. En un celular esa misma frase
 * son cuatro líneas de letra grande antes de llegar al botón. El título se
 * queda con la primera parte y lo demás baja a una línea gris: no se pierde
 * nada, y hace falta que no se pierda, porque la matrícula del inmueble es
 * justo lo que distingue un predial de otro.
 */
function partirDescripcion(descripcion) {
  let titulo = String(descripcion ?? '').trim()
  const detalles = []
  const dosPuntos = titulo.indexOf(':')
  if (dosPuntos >= 12) {
    detalles.push(titulo.slice(dosPuntos + 1).trim())
    titulo = titulo.slice(0, dosPuntos).trim()
  }
  const parentesis = titulo.match(/^(.*?)\s*\(([^)]*)\)$/)
  if (parentesis && parentesis[1].trim().length >= 12) {
    titulo = parentesis[1].trim()
    detalles.unshift(parentesis[2].trim())
  }
  return { titulo, detalle: detalles.filter(Boolean).join(' · ') }
}

const textos = computed(() => {
  const mapa = {}
  for (const d of documentos.value) mapa[d.clave] = partirDescripcion(d.descripcion)
  return mapa
})

function estaAbierto(documento) {
  // Lo que el contribuyente marcó como «no sé qué es» se abre solo: ahí es
  // donde necesita leer y escribir, no donde necesita un botón más.
  return abiertos.value[documento.clave] ?? documento.estado === 'NO_ENTIENDO'
}

function alternar(documento) {
  abiertos.value[documento.clave] = !estaAbierto(documento)
}

function numero(texto) {
  const limpio = String(texto ?? '').replace(/[^\d]/g, '')
  return limpio === '' ? null : Number(limpio)
}

async function responder(documento, estado) {
  error.value = ''
  guardando.value = documento.clave
  try {
    await responderDocumento(token, documento.clave, {
      estado,
      valor_informado: numero(valores.value[documento.clave] ?? documento.valor_informado),
      nota: notas.value[documento.clave] ?? documento.nota,
    })
    await cargar()
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    guardando.value = null
  }
}

async function alElegirSoporte(documento, evento) {
  const archivo = evento.target.files?.[0]
  if (!archivo) return
  error.value = ''
  guardando.value = documento.clave
  try {
    await subirSoporte(token, documento.clave, archivo)
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
const abrirFormularioAdicional = ref(false)

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
    abrirFormularioAdicional.value = false
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
        <h1 class="text-xl">
          <template v-if="primerNombre">Hola, {{ primerNombre }}</template>
          <template v-else>Documentos para tu declaración</template>
        </h1>
        <p class="mt-1 text-sm text-tinta-suave">
          Aquí vas a reunir los documentos de tu declaración de renta del año
          {{ sesion.anio_gravable }}. Te lo pide {{ sesion.contador_nombre }}.
        </p>
        <p class="mt-1 text-xs text-tinta-tenue">
          {{ sesion.contribuyente_nombre }} · {{ sesion.documento_enmascarado }} · el enlace sirve
          hasta el {{ fecha(sesion.expira_en) }}
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
      <form v-if="!sesion.autorizacion" class="hoja space-y-5 p-5" @submit.prevent="aceptar">
        <div>
          <h2>{{ sesion.politica.titulo }}</h2>
          <p class="mt-2 text-sm text-tinta-suave">{{ sesion.politica.texto }}</p>
        </div>

        <!-- El detalle de la política se guarda, no se esconde: está a un
             toque y queda registrado que esta versión fue la que se aceptó. -->
        <details class="rounded border border-papel-linea bg-papel-hondo/40">
          <summary class="cursor-pointer px-4 py-3 text-sm font-medium">
            Ver en detalle para qué se usan tus datos
          </summary>
          <div class="space-y-3 border-t border-papel-linea px-4 py-3 text-sm">
            <div>
              <p class="font-medium">¿Para qué se usan?</p>
              <ul class="mt-1 list-disc space-y-1 pl-5 text-tinta-suave">
                <li v-for="(finalidad, i) in sesion.politica.finalidades" :key="i">
                  {{ finalidad }}
                </li>
              </ul>
            </div>
            <div>
              <p class="font-medium">¿Quién responde por ellos?</p>
              <p class="text-tinta-suave">{{ sesion.politica.responsable }}</p>
            </div>
            <div>
              <p class="font-medium">Tus derechos</p>
              <p class="text-tinta-suave">{{ sesion.politica.derechos }}</p>
            </div>
            <p class="text-xs text-tinta-tenue">
              Versión {{ sesion.politica.version }}, vigente desde
              {{ fecha(sesion.politica.vigente_desde) }}. Queda registrado que aceptaste esta
              versión, con la fecha.
            </p>
          </div>
        </details>

        <div class="space-y-4 rounded border border-papel-linea p-4">
          <p class="text-sm text-tinta-suave">
            Confirma que eres tú. Tienen que coincidir con los datos que tu contador tiene
            registrados.
          </p>
          <div>
            <label class="etiqueta" for="p-nombre">Tus nombres y apellidos</label>
            <input
              id="p-nombre"
              v-model="autorizacion.nombre"
              class="campo"
              required
              minlength="3"
              autocomplete="name"
              placeholder="Como aparecen en tu documento"
            />
          </div>
          <div>
            <label class="etiqueta" for="p-doc">Tu número de documento</label>
            <input
              id="p-doc"
              v-model="autorizacion.documento"
              class="campo"
              required
              minlength="4"
              inputmode="numeric"
              placeholder="Sin puntos ni guiones"
            />
          </div>
        </div>

        <label class="flex items-start gap-3 text-sm">
          <input v-model="autorizacion.acepto" type="checkbox" class="mt-0.5 h-5 w-5" required />
          <span>Autorizo el tratamiento de mis datos para los fines descritos arriba.</span>
        </label>
        <button
          type="submit"
          class="boton w-full py-3"
          :disabled="aceptando || !autorizacion.acepto"
        >
          {{ aceptando ? 'Un momento…' : 'Autorizar y continuar' }}
        </button>
      </form>

      <template v-else>
        <!-- Avance: lo primero que se ve es cuánto falta, no cuánto hay. -->
        <div v-if="documentos.length" class="hoja mb-5 p-4">
          <div class="flex items-baseline justify-between gap-3">
            <p class="text-sm font-medium">
              <template v-if="!faltan">Ya está todo. Gracias.</template>
              <template v-else-if="faltan === 1">Te falta 1 documento</template>
              <template v-else>Te faltan {{ faltan }} documentos</template>
            </p>
            <p class="text-xs text-tinta-tenue">{{ listos.length }} de {{ documentos.length }}</p>
          </div>
          <div
            class="mt-2 h-2 overflow-hidden rounded-full bg-papel-hondo"
            role="progressbar"
            :aria-valuenow="porcentaje"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-label="Documentos resueltos"
          >
            <div class="h-full rounded-full bg-libro transition-all" :style="{ width: porcentaje + '%' }" />
          </div>
        </div>

        <nav class="mb-5 flex gap-1 border-b border-papel-linea" aria-label="Secciones">
          <button
            v-for="s in [
              { id: 'archivo', texto: sesion.exogena_cargada ? 'Archivo DIAN ✓' : 'Archivo DIAN' },
              { id: 'documentos', texto: faltan ? `Documentos (${faltan})` : 'Documentos ✓' },
              { id: 'adicionales', texto: 'Lo que falta contar' },
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
            Con este archivo armamos la lista de documentos que te vamos a pedir, así no tienes que
            adivinar cuáles son.
          </p>
          <ol class="space-y-2 text-sm text-tinta-suave">
            <li class="flex gap-3">
              <span class="shrink-0 font-semibold text-tinta">1.</span>
              <span>Entra al portal de la DIAN (MUISCA) con tu usuario.</span>
            </li>
            <li class="flex gap-3">
              <span class="shrink-0 font-semibold text-tinta">2.</span>
              <span>
                Abre «Consulta de información reportada por terceros» y elige el año
                {{ sesion.anio_gravable }}.
              </span>
            </li>
            <li class="flex gap-3">
              <span class="shrink-0 font-semibold text-tinta">3.</span>
              <span>Descarga el Excel y cárgalo aquí abajo.</span>
            </li>
          </ol>
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
        <section v-else-if="seccion === 'documentos'" class="space-y-5">
          <div v-if="!documentos.length" class="hoja p-6 text-center text-sm text-tinta-suave">
            <p class="font-medium text-tinta">Todavía no hay documentos que pedirte</p>
            <p class="mt-1">
              Carga primero el Excel de la DIAN y la lista aparece aquí.
            </p>
            <button type="button" class="boton mt-4 py-3" @click="seccion = 'archivo'">
              Ir a cargar el archivo
            </button>
          </div>

          <template v-else>
            <!-- Lo que el contribuyente no entiende: primero, abierto y con
                 espacio para escribir. Es lo que esta pantalla no puede
                 resolver sola. -->
            <div v-if="sinEntender.length" class="space-y-3">
              <h2 class="text-base">Esto te lo resuelve tu contador</h2>
              <p class="-mt-1 text-sm text-tinta-suave">
                Marcaste que no sabes qué te están pidiendo. Ya le quedó anotado. Si puedes,
                cuéntale qué sí tienes: con eso suele ser suficiente.
              </p>
              <article
                v-for="d in sinEntender"
                :key="d.clave"
                class="rounded-md border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro p-4"
              >
                <h3 class="leading-snug">{{ textos[d.clave].titulo }}</h3>
                <p v-if="d.tercero" class="text-sm text-tinta-suave">{{ d.tercero }}</p>
                <p v-if="textos[d.clave].detalle" class="text-xs text-tinta-suave">
                  {{ textos[d.clave].detalle }}
                </p>
                <p v-if="d.motivo" class="mt-2 text-sm text-tinta-suave">{{ d.motivo }}</p>

                <div class="mt-3">
                  <label class="etiqueta" :for="`nota-ne-${d.clave}`">
                    ¿Qué tienes de esto? Escríbelo como puedas
                  </label>
                  <textarea
                    :id="`nota-ne-${d.clave}`"
                    :value="notas[d.clave] ?? d.nota ?? ''"
                    class="campo"
                    rows="2"
                    maxlength="500"
                    placeholder="Ej.: me llegó un correo del banco pero no sé si es esto"
                    @input="notas[d.clave] = $event.target.value"
                  ></textarea>
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    class="boton-secundario py-2.5"
                    :disabled="guardando === d.clave"
                    @click="responder(d, 'NO_ENTIENDO')"
                  >
                    Guardar lo que escribí
                  </button>
                  <label class="boton-secundario cursor-pointer py-2.5">
                    <input
                      type="file"
                      accept="image/*,.pdf,.png,.jpg,.jpeg"
                      class="sr-only"
                      :disabled="guardando === d.clave"
                      @change="alElegirSoporte(d, $event)"
                    />
                    Subir algo que creo que es
                  </label>
                </div>
              </article>
            </div>

            <!-- El resto: un botón por documento. Lo demás, a un toque. -->
            <div v-if="porHacer.length" class="space-y-3">
              <h2 v-if="sinEntender.length" class="text-base">Lo que falta subir</h2>
              <article v-for="d in porHacer" :key="d.clave" class="hoja p-4">
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <h3 class="leading-snug">{{ textos[d.clave].titulo }}</h3>
                    <p v-if="d.tercero" class="text-sm text-tinta-suave">{{ d.tercero }}</p>
                    <p v-if="textos[d.clave].detalle" class="mt-0.5 text-xs text-tinta-tenue">
                      {{ textos[d.clave].detalle }}
                    </p>
                  </div>
                  <span
                    v-if="d.estado === 'PENDIENTE' && d.respondido_por_contribuyente"
                    class="shrink-0 rounded-full bg-papel-hondo px-2 py-0.5 text-xs text-tinta-suave"
                  >
                    Buscándolo
                  </span>
                </div>

                <div v-if="d.archivos.length" class="mt-3 rounded bg-papel-hondo/60 px-3 py-2 text-sm">
                  <p class="font-medium">Ya cargaste:</p>
                  <ul class="mt-1 space-y-0.5 text-tinta-suave">
                    <li v-for="a in d.archivos" :key="a.id">{{ a.nombre_original }}</li>
                  </ul>
                </div>

                <label class="boton mt-3 w-full cursor-pointer py-3">
                  <input
                    type="file"
                    accept="image/*,.pdf,.png,.jpg,.jpeg"
                    class="sr-only"
                    :disabled="guardando === d.clave"
                    @change="alElegirSoporte(d, $event)"
                  />
                  {{ guardando === d.clave ? 'Subiendo…' : 'Tomar foto o subir archivo' }}
                </label>

                <button
                  type="button"
                  class="mt-2 w-full py-2 text-sm text-libro underline underline-offset-2"
                  :aria-expanded="estaAbierto(d)"
                  @click="alternar(d)"
                >
                  {{ estaAbierto(d) ? 'Cerrar' : 'No lo tengo o no sé qué es' }}
                </button>

                <!-- Lo cargado, solo cuando hace falta. -->
                <div v-if="estaAbierto(d)" class="mt-3 space-y-4 border-t border-papel-linea pt-4">
                  <p v-if="d.motivo" class="rounded bg-papel-hondo/60 px-3 py-2 text-sm text-tinta-suave">
                    <span class="font-medium text-tinta">¿Qué es esto?</span> {{ d.motivo }}
                  </p>

                  <fieldset>
                    <legend class="etiqueta">Dinos qué pasa con este documento</legend>
                    <div class="space-y-2">
                      <button
                        v-for="estado in RESPUESTAS"
                        :key="estado"
                        type="button"
                        class="w-full rounded border px-3 py-3 text-left transition-colors"
                        :class="
                          d.estado === estado
                            ? 'border-libro bg-libro-claro'
                            : 'border-papel-linea bg-white'
                        "
                        :aria-pressed="d.estado === estado"
                        :disabled="guardando === d.clave"
                        @click="responder(d, estado)"
                      >
                        <span class="block text-sm font-semibold">
                          {{ RESPUESTAS_CONTRIBUYENTE[estado] }}
                        </span>
                        <span class="mt-0.5 block text-xs text-tinta-suave">
                          {{ CONSECUENCIA_RESPUESTA[estado] }}
                        </span>
                      </button>
                    </div>
                  </fieldset>

                  <div>
                    <label class="etiqueta" :for="`valor-${d.clave}`">
                      Si sabes el valor, escríbelo (opcional)
                    </label>
                    <input
                      :id="`valor-${d.clave}`"
                      :value="valores[d.clave] ?? d.valor_informado ?? ''"
                      class="campo"
                      inputmode="numeric"
                      placeholder="Solo si lo tienes a mano"
                      @input="valores[d.clave] = $event.target.value"
                    />
                  </div>
                  <div>
                    <label class="etiqueta" :for="`nota-${d.clave}`">
                      Nota para tu contador (opcional)
                    </label>
                    <input
                      :id="`nota-${d.clave}`"
                      :value="notas[d.clave] ?? d.nota ?? ''"
                      class="campo"
                      maxlength="500"
                      @input="notas[d.clave] = $event.target.value"
                    />
                  </div>
                </div>
              </article>
            </div>

            <!-- Lo resuelto se cuenta, no se muestra: ocupa lugar y ya no
                 hay nada que hacer con él. -->
            <div v-if="listos.length" class="hoja overflow-hidden">
              <button
                type="button"
                class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm"
                :aria-expanded="mostrarListos"
                @click="mostrarListos = !mostrarListos"
              >
                <span class="font-medium">
                  {{ listos.length }} documento{{ listos.length === 1 ? '' : 's' }} ya resuelto{{
                    listos.length === 1 ? '' : 's'
                  }}
                </span>
                <span class="text-tinta-suave">{{ mostrarListos ? 'Ocultar' : 'Ver' }}</span>
              </button>
              <ul v-if="mostrarListos" class="divide-y divide-papel-hondo border-t border-papel-linea">
                <li v-for="d in listos" :key="d.clave" class="px-4 py-3">
                  <p class="text-sm">{{ textos[d.clave].titulo }}</p>
                  <p class="text-xs text-tinta-suave">
                    {{ d.tercero }}
                    <span v-if="d.estado === 'RECIBIDO'"> · recibido</span>
                    <span v-else-if="d.estado === 'NO_APLICA'"> · no te corresponde</span>
                    <span v-else-if="d.estado === 'NO_LO_TENGO'"> · lo revisa tu contador</span>
                  </p>
                </li>
              </ul>
            </div>

            <p v-if="!faltan" class="hoja bg-libro-claro p-5 text-center text-sm">
              <span class="block font-medium">Terminaste con los documentos.</span>
              Revisa la pestaña «Lo que falta contar»: ahí va lo que la DIAN no sabe de ti.
            </p>
          </template>
        </section>

        <!-- Adicionales -->
        <section v-else class="space-y-4">
          <div class="hoja space-y-4 p-5">
            <h2>Lo que la DIAN no sabe de ti</h2>
            <p class="text-sm text-tinta-suave">
              Hay cosas que nadie le reporta a la DIAN y que solo tú sabes: tus dependientes, lo
              que pagaste de medicina prepagada, tus deudas, lo que tengas en el exterior. Si no
              se registran aquí, no entran a tu declaración y pagarías más de lo que te toca.
            </p>

            <p
              v-if="!parametros"
              class="rounded border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro px-4 py-3 text-sm"
            >
              Esta sección no está disponible para el año {{ sesion.anio_gravable }}. Habla con tu
              contador.
            </p>

            <button
              v-else-if="!abrirFormularioAdicional"
              type="button"
              class="boton w-full py-3"
              @click="abrirFormularioAdicional = true"
            >
              Agregar algo
            </button>

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

              <template v-if="conceptoElegido">
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

                <div v-if="conceptoElegido.pide_cantidad">
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
                <div v-else>
                  <label class="etiqueta" for="a-valor">Valor del año</label>
                  <input
                    id="a-valor"
                    v-model="nuevo.valor"
                    class="campo"
                    inputmode="numeric"
                    required
                  />
                </div>

                <div v-if="conceptoElegido.pide_pais">
                  <label class="etiqueta" for="a-pais">¿En qué país?</label>
                  <input id="a-pais" v-model="nuevo.pais" class="campo" required maxlength="60" />
                </div>
              </template>

              <p
                v-if="errorAdicional"
                role="alert"
                class="rounded border-l-4 border-estado-nodeclarado bg-estado-nodeclarado-claro px-4 py-3 text-sm text-estado-nodeclarado"
              >
                {{ errorAdicional }}
              </p>

              <div class="flex gap-2">
                <button
                  type="submit"
                  class="boton flex-1 py-3"
                  :disabled="agregando || !nuevo.tipo"
                >
                  {{ agregando ? 'Guardando…' : 'Agregar' }}
                </button>
                <button
                  type="button"
                  class="boton-secundario py-3"
                  @click="abrirFormularioAdicional = false"
                >
                  Cancelar
                </button>
              </div>
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
                <button
                  type="button"
                  class="text-sm text-estado-nodeclarado underline"
                  @click="quitar(a)"
                >
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

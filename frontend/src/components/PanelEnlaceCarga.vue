<script setup>
/**
 * El enlace de carga, desde la ficha del contribuyente.
 *
 * El token se muestra UNA vez, al generarlo: después solo queda el prefijo.
 * Por eso la pantalla insiste en copiarlo en ese momento y explica que si se
 * pierde hay que generar otro, en vez de dejar al contador buscando un botón
 * de «ver enlace» que no existe.
 */
import { computed, ref, watch } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { generarEnlace, listarEnlaces, revocarEnlace } from '../api/portal'
import MensajeError from './MensajeError.vue'
import { fechaHora } from '../formato'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  periodoId: { type: Number, required: true },
  anioGravable: { type: Number, required: true },
  cerrado: { type: Boolean, default: false },
})

const enlaces = ref([])
const error = ref('')
const generando = ref(false)
const recienCreado = ref(null)
const copiado = ref(false)
const dias = ref(30)
const nota = ref('')

const delPeriodo = computed(() =>
  enlaces.value.filter((e) => e.periodo_fiscal_id === props.periodoId),
)
const vigente = computed(() => delPeriodo.value.find((e) => e.vigente) ?? null)

const direccionCompleta = computed(() =>
  recienCreado.value ? `${window.location.origin}${recienCreado.value.ruta}` : '',
)

async function cargar() {
  error.value = ''
  recienCreado.value = null
  try {
    enlaces.value = await listarEnlaces(props.contribuyenteId)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function generar() {
  error.value = ''
  copiado.value = false
  generando.value = true
  try {
    recienCreado.value = await generarEnlace(props.contribuyenteId, {
      periodo_fiscal_id: props.periodoId,
      dias_vigencia: Number(dias.value),
      nota: nota.value || null,
    })
    enlaces.value = await listarEnlaces(props.contribuyenteId)
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    generando.value = false
  }
}

async function revocar(enlace) {
  error.value = ''
  try {
    await revocarEnlace(props.contribuyenteId, enlace.id)
    if (recienCreado.value?.id === enlace.id) recienCreado.value = null
    enlaces.value = await listarEnlaces(props.contribuyenteId)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function copiar() {
  try {
    await navigator.clipboard.writeText(direccionCompleta.value)
    copiado.value = true
  } catch {
    copiado.value = false
  }
}

watch(() => [props.contribuyenteId, props.periodoId], cargar, { immediate: true })
</script>

<template>
  <section class="hoja space-y-4 p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2>Enlace de carga del contribuyente</h2>
        <p class="mt-1 max-w-prose text-sm text-tinta-suave">
          Un enlace para que el contribuyente cargue su exógena y sus soportes desde el celular,
          sin crear una cuenta. Solo escribe sobre el año {{ anioGravable }} y no muestra la
          liquidación.
        </p>
      </div>
      <p v-if="vigente" class="rounded-full bg-libro-claro px-3 py-1 text-xs font-semibold text-estado-coincide">
        Enlace activo
      </p>
      <p v-else class="rounded-full bg-estado-noreportado-claro px-3 py-1 text-xs font-semibold text-estado-noreportado">
        Sin enlace activo
      </p>
    </div>

    <MensajeError :mensaje="error" />

    <!-- El token, la única vez que se puede ver. -->
    <div v-if="recienCreado" class="rounded border border-libro bg-libro-claro p-4">
      <p class="text-sm font-semibold">Cópialo ahora: no se puede volver a ver.</p>
      <p class="mt-1 text-xs text-tinta-suave">
        De este enlace solo guardamos su huella, así que ni la aplicación puede recuperarlo. Si se
        pierde, genera otro (eso revoca este).
      </p>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <input
          :value="direccionCompleta"
          readonly
          class="campo flex-1 min-w-0 font-mono text-xs"
          aria-label="Dirección del enlace de carga"
          @focus="$event.target.select()"
        />
        <button type="button" class="boton" @click="copiar">
          {{ copiado ? 'Copiado' : 'Copiar' }}
        </button>
      </div>
      <p class="mt-2 text-xs text-tinta-suave">
        Vence el {{ fechaHora(recienCreado.expira_en) }}.
      </p>
    </div>

    <form v-if="!cerrado" class="flex flex-wrap items-end gap-3" @submit.prevent="generar">
      <div>
        <label class="etiqueta" for="enlace-dias">Días de vigencia</label>
        <input id="enlace-dias" v-model="dias" type="number" min="1" max="180" class="campo w-28" />
      </div>
      <div class="min-w-48 flex-1">
        <label class="etiqueta" for="enlace-nota">Nota interna (opcional)</label>
        <input id="enlace-nota" v-model="nota" class="campo" maxlength="200" placeholder="Para recordar a quién se lo enviaste" />
      </div>
      <button type="submit" class="boton" :disabled="generando">
        {{ vigente ? 'Generar uno nuevo' : 'Generar enlace' }}
      </button>
    </form>
    <p v-else class="text-sm text-tinta-suave">
      El año {{ anioGravable }} está cerrado: no se generan enlaces nuevos.
    </p>

    <div v-if="delPeriodo.length" class="overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Enlace</th>
            <th>Generado</th>
            <th>Vence</th>
            <th>Última vez que entró</th>
            <th>Política</th>
            <th><span class="sr-only">Acciones</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in delPeriodo" :key="e.id">
            <td>
              <span class="font-mono text-xs">{{ e.prefijo }}…</span>
              <p v-if="e.nota" class="text-xs text-tinta-tenue">{{ e.nota }}</p>
              <p v-if="!e.vigente" class="text-xs text-tinta-tenue">
                {{ e.revocado_en ? 'Revocado' : 'Vencido' }}
              </p>
            </td>
            <td class="text-sm">{{ fechaHora(e.creado_en) }}</td>
            <td class="text-sm">{{ fechaHora(e.expira_en) }}</td>
            <td class="text-sm">
              {{ e.ultimo_acceso_en ? fechaHora(e.ultimo_acceso_en) : '—' }}
            </td>
            <td class="text-sm">
              <template v-if="e.politica_aceptada">
                Aceptada {{ fechaHora(e.politica_aceptada_en) }}
                <p class="text-xs text-tinta-tenue">Versión {{ e.version_politica_aceptada }}</p>
              </template>
              <span v-else class="text-tinta-tenue">Sin aceptar</span>
            </td>
            <td class="text-right">
              <button
                v-if="e.vigente"
                type="button"
                class="whitespace-nowrap text-sm text-estado-nodeclarado underline"
                @click="revocar(e)"
              >
                Revocar
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

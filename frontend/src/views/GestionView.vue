<script setup>
// Gestión: etapas, documentos, presentación, comparativo, firmeza e intereses.
import { onMounted, ref, watch } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { actualizarSeguimiento, descargarInforme, obtenerGestion } from '../api/gestion'
import Cargando from '../components/Cargando.vue'
import MensajeError from '../components/MensajeError.vue'
import AnioAnterior from '../components/gestion/AnioAnterior.vue'
import FirmezaBeneficio from '../components/gestion/FirmezaBeneficio.vue'
import PagoIntereses from '../components/gestion/PagoIntereses.vue'
import PresentacionCorreccion from '../components/gestion/PresentacionCorreccion.vue'
import ProcesoDeclaracion from '../components/gestion/ProcesoDeclaracion.vue'
import SolicitudDocumentos from '../components/gestion/SolicitudDocumentos.vue'
import { useContribuyente } from '../contexto'

const { contribuyente, periodo, recargarPeriodos } = useContribuyente()
const cid = contribuyente.value.id

const gestion = ref(null)
const error = ref('')
const descargando = ref(false)

async function cargar(fechaPago) {
  error.value = ''
  try {
    gestion.value = await obtenerGestion(cid, periodo.value.id, fechaPago)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function guardarSeguimiento(cambios) {
  error.value = ''
  try {
    gestion.value = await actualizarSeguimiento(cid, periodo.value.id, cambios)
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

async function trasPresentar() {
  await recargarPeriodos()
  await cargar()
}

async function informe() {
  descargando.value = true
  try {
    await descargarInforme(cid, periodo.value.id)
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    descargando.value = false
  }
}

onMounted(() => cargar())
watch(() => periodo.value?.id, () => cargar())
</script>

<template>
  <MensajeError :mensaje="error" />
  <Cargando v-if="!gestion && !error" />
  <div v-if="gestion" class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <div class="space-y-6">
      <ProcesoDeclaracion :gestion="gestion" @marcar="guardarSeguimiento" />
      <section class="hoja space-y-2 p-5">
        <h2>Informe para el cliente</h2>
        <p class="text-sm text-tinta-suave">
          PDF en lenguaje del contribuyente: cuánto paga y hasta cuándo, de dónde sale la cifra,
          lo que la DIAN tiene reportado y los documentos que faltan.
        </p>
        <button type="button" class="boton w-full" :disabled="descargando" @click="informe">Descargar informe</button>
      </section>
      <FirmezaBeneficio :gestion="gestion" />
    </div>

    <div class="space-y-6">
      <ul v-if="gestion.avisos.length" class="space-y-1">
        <li v-for="a in gestion.avisos" :key="a" class="rounded bg-estado-discrepancia-claro px-4 py-2 text-sm">{{ a }}</li>
      </ul>
      <SolicitudDocumentos :contribuyente-id="cid" :periodo-id="periodo.id" @cambio="cargar()" />
      <AnioAnterior :gestion="gestion" :contribuyente-id="cid" :periodo-id="periodo.id" @cambio="cargar()" />
      <PresentacionCorreccion :gestion="gestion" :contribuyente-id="cid" :periodo-id="periodo.id" @cambio="trasPresentar" />
      <PagoIntereses :gestion="gestion" @guardar="guardarSeguimiento" @simular="cargar" />
    </div>
  </div>
</template>

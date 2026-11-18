<script setup>
// Registrar lo presentado (una copia de la liquidación) y, si después cambia
// algo, ver qué cuesta corregir.
import { reactive, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { registrarPresentacion } from '../../api/gestion'
import { dinero, fecha } from '../../formato'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  gestion: { type: Object, required: true },
  contribuyenteId: { type: Number, required: true },
  periodoId: { type: Number, required: true },
})
const emit = defineEmits(['cambio'])

function hoyIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const form = reactive({ abierto: false, fecha_presentacion: hoyIso(), numero_formulario: '' })
const error = ref('')

async function registrar() {
  error.value = ''
  try {
    await registrarPresentacion(props.contribuyenteId, props.periodoId, {
      fecha_presentacion: form.fecha_presentacion,
      numero_formulario: form.numero_formulario || null,
    })
    form.abierto = false
    emit('cambio')
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

const TIPO = {
  AUMENTA: 'La liquidación de hoy da más impuesto (o menos saldo a favor) que lo presentado',
  DISMINUYE: 'La liquidación de hoy da menos impuesto (o más saldo a favor) que lo presentado',
  SIN_EFECTO: 'La liquidación cambió sin mover el valor a pagar ni el saldo a favor',
}
</script>

<template>
  <section class="hoja p-5">
    <h2>Presentación</h2>
    <MensajeError :mensaje="error" />

    <ul v-if="gestion.presentaciones.length" class="mt-3 space-y-1 text-sm">
      <li v-for="p in gestion.presentaciones" :key="p.id" class="flex flex-wrap justify-between gap-2">
        <span>{{ p.es_correccion ? 'Corrección' : 'Declaración inicial' }} · {{ fecha(p.fecha_presentacion) }}
          <template v-if="p.numero_formulario"> · formulario {{ p.numero_formulario }}</template></span>
        <span class="cifra">{{ p.casillas[136] > 0 ? `A pagar ${dinero(p.casillas[136])}` : p.casillas[137] > 0 ? `A favor ${dinero(p.casillas[137])}` : 'Sin saldo' }}</span>
      </li>
    </ul>
    <p v-else-if="gestion.fecha_presentacion" class="mt-2 rounded bg-estado-discrepancia-claro p-3 text-sm">
      La fecha de presentación ({{ fecha(gestion.fecha_presentacion) }}) se registró sin guardar lo que se
      presentó. Regístrela aquí con la misma fecha para poder detectar correcciones y compararla el año siguiente.
    </p>
    <p v-else class="mt-1 text-sm text-tinta-suave">
      Al registrar la presentación se guarda una copia de la liquidación de hoy, casilla por casilla.
      Esa copia es la base para detectar correcciones y para el comparativo del año siguiente.
    </p>

    <div v-if="gestion.correccion" class="mt-4 rounded bg-estado-discrepancia-claro p-4 text-sm">
      <p class="font-semibold">{{ TIPO[gestion.correccion.tipo] }}</p>
      <dl class="mt-2 space-y-1">
        <div class="flex justify-between"><dt>Mayor valor frente a lo presentado</dt><dd class="cifra">{{ dinero(gestion.correccion.mayor_valor) }}</dd></div>
        <div v-if="gestion.correccion.tipo === 'AUMENTA'" class="flex justify-between"><dt>Sanción por corrección</dt><dd class="cifra">{{ dinero(gestion.correccion.sancion) }}</dd></div>
        <div v-if="gestion.correccion.intereses" class="flex justify-between"><dt>Intereses de mora sobre el mayor impuesto, a hoy</dt><dd class="cifra">{{ dinero(gestion.correccion.intereses.valor) }}</dd></div>
        <div v-if="gestion.correccion.tipo === 'AUMENTA'" class="flex justify-between font-semibold"><dt>Total a pagar con la corrección</dt><dd class="cifra">{{ dinero(gestion.correccion.total_a_pagar) }}</dd></div>
        <div class="flex justify-between"><dt>Plazo para corregir</dt><dd>{{ fecha(gestion.correccion.plazo) }}<span v-if="gestion.correccion.vencida" class="text-estado-nodeclarado"> (vencido)</span></dd></div>
      </dl>
      <p class="mt-2 text-tinta-suave">{{ gestion.correccion.formula }} — {{ gestion.correccion.fuente }}</p>
      <p v-for="n in gestion.correccion.notas" :key="n" class="mt-1 text-tinta-suave">{{ n }}</p>
      <p v-if="gestion.correccion.intereses?.meses_sin_tasa.length" class="mt-1 text-estado-nodeclarado">
        Faltan tasas de mora de {{ gestion.correccion.intereses.meses_sin_tasa.join(', ') }}: los intereses están incompletos.
      </p>
    </div>

    <div class="mt-4">
      <button v-if="!form.abierto" type="button" :class="gestion.presentaciones.length ? 'boton-secundario' : 'boton'" @click="form.abierto = true">
        {{ gestion.presentaciones.length ? 'Registrar una corrección presentada' : 'Registrar la presentación' }}
      </button>
      <form v-else class="grid gap-2 sm:grid-cols-[12rem_1fr_auto]" @submit.prevent="registrar">
        <input v-model="form.fecha_presentacion" type="date" class="campo" required aria-label="Fecha de presentación" />
        <input v-model="form.numero_formulario" class="campo" placeholder="Número de formulario (opcional)" />
        <button class="boton">Guardar</button>
      </form>
    </div>
  </section>
</template>

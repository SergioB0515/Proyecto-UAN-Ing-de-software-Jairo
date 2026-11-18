<script setup>
// Pago, devolución, emplazamiento e intereses de mora.
import { reactive, watch } from 'vue'

import { dinero, fecha } from '../../formato'

const props = defineProps({ gestion: { type: Object, required: true } })
const emit = defineEmits(['guardar', 'simular'])

const form = reactive({})
watch(() => props.gestion, (g) => Object.assign(form, {
  pagada_en: g.seguimiento.pagada_en || '',
  valor_pagado: g.seguimiento.valor_pagado ?? '',
  solicitud_devolucion_en: g.seguimiento.solicitud_devolucion_en || '',
  emplazamiento_notificado: g.seguimiento.emplazamiento_notificado,
  fecha_simulada: '',
}), { immediate: true })

function guardar() {
  emit('guardar', {
    pagada_en: form.pagada_en || null,
    valor_pagado: form.valor_pagado === '' ? null : form.valor_pagado,
    solicitud_devolucion_en: form.solicitud_devolucion_en || null,
    emplazamiento_notificado: form.emplazamiento_notificado,
  })
}
</script>

<template>
  <section class="hoja space-y-4 p-5">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2>Pago</h2>
      <p class="text-sm">
        <template v-if="gestion.saldo_a_pagar > 0">A pagar <span class="cifra font-semibold">{{ dinero(gestion.saldo_a_pagar) }}</span></template>
        <template v-else-if="gestion.saldo_a_favor > 0">Saldo a favor <span class="cifra font-semibold">{{ dinero(gestion.saldo_a_favor) }}</span></template>
        <template v-else>Sin saldo</template>
        <template v-if="gestion.vencimiento"> · {{ gestion.intereses && !gestion.seguimiento.pagada_en ? 'venció' : 'vence' }} {{ fecha(gestion.vencimiento) }}</template>
      </p>
    </div>

    <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="guardar">
      <label><span class="etiqueta">Fecha de pago</span><input v-model="form.pagada_en" type="date" class="campo" /></label>
      <label><span class="etiqueta">Valor pagado</span><input v-model.number="form.valor_pagado" type="number" min="0" step="1000" class="campo" /></label>
      <label v-if="gestion.saldo_a_favor > 0"><span class="etiqueta">Solicitud de devolución o compensación</span>
        <input v-model="form.solicitud_devolucion_en" type="date" class="campo" /></label>
      <label class="flex items-center gap-2 self-end text-sm">
        <input v-model="form.emplazamiento_notificado" type="checkbox" /> La DIAN notificó emplazamiento para corregir
      </label>
      <div class="sm:col-span-2"><button class="boton">Guardar</button></div>
    </form>

    <div v-if="gestion.saldo_a_pagar > 0 && !gestion.seguimiento.pagada_en" class="border-t border-papel-hondo pt-4">
      <p class="text-sm font-medium">¿Cuánto costaría pagar en otra fecha?</p>
      <div class="mt-2 flex gap-2">
        <input v-model="form.fecha_simulada" type="date" class="campo w-auto" aria-label="Fecha de pago simulada" />
        <button type="button" class="boton-secundario" :disabled="!form.fecha_simulada" @click="emit('simular', form.fecha_simulada)">Calcular</button>
      </div>
    </div>

    <div v-if="gestion.intereses" class="rounded bg-papel-hondo p-4 text-sm">
      <p class="font-semibold">
        Intereses de mora {{ gestion.intereses.pagado ? 'causados' : `si paga el ${fecha(gestion.intereses.fecha_pago)}` }}:
        <span class="cifra">{{ dinero(gestion.intereses.valor) }}</span>
      </p>
      <p class="text-tinta-suave">{{ gestion.intereses.dias }} días sobre {{ dinero(gestion.intereses.capital) }} de impuesto.</p>
      <table class="mt-2 w-full text-xs">
        <tbody>
          <tr v-for="t in gestion.intereses.tramos" :key="t.desde">
            <td class="py-0.5">{{ fecha(t.desde) }} – {{ fecha(t.hasta) }}</td>
            <td class="text-right">{{ t.dias }} días</td>
            <td class="text-right">{{ Number(t.tasa_efectiva_anual).toLocaleString('es-CO') }} % E.A.</td>
            <td class="cifra text-right">{{ dinero(t.interes) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="gestion.intereses.meses_sin_tasa.length" class="mt-2 text-estado-nodeclarado">
        Falta la tasa de {{ gestion.intereses.meses_sin_tasa.join(', ') }}: cárguela en Parámetros DIAN.
      </p>
      <p class="mt-2 text-xs text-tinta-tenue">{{ gestion.intereses.formula }} · {{ gestion.intereses.fuente }}</p>
    </div>
  </section>
</template>

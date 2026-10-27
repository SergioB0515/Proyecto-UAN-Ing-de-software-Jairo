<script setup>
import { computed } from 'vue'

import { fecha } from '../formato'

const props = defineProps({
  vencimiento: { type: Object, default: null },
  compacto: { type: Boolean, default: false },
})

const ESTADOS = {
  VENCIDA: { texto: 'Vencida', clase: 'bg-estado-nodeclarado-claro text-estado-nodeclarado', marca: '▲' },
  PROXIMA: { texto: 'Próxima a vencer', clase: 'bg-estado-discrepancia-claro text-estado-discrepancia', marca: '◆' },
  PENDIENTE: { texto: 'Pendiente', clase: 'bg-estado-noreportado-claro text-estado-noreportado', marca: '○' },
  PRESENTADA: { texto: 'Presentada', clase: 'bg-libro-claro text-estado-coincide', marca: '●' },
  SIN_FECHA: { texto: 'Sin fecha límite', clase: 'bg-papel-hondo text-tinta-suave', marca: '–' },
}

const info = computed(() => ESTADOS[props.vencimiento?.estado] ?? ESTADOS.SIN_FECHA)

const detalle = computed(() => {
  const v = props.vencimiento
  if (!v) return ''
  if (v.estado === 'PRESENTADA') return v.fecha_presentacion ? `el ${fecha(v.fecha_presentacion)}` : ''
  if (!v.fecha) return ''
  const dias = v.dias_restantes
  const cuando = dias === 0 ? 'hoy' : dias === 1 ? 'mañana' : dias > 0 ? `en ${dias} días` : `hace ${-dias} días`
  return `${fecha(v.fecha)} (${cuando})`
})
</script>

<template>
  <span class="inline-flex flex-col gap-0.5">
    <span class="inline-flex w-fit items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="info.clase">
      <span aria-hidden="true">{{ info.marca }}</span>{{ info.texto }}
    </span>
    <span v-if="detalle" class="whitespace-nowrap text-xs text-tinta-suave">{{ detalle }}</span>
    <span v-if="!compacto && vencimiento?.origen === 'MANUAL'" class="text-xs text-tinta-tenue">Fecha especial registrada a mano</span>
  </span>
</template>

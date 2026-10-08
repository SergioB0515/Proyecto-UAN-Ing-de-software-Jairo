<script setup>
import { computed } from 'vue'

const props = defineProps({ estado: { type: String, required: true } })

const ESTADOS = {
  COINCIDE: { texto: 'Coincide', clase: 'bg-libro-claro text-estado-coincide', marca: '●' },
  DISCREPANCIA: {
    texto: 'Discrepancia',
    clase: 'bg-estado-discrepancia-claro text-estado-discrepancia',
    marca: '◆',
  },
  NO_DECLARADO: {
    texto: 'No declarado',
    clase: 'bg-estado-nodeclarado-claro text-estado-nodeclarado',
    marca: '▲',
  },
  NO_REPORTADO_POR_TERCERO: {
    texto: 'Sin reporte de terceros',
    clase: 'bg-estado-noreportado-claro text-estado-noreportado',
    marca: '○',
  },
}

const info = computed(() => ESTADOS[props.estado] ?? { texto: props.estado, clase: '', marca: '' })
</script>

<template>
  <!-- La marca de forma acompaña al color para que el estado no dependa solo de él. -->
  <span class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="info.clase">
    <span aria-hidden="true">{{ info.marca }}</span>{{ info.texto }}
  </span>
</template>

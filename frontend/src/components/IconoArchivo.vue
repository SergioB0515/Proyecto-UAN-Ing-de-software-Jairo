<script setup>
import { computed } from 'vue'

const props = defineProps({ tipoMime: { type: String, default: '' } })

const clase = computed(() => {
  if (props.tipoMime === 'application/pdf') return 'text-estado-nodeclarado'
  if (props.tipoMime.startsWith('image/')) return 'text-libro'
  if (props.tipoMime.includes('spreadsheet') || props.tipoMime === 'text/csv') return 'text-estado-coincide'
  return 'text-tinta-suave'
})

const rotulo = computed(() => {
  if (props.tipoMime === 'application/pdf') return 'PDF'
  if (props.tipoMime.startsWith('image/')) return 'IMG'
  if (props.tipoMime.includes('spreadsheet')) return 'XLS'
  if (props.tipoMime.includes('wordprocessing')) return 'DOC'
  if (props.tipoMime === 'text/csv') return 'CSV'
  return 'TXT'
})
</script>

<template>
  <span
    class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded border border-papel-linea bg-papel text-[10px] font-bold tracking-wide"
    :class="clase"
    aria-hidden="true"
  >
    {{ rotulo }}
  </span>
</template>

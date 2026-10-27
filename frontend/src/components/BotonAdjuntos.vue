<script setup>
defineProps({
  total: { type: Number, default: 0 },
  abierto: { type: Boolean, default: false },
  etiqueta: { type: String, required: true },
  destacarFalta: { type: Boolean, default: false },
})
defineEmits(['alternar'])
</script>

<template>
  <button
    type="button"
    class="inline-flex items-center gap-1.5 whitespace-nowrap rounded px-2 py-1 text-sm hover:bg-papel-hondo"
    :class="[
      total ? 'font-medium text-libro' : destacarFalta ? 'text-estado-discrepancia' : 'text-tinta-suave',
      abierto ? 'bg-papel-hondo' : '',
    ]"
    :aria-expanded="abierto"
    :aria-label="`Soportes de ${etiqueta}: ${total}`"
    @click="$emit('alternar')"
  >
    <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M21 11.5 12.5 20a5.5 5.5 0 0 1-7.8-7.8l8.5-8.5a3.7 3.7 0 0 1 5.2 5.2l-8.5 8.5a1.8 1.8 0 0 1-2.6-2.6l7.8-7.8" />
    </svg>
    <span v-if="total">{{ total }}</span>
    <span v-else-if="destacarFalta">Sin soporte</span>
    <span v-else>Adjuntar</span>
  </button>
</template>

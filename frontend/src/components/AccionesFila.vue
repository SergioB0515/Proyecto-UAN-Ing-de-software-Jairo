<script setup>
// Editar / Eliminar al final de una fila, con confirmación en la misma
// fila (sin diálogos del navegador).
import { ref } from 'vue'

defineProps({ etiqueta: { type: String, required: true } })
const emit = defineEmits(['editar', 'eliminar'])
const confirmando = ref(false)

function confirmar() {
  confirmando.value = false
  emit('eliminar')
}
</script>

<template>
  <span v-if="!confirmando" class="flex justify-end gap-3 whitespace-nowrap text-sm">
    <button type="button" class="text-tinta-suave underline hover:text-tinta" :aria-label="`Editar ${etiqueta}`" @click="emit('editar')">
      Editar
    </button>
    <button
      type="button"
      class="text-tinta-suave underline hover:text-estado-nodeclarado"
      :aria-label="`Eliminar ${etiqueta}`"
      @click="confirmando = true"
    >
      Eliminar
    </button>
  </span>
  <span v-else class="flex items-center justify-end gap-3 whitespace-nowrap text-sm" role="group" :aria-label="`Confirmar eliminación de ${etiqueta}`">
    <span class="font-medium">¿Eliminar?</span>
    <button type="button" class="font-semibold text-estado-nodeclarado underline" @click="confirmar">Sí, eliminar</button>
    <button type="button" class="text-tinta-suave underline" @click="confirmando = false">No</button>
  </span>
</template>

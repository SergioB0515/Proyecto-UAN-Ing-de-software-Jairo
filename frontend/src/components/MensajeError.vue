<script setup>
defineProps({ mensaje: { type: String, default: '' } })
</script>

<template>
  <p
    v-if="mensaje"
    role="alert"
    class="rounded border-l-4 border-estado-nodeclarado bg-estado-nodeclarado-claro px-4 py-3 text-sm text-estado-nodeclarado"
  >
    {{ mensaje }}
  </p>
</template>

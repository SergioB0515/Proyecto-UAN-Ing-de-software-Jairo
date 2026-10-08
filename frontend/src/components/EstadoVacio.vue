<script setup>
defineProps({ titulo: { type: String, required: true } })
</script>

<template>
  <div class="rounded-md border border-dashed border-papel-linea bg-white/60 px-6 py-10 text-center">
    <p class="font-medium">{{ titulo }}</p>
    <div class="mx-auto mt-1 max-w-prose text-sm text-tinta-suave"><slot /></div>
  </div>
</template>

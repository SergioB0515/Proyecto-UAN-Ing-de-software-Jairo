<script setup>
import { useRoute, useRouter } from 'vue-router'

import { cerrarSesion, sesion } from './sesion'

const route = useRoute()
const router = useRouter()

const navegacion = [
  { nombre: 'cartera', texto: 'Cartera' },
  { nombre: 'contribuyentes', texto: 'Contribuyentes' },
  { nombre: 'umbrales', texto: 'Umbrales UVT' },
]

function salir() {
  cerrarSesion()
  router.push({ name: 'login' })
}

function estaActiva(nombre) {
  if (nombre === 'contribuyentes') return route.path.startsWith('/contribuyentes')
  return route.name === nombre
}
</script>

<template>
  <RouterView v-if="route.meta.publica" />
  <div v-else class="min-h-screen md:grid md:grid-cols-[13.5rem_1fr]">
    <aside class="flex flex-col bg-tinta text-papel md:sticky md:top-0 md:h-screen">
      <div class="flex items-center gap-3 px-5 py-5">
        <img src="/favicon.svg" alt="" class="h-7 w-7" />
        <span class="font-semibold leading-tight">Conciliación<br />de renta</span>
      </div>
      <nav class="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0" aria-label="Principal">
        <RouterLink
          v-for="item in navegacion"
          :key="item.nombre"
          :to="{ name: item.nombre }"
          class="whitespace-nowrap rounded px-3 py-2 text-sm transition-colors"
          :class="estaActiva(item.nombre) ? 'bg-white/10 font-semibold text-white' : 'text-papel/75 hover:text-white'"
        >
          {{ item.texto }}
        </RouterLink>
      </nav>
      <div class="mt-auto hidden border-t border-white/10 px-5 py-4 text-sm md:block">
        <p class="font-medium text-white">{{ sesion.contador?.nombre }}</p>
        <p class="truncate text-papel/60">{{ sesion.contador?.email }}</p>
        <button type="button" class="mt-3 text-papel/80 underline underline-offset-2 hover:text-white" @click="salir">
          Cerrar sesión
        </button>
      </div>
    </aside>
    <main class="min-w-0 px-4 py-6 sm:px-8 sm:py-8">
      <RouterView />
      <button type="button" class="mt-10 text-sm text-tinta-suave underline md:hidden" @click="salir">
        Cerrar sesión
      </button>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { mensajeDeError } from '../api/cliente'
import { iniciarSesion, obtenerContadorActual, registrarContador } from '../api/contadores'
import MensajeError from '../components/MensajeError.vue'
import { guardarToken, sesion } from '../sesion'

const route = useRoute()
const router = useRouter()

const modo = ref('ingresar') // 'ingresar' | 'registrarse'
const nombre = ref('')
const email = ref('')
const contrasena = ref('')
const error = ref('')
const enviando = ref(false)

async function enviar() {
  error.value = ''
  enviando.value = true
  try {
    if (modo.value === 'registrarse') {
      await registrarContador({ nombre: nombre.value, email: email.value, contrasena: contrasena.value })
    }
    guardarToken(await iniciarSesion(email.value, contrasena.value))
    sesion.contador = await obtenerContadorActual()
    router.push(route.query.siguiente || { name: 'cartera' })
  } catch (e) {
    error.value = mensajeDeError(e)
  } finally {
    enviando.value = false
  }
}

function cambiarModo() {
  modo.value = modo.value === 'ingresar' ? 'registrarse' : 'ingresar'
  error.value = ''
}
</script>

<template>
  <div class="grid min-h-screen lg:grid-cols-[1fr_28rem]">
    <section class="hidden flex-col justify-between bg-tinta p-12 text-papel lg:flex">
      <div class="flex items-center gap-3">
        <img src="/favicon.svg" alt="" class="h-8 w-8" />
        <span class="font-semibold">Conciliación de renta</span>
      </div>
      <div class="max-w-lg">
        <p class="text-3xl font-semibold leading-snug text-white">
          Lo que tus clientes declaran, frente a lo que terceros le reportaron a la DIAN.
        </p>
        <!-- Muestra del cruce que hace la aplicación: el centro del producto. -->
        <table class="mt-10 text-sm text-papel/90" aria-label="Ejemplo de conciliación">
          <thead>
            <tr>
              <th class="border-white/15 px-0 text-papel/60">Concepto</th>
              <th class="cifra border-white/15 text-papel/60">Declarado</th>
              <th class="cifra border-white/15 text-papel/60">Exógena</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="border-white/10 px-0">Apartamento</td>
              <td class="cifra border-white/10">$120.000.000</td>
              <td class="cifra border-white/10">$120.000.000</td>
            </tr>
            <tr>
              <td class="border-white/10 px-0">Cuenta de ahorros</td>
              <td class="cifra border-white/10">$3.500.000</td>
              <td class="cifra border-white/10 text-[#E8B46A]">$3.000.000</td>
            </tr>
            <tr>
              <td class="border-white/10 px-0">CDT Banco</td>
              <td class="cifra border-white/10 text-papel/40">—</td>
              <td class="cifra border-white/10 text-[#F2998F]">$15.000.000</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-sm text-papel/60">Proyecto de Ingeniería de Software — UAN</p>
    </section>

    <section class="flex items-center justify-center px-4 py-12 sm:px-10">
      <form class="w-full max-w-sm space-y-5" @submit.prevent="enviar">
        <div>
          <h1>{{ modo === 'ingresar' ? 'Ingresar' : 'Crear cuenta de contador' }}</h1>
          <p v-if="route.query.expirada" class="mt-2 text-sm text-tinta-suave">
            La sesión expiró. Vuelve a ingresar.
          </p>
        </div>

        <div v-if="modo === 'registrarse'">
          <label class="etiqueta" for="nombre">Nombre</label>
          <input id="nombre" v-model="nombre" class="campo" required autocomplete="name" />
        </div>
        <div>
          <label class="etiqueta" for="email">Correo electrónico</label>
          <input id="email" v-model="email" type="email" class="campo" required autocomplete="email" />
        </div>
        <div>
          <label class="etiqueta" for="contrasena">Contraseña</label>
          <input
            id="contrasena"
            v-model="contrasena"
            type="password"
            class="campo"
            required
            :minlength="modo === 'registrarse' ? 8 : undefined"
            :autocomplete="modo === 'ingresar' ? 'current-password' : 'new-password'"
          />
          <p v-if="modo === 'registrarse'" class="mt-1 text-xs text-tinta-tenue">Mínimo 8 caracteres, con letras y números.</p>
        </div>

        <MensajeError :mensaje="error" />

        <button type="submit" class="boton w-full" :disabled="enviando">
          {{ enviando ? 'Un momento…' : modo === 'ingresar' ? 'Ingresar' : 'Crear cuenta' }}
        </button>

        <p class="text-center text-sm text-tinta-suave">
          {{ modo === 'ingresar' ? '¿No tienes cuenta?' : '¿Ya tienes cuenta?' }}
          <button type="button" class="enlace" @click="cambiarModo">
            {{ modo === 'ingresar' ? 'Crear una' : 'Ingresar' }}
          </button>
        </p>
      </form>
    </section>
  </div>
</template>

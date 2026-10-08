<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { listarAccesos } from '../api/auditoria'
import { mensajeDeError } from '../api/cliente'
import { cambiarContrasena } from '../api/contadores'
import MensajeError from '../components/MensajeError.vue'
import { sesion } from '../sesion'

const accesos = ref([])
const errorAccesos = ref('')
const form = reactive({ actual: '', nueva: '', confirmacion: '', error: '', listo: false, guardando: false })

const RESULTADOS = {
  EXITOSO: { texto: 'Ingreso correcto', clase: 'text-libro' },
  FALLIDO: { texto: 'Contraseña incorrecta', clase: 'text-estado-discrepancia' },
  BLOQUEADO: { texto: 'Rechazado por bloqueo', clase: 'text-estado-nodeclarado' },
}

// Fallos desde el último ingreso correcto: si los hay, alguien (quizá tú)
// intentó entrar con una contraseña equivocada.
const fallosRecientes = computed(() => {
  const indice = accesos.value.findIndex((a) => a.resultado === 'EXITOSO')
  // El primero exitoso es la sesión actual; se cuentan los fallos anteriores a ella.
  const antes = accesos.value.slice(indice + 1)
  const siguienteExito = antes.findIndex((a) => a.resultado === 'EXITOSO')
  return (siguienteExito === -1 ? antes : antes.slice(0, siguienteExito)).filter((a) => a.resultado !== 'EXITOSO').length
})

function fechaHora(valor) {
  return new Date(valor).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' })
}

async function guardar() {
  form.error = ''
  form.listo = false
  if (form.nueva !== form.confirmacion) {
    form.error = 'La contraseña nueva y su confirmación no coinciden.'
    return
  }
  form.guardando = true
  try {
    await cambiarContrasena(form.actual, form.nueva)
    Object.assign(form, { actual: '', nueva: '', confirmacion: '', listo: true })
  } catch (e) {
    form.error = mensajeDeError(e)
  } finally {
    form.guardando = false
  }
}

onMounted(async () => {
  try {
    accesos.value = await listarAccesos()
  } catch (e) {
    errorAccesos.value = mensajeDeError(e)
  }
})
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <header>
      <h1>Mi cuenta</h1>
      <p class="text-tinta-suave">{{ sesion.contador?.nombre }}, {{ sesion.contador?.email }}</p>
    </header>

    <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
      <form class="hoja h-fit space-y-3 p-5" @submit.prevent="guardar">
        <h2>Cambiar contraseña</h2>
        <div>
          <label class="etiqueta" for="c-actual">Contraseña actual</label>
          <input id="c-actual" v-model="form.actual" type="password" class="campo" required autocomplete="current-password" />
        </div>
        <div>
          <label class="etiqueta" for="c-nueva">Contraseña nueva</label>
          <input id="c-nueva" v-model="form.nueva" type="password" class="campo" required minlength="8" autocomplete="new-password" />
          <p class="mt-1 text-xs text-tinta-tenue">Mínimo 8 caracteres, con letras y números.</p>
        </div>
        <div>
          <label class="etiqueta" for="c-confirmacion">Repite la contraseña nueva</label>
          <input id="c-confirmacion" v-model="form.confirmacion" type="password" class="campo" required autocomplete="new-password" />
        </div>
        <MensajeError :mensaje="form.error" />
        <p v-if="form.listo" class="text-sm text-libro" role="status">Contraseña cambiada.</p>
        <button type="submit" class="boton" :disabled="form.guardando">Cambiar contraseña</button>
      </form>

      <section class="space-y-3">
        <h2>Accesos a tu cuenta</h2>
        <p
          v-if="fallosRecientes"
          class="rounded border-l-4 border-estado-discrepancia bg-estado-discrepancia-claro px-4 py-3 text-sm"
        >
          Antes de este ingreso hubo {{ fallosRecientes }} intento(s) fallido(s). Si no fuiste tú, cambia tu
          contraseña. Tras 5 fallos seguidos la cuenta se bloquea 15 minutos.
        </p>
        <MensajeError :mensaje="errorAccesos" />
        <div class="hoja overflow-x-auto">
          <table>
            <thead>
              <tr><th>Fecha</th><th>Resultado</th><th>Dirección IP</th></tr>
            </thead>
            <tbody>
              <tr v-for="(a, i) in accesos" :key="i">
                <td>{{ fechaHora(a.fecha) }}</td>
                <td :class="RESULTADOS[a.resultado].clase">{{ RESULTADOS[a.resultado].texto }}</td>
                <td class="text-tinta-suave">{{ a.ip ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

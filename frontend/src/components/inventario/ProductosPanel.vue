<script setup>
import { computed, reactive, ref } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { actualizarProducto, crearCategoria, crearProducto, eliminarCategoria } from '../../api/inventario'
import { cantidad } from '../../formato'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  productos: { type: Array, required: true },
  categorias: { type: Array, required: true },
})
const emit = defineEmits(['cambio'])

const nombreCategoria = computed(() => Object.fromEntries(props.categorias.map((c) => [c.id, c.nombre])))

const formCategoria = reactive({ nombre: '', error: '' })
const formProducto = reactive({
  abierto: false,
  error: '',
  datos: { codigo: '', nombre: '', clasificacion_iva: 'GRAVADO', metodo_costeo: 'PEPS', categoria_id: null },
})
const errorLista = ref('')

async function agregarCategoria() {
  formCategoria.error = ''
  try {
    await crearCategoria(props.contribuyenteId, { nombre: formCategoria.nombre })
    formCategoria.nombre = ''
    emit('cambio')
  } catch (e) {
    formCategoria.error = mensajeDeError(e)
  }
}

async function quitarCategoria(categoria) {
  errorLista.value = ''
  try {
    await eliminarCategoria(props.contribuyenteId, categoria.id)
    emit('cambio')
  } catch (e) {
    errorLista.value = mensajeDeError(e)
  }
}

async function agregarProducto() {
  formProducto.error = ''
  try {
    await crearProducto(props.contribuyenteId, { ...formProducto.datos })
    formProducto.datos = { codigo: '', nombre: '', clasificacion_iva: 'GRAVADO', metodo_costeo: 'PEPS', categoria_id: null }
    formProducto.abierto = false
    emit('cambio')
  } catch (e) {
    formProducto.error = mensajeDeError(e)
  }
}

async function alternarActivo(producto) {
  errorLista.value = ''
  try {
    await actualizarProducto(props.contribuyenteId, producto.id, { activo: !producto.activo })
    emit('cambio')
  } catch (e) {
    errorLista.value = mensajeDeError(e)
  }
}

const METODOS = { PEPS: 'PEPS', PROMEDIO_PONDERADO: 'Promedio ponderado' }
const IVA = { GRAVADO: 'Gravado', EXENTO: 'Exento', EXCLUIDO: 'Excluido' }
</script>

<template>
  <div class="grid gap-8 lg:grid-cols-[1fr_16rem]">
    <section class="min-w-0 space-y-3">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <h2>Productos</h2>
        <button v-if="!formProducto.abierto" type="button" class="boton" @click="formProducto.abierto = true">Agregar producto</button>
      </div>

      <form v-if="formProducto.abierto" class="hoja space-y-4 p-5" @submit.prevent="agregarProducto">
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="etiqueta" for="p-codigo">Código</label>
            <input id="p-codigo" v-model="formProducto.datos.codigo" class="campo" required maxlength="40" />
          </div>
          <div>
            <label class="etiqueta" for="p-nombre">Nombre</label>
            <input id="p-nombre" v-model="formProducto.datos.nombre" class="campo" required maxlength="200" />
          </div>
          <div>
            <label class="etiqueta" for="p-iva">IVA</label>
            <select id="p-iva" v-model="formProducto.datos.clasificacion_iva" class="campo">
              <option v-for="(t, v) in IVA" :key="v" :value="v">{{ t }}</option>
            </select>
          </div>
          <div>
            <label class="etiqueta" for="p-metodo">Método de costeo</label>
            <select id="p-metodo" v-model="formProducto.datos.metodo_costeo" class="campo">
              <option v-for="(t, v) in METODOS" :key="v" :value="v">{{ t }}</option>
            </select>
            <p class="mt-1 text-xs text-tinta-tenue">No se puede cambiar después del primer movimiento.</p>
          </div>
          <div>
            <label class="etiqueta" for="p-cat">Categoría</label>
            <select id="p-cat" v-model="formProducto.datos.categoria_id" class="campo">
              <option :value="null">Sin categoría</option>
              <option v-for="c in categorias" :key="c.id" :value="c.id">{{ c.nombre }}</option>
            </select>
          </div>
        </div>
        <MensajeError :mensaje="formProducto.error" />
        <div class="flex gap-3">
          <button type="submit" class="boton">Guardar producto</button>
          <button type="button" class="boton-secundario" @click="formProducto.abierto = false">Cancelar</button>
        </div>
      </form>

      <MensajeError :mensaje="errorLista" />
      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Código</th>
              <th>Producto</th>
              <th>Costeo</th>
              <th class="cifra">Existencias</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!productos.length">
              <td colspan="5" class="py-6 text-center text-tinta-suave">Sin productos. Agrega el primero para registrar compras y ventas.</td>
            </tr>
            <tr v-for="p in productos" :key="p.id" :class="p.activo ? '' : 'text-tinta-tenue'">
              <td>{{ p.codigo }}</td>
              <td>
                {{ p.nombre }}
                <p class="text-xs text-tinta-tenue">
                  {{ nombreCategoria[p.categoria_id] ?? 'Sin categoría' }}, IVA {{ IVA[p.clasificacion_iva].toLowerCase() }}
                  <template v-if="!p.activo">, inactivo</template>
                </p>
              </td>
              <td>{{ METODOS[p.metodo_costeo] }}</td>
              <td class="cifra">{{ cantidad(p.stock_actual) }}</td>
              <td class="text-right">
                <button type="button" class="text-sm text-tinta-suave underline hover:text-tinta" @click="alternarActivo(p)">
                  {{ p.activo ? 'Desactivar' : 'Activar' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="space-y-3">
      <h2>Categorías</h2>
      <ul class="hoja divide-y divide-papel-hondo">
        <li v-if="!categorias.length" class="px-4 py-3 text-sm text-tinta-suave">Sin categorías.</li>
        <li v-for="c in categorias" :key="c.id" class="flex items-center justify-between px-4 py-2 text-sm">
          {{ c.nombre }}
          <button type="button" class="text-tinta-suave underline hover:text-estado-nodeclarado" @click="quitarCategoria(c)">
            Eliminar
          </button>
        </li>
      </ul>
      <form class="flex gap-2" @submit.prevent="agregarCategoria">
        <label class="sr-only" for="cat-nombre">Nueva categoría</label>
        <input id="cat-nombre" v-model="formCategoria.nombre" class="campo" placeholder="Nueva categoría" required maxlength="120" />
        <button type="submit" class="boton-secundario">Agregar</button>
      </form>
      <MensajeError :mensaje="formCategoria.error" />
    </section>
  </div>
</template>

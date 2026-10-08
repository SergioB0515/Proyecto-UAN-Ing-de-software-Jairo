<script setup>
import { onMounted, ref } from 'vue'

import { mensajeDeError } from '../api/cliente'
import { listarCategorias, listarDocumentosSoporte, listarProductos, listarProveedores } from '../api/inventario'
import Cargando from '../components/Cargando.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import MensajeError from '../components/MensajeError.vue'
import KardexPanel from '../components/inventario/KardexPanel.vue'
import MovimientosPanel from '../components/inventario/MovimientosPanel.vue'
import ProductosPanel from '../components/inventario/ProductosPanel.vue'
import TercerosPanel from '../components/inventario/TercerosPanel.vue'
import { useContribuyente } from '../contexto'

const { contribuyente, periodo, manejaInventario } = useContribuyente()
const cid = contribuyente.value.id

const seccion = ref('movimientos')
const SECCIONES = [
  { id: 'movimientos', texto: 'Movimientos' },
  { id: 'kardex', texto: 'Kardex y costo de ventas' },
  { id: 'productos', texto: 'Productos' },
  { id: 'terceros', texto: 'Proveedores y documentos' },
]

const productos = ref([])
const categorias = ref([])
const proveedores = ref([])
const documentos = ref([])
const cargado = ref(false)
const error = ref('')

async function cargar() {
  try {
    ;[productos.value, categorias.value, proveedores.value, documentos.value] = await Promise.all([
      listarProductos(cid),
      listarCategorias(cid),
      listarProveedores(cid),
      listarDocumentosSoporte(cid),
    ])
    if (!cargado.value && !productos.value.length) seccion.value = 'productos'
    cargado.value = true
  } catch (e) {
    error.value = mensajeDeError(e)
  }
}

onMounted(() => {
  if (manejaInventario.value) cargar()
})
</script>

<template>
  <EstadoVacio v-if="!manejaInventario" titulo="Este contribuyente no maneja inventario">
    El inventario aplica solo a contribuyentes independientes o mixtos.
  </EstadoVacio>
  <template v-else>
    <MensajeError :mensaje="error" />
    <Cargando v-if="!cargado && !error" />
    <div v-if="cargado" class="space-y-6">
      <div class="flex flex-wrap gap-2" role="tablist" aria-label="Secciones de inventario">
        <button
          v-for="s in SECCIONES"
          :key="s.id"
          type="button"
          role="tab"
          :aria-selected="seccion === s.id"
          class="rounded px-3 py-1.5 text-sm"
          :class="seccion === s.id ? 'bg-tinta text-white' : 'bg-white text-tinta-suave ring-1 ring-papel-linea hover:text-tinta'"
          @click="seccion = s.id"
        >
          {{ s.texto }}
        </button>
      </div>

      <MovimientosPanel
        v-if="seccion === 'movimientos'"
        :contribuyente-id="cid"
        :periodo="periodo"
        :productos="productos"
        :proveedores="proveedores"
        :documentos="documentos"
        @cambio="cargar"
      />
      <KardexPanel v-else-if="seccion === 'kardex'" :contribuyente-id="cid" :periodo="periodo" />
      <ProductosPanel
        v-else-if="seccion === 'productos'"
        :contribuyente-id="cid"
        :productos="productos"
        :categorias="categorias"
        @cambio="cargar"
      />
      <TercerosPanel
        v-else
        :contribuyente-id="cid"
        :proveedores="proveedores"
        :documentos="documentos"
        @cambio="cargar"
      />
    </div>
  </template>
</template>

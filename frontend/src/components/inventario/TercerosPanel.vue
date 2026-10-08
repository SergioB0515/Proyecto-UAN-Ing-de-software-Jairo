<script setup>
import { reactive } from 'vue'

import { mensajeDeError } from '../../api/cliente'
import { crearDocumentoSoporte, crearProveedor } from '../../api/inventario'
import { fecha } from '../../formato'
import MensajeError from '../MensajeError.vue'

const props = defineProps({
  contribuyenteId: { type: Number, required: true },
  proveedores: { type: Array, required: true },
  documentos: { type: Array, required: true },
})
const emit = defineEmits(['cambio'])

const TIPOS_DOCUMENTO = {
  FACTURA: 'Factura',
  DOCUMENTO_SOPORTE: 'Documento soporte',
  NOTA_CREDITO: 'Nota crédito',
  NOTA_DEBITO: 'Nota débito',
  ACTA: 'Acta',
  OTRO: 'Otro',
}

const formProveedor = reactive({ error: '', datos: { nombre: '', tipo_persona: 'JURIDICA', identificacion: '' } })
const formDocumento = reactive({
  error: '',
  datos: { tipo: 'FACTURA', numero: '', fecha: '', descripcion: '' },
})

async function agregarProveedor() {
  formProveedor.error = ''
  try {
    await crearProveedor(props.contribuyenteId, { ...formProveedor.datos })
    formProveedor.datos = { nombre: '', tipo_persona: 'JURIDICA', identificacion: '' }
    emit('cambio')
  } catch (e) {
    formProveedor.error = mensajeDeError(e)
  }
}

async function agregarDocumento() {
  formDocumento.error = ''
  try {
    await crearDocumentoSoporte(props.contribuyenteId, {
      ...formDocumento.datos,
      descripcion: formDocumento.datos.descripcion || null,
    })
    formDocumento.datos = { tipo: 'FACTURA', numero: '', fecha: '', descripcion: '' }
    emit('cambio')
  } catch (e) {
    formDocumento.error = mensajeDeError(e)
  }
}
</script>

<template>
  <div class="grid gap-8 lg:grid-cols-2">
    <section class="space-y-3">
      <h2>Proveedores</h2>
      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr><th>Nombre</th><th>Identificación</th><th>Persona</th></tr>
          </thead>
          <tbody>
            <tr v-if="!proveedores.length"><td colspan="3" class="py-4 text-center text-tinta-suave">Sin proveedores.</td></tr>
            <tr v-for="p in proveedores" :key="p.id">
              <td>{{ p.nombre }}</td>
              <td>{{ p.identificacion }}</td>
              <td>{{ p.tipo_persona === 'NATURAL' ? 'Natural' : 'Jurídica' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <form class="hoja space-y-3 p-4" @submit.prevent="agregarProveedor">
        <h3>Nuevo proveedor</h3>
        <div class="grid gap-3 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <label class="etiqueta" for="pv-nombre">Nombre</label>
            <input id="pv-nombre" v-model="formProveedor.datos.nombre" class="campo" required maxlength="200" />
          </div>
          <div>
            <label class="etiqueta" for="pv-id">NIT o cédula</label>
            <input id="pv-id" v-model="formProveedor.datos.identificacion" class="campo" required maxlength="20" />
          </div>
          <div>
            <label class="etiqueta" for="pv-tipo">Tipo de persona</label>
            <select id="pv-tipo" v-model="formProveedor.datos.tipo_persona" class="campo">
              <option value="JURIDICA">Jurídica</option>
              <option value="NATURAL">Natural</option>
            </select>
          </div>
        </div>
        <MensajeError :mensaje="formProveedor.error" />
        <button type="submit" class="boton-secundario">Guardar proveedor</button>
      </form>
    </section>

    <section class="space-y-3">
      <h2>Documentos soporte</h2>
      <p class="text-sm text-tinta-suave">Todo movimiento de inventario debe tener uno.</p>
      <div class="hoja overflow-x-auto">
        <table>
          <thead>
            <tr><th>Documento</th><th>Fecha</th><th>Descripción</th></tr>
          </thead>
          <tbody>
            <tr v-if="!documentos.length"><td colspan="3" class="py-4 text-center text-tinta-suave">Sin documentos.</td></tr>
            <tr v-for="d in documentos" :key="d.id">
              <td>{{ TIPOS_DOCUMENTO[d.tipo] }} {{ d.numero }}</td>
              <td>{{ fecha(d.fecha) }}</td>
              <td class="text-tinta-suave">{{ d.descripcion ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <form class="hoja space-y-3 p-4" @submit.prevent="agregarDocumento">
        <h3>Nuevo documento</h3>
        <div class="grid gap-3 sm:grid-cols-3">
          <div>
            <label class="etiqueta" for="d-tipo">Tipo</label>
            <select id="d-tipo" v-model="formDocumento.datos.tipo" class="campo">
              <option v-for="(t, v) in TIPOS_DOCUMENTO" :key="v" :value="v">{{ t }}</option>
            </select>
          </div>
          <div>
            <label class="etiqueta" for="d-numero">Número</label>
            <input id="d-numero" v-model="formDocumento.datos.numero" class="campo" required maxlength="60" />
          </div>
          <div>
            <label class="etiqueta" for="d-fecha">Fecha</label>
            <input id="d-fecha" v-model="formDocumento.datos.fecha" type="date" class="campo" required />
          </div>
          <div class="sm:col-span-3">
            <label class="etiqueta" for="d-desc">Descripción (opcional)</label>
            <input id="d-desc" v-model="formDocumento.datos.descripcion" class="campo" maxlength="300" />
          </div>
        </div>
        <MensajeError :mensaje="formDocumento.error" />
        <button type="submit" class="boton-secundario">Guardar documento</button>
      </form>
    </section>
  </div>
</template>

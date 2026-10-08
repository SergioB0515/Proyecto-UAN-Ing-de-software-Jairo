<script setup>
// Vínculo DIAN opcional de un activo o fuente de ingreso (HU-03, HU-04):
// es lo que usa la conciliación para cruzarlo contra la exógena.
const codigo = defineModel('codigo', { type: String, default: '' })
const palabra = defineModel('palabra', { type: String, default: '' })
defineProps({ prefijo: { type: String, required: true } })
</script>

<template>
  <fieldset class="rounded border border-papel-linea p-4">
    <legend class="px-1 text-sm font-medium text-tinta-suave">Cruce con la exógena (opcional)</legend>
    <div class="grid gap-4 sm:grid-cols-2">
      <div>
        <label class="etiqueta" :for="`${prefijo}-codigo`">Código de concepto DIAN</label>
        <input :id="`${prefijo}-codigo`" v-model="codigo" class="campo" maxlength="10" placeholder="Ej. 1476" />
      </div>
      <div>
        <label class="etiqueta" :for="`${prefijo}-palabra`">O una palabra del detalle</label>
        <input :id="`${prefijo}-palabra`" v-model="palabra" class="campo" maxlength="200" placeholder="Ej. movimientos en cuentas" />
      </div>
    </div>
    <p class="mt-2 text-xs text-tinta-tenue">
      Sin esto, el registro queda como «sin reporte de terceros» en la conciliación.
    </p>
  </fieldset>
</template>

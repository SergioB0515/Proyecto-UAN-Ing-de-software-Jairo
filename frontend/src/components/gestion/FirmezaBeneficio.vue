<script setup>
import { dinero, fecha } from '../../formato'

defineProps({ gestion: { type: Object, required: true } })
const icono = (c) => (c === true ? '✓' : c === false ? '✗' : '?')
</script>

<template>
  <section class="hoja space-y-4 p-5">
    <div>
      <h2>Firmeza</h2>
      <p v-if="gestion.firmeza.fecha" class="mt-1 text-2xl font-semibold">{{ fecha(gestion.firmeza.fecha) }}</p>
      <p class="text-sm text-tinta-suave">{{ gestion.firmeza.regla }} · {{ gestion.firmeza.fuente }}</p>
      <p v-for="n in gestion.firmeza.notas" :key="n" class="mt-1 text-xs text-tinta-suave">{{ n }}</p>
    </div>

    <div class="border-t border-papel-hondo pt-4">
      <h3 class="font-semibold">Beneficio de auditoría</h3>
      <p class="mt-1 text-sm">{{ gestion.beneficio_auditoria.conclusion }}</p>
      <dl v-if="gestion.beneficio_auditoria.impuesto_anterior !== null" class="mt-2 space-y-1 text-sm">
        <div class="flex justify-between"><dt class="text-tinta-suave">Impuesto neto de renta del año anterior</dt><dd class="cifra">{{ dinero(gestion.beneficio_auditoria.impuesto_anterior) }}</dd></div>
        <div class="flex justify-between"><dt class="text-tinta-suave">Este año</dt><dd class="cifra">{{ dinero(gestion.beneficio_auditoria.impuesto_actual) }}</dd></div>
        <div v-if="gestion.beneficio_auditoria.impuesto_para_12_meses" class="flex justify-between"><dt class="text-tinta-suave">Necesario para 12 meses (+25 %)</dt><dd class="cifra">{{ dinero(gestion.beneficio_auditoria.impuesto_para_12_meses) }}</dd></div>
        <div v-if="gestion.beneficio_auditoria.impuesto_para_6_meses" class="flex justify-between"><dt class="text-tinta-suave">Necesario para 6 meses (+35 %)</dt><dd class="cifra">{{ dinero(gestion.beneficio_auditoria.impuesto_para_6_meses) }}</dd></div>
      </dl>
      <ul v-if="gestion.beneficio_auditoria.condiciones.length" class="mt-3 space-y-1 text-sm">
        <li v-for="c in gestion.beneficio_auditoria.condiciones" :key="c.descripcion" class="flex gap-2">
          <span :class="c.cumple === true ? 'text-libro' : c.cumple === false ? 'text-estado-nodeclarado' : 'text-tinta-tenue'">{{ icono(c.cumple) }}</span>
          <span>{{ c.descripcion }}<span v-if="c.detalle" class="text-tinta-suave"> — {{ c.detalle }}</span></span>
        </li>
      </ul>
      <p class="mt-2 text-xs text-tinta-tenue">{{ gestion.beneficio_auditoria.fuente }}</p>
    </div>
  </section>
</template>

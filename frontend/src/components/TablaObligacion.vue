<script setup>
import { dinero } from '../formato'

defineProps({ obligacion: { type: Object, required: true } })
</script>

<template>
  <div>
    <p class="text-lg font-semibold" :class="obligacion.obligado ? 'text-estado-nodeclarado' : 'text-libro'">
      {{ obligacion.obligado ? 'Está obligado a declarar renta' : 'No está obligado por los topes de la exógena' }}
      ({{ obligacion.anio_gravable }})
    </p>
    <div class="mt-3 overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Criterio</th>
            <th class="cifra">Reportado</th>
            <th class="cifra">Umbral</th>
            <th>¿Lo supera?</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in obligacion.criterios" :key="c.criterio">
            <td>{{ c.criterio }}</td>
            <td class="cifra">{{ dinero(c.valor_reportado) }}</td>
            <td class="cifra text-tinta-suave">{{ dinero(c.umbral) }}</td>
            <td :class="c.supera_umbral ? 'font-semibold text-estado-nodeclarado' : 'text-tinta-suave'">
              {{ c.supera_umbral ? 'Sí' : 'No' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="mt-3 max-w-prose text-xs text-tinta-suave">{{ obligacion.advertencia }}</p>
  </div>
</template>

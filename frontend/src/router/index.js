import { createRouter, createWebHistory } from 'vue-router'

import { obtenerContadorActual } from '../api/contadores'
import { cerrarSesion, sesion } from '../sesion'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { publica: true },
  },
  { path: '/', redirect: { name: 'cartera' } },
  { path: '/cartera', name: 'cartera', component: () => import('../views/CarteraView.vue') },
  {
    path: '/contribuyentes',
    name: 'contribuyentes',
    component: () => import('../views/ContribuyentesView.vue'),
  },
  {
    path: '/contribuyentes/:id(\\d+)',
    component: () => import('../views/ContribuyenteView.vue'),
    props: (route) => ({ id: Number(route.params.id) }),
    children: [
      { path: '', name: 'contribuyente', redirect: (to) => ({ name: 'resumen', params: to.params, query: to.query }) },
      { path: 'resumen', name: 'resumen', component: () => import('../views/ResumenView.vue') },
      { path: 'patrimonio', name: 'patrimonio', component: () => import('../views/PatrimonioView.vue') },
      { path: 'exogena', name: 'exogena', component: () => import('../views/ExogenaView.vue') },
      { path: 'conciliacion', name: 'conciliacion', component: () => import('../views/ConciliacionView.vue') },
      { path: 'borrador', name: 'borrador', component: () => import('../views/BorradorView.vue') },
      { path: 'liquidacion', name: 'liquidacion', component: () => import('../views/LiquidacionView.vue') },
      { path: 'inventario', name: 'inventario', component: () => import('../views/InventarioView.vue') },
      { path: 'soportes', name: 'soportes', component: () => import('../views/SoportesView.vue') },
      { path: 'cierre', name: 'cierre', component: () => import('../views/CierreView.vue') },
    ],
  },
  { path: '/umbrales', name: 'umbrales', component: () => import('../views/UmbralesView.vue') },
  { path: '/actividad', name: 'actividad', component: () => import('../views/ActividadView.vue') },
  { path: '/cuenta', name: 'cuenta', component: () => import('../views/CuentaView.vue') },
  { path: '/:pathMatch(.*)*', redirect: { name: 'cartera' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.meta.publica) return true
  if (!sesion.token) return { name: 'login', query: { siguiente: to.fullPath } }
  if (!sesion.contador) {
    try {
      sesion.contador = await obtenerContadorActual()
    } catch {
      cerrarSesion()
      return { name: 'login', query: { siguiente: to.fullPath } }
    }
  }
  return true
})

export default router

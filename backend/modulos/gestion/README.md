# modulos/gestion/

Proceso de la declaración alrededor de la liquidación. `calculos.py`: funciones
puras con su norma. `servicios.py`: conexión con liquidación, calendario y exógena.

| Qué | Endpoint | Norma |
|---|---|---|
| Etapas del proceso (7) y vista completa | `GET …/periodos-fiscales/{pid}/gestion` | — |
| Marcar etapas de criterio, pago, devolución, emplazamiento | `PATCH …/gestion/seguimiento` | — |
| Documentos a pedir al cliente, con mensaje listo | `GET …/documentos`, `PATCH …/documentos/{clave}`, `POST …/documentos` | — |
| Registrar lo presentado (copia de la liquidación) o una corrección | `POST …/gestion/presentaciones` | — |
| Registrar a mano la declaración de un año que no se hizo en la app | `POST /contribuyentes/{cid}/declaraciones-anteriores` | — |
| Traer a la hoja impuesto neto (126), anticipo (133→130) y saldo a favor (137→131) | `POST …/gestion/traer-del-anio-anterior` | Art. 807 ET |
| Comparativo casilla por casilla y coherencias 130/133 y 131/137 | dentro de `/gestion` | — |
| Firmeza | dentro de `/gestion` | Art. 714 ET |
| Beneficio de auditoría (35 % → 6 meses, 25 % → 12 meses, mínimo 71 UVT) | dentro de `/gestion` | Art. 689-3 ET; Ley 2294 de 2023 art. 69 (AG 2024–2026) |
| Sanción por corrección y plazos | dentro de `/gestion` | Arts. 588, 589, 639, 640 y 644 ET |
| Intereses de mora por tramos mensuales | dentro de `/gestion` (`?fecha_pago=` simula) | Arts. 634 y 635 ET |
| Informe de la declaración para el cliente (PDF) | `GET …/informe-cliente` | — |
| Tasas de interés moratorio (las publicadas vienen con la app; la base agrega o corrige meses) | `GET/PUT /tasas-interes-moratorio` | Art. 635 ET |

## Reglas

- Exógena, documentos y presentación se calculan; revisar, aprobar y pagar los
  marca el contador.
- Lo presentado se guarda como copia: base de correcciones, comparativo y
  patrimonio anterior (casilla 31).
- La fecha de presentación se fija antes de copiar la liquidación.
- Mes sin tasa: el tramo no se calcula y se informa. Tasas oficiales ene. 2025 -
  oct. 2026 incluidas en el código; la base las completa o corrige.
- Declaración anterior manual: casilla ausente = desconocida, no cero.
- Un certificado por tercero y tipo. No se pide lo reportado por la DIAN o el
  propio contribuyente.

## Fuera de alcance

- Art. 642 y abonos parciales en intereses.
- Requerimiento especial notificado (interrumpe firmeza): lo registra el contador.
- Condiciones externas del beneficio de auditoría (Zomac, Zese, zonas francas).

# modulos/gestion/

La declaración como proceso de trabajo del contador: lo que pasa alrededor de la
liquidación durante la temporada. Los cálculos están en `calculos.py`, funciones
puras que citan su norma; `servicios.py` los conecta con la liquidación, el
calendario y la exógena.

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

## Decisiones

- **Las etapas que se pueden saber solas no se marcan.** Exógena cargada,
  documentos completos y presentada se calculan; revisar el cruce, revisar la
  liquidación, la aprobación del cliente y el pago los marca el contador.
- **Lo presentado se guarda como copia.** La liquidación cambia cada vez que
  cambia un dato; la declaración presentada no. La copia es la base de las
  correcciones, del comparativo del año siguiente y del patrimonio líquido
  anterior que usa la liquidación (casilla 31 declarada, si existe).
- **La fecha se fija antes de copiar.** Sin fecha de presentación la
  liquidación calcula la sanción «si se presentara hoy»; una copia tomada así
  guardaría una sanción que la declaración presentada a tiempo no tiene.
- **Sin tasa no hay interés.** Si falta la tasa de un mes, ese tramo no se
  calcula y se avisa. Las tasas de enero de 2025 a septiembre de 2026 vienen
  con la app, tomadas de la tabla publicada por la DIAN; la de octubre de 2026,
  de la resolución de usura de la Superfinanciera menos dos puntos. Están en el
  código y no en la base para que una instalación nueva nunca arranque sin
  ellas; lo que el contador guarda en la base las completa o las corrige.
- **Una casilla no copiada de una declaración anterior manual es desconocida,
  no cero**: no se marca en el comparativo.
- **Un certificado por tercero y tipo**: los bancos expiden un solo certificado
  tributario anual, así que tarjetas, cuentas y CDT del mismo banco son una sola
  solicitud. Lo que reporta la DIAN o el propio contribuyente no se pide.

## Lo que no hace

- Sanción por extemporaneidad después del emplazamiento (art. 642) y abonos
  parciales en el cálculo de intereses.
- Saber si la DIAN ya notificó requerimiento especial (interrumpe la firmeza y
  cierra la corrección del art. 588): lo registra el contador.
- Verificar las condiciones del beneficio de auditoría que dependen de hechos
  externos (Zomac, Zese, zonas francas, retenciones inexistentes).

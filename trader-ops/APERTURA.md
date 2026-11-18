# APERTURA — cuanto cuesta esperar (y cuanto cuesta no esperar)

Estudio por valor con **60 dias de barras de 5 min** de Yahoo. NVDA: 59 sesiones completas,
2026-08-25 a 2026-11-17. Artefacto: `trader-ops/state/apertura_nvda.json`.
Reproducible con `/apertura NVDA`. Se recalcula cada dia antes del briefing.

## 1. Metodologia

Para cada sesion completa (>= 70 barras de 5 min, primera barra 9:30 NY):

- **Hueco**: apertura / cierre de la sesion anterior − 1.
- **Retorno 5/15/30 min**: cierre de la barra 1/3/6 / apertura − 1.
- **% del movimiento del dia en 15 min**: |cierre 9:45 − apertura| / |cierre final − apertura|.
- **Estrategia A**: comprar en la apertura y vender en el cierre, todos los dias.
- **Estrategia B**: comprar solo si hay un cierre de 5 min por encima del maximo de las 3 primeras
  barras (ORB), y vender en el cierre.
- **Hueco rellenado**: el precio toca el cierre previo durante la sesion.
- **Stop peor que su precio**: tras cruzar el mid del rango, el cierre queda por debajo.

## 2. Resultados NVDA (n=59)

| metrica | valor |
| --- | --- |
| Hueco de apertura | mediana **0,27 %**, p5 −3,26 %, p95 +2,33 % (n=58) |
| Retorno primeros 5 min | media +0,11 %, mediana +0,06 % |
| Retorno primeros 15 min | media +0,08 %, mediana **+0,01 %**, p5 −1,12 %, p95 +1,45 % |
| Retorno primeros 30 min | media +0,12 %, mediana −0,00 % |
| Movimiento del dia hecho en los primeros 15 min | mediana **52,2 %** |
| Comprar en la apertura, salir al cierre | 59 dias, media **−0,25 %/dia**, 21 positivos |
| Comprar solo si hay ORB, salir al cierre | 32 dias, media **−0,23 %**, 13 positivos |
| La ruptura paga peor precio que la apertura | **32 de 32 casos**, media **−1,00 %** |
| Hueco rellenado | **46,6 %** de las sesiones (n=58) |
| Stop en el mid: cierre por debajo | mediana **0,064 %**, peor 0,185 % (n=8) |

## 3. Lectura honesta

1. **El hueco existe y es grande en las colas**: p5 −3,26 % y p95 +2,33 %. Quien no esta comprado
   se lo pierde cuando es a favor, y quien esta dentro lo sufre cuando es en contra. Es simetrico.
2. **Los primeros 15 minutos no son "todo el movimiento"**: la mediana dice que ahi se hace el 52 %
   del recorrido del dia, pero la mediana del retorno en esos 15 min es +0,01 %. Es decir: se mueve
   mucho y acaba casi donde empezo. Esperar 15 min no cuesta retorno medio; cuesta **pagando mas
   caro** cuando la ruptura es real (1,00 % de media).
3. **Comprar en la apertura tampoco gana**: −0,25 %/dia en 59 sesiones. La conclusion no es "mejor
   comprar pronto", es "ninguna de las dos es una ventaja por si sola".
4. **La ruptura evita 27 de 59 dias**, pero en los 32 en que entra pierde de media lo mismo. Con
   costes de 0,52R, el resultado es peor que no operar.
5. **El hueco se rellena casi la mitad de las veces (46,6 %)**: ni "siempre continua" ni "siempre
   se cierra". Cualquier regla del tipo "compra el hueco" o "espera el relleno" es una moneda.
6. **El stop se ejecuta peor**: mediana 0,064 %, peor 0,185 %. Con 8 acciones y 5,86 de riesgo, eso
   son 0,03 USD/accion de media: pequeño, pero real y en contra.

## 4. Plan condicional (solo niveles calculados)

Para el proximo dia, con el rango 9:30–9:45 ET calculado por `entry.py`:

- **Si** el primer cierre de 5 min tras el rango queda por encima del maximo → entrada en ese cierre,
  stop en el mid del rango (redondeado abajo), objetivo 2R, fuera a las 15:55 ET.
- **Si** el precio ya esta a mas de 0,5R de la entrada cuando llega el aviso → no perseguir: la señal
  caduca (asi lo aplica el validador).
- **Si** el hueco de apertura supera el p95 (+2,33 % en NVDA) o cae por debajo del p5 (−3,26 %) →
  el plan de hoy no aplica: es otra sesion, con otra volatilidad.
- **Si** se cruza el stop → asumir que puede llenarse 0,064 % peor de media, 0,185 % en el peor caso.
- **Si** no hay ninguna de las condiciones anteriores → no se hace nada. Cero señales es valido.

## 5. Limitaciones

- 59 sesiones es una muestra corta: un trimestre. No cubre resultados trimestrales de NVDA
  (hubo uno en el periodo) ni un cambio de regimen.
- Barras de 5 min, no ticks: el "stop peor" es una aproximacion con el cierre de la barra siguiente.
- El spread proxy no es el bid-ask.
- El estudio mide retornos **antes de costes**; con 0,52R de coste por operacion, ninguna de las dos
  estrategias es positiva en esta muestra.
- NVDA es un solo valor: no se extrapola a todo el mercado.

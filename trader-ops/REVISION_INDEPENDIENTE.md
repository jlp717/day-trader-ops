# REVISION INDEPENDIENTE — intento, resultado y hallazgos

## 1. Aviso honesto sobre la independencia

Se lanzo un subagente `security-reviewer` (y un segundo `verifier`) para que auditara el codigo
**sin haberlo escrito** e intentara romper el validador. **Los dos fallaron** con
`The usage limit has been reached` (limite de uso de subagentes agotado en la cuenta, 2026-11-18).

Por tanto esta revision **no es independiente**: la hace el mismo que escribio el codigo, apoyada en
52 pruebas automaticas (41 funcionales + 11 de red team). Se documenta asi para que nadie la confunda
con una auditoria externa. Cuando haya cupo de subagentes, el brief exacto esta en `AGENTS.md` §6.

Lo que si es objetivo: cada hallazgo de abajo tiene una prueba que lo reproduce o una linea de codigo.

## 2. Hallazgos y correcciones (todos aplicados)

### ALTO — `/pausa` no pausaba de verdad
`telegram_bot.c_pausa` escribia `state/pausa.json`, pero `orquestador.t_orb` llamaba a
`proceso.evaluar_symbol(..., enviar=not self.dry)` sin consultarlo. Una señal se habria enviado
en pausa. **Corregido**: `orquestador.pausado()` y `enviar = (not dry) and (not pausado())`.
Prueba: `test_caos.ReinicioYDuplicados` + revision manual del flujo.

### MEDIO — mensajes programados sin deduplicacion
Briefing, apertura, flat y cierre usaban `bot.send` directo. Si `agenda_done.json` se corrompia o el
reloj saltaba hacia atras, se reenviaban. **Corregido**: `avisos.send_once` con clave por dia en las
cuatro tareas y en el premarket.

### MEDIO — argumentos de mas se ignoraban en silencio
`/alerta NVDA 1 && calc` creaba una alerta a 1,0 USD e ignoraba el resto. No habia ejecucion de shell
(los argumentos son listas), pero si ambiguedad. **Corregido**: `/alerta` exige exactamente 2
argumentos, `/entre` entre 3 y 5. Prueba: `test_redteam.Bot.test_no_hay_shell`.

### MEDIO — precios enteros inventados pasaban el validador
`texto._structural` aceptaba cualquier entero <= 40 como "conteo". Un "37" escrito a mano pasaba.
**Corregido**: el limite baja a 12, y los conteos del mensaje de señal (disparos, acciones, replays)
ahora se formatean con `Builder.num`, que los registra. Prueba:
`test_redteam.Validador.test_precio_entero_inventado`.

### MEDIO — comision convertida mal si la cuenta es en USD
`datos.coste_ida_vuelta_usd(..., cuenta_eur=False)` usaba tipo de cambio 1,0 para convertir la
comision (que se cobra en EUR), asi que el coste salia 0. **Corregido**: el EUR/USD se usa siempre
para la comision; solo el 0,30 % de FX depende de la divisa de la cuenta.
Prueba: el ensayo muestra 24,47 USD (EUR) y 6,99 USD (USD), coherentes con el calculo a mano.

### BAJO — el corte ORB no se movia en cierre anticipado
`orquestador.tareas` usaba `no_entries_after` (15:30 ET) tal cual; en el 27-nov el ORB habria
escaneado hasta las 21:30 Madrid en vez de las 18:30. **Corregido** y verificado con
`orquestador.py --simular 2026-11-27`.

### BAJO — `analyst` sin email de la SEC
No es un bug: `facts.py` se niega a llamar a la SEC sin User-Agent con email. Se documenta como
"no disponible" en vez de inventar. Pendiente de Javier.

## 3. Ataques que NO funcionaron (y por que)

| ataque | resultado |
| --- | --- |
| Meter una cifra falsa en `plan.json` despues de ejecutar `exit.py` | bloqueado: el validador compara contra la salida cruda del comando, no contra el JSON |
| `texto` con `$()` o `;` en tickers, precios o cantidades | rechazado por regex; `subprocess` usa listas, nunca `shell=True` |
| `callback_data` inventado | cae en `/ayuda`; el mapa es fijo |
| Repetir el mismo mensaje | `avisos.send_once` lo bloquea (probado) |
| Corromper `agenda_done.json` | se reconstruye; con la deduplicacion nueva no reenvía |
| Token en logs | no se registra: `telegram._log` guarda texto y chat, nunca el token; `skills.run` guarda argv, que no contiene secretos |
| `secrets/` en git | `.gitignore` lo excluye; permisos con `icacls`/`chmod 600` |

## 4. Riesgos residuales (aceptados, con motivo)

1. **El validador confia en la salida del skill.** Si Yahoo devolviera un precio manipulado y el
   skill lo imprimiera, el mensaje pasaria: es la fuente. Mitigacion: segunda lectura de precio,
   rango de plausibilidad en `criterios` y fuente unica declarada.
2. **Cifras calculadas sin `src`** (coste y EV) no se comparan con una salida de comando. Son
   aritmetica sobre datos ya validados y van marcadas; riesgo bajo.
3. **Una sola fuente de datos** (Yahoo). Stooq responde 404. Si Yahoo cae, el sistema avisa de
   "sin datos" y no inventa.
4. **Windows y suspension**: se evita con `SetThreadExecutionState`, pero un apagado del equipo
   detiene el sistema hasta el siguiente inicio de sesion (la tarea se dispara al entrar).
5. **Sin MCP de MyInvestor**: la contratacion exacta de cada valor no esta verificada; se asume que
   un ticker US simple cotiza en NDQ/NYS, y se dice en cada aviso.
6. **Revision no independiente** (ver §1): repetir con subagente cuando haya cupo.

## 5. Como reproducir

```powershell
python -m unittest discover -s trader-ops/tests -v      # 52 pruebas
python trader-ops/run/ensayo.py                          # contrato de calidad completo
python trader-ops/run/smoke.py                           # 14 comandos del skill
```

Resultado en esta sesion: `Ran 52 tests ... OK (skipped=1)`, ensayo `validador ok=True`,
smoke `14/14 sin fallo inesperado`.

# INICIO RAPIDO — 10 minutos y queda arrancado

## 1. Crear el bot de Telegram (3 minutos)

1. Abre Telegram y busca **@BotFather** (el oficial, con la marca azul).
2. Escribe `/newbot`.
3. Te pide un **nombre** (el que quieras, p. ej. `Day Trader Papel`) y un **usuario**, que debe
   terminar en `bot` (p. ej. `jlacal_papel_bot`).
4. Te responde con un **token** con esta forma: `123456789:AAH...` (unos 45 caracteres).
   **No lo pegues en el chat de OpenCode.** Lo pegas en la terminal, en el paso 2.
5. Abre tu bot nuevo y envíale `/start`. Ese mensaje es el que permite detectar tu `chat_id`.

Si ya tienes bot, salta al paso 2.

## 2. Guardar secretos (2 minutos)

```powershell
cd C:\Users\Javier\Desktop\Repositorios\day-trader-ops
python trader-ops/run/configurar_secretos.py
```

- Pide el token con `getpass`: no se ve en pantalla y no queda en el historial.
- Comprueba el token contra Telegram (`getMe`) y te dice el `@usuario` del bot.
- Se queda esperando tu `/start` hasta 5 minutos y **detecta el chat_id solo**. No hay que buscarlo.
- Luego pide tu nombre y email para la SEC (la SEC lo exige; sin email, `facts.py` no funciona).
- Guarda en `secrets/telegram.json` y `secrets/sec.json` con permisos solo para tu usuario.
  Esa carpeta esta en `.gitignore` y nunca se envia al chat.

Comprobar sin mostrar secretos:

```powershell
python trader-ops/run/configurar_secretos.py --estado
```

## 3. Reiniciar el orquestador para que salga de modo dry (30 segundos)

```powershell
Stop-ScheduledTask  -TaskName DayTraderOps
Start-ScheduledTask -TaskName DayTraderOps
```

El orquestador lee el token al arrancar; si ya estaba corriendo en dry, hay que reiniciarlo.

## 4. Probar el bot (1 minuto)

En Telegram, con tu bot:

```
/estado
/reloj
/ayuda
```

Debe responder en segundos. Si no responde:

```powershell
python trader-ops/run/telegram_bot.py      # en una terminal, para ver el error
```

## 5. Comprobar que todo esta sano (1 minuto)

```powershell
python trader-ops/run/smoke.py
python trader-ops/run/watchdog.py
powershell -File trader-ops/run/instalar_tarea.ps1 -Estado
```

`smoke.py` debe dar 14/14 sin fallo inesperado (las excepciones normales son `scanner.orb` con el
mercado cerrado y `analyst` si aun no hay email de SEC).

## 6. Que pasa manana sin tocar nada

| hora Madrid | que ocurre |
| --- | --- |
| 13:00 | scanner diario completo + noticias + resultados + Pelosi (contexto) |
| 15:00 | briefing con candidatos, plan condicional y bloque "coste de esperar" |
| 15:30 | apertura NYSE: mensaje de inicio y alertas cada 20 s |
| 15:50-21:30 | escaneo ORB cada 5 min; por cada disparo, cadena completa (entry, exit, Time Machine, tamaño, risk, criterios, validador) |
| 21:55 | aviso de flat by close (18:55 en cierre anticipado) |
| 22:00 | informe del dia y silencio hasta manana |

Si no hay ninguna SEÑAL A, **no se inventa nada**: el informe dira cuantos valores se analizaron,
cuantos fueron candidatos y por que se descartaron.

## 7. Parar y reanudar

```powershell
# parar todo
Stop-ScheduledTask -TaskName DayTraderOps
Stop-ScheduledTask -TaskName DayTraderOps-Watchdog

# reanudar
Start-ScheduledTask -TaskName DayTraderOps
Start-ScheduledTask -TaskName DayTraderOps-Watchdog
```

Solo silenciar avisos: `/pausa` y `/reanudar` en Telegram.

## 8. Desinstalar el autoarranque (reversible)

```powershell
powershell -File trader-ops/run/instalar_tarea.ps1 -Quitar
```

No borra nada del proyecto: solo quita las dos tareas del Programador.

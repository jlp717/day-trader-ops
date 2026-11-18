# AUDITORÍA DE SEGURIDAD — day-trader-skill v2

Alcance: los 11 scripts de `vendor/day-trader-skill/trader-*/` y `tests/`, en el commit
`3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd`. Auditoría hecha **antes** de ejecutar nada del skill
salvo `git clone`, lectura y los `--help`/`--json` de comprobación del mapa de capacidades.
Método: lectura completa + grep dirigido. Fecha: 2026-11-18, Madrid 05:2x–06:4x.

## 1. Salidas de red: solo las cuatro fuentes anunciadas (+1)

| host | dónde | uso |
| --- | --- | --- |
| `query1.finance.yahoo.com`, `query2.finance.yahoo.com` | scan, entry, exit, timemachine, alerts, news | gráficos y quotes |
| `feeds.finance.yahoo.com` | news | RSS de titulares |
| `www.nasdaqtrader.com` | scan universe | `nasdaqlisted.txt`, `otherlisted.txt` |
| `www.sec.gov`, `data.sec.gov` | news, facts | 8-K, XBRL, submissions, company_tickers |
| `disclosures-clerk.house.gov` | ptr | índice anual y PTRs en PDF |
| `stooq.com` | **alerts** (`--source stooq`, no es el defecto) | CSV de cotización de reserva |

`stooq.com` no estaba en la lista del encargo. Es un CSV público sin claves, solo se usa si se pide
explícitamente (`--source stooq`) y el propio SKILL.md dice que hoy responde 404. **No lo usamos.**
No hay ninguna otra URL, ni IP, ni dominio, ni endpoint de telemetría en todo el repo:

```
Select-String -Path trader-*\*.py -Pattern "https?://"  ->  24 coincidencias, todas de la tabla anterior
```

Sin `socket` directo, sin DNS propio, sin `requests`, sin `http.client` a mano.

## 2. Ejecución de código

- `eval(` / `exec(` / `compile(` / `__import__` / `pickle` / `marshal`: **cero** coincidencias en los 11 scripts.
- `subprocess`: **una sola**, en `trader-pelosi/ptr.py:342`:
  ```python
  out = subprocess.run([exe, "-layout", pdf_path, "-"], capture_output=True, timeout=60)
  ```
  Lista de argumentos (sin `shell=True`), ejecutable buscado por nombre (`pdftotext`), ruta del PDF
  construida por el propio script dentro de `trader/state/ptr-pdfs/`, timeout de 60 s.
  Riesgo: bajo. Depende de que exista `pdftotext` (poppler) en el PATH; si no, el propio script
  avisa y el PDF se abre a mano. **No instalamos poppler**: sin él, `parse` sigue funcionando sobre
  texto pegado.
- `os.system`, `os.popen`, `shutil.rmtree` en los scripts: **ninguno**. (`shutil.rmtree` solo aparece en
  los tests, sobre directorios temporales que ellos mismos crean.)

## 3. Lectura de entorno y archivos ajenos

- Variables de entorno leídas: **solo** `SEC_USER_AGENT` (`facts.py:80`, `news.py:149`), que es el
  User-Agent que la SEC exige. Nada de tokens, claves, `PATH` ni credenciales.
- `expanduser`, `USERPROFILE`, `APPDATA`, `winreg`, `keyring`, `getpass`: **cero** coincidencias.
- Archivos que abre: solo los que se le pasan por argumento y los de `trader/` (ver §4). No lee
  configuración del navegador, del broker ni del sistema.
- No hay `os.walk` sobre el disco: `tests/test_repo.py` recorre **su propio** repo, y solo en tests.

## 4. Escrituras: confinadas a `trader/`

Todos los `open(..., "w")` y `os.makedirs` de los scripts van a rutas que salen de:
`--out`, `--write`, `--state`, `--metrics`, `--pdf-dir`, `--rules`, `--orders`, `--prices-out`
(cuyos valores por defecto son siempre `trader/...`) o a `trader/entry.json`/`plan.json`/
`watchlist.json`/`universe.txt`. No hay ninguna ruta absoluta incrustada ni escritura en
`C:\`, `%APPDATA%`, `~` ni `Temp`.

Nuestro orquestador siempre pasa rutas explícitas bajo `trader/` y `trader-ops/`, y ejecuta los
scripts con `cwd` = raíz del proyecto, así que un `--out` relativo nunca escapa.

## 5. Credenciales y datos personales

- No hay claves de broker. `trader-broker` no contiene ni una llamada de red: solo renderiza tickets
  desde archivos locales. Verificado: `grep urllib trader-broker/ticket.py` → sin coincidencias.
- No hay `ALPACA_*`, `IBKR_*` ni ninguna variable de broker en el código.
- El único dato personal que el skill pide es `sec_user_agent` ("Nombre email"), que acaba en la
  cabecera HTTP de las peticiones a la SEC. Va en `trader/config.json`, que está en `.gitignore`?
  **No**: `trader/config.json` sí se versiona (es configuración, no secreto). Por eso el UA se
  guardará además en `secrets/` y se inyectará por `SEC_USER_AGENT`, y en `config.json` quedará solo
  el valor de reserva. Ver `AGENTS.md` §secretos.
- Los PDFs de PTR se guardan en `trader/state/ptr-pdfs/`, dentro del proyecto y en `.gitignore`.

## 6. Integridad y cadena de suministro

- Repo fijado por hash; no se actualiza solo (comprobación semanal por el orquestador, aviso por
  Telegram si cambia).
- Solo librería estándar en los 11 scripts (`argparse, datetime, gzip, json, os, re, sys, time,
  urllib, decimal, random, statistics, math, subprocess`). `zoneinfo` no lo usan (y un test lo prohíbe
  para mantener compatibilidad 3.8).
- TLS: `urllib.request` con los certificados del sistema. No se desactiva la verificación en ningún sitio
  (`ssl._create_unverified_context` / `verify=False`: cero coincidencias).
- No hay `pip install`, ni `curl | sh`, ni descarga de binarios. `pdftotext` es opcional y externo.

## 7. Veredicto

**PASA.** El código hace exactamente lo que dice: leer datos públicos y hacer aritmética. No hay
ejecución dinámica, ni telemetría, ni acceso a secretos, ni escrituras fuera de `trader/`.
Tres observaciones, ninguna bloqueante:

1. `stooq.com` como fuente de reserva de cotizaciones (no se usa; documentado).
2. `pdftotext` vía `subprocess` con argumentos fijos y timeout (riesgo bajo; no se instala).
3. Los scripts no validan el contenido de los JSON que leen de `trader/`: si alguien edita
   `plan.json` a mano, `risk`/`budget` trabajan sobre datos falsos. Mitigación nuestra: el
   validador y el diario guardan hash de cada salida, y el orquestador es el único que escribe.

No se encontró nada que obligue a parar.

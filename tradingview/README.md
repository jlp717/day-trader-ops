# Indicadores RAW para TradingView

Cuatro archivos, dos mercados y dos niveles:

| Archivo | Mercado | Qué hace |
| --- | --- | --- |
| `RAW_NASDAQ_LITE.pine` | EE. UU. (09:30 ET) | original de nico66fx, sin cambios: solo COMPRA/VENTA |
| `RAW_XETRA_LITE.pine` | Xetra (09:00 CET) | misma regla adaptada: solo COMPRA/VENTA |
| `RAW_PRO_US.pine` | EE. UU. | completa: stop, objetivo, tamaño por riesgo, multiplicador y filtro diario |
| `RAW_PRO_XETRA.pine` | Xetra | la completa adaptada a las 09:00 |

## Cómo cargar uno

1. TradingView → gráfico → **Pine Editor** (abajo).
2. Pega el contenido del archivo.
3. **Guardar** → **Añadir al gráfico**.
4. Temporalidad: 5 minutos.
5. Símbolo: `MNQ1!` o `NVDA` para EE. UU.; `SAP.DE`/`XETR:SAP` para Xetra.

## Qué añade la versión PRO

- **Stop** en el mínimo de la primera vela, con buffer configurable.
- **Objetivo** a N veces el riesgo (1R, 2R, 3R...).
- **Tamaño** calculado con riesgo por operación (%) y multiplicador (1 acción, 2 MNQ, 20 NQ).
- **Filtro de tendencia**: solo largos si el cierre diario anterior está sobre la SMA200.
- **Panel** con entrada, stop, objetivo, tamaño y riesgo en USD.
- **Alerta** con el plan completo, una vez al día, sin repintar.

## Qué NO hace

- No envía órdenes.
- No promete ventaja: medido en 60 sesiones (ver `REFERENCIA.md` §17), ninguna
  variante es positiva después de costes.
- No replica el "modo fondeo" del autor original: eso exige conocer tu P&L diario,
  y aquí no se inventa.

## Aviso

El Pine no se puede compilar desde este repositorio. Si el editor de TradingView
marca un error, pásalo y se corrige; no se afirma que esté verificado en tu cuenta.

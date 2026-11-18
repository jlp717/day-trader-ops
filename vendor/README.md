# vendor/day-trader-skill — copia fija (snapshot)

Este directorio **no es un submódulo**. Es una copia plana de los 85 archivos del repositorio
original, congelada en un commit concreto para que el banco de pruebas no cambie solo:

| Dato | Valor |
| --- | --- |
| Origen | https://github.com/Jakeschincariol/day-trader-skill |
| Commit | `3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd` (también en `vendor/VENDOR_COMMIT`) |
| Contenido | 85 archivos versionados + fixtures de test |
| Licencia | ver `LICENSE` en esta carpeta |

## Por qué snapshot y no submódulo

- El repo padre se clona con **un solo `git clone`** en el mini PC; no hay que añadir
  `--recurse-submodules`.
- Un `git pull` del proyecto nunca puede mover la versión del skill por accidente.
- El código del skill **no se modifica** (regla 5 de `AGENTS.md`). Si algún día hay que
  parchear algo, se documenta el diff aquí.

## Cómo actualizar el skill (solo si se decide, nunca automático)

```powershell
# 1. Clonar el original en una carpeta aparte
git clone https://github.com/Jakeschincariol/day-trader-skill.git C:\Temp\dts-nuevo
cd C:\Temp\dts-nuevo
git log --oneline -5          # anotar el commit nuevo

# 2. Comparar antes de sustituir
#    (leer los cambios de los .py que usa el pipeline)

# 3. Reemplazar el contenido, sin traer .git
robocopy C:\Temp\dts-nuevo vendor\day-trader-skill /MIR /XD .git

# 4. Verificar y dejar evidencia
python trader-ops\run\verificar_skill.py --tests
python -m unittest discover -s trader-ops/tests
```

Después de actualizar, cambiar el hash de la tabla de arriba y el de `AGENTS.md`, y anotar el
motivo en `trader-ops/ESTADO.md`. Si `verificar_skill.py --tests` no da 315 tests OK, se revierte.

## Reversión

```powershell
git checkout -- vendor/day-trader-skill
```

Al ser archivos normales del repo padre, la vuelta atrás es un `git checkout` de esa carpeta.

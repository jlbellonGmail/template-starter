# STATUS, observabilidad y reentrada

F13 define `STATUS.md` como vista humana derivada del presente. La precedencia es: Git, PR/CI, ROADMAP y `runs/` verificables; `STATUS.md` es una vista; el bloque AUTO y `update-status.ps1 -Json` son snapshots derivados y nunca sustituyen evidencia.

`STATUS.md` es un snapshot regenerable del estado actual; no es una bitácora.
`update-status.ps1` y `check-status.ps1` comparten `scripts/status-lib.ps1`, por
lo que usan la misma interpretación y nunca leen el snapshot anterior para
decidir el presente. GitHub no disponible se representa como `NOT AVAILABLE` y
el checker lo clasifica como `STALE`/temporal; un snapshot con HEAD distinto es
`STALE`; marcadores o rama contradictorios son `INCONSISTENTE`; fallos de
ejecución son `ERROR_REAL`.

La versión de desarrollo se obtiene, en orden, de `VERSION`/`version.txt`/
`.version`, metadata genérica de `pyproject.toml` o `package.json`, versión
explícita en la rama y el encabezado activo de `ROADMAP.md`. Si no hay una
fuente segura se informa `UNKNOWN`; nunca se inventa una versión fija. La
última release publicada se consulta separadamente a GitHub; el último tag
local se muestra como dato distinto y no se confunde con una release.

Los worktrees se enumeran exclusivamente desde `git worktree list`; el
checkout principal se marca como `primary`. Una unidad `ACTIVE` requiere una
rama Feature/Milestone actualmente registrada y un ítem no cerrado en
`ROADMAP.md`; `runs/` sólo es evidencia histórica/auditable y por sí solo no
crea unidades, PRs ni CI vigentes. El CI vigente se consulta por rama **y por
el HEAD exacto**; un run de otro commit no puede representar PASS/FAIL actual.

La salida machine-readable se obtiene sin persistencia con `pwsh -File scripts/update-status.ps1 -Json`; `-MachinePath` es explícito para consumidores que necesitan un archivo. Así, consultar no ensucia el checkout. Las carpetas Windows residuales no se cuentan como unidades: T04 conserva su clasificación en `check-integrity.ps1`.

Reentrada: leer STATUS, ejecutar `check-status.ps1`, verificar ROADMAP, localizar worktree/branch, abrir SUMMARY y evidencia de la unidad, y ejecutar la siguiente acción indicada. F14 puede consumir `activeUnits`, branch, worktree, HEAD, estado de ROADMAP y snapshot sin asumir que una carpeta física es actividad.

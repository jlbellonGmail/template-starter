# Retomar el proyecto

Lee `STATUS.md` para conocer el presente y ejecuta:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-status.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\update-status.ps1 -Json
```

`STATUS.md` es un snapshot regenerable del estado actual. `runs/` conserva
evidencia histórica y no implica actividad actual. Si el checker informa
`STALE`, regenera STATUS. `INCONSISTENTE` requiere revisar la evidencia real;
`TEMPORAL`/`NOT AVAILABLE` indica que GitHub o CI no pudieron consultarse;
`ERROR_REAL` requiere corregir el problema. La carpeta física de un worktree
eliminado no representa una unidad activa. La versión de desarrollo y la
última release publicada se muestran por separado; CI sólo es vigente si su
commit coincide con el HEAD actual.

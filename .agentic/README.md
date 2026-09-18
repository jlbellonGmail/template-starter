# Fuente canonica agentica

`.agentic/` contiene la configuracion canonica del circuito agentico que
no pertenece a una herramienta concreta.

- `agents.json`: roles canónicos `planner`, `builder` y `reviewer`, sus
  capacidades, modelos por herramienta y permisos de adaptador. Referencia
  `./schemas/agents.schema.json` via `$schema`.
- `roles/*.md`: definición funcional canónica de cada rol. Los aliases
  históricos se mantienen sólo en el router para migración.
- `models.json`: router minimo de modelos para OpenCode, allowlists,
  credenciales esperadas y fallbacks autorizados. Referencia
  `./schemas/models.schema.json` via `$schema`.
- `schemas/*.schema.json`: JSON Schema real (no ornamental) de
  `agents.json`, `models.json` y del manifest de Milestone
  (`work-unit.json`), validado en `tests/test_agentic_schemas.py`.
- `mcp.json`: fuente canonica de servidores MCP del template. Arranca
  vacia a proposito; no se inventan servidores.
- `run.example.yaml`: declaracion minima previa a `spec.md` para elegir
  modelo, variante y fallback.

Editar estos archivos y luego ejecutar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1 -Check
```

Los adaptadores en `.claude/`, `.codex/`, `.opencode/` y `opencode.json`
se regeneran desde esta fuente. No editarlos manualmente.

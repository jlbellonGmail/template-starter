# Fuente unica router modelos

## Proposito tecnico

Esta feature elimina la duplicacion entre configuraciones de Claude Code,
Codex y OpenCode. La fuente editable vive en `.agentic/` y los archivos
propios de cada herramienta se tratan como adaptadores generados.

## Fuente canonica

- `.agentic/agents.json`: roles, descripciones, permisos, modelos y
  esfuerzo por herramienta.
- `.agentic/roles/*.md`: prompt funcional de cada agente.
- `.agentic/models.json`: allowlists, variantes y fallback OpenCode.
- `.agentic/mcp.json`: servidores MCP canonicos.
- `.agents/skills/`: skills portables.

Los adaptadores se regeneran con:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1
```

Y se validan con:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1 -Check
```

## Router OpenCode

`scripts/resolve-agentic-model.ps1` resuelve el modelo antes de una etapa
OpenCode. Lee `runs/<NN>-<slug>/run.yaml` si existe, valida modelo y
variante contra `.agentic/models.json`, exige marcas de disponibilidad o
credenciales externas y escribe evidencia en `model-routing.jsonl`.

El fallback autorizado es Go -> Zen -> OpenRouter explicito. OpenRouter
no se usa si no aparece en `run.yaml` o en el parametro `-Fallback`.

## Gate post-HITL

`scripts/complete-approved-pr.ps1` se invoca desde
`.github/workflows/post-hitl-merge-gate.yml` cuando el humano aprueba una
PR contra `develop`. El gate vuelve a esperar checks de Actions despues
de la aprobacion:

- si quedan verdes, ejecuta el merge;
- si fallan o expiran, no mergea y produce
  `runs/<NN>-<slug>/post-hitl-gate-N.md` con feedback para builder.

El cierre `[x]` de `ROADMAP.md` sigue reservado al workflow post-merge.

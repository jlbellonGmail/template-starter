# AI-Native Project Starter

Este repositorio es un punto de partida limpio generado desde el circuito
AI-Native Template v2.0.1. Es un snapshot independiente: no conserva la
historia, tags, releases ni evidencias del repositorio fuente.

> ¿Estás retomando un repo que ya usa este template? Antes de seguir estos
> pasos, leé `STATUS.md` (raíz del repo) para el estado operativo actual —
> ver `AGENTS.md`, sección "Reentrada operativa (STATUS.md)".

## Inicio

```bash
# Clonar este proyecto
git clone https://github.com/ORG/PROYECTO.git
cd PROYECTO

# Inicializar la rama de integración
git switch -c develop
git push -u origin develop
```

## Configuración inicial

```bash
# Sincronizar adaptadores para Claude Code, opencode y Codex
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1

# Validar estructura y tests
pytest -v tests/

# Agregar tu primera feature al backlog: editar ROADMAP.md, sección
#    "Backlog", y agregar una línea con el patrón
#    `- [ ] 01-mi-feature — Descripción corta y verificable.` Luego
#    commitear ese cambio en develop (o pushearlo si develop es remoto).

# Arrancar la work unit: crea la rama feature/01-mi-feature y su
#    worktree en ../worktrees/01-mi-feature/ (debe correrse desde el
#    checkout principal de develop, con el árbol de trabajo limpio)
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-work-unit.ps1 -Mode Feature -Slug 01-mi-feature
```

## Flujo de trabajo

```bash
# Dentro del worktree creado en el PASO 2, el circuito corre como
# subagentes en sesión nueva, en este orden — cada uno produce su
# artefacto en runs/01-mi-feature/ antes de que el siguiente empiece:
# Analyst-agent    → spec.md, plan.md, tasks.md
# Reviewer-agent   → audit-N.md (approved/rejected sobre spec+plan+tasks)
# Builder-agent    → código + docs/tecnica + docs/usuario + decision.md
# QA-agent         → test-report-N.md (pytest real + contrato completo)
# Code-Reviewer    → code-review-N.md sobre el diff final

# Recién cuando code-review aprueba, se marca READY_FOR_PR y se crea la PR:
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\ready-for-pr.ps1 -Mode Feature -Slug 01-mi-feature

# HITL humano → único punto de decisión: MERGE o NO MERGE sobre la PR
# Merge → lo ejecuta el humano (directo en GitHub, o vía el gate
#         post-HITL si aprobó con una GitHub Review formal)
# Post-merge close → ROADMAP.md [ ] → [x] automático
```

## 💻 Compatibilidad de plataforma

El motor del circuito (`scripts/*.ps1`) es PowerShell **por decisión
explícita**, no por descuido — ver "Decisión: motor de scripts en
PowerShell, plataforma primaria Windows" en `docs/tecnica/arquitectura.md`.

- La mayoría de los scripts corren igual en Windows, macOS o Linux con
  **PowerShell 7 (`pwsh`)**: `brew install --cask powershell` (macOS) o
  el paquete `powershell` de Microsoft para `apt`/`dnf` (Linux).
- Excepción: el reconciliador local
  (`scripts/local-feature-reconcile.ps1`, invocado por
  `ready-for-pr.ps1`/`complete-approved-pr.ps1` para limpiar
  worktree/rama tras un merge) usa `Start-Process -WindowStyle Hidden` y
  en un punto llama directo a `powershell.exe`. Solo está validado en
  Windows. Si no arranca en tu plataforma, no bloquea el circuito: es
  limpieza local de conveniencia (CI, el gate post-HITL y el cierre
  remoto de `ROADMAP.md` corren en GitHub Actions, no dependen de esto).
  Alternativa manual: `git worktree remove` + `git branch -d`.

## 📁 Estructura importante

- `.agentic/` - Configuración de roles, modelos y schemas JSON
- `scripts/` - Motor ejecutable (ver `scripts/*.ps1` para el listado y número actuales)
- `tests/` - tests de validación estructural del circuito (correr `pytest -v tests/` para el número y detalle actuales)
- `docs/producto/contexto-producto.md` - Conocimiento funcional persistente
- `docs/tecnica/` - Decisiones de diseño e implementación
- `docs/usuario/` - Guía de uso y propósito
- `ROADMAP.md` - Estados `[ ]` pendiente, `[−]` READY_FOR_PR, `[x]` completado

## 🆘 ¿Problemas?

- Si los adapters están desactualizados: `scripts/sync-agentic-adapters.ps1 -Check`
- Si los tests fallan: revisa `tests/test_workunit_lib.py` y `tests/test_ci_integration.py`
- Si el circuito no avanza: revisa `ROADMAP.md` estados y `spec.md` criterios de aceptación

## 📚 Más información

- `AGENTS.md` - Reglas compartidas del repositorio
- `ROADMAP.md` - Mapa de features y estados
- `docs/producto/contexto-producto.md` - Contexto del producto
- `.github/workflows/ci.yml` - Workflows de integración continua

---

El proyecto nuevo debe completar `docs/tecnica/arquitectura.md`, definir su
contexto de producto y adaptar `AGENTS.md` con sus reglas específicas antes
de asumir cualquier stack o comportamiento de negocio.

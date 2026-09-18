# Manual operativo del Template

Este archivo define cómo operar este repositorio. Es una guía de ejecución,
no el backlog, una spec de feature ni una fotografía del estado de Git.
Para una regla normativa estable consultar [CONSTITUTION.md](CONSTITUTION.md);
para el trabajo planificado consultar [ROADMAP.md](ROADMAP.md); para la
reentrada consultar [STATUS.md](STATUS.md). Las decisiones técnicas y la
matriz de compatibilidad del proyecto nuevo deben documentarse en
`docs/tecnica/arquitectura.md`.

## Reentrada operativa (STATUS.md)

Al comenzar una sesión leer, en este orden operativo, `AGENTS.md`,
`CONSTITUTION.md`, `ROADMAP.md`, `STATUS.md` y el estado real de Git:

```powershell
git status --short --branch
git log -1 --oneline --decorate
git branch -vv
git worktree list
```

Si la tarea depende de GitHub, verificar también el estado real:

```powershell
gh pr list --state all --limit 20
gh run list --limit 20
```

La evidencia real de Git, GitHub, `runs/` y los scripts prevalece sobre un
resumen desactualizado en `STATUS.md`. Antes de devolver control, bloquearse
o solicitar HITL, actualizar el estado y ejecutar:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\update-status.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-status.ps1
```

`update-status.ps1` sólo administra el bloque `STATUS:AUTO:BEGIN/END`;
el texto manual permanece bajo responsabilidad del agente. `STATUS.md` no
reemplaza artefactos, tests, PR, CI ni la evidencia primaria.

## Autoridad y reglas de seguridad

La precedencia es: instrucción humana vigente; reglas de este repositorio;
ítems y referencias de `ROADMAP.md`; contexto de producto; arquitectura y
ADRs; código y tests; supuestos explícitos. Una contradicción material no se
resuelve por preferencia del agente: se registra y se pregunta antes de cerrar
la spec. No se inventan reglas de negocio, permisos, datos, seguridad,
privacidad, cumplimiento, resultados funcionales ni contenido legal.

Los principios de `CONSTITUTION.md` son obligatorios: SDD antes de cambiar,
determinismo antes que IA, roles por capacidad, complejidad proporcional,
evidencia trazable, fail-safe, reversibilidad, mínimo privilegio,
portabilidad, evaluabilidad y observabilidad. El diseño v2 no habilita por sí
mismo una fase futura ni permite saltar un gate v1.

No modificar `D:\Proyectos\gi-platform-core` desde este repositorio. No
editar manualmente adaptadores generados. No hacer `force-push`, no destruir
trabajo ajeno y no marcar una unidad como completada sin la transición real
que corresponda.

## Roles canónicos

Los roles conceptuales son tres:

- **Planner** interpreta intención, consume ASSESS y produce intención y plan.
- **Builder** modifica el worktree, genera implementación y evidencia; no se
  aprueba a sí mismo.
- **Reviewer** valida independientemente el estado vigente y reúne spec review,
  QA y code review según el riesgo.

`analyst-agent`, `qa-agent` y `code-reviewer-agent` son aliases históricos de
migración en el router y en artefactos v1.1, no roles arquitectónicos. Los
modelos, proveedores, herramientas y adaptadores son reemplazables. La fuente
canónica de roles está en `.agentic/roles/`; sus metadatos y routing están en
`.agentic/agents.json` y `.agentic/models.json`.

La coordinación normal es Builder → validación determinística → Reviewer →
feedback estructurado → Builder. `scripts/convergence.ps1` consume ASSESS y
la profundidad SDD; no reclasifica ni inventa otra política. El Reviewer
siempre valida el diff vigente. Planner sólo reingresa ante decisión material,
ambigüedad, contradicción o cambio de alcance. Un bloqueo externo o fallo
técnico se conserva con evidencia y termina de forma segura.

## Stack

Este template no tiene stack de producto. `scripts/` contiene el motor del
`scripts/` contiene el motor del circuito. Un proyecto real documenta su stack en
`docs/tecnica/arquitectura.md` antes de asumir tecnología.

## Estructura del repo

`.agentic/` es la fuente de capacidades; `.agents/skills/` contiene skills
portables; `runs/` conserva evidencia; `tests/` prueba el circuito; `scripts/`
ejecuta operaciones y gates; `docs/` contiene documentación técnica y de uso.

## Identidad de una work unit

Una Feature es un ítem de `ROADMAP.md`, una rama y un run. Una unidad v2 con
identidad completa se inicia desde el checkout principal de `develop`:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-work-unit.ps1 `
  -Version v2.0.1 -Mode Feature -Slug 23-ejemplo
```

El script valida estado, reclama el ítem, crea `feature/v2.0.1-23-ejemplo`,
el worktree bajo `../worktrees/` y `runs/v2.0.1/23-ejemplo/`. Omitir
`-Version` conserva la interfaz legacy. No iniciar una unidad desde un
worktree de otra unidad ni sobre un checkout sucio.

Un Milestone agrupa sólo ítems realmente interdependientes:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-work-unit.ps1 `
  -Version v2.0.1 -Mode Milestone -Slug nombre-del-milestone `
  -Items 23-uno,24-dos
```

El manifest `runs/v2.0.1/milestone-<slug>/work-unit.json` es la identidad.
Todos los ítems deben estar pendientes, no reclamados y se cierran de forma
atómica. Si pueden publicarse como Features independientes, dividirlos.
Usar `Get-WorkUnitInfo` de `scripts/workunit-lib.ps1` y los contratos de
`scripts/feature-contract.ps1`; no duplicar parsers de identidad.

## ASSESS y SDD adaptativo

Ejecutar ASSESS sobre las rutas efectivamente evaluadas y conservar su salida:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\assess-work-unit.ps1 `
  -ChangedPath AGENTS.md,scripts/ejemplo.ps1 `
  -EvidencePath runs/v2.0.1/23-ejemplo/assess.jsonl
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\materialize-sdd.ps1 `
  -AssessmentPath runs/v2.0.1/23-ejemplo/assess.jsonl `
  -Objective "objetivo verificable" `
  -OutputPath runs/v2.0.1/23-ejemplo/sdd.json
```

ASSESS clasifica riesgo y produce `LIGHT`, `STANDARD` o `FULL`; el materializador
sólo traduce esa salida. No volver a clasificar manualmente. La ausencia de
`sdd.json` conserva el contrato legacy.

- LIGHT: `SUMMARY.md` y review vigente; no crear placeholders de artefactos
  opcionales.
- STANDARD: agrega intención/spec, plan, QA y documentación técnica y de uso.
- FULL: agrega tasks, decisión, auditoría y validaciones reforzadas.

La política declarativa vigente y sus validaciones viven en
`scripts/feature-contract.ps1`; el resumen humano siempre es `SUMMARY.md`.
Los artefactos opcionales sólo se crean si aportan evidencia real.

## Circuito

El circuito no tiene checkpoints humanos intermedios. Cada agente corre como
subagente en una sesión apropiada y deja evidencia en `runs/`.

1. **Planner/analyst** lee el ítem, sus referencias, el contexto de producto
   si existe, arquitectura, reglas, código y tests. Produce la intención
   proporcional, detecta ambigüedades y aplica CLARIFY. No inventa decisiones.
2. **Reviewer/reviewer-agent** valida coherencia, trazabilidad y profundidad.
   Rechaza una intención incompleta o una decisión material pendiente. Un
   rechazo vuelve al Planner.
3. **Builder/builder-agent** implementa y documenta en el worktree propio.
   Debe conservar compatibilidad, actualizar índices cuando corresponda y
   registrar decisiones demostrables.
4. **Validación/qa-agent** ejecuta la suite del producto si existe, la suite
   del circuito y `Assert-FeatureContract` o `Assert-WorkUnitContract`. Un
   fallo vuelve al Builder con evidencia.
5. **Reviewer/code-reviewer-agent** inspecciona el diff final después de QA.
   Si rechaza, vuelve al Builder y cualquier cambio relevante repite QA.
6. Con review aprobada, ejecutar `ready-for-pr.ps1`. La unidad queda `[-]`
   `READY_FOR_PR`, nunca `[x]`.
7. Publicar la rama propia, crear PR contra `develop` y esperar CI con
   `wait-pr-ci.ps1`. La PR contiene resumen, tests, riesgos y enlaces a la
   evidencia.
8. Detenerse para el único HITL: el humano decide `MERGE` o `NO MERGE` sobre
   la PR real con CI verde. El agente nunca infiere esa decisión por un SHA.
9. Con MERGE humano se puede usar `complete-approved-pr.ps1`; espera de nuevo
   los checks y sólo mergea si siguen verdes. El merge directo humano en
   GitHub también es válido después de revisar CI y evidencia.
10. Después del merge, `close-feature.ps1` confirma PR mergeada hacia
    `develop`, cambia `[-]` a `[x]` y sincroniza el remoto. La limpieza local
    es posterior y separada; `local-feature-reconcile.ps1` elimina worktree y
    rama sólo cuando el estado remoto confirma el cierre.

Los retornos permitidos son Reviewer → Planner, QA → Builder, code review →
Builder y HITL NO MERGE → Builder. Un cambio en código, tests o configuración
invalida las verificaciones afectadas y la review del diff viejo.

## Artefactos

El contrato ejecutable es la única fuente de archivos y estados requeridos.
Para legacy puede exigir `spec.md`, `plan.md`, `tasks.md`, `decision.md`,
`audit-N.md`, `test-report-N.md`, `code-review-N.md`, docs e índices. Para
v2, `Get-EvidenceContract` deriva exigencias de `sdd.json`. Nunca crear un
archivo vacío para simular cobertura.

Los veredictos de auditoría, QA y code review usan:

```yaml
status: approved | rejected
attempt: <n>
feedback:
  - punto concreto
```

Se evalúa el intento numéricamente mayor; un aprobado viejo no cubre un
rechazo nuevo. JSON/JSONL es evidencia de máquina y Markdown es entrada o
salida humana según el contrato.

## Formato de veredicto

El bloque YAML anterior debe abrir cada `audit-N.md`, `test-report-N.md` y
`code-review-N.md`; el campo `attempt` debe coincidir con el número del archivo.

Estados de `ROADMAP.md`: `[ ]` pendiente, `[-]` listo para PR y `[x]` sólo
después del merge confirmado a `develop`. El backlog es una línea por ítem;
las referencias indentadas son opcionales. Un milestone cambia sus ítems de
forma atómica. El cierre remoto no puede ejecutarse sobre una PR no mergeada.

## Contexto de producto y bootstrap

Si existe `docs/producto/contexto-producto.md`, Planner lo lee siempre. Es
conocimiento funcional persistente confirmado, no un artefacto de feature.
Si no existe, no se bloquea la unidad y se declara el supuesto.

El bootstrap de ese archivo es documentación transversal: el Planner devuelve
un borrador read-only, el Main Agent formula preguntas materiales al humano,
y luego escribe el archivo. No crea rama, run, PR ni modifica `ROADMAP.md`.

CLARIFY resuelve sólo huecos no deducibles de fuentes autoritativas. Las
preguntas deben ser concretas y orientadas a una decisión. La respuesta se
registra en la intención; una sección no vacía de decisiones bloqueantes
impide aprobarla.

## Git

`develop` es la integración diaria; cada Feature/Milestone usa rama y
worktree propios. Nunca commitear directamente a `develop` ni `main` desde
un agente. `guard-develop-branch.yml` es una mitigación reactiva cuando la
protección nativa de GitHub no está disponible; no se debe tratar como
protección preventiva. Los cambios de backlog y los cierres automáticos tienen
la excepción documentada por la auditoría, y deben conservar evidencia.

`main` es estable y recibe releases desde `develop` por PR. Una release es un
evento separado: requiere decisión humana explícita sobre versión y commit.
Los agentes no crean, mueven, recrean ni borran tags o releases. Cada release
usa SemVer `vX.Y.Z` y conserva todos los tags históricos, incluidos sus objetos
anotados. `scripts/release-readiness.ps1` es el preflight read-only; no
publica ni mergea.

El estado de v2.0.0 y su commit/tag congelados no se reutilizan como destino
de cambios nuevos. Una corrección posterior pertenece a su propia unidad,
versión, PR y evidencia. No se declara una release preparada por el solo
hecho de que una feature esté mergeada a `develop`.

## Versionado (tags)

Cada release usa un tag anotado `vX.Y.Z` sobre el commit de `main` aprobado
por el humano. Los agentes no crean, mueven, recrean ni borran tags o releases.
`scripts/release-readiness.ps1` sólo verifica readiness y no publica.

## CI/CD

Los tres jobs de `.github/workflows/ci.yml` son obligatorios y deben pasar:
`circuit-tests` (pytest de `tests/`), `product-tests` (placeholder deliberado
hasta que exista stack de producto) y `local-reconciler-tests` (Windows).
No usar `continue-on-error` para ocultar fallos. `docs.yml` publica MkDocs
desde `main` cuando corresponde. Los workflows post-HITL y post-merge sólo
actúan según sus contratos; no duplicar su lógica en prompts.

## Herramientas locales requeridas

PowerShell 7 para scripts, Git, `gh` autenticado y Python 3.12+ con `pytest`
(`requirements-dev.txt`). El reconciliador puede usar Windows PowerShell 5.1
internamente; esa dependencia es Windows-only.
No asumir stack de producto: documentarlo antes en
`docs/tecnica/arquitectura.md`.

## Configuración de modelos (Claude Code, opencode, Codex)

Después de modificar `.agentic/`, regenerar y verificar adaptadores:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1 -Check
```

No editar `.claude/agents/`, `.codex/*.config.toml`, `.mcp.json`,
`opencode.json` ni otros adaptadores generados. `run.yaml` declara modelo,
variante y fallback autorizado; `resolve-agentic-model.ps1` valida la
selección y `model-routing.jsonl` registra proveedor, modelo, motivo, etapa,
resultado y costo sólo si éste es confiable. Nunca registrar secretos ni
inventar costos. Una herramienta externa aporta datos, no autoridad ni
permisos implícitos.

## Reglas de dominio

No agregar backend, base de datos, integración externa o dependencia de build
sin decisión explícita en `docs/tecnica/arquitectura.md`. No conectar un
endpoint real sin spec que declare destino, datos y consentimiento aplicable.
El template no tiene dominio propio: cada proyecto real añade sus reglas en
`.claude/rules/` y las refleja en su documentación.

La documentación técnica está en `docs/tecnica/<slug>.md`, la de uso en
`docs/usuario/<slug>.md`, con enlaces exactos en sus índices cuando el
contrato de la unidad lo exige. `docs/tecnica/circuito-agentico.md`,
`docs/tecnica/operational-readiness-docs.md` y los scripts son referencias
canónicas para detalle, instalación y comprobaciones; no copiar aquí sus
listados completos.

## Reglas adicionales

Las reglas modulares de `.claude/rules/` son parte del contexto cuando no
están vacías; opencode las recibe por `instructions`. Codex debe referenciarlas
si genera prompts propios. No duplicarlas en este manual.

## Setup manual

La configuración única de GitHub Pages, remoto, branch protection y permisos
se describe en [docs/tecnica/operational-readiness-docs.md](docs/tecnica/operational-readiness-docs.md).
Verificar antes de aplicar cualquier `PUT` de GitHub; no sobrescribir reglas
existentes sin inspección. La protección nativa puede estar limitada por el
plan del repositorio; conservar entonces la mitigación reactiva y su evidencia.

Este manual no amplía permisos, no crea un sexto agente, no crea un MODE
operativo nuevo y no sustituye scripts, CI, contratos, PR, auditoría ni la
decisión humana final. Cuando una regla aquí y un script ejecutable divergen,
detenerse, registrar la contradicción y corregir la fuente apropiada mediante
PR; no compensarla con interpretación informal.

# Circuito agentico multiherramienta

El circuito tiene 5 roles: `Analyst → Reviewer → Builder → QA → Code
Reviewer`. `analyst-agent` produce `spec.md` (QUÉ+POR QUÉ), `plan.md`
(CÓMO) y `tasks.md` (desglose ejecutable trazable a cada `AC-N` de
`spec.md`) — Spec-Driven Development (SDD). `reviewer-agent` audita los
tres juntos. `builder-agent` implementa. `qa-agent` testea. Recién
después de que QA aprueba, `code-reviewer-agent` (read-only) revisa el
DIFF FINAL y produce `code-review-N.md` con el mismo formato de veredicto
que `audit-N.md`/`test-report-N.md`; un rechazo vuelve a `builder-agent`
(nunca a `analyst-agent`). Ver `AGENTS.md` seccion "Circuito" para el
detalle completo, incluido el orden numerado de pasos.

## Contexto de producto, CLARIFY y bootstrap

`analyst-agent` no depende solo de lo que el humano escribe en el pedido:
antes de escribir `spec.md` inspecciona activamente el/los item/s de
`ROADMAP.md` (con su bloque `Referencias:` opcional),
`docs/producto/contexto-producto.md` (si existe), `AGENTS.md` y
`.claude/rules/*.md`, `docs/tecnica/arquitectura.md` y otros docs
tecnicos relevantes, y el codigo/tests existentes. Aplica una precedencia
explicita de fuentes cuando dos parecen contradecirse (detalle completo
en `AGENTS.md`, seccion "Contexto de producto y bootstrap" →
"Política de fuentes y trazabilidad").

Puede inferir sin preguntar decisiones tecnicas ya establecidas
inequivocamente por codigo/arquitectura/stack/tests/ADR/reglas globales
(las declara como "Supuestos" en `spec.md`). No puede inventar decisiones
de producto, reglas de negocio, UX, seguridad, privacidad, datos,
permisos o cualquier politica con varias respuestas validas: esas pasan
por **Fase CLARIFY**, una ronda de preguntas concretas devuelta al Main
Agent (que las conversa con el humano en el chat ordinario, no en un
nuevo checkpoint formal) antes de reinvocar a `analyst-agent`. Si una
ambiguedad material queda sin resolver, `spec.md` la deja explicita en
"Decisiones pendientes bloqueantes" y `reviewer-agent` rechaza
automaticamente por ese motivo. Esto no reemplaza ni duplica el unico
HITL formal del circuito (la decision `MERGE`/`NO MERGE` sobre la PR).

`docs/producto/contexto-producto.md` es conocimiento funcional
persistente (propósito, usuarios, reglas de negocio ya adoptadas),
transversal a todas las features. Su ausencia nunca bloquea el circuito.
Se crea o actualiza de dos formas: (a) bootstrap — el humano pide
inicializar el contexto de producto, el Main Agent invoca a
`analyst-agent` (read-only) para investigar el repo y devolver un
borrador de texto (mas preguntas CLARIFY si hacen falta), y el Main Agent
mismo escribe el archivo con el borrador final, sin tocar `ROADMAP.md` ni
crear rama/PR; (b) evolucion — `builder-agent` actualiza el archivo al
cerrar una feature cuando confirma una decision de producto estable y
reutilizable, igual que ya escribe `docs/tecnica/` y `docs/usuario/`.
Ningun agente llena este archivo con contenido de negocio inventado.

## Fuente canónica

Las reglas compartidas siguen en `AGENTS.md`. La configuración que cambia
por herramienta vive en `.agentic/`:

- `.agentic/roles/*.md`: prompts funcionales canónicos (`analyst-agent`,
  `reviewer-agent`, `builder-agent`, `qa-agent`, `code-reviewer-agent`).
- `.agentic/agents.json`: descripciones, permisos, herramientas, modelos
  y esfuerzo por adaptador.
- `.agentic/models.json`: modelos permitidos, variantes y fallbacks de
  OpenCode.
- `.agentic/mcp.json`: servidores MCP canónicos del template.
- `.agentic/schemas/*.schema.json`: JSON Schema real de `agents.json`,
  `models.json` y del manifest de Milestone (`work-unit.json`),
  referenciado por `$schema` desde `agents.json`/`models.json` y validado
  en `tests/test_agentic_schemas.py`.
- `.agents/skills/`: skills Agent Skills portables.

## Adaptadores generados

No editar manualmente:

- `.claude/agents/*.md`
- `.codex/config.toml`
- `.codex/<role>.config.toml`
- `.mcp.json`
- `opencode.json`
- mirrors de skills en `.claude/skills/` y `.opencode/skills/`

Regenerar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1
```

Validar sin escribir:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1 -Check
```

## Router OpenCode

Antes de iniciar una etapa OpenCode:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\resolve-agentic-model.ps1 `
  -Role analyst-agent `
  -Feature 01-mi-feature
```

El archivo opcional `runs/<NN>-<slug>/run.yaml` puede fijar modelo,
variante y fallback antes de que exista `spec.md`:

```yaml
execution:
  model: default
  variant: high
  fallback:
    - go
    - zen
```

El script no invoca modelos ni consulta catalogos remotos. Valida contra
`.agentic/models.json`, exige credenciales o marcas de disponibilidad del
entorno y registra evidencia en `model-routing.jsonl`.

## Gate post-HITL

La aprobacion humana de una PR no implica merge inmediato. El gate comun
vive en `scripts/complete-approved-pr.ps1` y se invoca desde
`.github/workflows/post-hitl-merge-gate.yml` cuando una review humana
aprueba una PR contra `develop`.

El gate valida que la PR siga abierta, pertenezca a `feature/<NN>-<slug>`,
apunte a `develop` y tenga `reviewDecision=APPROVED`. Luego consulta los
checks con `gh pr checks --json ...`, excluyendo el propio workflow
`Post-HITL merge gate` para no esperarse a si mismo.

Si algun check queda en `fail` o `cancel`, o si expira la espera, no hay
merge. Se escribe `runs/<NN>-<slug>/post-hitl-gate-N.md` con
`status: rejected` y feedback para que `builder-agent` corrija la rama y
el circuito continue desde implementacion/QA.

Si todos los checks relevantes quedan en verde, el gate ejecuta
`gh pr merge --merge --delete-branch`. El cierre remoto de `ROADMAP.md`
lo sigue haciendo `post-merge-close-feature.yml` mediante
`scripts/close-feature.ps1`; la limpieza local queda en manos del
reconciliador local que observa `origin/develop`.

**Este gate es la automatización recomendada, no el único mecanismo de
merge permitido.** Requiere `reviewDecision=APPROVED` (una GitHub Review
formal) para disparar el workflow que lo invoca
(`pull_request_review: submitted`). El único HITL definido en
`AGENTS.md` (paso 9) exige que un humano decida y ejecute el merge sobre
una PR real, no que exista necesariamente ese objeto de Review: si el
humano mergea la PR directamente desde GitHub después de verificar CI y
evidencias (paso 8 del circuito), esa decisión también satisface el
único HITL — simplemente este workflow no tiene evento que lo dispare en
ese caso, porque nunca hubo una Review formal que lo activara. Lo que
`guard-develop-branch.yml` sí exige siempre, sin excepción, es que el
commit llegue a `develop` a través de una PR mergeada y no de un push
directo.

## Troubleshooting: EDR/antivirus agresivo bloquea el reconciliador local (Windows)

**Síntoma**: `ready-for-pr.ps1` lanza
`local-feature-reconcile.ps1 -StartBackground` como proceso de
PowerShell en segundo plano (`Start-Process ... -WindowStyle Hidden`,
ver `scripts/local-feature-reconcile.ps1`). En máquinas Windows con
software de seguridad (EDR/antivirus) agresivo, ese proceso de fondo
puede quedar bloqueado, terminado abruptamente o impedido de completar
sus operaciones de archivo sobre el worktree de la feature.

**Causa**: el EDR interfiere con el proceso PowerShell que corre en
background (comportamiento típico de heurísticas que tratan procesos
`powershell.exe` sin ventana visible como sospechosos), no con git, con
GitHub Actions ni con el estado remoto de `ROADMAP.md`.

**Alcance del problema**: es exclusivamente local a la máquina del
operador. No corrompe el estado de git, no afecta el CI de la PR, ni el
gate post-HITL, ni el cierre remoto de `ROADMAP.md` en `develop` (esos
tres corren en GitHub Actions, independientes de este proceso local). El
único efecto es que el worktree/rama local de la feature puede no
limpiarse automáticamente cuando corresponde.

**Solución**: reubicar el worktree en un path nuevo, forzando la
remoción del bloqueado:

```powershell
git worktree remove --force <path-del-worktree-bloqueado>
git worktree add <path-nuevo> <rama-de-la-feature>
```

`git worktree remove --force` descarta cualquier cambio sin commitear en
ese worktree — revisar `git status` ahí antes de forzar, si el worktree
sigue siendo accesible. El estado del reconciliador
(`<git-common-dir>/feature-reconcilers/`, ver
`Get-FeatureStateDir` en `scripts/feature-contract.ps1`) vive fuera de
cualquier worktree, así que no hace falta matar el proceso bloqueado
antes de remover el worktree. Después de recrear el worktree en el path
nuevo, se puede relanzar el reconciliador corriendo de nuevo
`scripts/ready-for-pr.ps1` (o directamente
`scripts/local-feature-reconcile.ps1 -Slug <slug> -StartBackground`)
desde ahí.

**Nota — mismo síntoma bajo `pytest tests/`, causa distinta (corregida)**:
`tests/test_local_reconciler_scripts.py`
(`test_start_reconciler_in_main_checkout`, `test_start_reconciler_from_linked_worktree`,
`test_start_reconciler_replaces_stale_lock`) a veces fallaban con "no
arranco en 60s". Una hipótesis anterior en esta misma sección atribuía
esto a un EDR local interfiriendo con "Python lanzando PowerShell
oculto" — **esa hipótesis quedó descartada** para el caso de estos tests
específicamente: se reprodujo el mismo fallo en runs limpios de GitHub
Actions `windows-latest` (`33580980427`, `33583676654`) sin ningún EDR
de terceros (`Get-MpComputerStatus` confirmó `RealTimeProtectionEnabled:
False` y sin detecciones), y un diagnóstico forense agregado
temporalmente al job (run `33585370715`) demostró que el reconciliador
**sí arrancaba y corría correctamente**: el log de cada test mostraba
"Reconciliador local activo para 99-demo" segundos después de iniciar, y
el proceso seguía haciendo `git fetch` hasta su timeout normal. La causa
real era un falso negativo en el propio *test harness* — ver "Bug real
corregido" más abajo, segunda parte, ya corregida.

El job `circuit-tests` (`ubuntu-latest`) de `.github/workflows/ci.yml`
sigue sin correr estos 7 tests: el `pytestmark` del propio archivo los
salta con `os.name != "nt"`, y ese job corre en Linux. El job
`local-reconciler-tests` (`windows-latest`, gate obligatorio igual que
`circuit-tests`/`product-tests`, sin `continue-on-error` — ver
AGENTS.md, sección "CI/CD") corre específicamente
`pytest tests/test_local_reconciler_scripts.py` en un runner Windows
limpio de GitHub Actions. La hipótesis de EDR local descripta arriba en
esta misma sección sigue siendo válida como explicación para el
escenario de uso real (`ready-for-pr.ps1` corrido por un humano o un
agente en su propia máquina, con Python en la cadena de lanzamiento del
reconciliador) — no fue descartada en general, solo como explicación de
los fallos de esta suite de tests, que ya no dependen de ese mecanismo
(ver más abajo).

## Bug real corregido: `local-reconciler-tests` fallaba en GitHub Actions windows-latest (no era EDR)

**Síntoma observado** (run `33580980427`): 3 de los 7 tests de
`tests/test_local_reconciler_scripts.py`
(`test_start_reconciler_in_main_checkout`,
`test_start_reconciler_from_linked_worktree`,
`test_start_reconciler_replaces_stale_lock`) fallaban en el propio job
`local-reconciler-tests` (`windows-latest`), sin ningún EDR de terceros
de por medio. `start_reconciler()` devolvía exit 0 pero, pasados 60s, no
existían ni el log ni el lock del reconciliador.

**Causa raíz real**: `Start-LocalReconciler`
(`scripts/local-feature-reconcile.ps1`) lanzaba el proceso de fondo con
`Start-Process -WindowStyle Hidden -RedirectStandardOutput ...
-RedirectStandardError ...`. `-WindowStyle` (incluso `Hidden`) requiere
una window station/desktop interactivo para crear la ventana. Los
runners de GitHub Actions `windows-latest` ejecutan los steps del job en
una sesión no interactiva (Session 0, sin desktop), donde
`Start-Process` con `-WindowStyle Hidden` combinado con redirección de
stdio lanza una excepción (`InvalidOperationException` /
`PlatformNotSupportedException` según la versión de .NET). Esa excepción
caía en el `catch` de `Start-LocalReconciler`, que solo hacía
`Write-Warning` sin fijar un código de salida distinto de cero — el
bloque `if ($StartBackground) { Start-LocalReconciler; exit 0 }`
terminaba igual en `exit 0` aunque el proceso hijo nunca hubiera
arrancado. Esto es independiente del problema de EDR documentado arriba
(que afecta máquinas locales con seguridad de terceros): ambos síntomas
son similares ("no arrancó a tiempo") pero tienen causas distintas.

**Corrección aplicada**:

1. `-WindowStyle Hidden` → `-NoNewWindow`. `-NoNewWindow` no depende de
   ninguna window station y es compatible con
   `-RedirectStandardOutput`/`-RedirectStandardError` tanto en sesiones
   interactivas como no interactivas — funciona igual en un desktop
   local que en Session 0 de un runner de GitHub Actions.
2. Fail-safe: `Start-LocalReconciler` ya no asume éxito solo porque
   `Start-Process` no lanzó una excepción. Después de lanzar el proceso,
   confirma durante hasta 2 segundos que el PID devuelto sigue vivo
   (`Get-Process -Id ...`) antes de escribir el lock. Si el proceso no
   sigue vivo, o si `Start-Process` lanza una excepción, la función
   termina con `exit 1` en vez de `exit 0` — un fallo real de arranque ya
   no se reporta como éxito silencioso. Los llamadores existentes
   (`ready-for-pr.ps1`) no revisan ese código de salida para la rama
   `-StartBackground`: es intencionalmente best-effort y no bloquea la
   creación de la PR, pero ahora un fallo de arranque queda visible en
   los logs (`Write-Warning`) y en el código de salida del script para
   quien lo invoque directamente o desde `pytest`.

**Esta corrección era necesaria pero no suficiente**: con `-NoNewWindow`
ya en `origin` (commit `fc6af4d`), los mismos 3 tests siguieron fallando
igual en un run posterior (`33583676654`). La causa raíz completa tenía
una segunda parte, en el propio test, no en el script — ver abajo.

## Segunda causa real: falso negativo en `wait_for_reconciler_running()` / `process_alive()` (test harness, no el script)

**Síntoma**: mismos 3 tests, mismo mensaje "no arranco en 60s
(log/lock ausentes)", incluso después de aplicar `-NoNewWindow` + el
fail-safe de arriba.

**Diagnóstico**: se agregó temporalmente al job `local-reconciler-tests`
un step que, sin enmascarar el exit code real de `pytest`, volcaba tras
cada corrida los procesos `powershell`/`pwsh` vivos, el árbol de
`.../main/.git/feature-reconcilers/` bajo el temp de pytest con el
contenido de cada log, y el estado/detecciones de Windows Defender (run
`33585370715`). Evidencia: `99-demo.log` existía y contenía
`"Reconciliador local activo para 99-demo"` pocos segundos después de
arrancar cada test, y el proceso seguía haciendo `git fetch` hasta su
timeout normal — es decir, `Start-LocalReconciler` funcionaba
correctamente de punta a punta. `Get-MpComputerStatus` mostró
`RealTimeProtectionEnabled: False` y sin detecciones: Windows Defender
tampoco era la causa.

**Causa raíz real**: `wait_for_reconciler_running()` (en
`tests/test_local_reconciler_scripts.py`) declaraba "no arrancó" en base
al predicado `process_alive()`, que lanzaba un proceso
`powershell.exe -NoProfile -Command "Get-Process -Id <pid> ..."` **nuevo,
como subproceso de Python, en cada uno de hasta 60 reintentos** (uno por
segundo) para verificar si el PID seguía vivo. Ese mecanismo demostró
dar falsos negativos —el proceso reconciliador estaba objetivamente vivo
y corriendo (ver log de arriba) mientras esta comprobación externa
reportaba que no lo encontraba— tanto en runners limpios de GitHub
Actions como, retrospectivamente, en la máquina de desarrollo local (lo
que también pone en duda que la interferencia de EDR local fuera la
explicación completa de los fallos locales previos de esta suite
específica, más allá del escenario real de `ready-for-pr.ps1` descripto
arriba). El bug estaba en el *harness de test*, no en
`local-feature-reconcile.ps1`.

**Corrección aplicada**: `process_alive()` ya no lanza ningún proceso
externo. Usa `ctypes` para llamar directamente a las funciones Win32
`OpenProcess` (con `PROCESS_QUERY_LIMITED_INFORMATION`) y
`GetExitCodeProcess`, comparando contra `STILL_ACTIVE` (259) — la misma
técnica que usa internamente el propio `.NET`/PowerShell, sin la
sobrecarga ni la fragilidad de lanzar y parsear la salida de un proceso
`powershell.exe` nuevo en un loop ajustado a intervalos de un segundo.
La condición de arranque (`started()` dentro de
`wait_for_reconciler_running`) sigue exigiendo evidencia real y
específica del contrato: el archivo `.pid` debe existir, su contenido
debe ser un PID numérico válido, y ese PID debe estar genuinamente vivo
según el sistema operativo — no se relajó ni se removió ninguna
comprobación, solo se reemplazó el mecanismo poco fiable de la última
comprobación (verificación de vida del proceso) por uno nativo y
determinístico.

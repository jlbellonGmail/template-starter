# Arquitectura — decisiones estructurales del repositorio

`AGENTS.md` (sección "Reglas de dominio") exige que ningún backend, base
de datos, integración externa o dependencia de build se incorpore al
repositorio sin que quede como una decisión explícita en este archivo.

Este template no fija stack: arranca sin código de producto, solo con el
circuito agéntico y su motor ejecutable (`scripts/*.ps1`). Cuando el
proyecto real que use este template agregue su primera pieza de stack
(frontend, backend, base de datos, hosting, integración externa),
documentar acá:

- **Qué se agrega** y en qué archivos/carpetas.
- **Por qué ahora**: qué feature o necesidad lo dispara.
- **Por qué este enfoque y no otro**: alternativas consideradas y motivo
  del descarte.
- **Qué sigue igual**: qué partes del repo no cambian con esta decisión.

Cada decisión nueva se agrega como una sección propia (`## Decisión:
<título>`), sin reescribir ni borrar las anteriores — este documento es
un historial acumulativo de arquitectura, no un snapshot que se
sobreescribe.

## Decisión: fuente canónica agentica y router de modelos

Los roles, modelos, fallbacks y MCP del circuito se centralizan en
`.agentic/` para evitar tres copias manuales entre Claude Code, Codex y
OpenCode.

- `AGENTS.md` conserva las reglas compartidas del repo.
- `.agentic/roles/*.md` contiene la definición funcional canónica por rol.
- `.agentic/agents.json` contiene metadatos, permisos y modelos por
  herramienta.
- `.agentic/models.json` contiene el router mínimo de modelos OpenCode,
  allowlists, variantes válidas, variables de entorno esperadas y
  fallbacks autorizados.
- `.agentic/mcp.json` contiene la fuente MCP canónica. Está vacía porque
  el template no necesita servidores MCP propios todavía.
- `.agents/skills/` es la fuente canónica de skills portables; los mirrors
  en `.claude/skills/` y `.opencode/skills/` se generan si existen skills.

Los adaptadores generados son `.claude/agents/*.md`, `.codex/config.toml`,
`.codex/<role>.config.toml`, `.mcp.json` y `opencode.json`. Se regeneran
con `scripts/sync-agentic-adapters.ps1` y se validan con el mismo script
en modo `-Check`.

El router de modelos se implementa en `scripts/resolve-agentic-model.ps1`.
Resuelve el modelo antes de iniciar cada agente, usando primero una
selección explícita, luego `runs/<NN>-<slug>/run.yaml` y finalmente el
default del rol. La variante se valida separada del modelo. Los fallbacks
no son silenciosos: se registran con motivo en `model-routing.jsonl` y
OpenRouter solo se habilita si se declara explícitamente.

La decisión no introduce backend, base de datos, servicio externo nuevo ni
dependencia de build. Solo agrega configuración, scripts PowerShell y
tests del circuito.

## Decisión: validación real de JSON Schema para `.agentic/`

`.agentic/agents.json` y `.agentic/models.json` declaraban `$schema`
apuntando a `.agentic/schemas/agents.schema.json` y
`.agentic/schemas/models.schema.json`, pero ese directorio no existía:
la referencia estaba rota y ningún test validaba la forma real de esos
archivos ni la del manifest de Milestone (`work-unit.json`).

- **Qué se agrega**: `.agentic/schemas/agents.schema.json`,
  `.agentic/schemas/models.schema.json` y
  `.agentic/schemas/work-unit.schema.json` (JSON Schema Draft 2020-12
  real, no ornamental), más la dependencia de test `jsonschema` (Python,
  fijada en `requirements-dev.txt` con el mismo criterio `>=` que
  `pytest`) usada exclusivamente por
  `tests/test_agentic_schemas.py` para validar `.agentic/agents.json`,
  `.agentic/models.json` y un manifest de Milestone real contra sus
  schemas respectivos, con casos positivos y negativos por schema.
- **Por qué ahora**: la feature `01-code-reviewer-y-sdd` corrige el
  `$schema` roto detectado en auditoría y formaliza el contrato de estos
  tres archivos JSON del propio circuito agéntico.
- **Por qué este enfoque y no otro**: escribir un validador JSON Schema
  artesanal sin dependencia externa era más riesgo (reinventar un motor
  de validación) que agregar una librería de testing estándar y madura.
  `jsonschema` es tooling exclusivo de test (paralelo a `pytest`, que
  `AGENTS.md` ya exige sin pasar por este documento), no una dependencia
  de runtime de producto — este template sigue sin tener stack de
  producto propio.
  - `agents.schema.json`/`models.schema.json` permiten propiedades
    adicionales a nivel raíz de cada rol (`additionalProperties: true`)
    para no romper con campos futuros menores, pero las prohíben dentro
    de los bloques `claude`/`codex`/`opencode` (`additionalProperties:
    false`) para detectar typos reales de configuración por herramienta.
  - `work-unit.schema.json` sí es estricto en su raíz
    (`additionalProperties: false`) porque el manifest de Milestone tiene
    una forma fija y pequeña, sin campos opcionales conocidos.
- **Qué sigue igual**: ningún backend, base de datos ni servicio externo
  nuevo. Los manifests de Milestone (`work-unit.json`) no autoreferencian
  su propio schema con un campo `$schema`: la validación se ejerce solo
  desde los tests, para no tocar el formato de archivo ya cubierto por
  `test_workunit_lib.py`/`test_start_work_unit.py` ni arriesgar
  compatibilidad con un manifest ya committeado en algún Milestone en
  curso.

## Decisión: contexto de producto persistente y Fase CLARIFY en analyst-agent

`analyst-agent` dependía de que el humano repitiera en cada pedido
información que ya vivía en el repo, y no tenía forma explícita de
distinguir un supuesto técnico razonable de una decisión de negocio
inventada.

- **Qué se agrega**: `docs/producto/contexto-producto.md` (plantilla
  neutral de conocimiento funcional persistente, transversal a features,
  leída automáticamente por `analyst-agent` cuando existe); una Política
  de fuentes y trazabilidad con precedencia explícita de 7 niveles; una
  Fase CLARIFY (ronda de preguntas concretas devuelta al Main Agent antes
  de cerrar `spec.md`, resuelta en la conversación ordinaria con el
  humano, sin crear un segundo HITL formal); secciones nuevas en
  `spec.md` (`Identificación`, `Contexto y fuentes`, `Supuestos`,
  `Clarificaciones realizadas`, `Decisiones pendientes bloqueantes`); un
  gate explícito de tamaño/descomposición de Milestone (independencia,
  cohesión, alcance, capacidad de revisión, capacidad de prueba, riesgo
  de integración, tamaño del cambio) aplicado por `analyst-agent`
  (autochequeo) y auditado por `reviewer-agent`; y una regla para que
  `builder-agent` traslade a `docs/producto/contexto-producto.md` las
  decisiones de producto estables detectadas al cerrar una feature.
- **Por qué ahora**: mejorar la calidad de `spec.md` sin que cada pedido
  tenga que repetir contexto ya documentado, y sin que ninguna
  ambigüedad de negocio se resuelva por invención silenciosa de un
  agente.
- **Por qué este enfoque y no otro**: se evaluó adoptar GitHub Spec Kit
  (Specify/Clarify) como herramienta, pero se descartó por agregar una
  dependencia externa y una estructura de directorios propia que
  duplicaría el circuito ya existente de este template; en cambio se
  tomaron sus conceptos (clarificación explícita, contexto persistente)
  y se integraron directamente en `analyst-agent`/`reviewer-agent`/
  `builder-agent` y en `AGENTS.md`. Se descartó también agregar un sexto
  agente o un nuevo `MODE` operativo para el bootstrap de contexto de
  producto: como `analyst-agent` no tiene `Write` (ver
  `.agentic/agents.json`), el Main Agent escribe el archivo a partir del
  borrador que `analyst-agent` devuelve como texto, sin tocar
  `ROADMAP.md` ni crear rama/PR para esa operación.
- **Qué sigue igual**: no se agrega backend, base de datos, servicio
  externo ni dependencia de build. El único HITL formal del circuito
  sigue siendo la decisión `MERGE`/`NO MERGE` sobre la PR; Fase CLARIFY
  es conversación ordinaria entre el Main Agent y el humano, no un
  checkpoint nuevo. El formato de `ROADMAP.md` (`[ ]`/`[-]`/`[x]`, patrón
  `NN-slug`) no cambia; el bloque `Referencias:` opcional es indentado y
  no interfiere con los parsers existentes (`Get-RoadmapItemState*` en
  `scripts/workunit-lib.ps1` matchean solo la línea del ítem).

## Decisión: motor de scripts en PowerShell, plataforma primaria Windows

El motor ejecutable del circuito (`scripts/*.ps1`) está escrito en
PowerShell desde el origen del template. Esto es una decisión explícita,
no un descuido a corregir: no hay ningún plan de reescribir el motor en
otro lenguaje. Lo que sí queda documentado acá es el alcance real de su
portabilidad, porque no es uniforme entre scripts.

- **Qué se agrega**: esta sección deja constancia de la decisión y del
  estado real de compatibilidad multiplataforma, sin cambiar código.
- **Por qué PowerShell y no otro lenguaje**: PowerShell Core (`pwsh`) es
  multiplataforma (Windows, macOS, Linux) desde PowerShell 6, provee
  objetos tipados en vez de solo texto (útil para JSON de `.agentic/*`),
  y evita mezclar dos lenguajes de scripting distintos (uno para
  Windows, otro para Unix) para el mismo motor. La mayoría de los
  scripts (`sync-agentic-adapters.ps1`, `feature-contract.ps1`,
  `workunit-lib.ps1`, `start-work-unit.ps1`, `ready-for-pr.ps1` en su
  lógica principal, `wait-pr-ci.ps1`, `close-feature.ps1`,
  `resolve-agentic-model.ps1`) solo usan cmdlets estándar de PowerShell
  más `git`/`gh` como procesos externos, y corren igual bajo `pwsh` en
  Windows, macOS o Linux.
- **Excepción real y honesta**: `scripts/local-feature-reconcile.ps1`
  (el reconciliador local que limpia worktree/rama tras el cierre
  remoto de una feature, ver "Troubleshooting" en
  `docs/tecnica/circuito-agentico.md`) usa
  `Start-Process -WindowStyle Hidden` para lanzarse a sí mismo en
  background, y prioriza `powershell.exe` (Windows PowerShell 5.1) sobre
  `pwsh`, con fallback a `pwsh` si `powershell.exe` no existe.
  `scripts/complete-approved-pr.ps1` (que invoca ese mismo reconciliador
  después de un merge aprobado) todavía llama directo a `powershell.exe`
  sin ese fallback. Ninguna de las dos rutas fue validada en macOS o
  Linux.
- **Qué necesita un usuario en Mac/Linux**: instalar PowerShell 7
  (`brew install --cask powershell` en macOS, o el paquete `powershell`
  de Microsoft para `apt`/`dnf` en Linux) cubre todos los scripts salvo
  el reconciliador local. Si el reconciliador local no arranca o se
  comporta distinto en su plataforma, no bloquea el circuito: es
  limpieza de conveniencia puramente local (worktree/rama), no afecta
  CI, el gate post-HITL ni el cierre remoto de `ROADMAP.md` (los tres
  corren en GitHub Actions). La alternativa manual es
  `git worktree remove` + `git branch -d` sobre la feature ya mergeada.
- **Qué sigue igual**: no se reemplaza PowerShell por otro lenguaje. No
  se agrega backend, base de datos, servicio externo ni dependencia de
  build. Adaptar `local-feature-reconcile.ps1`/`complete-approved-pr.ps1`
  para macOS/Linux (o unificar el orden de preferencia `pwsh` vs.
  `powershell.exe` entre ambos) queda pendiente como trabajo futuro, no
  resuelto por esta decisión.

## Decisión: modelo de evolución del template es `snapshot`, no sincronizado

Cuando un proyecto real adopta o clona este template (ver
`docs/tecnica/adopcion-proyecto-existente.md`), el resultado es una copia
independiente: ese proyecto evoluciona por su cuenta desde ese momento y
no existe ningún mecanismo, automático ni manual, que vuelva a sincronizar
cambios posteriores del template origen hacia los proyectos que ya lo
adoptaron, ni en sentido inverso.

- **Qué se agrega**: esta sección deja constancia explícita del modelo de
  evolución real (`snapshot`), sin agregar código ni mecanismo nuevo.
- **Por qué ahora**: el comportamiento ya era el diseño real desde el
  origen del template (no hay remote `upstream`, subtree, submódulo, ni
  workflow de sync en este repo ni en la guía de adopción), pero no
  estaba declarado en ningún lugar de forma inequívoca — quedaba implícito
  en la redacción de `docs/tecnica/adopcion-proyecto-existente.md`.
- **Por qué este enfoque y no otro**: se evaluó (solo como contraste, no
  como trabajo a implementar) un modelo de sincronización continua
  (`git subtree`/`submodule`/un workflow que compare contra el template
  origen), pero un modelo `snapshot` es consistente con el resto del
  diseño: `AGENTS.md` ya asume que cada proyecto real customiza
  "Stack", "Estructura del repo" y "Propósito del producto" con contenido
  propio no reversible a una plantilla genérica, y
  `docs/tecnica/adopcion-proyecto-existente.md` ya describe fusión manual
  sección por sección, no un mecanismo automático repetible.
- **Qué sigue igual**: no se crea ningún mecanismo nuevo de actualización
  o sincronización entre este template y los proyectos que ya lo
  adoptaron. Si un proyecto real quiere traer una mejora posterior del
  template (por ejemplo, un script nuevo en `scripts/`), es responsabilidad
  manual de ese equipo, con la misma estrategia de fusión de
  `docs/tecnica/adopcion-proyecto-existente.md`, no un `pull`/`merge`
  automático contra este repositorio.

## Decisión: enforcement técnico de `develop` sin branch protection nativa

`AGENTS.md` (sección "Setup manual" → "Branch protection de GitHub")
documenta que este repositorio, privado, recibe `403 Upgrade to GitHub
Pro or make this repository public to enable this feature` tanto en
`branches/{branch}/protection` como en `repos/.../rulesets` — ninguna
branch protection nativa de GitHub está disponible hoy contra `develop`
sin cambiar de plan o hacer público el repositorio, ambas decisiones
explícitamente fuera del alcance de cualquier agente.

- **Qué se agrega**: `.github/workflows/guard-develop-branch.yml`, un
  workflow disparado por cualquier `push` a `develop`. Para cada commit
  introducido por el push, consulta
  `GET /repos/{owner}/{repo}/commits/{sha}/pulls` (API de GitHub, no
  requiere branch protection) y verifica si el commit está asociado a
  una PR mergeada con `base.ref == develop`. Si algún commit no lo está
  (push directo) o si el push fue forzado (`github.event.forced`), el
  workflow: (a) revierte automáticamente los commits sin PR asociada con
  `git revert` (o restaura `develop` al estado previo al force-push si
  el commit anterior sigue siendo alcanzable), empujando la corrección
  de vuelta a `develop`; (b) deja evidencia auditable — abre un issue
  con el detalle del incidente y termina el run en rojo; y (c) si el
  revert automático entra en conflicto, o el commit previo al
  force-push ya no es alcanzable, no fuerza ningún estado: aborta,
  dejamos `develop` como quedó, y el issue lo marca como intervención
  manual inmediata requerida.
- **Por qué ahora**: es el único hallazgo `CRITICAL` de la auditoría
  baseline oficial (`AUDIT-2026-08-30-34773af-baseline-v1-1`, F-004): sin
  branch protection nativa, la regla "nunca commitear directo a
  `develop`" de `AGENTS.md` era solo convención documentada, sin ningún
  control técnico — y eso ya ocurrió en la práctica (ver el mismo
  `AGENTS.md`, historial de `develop` de agosto de 2026).
- **Por qué este enfoque y no otro**: GitHub no ofrece, en un repositorio
  privado de este plan, ningún equivalente a branch protection o
  rulesets vía API ni vía UI — se confirmó con `gh api
  repos/{owner}/{repo}/branches/develop/protection` y `.../rulesets`
  antes de implementar esta decisión. La alternativa real disponible es
  reactiva, no preventiva: como el `GITHUB_TOKEN` del propio repositorio
  sí puede empujar a `develop` (nada lo bloquea), un workflow puede
  detectar el estado no permitido después del hecho y revertirlo de
  forma automática y auditable, que es la definición de "enforcement
  técnicamente equivalente" que exige la remediación de F-004 cuando la
  prevención nativa no está disponible. Se descartó notificar sin
  revertir (no cierra el hallazgo, un push directo seguiría
  "pegado" en `develop`) y se descartó documentación/disciplina humana
  sola (ya demostrado insuficiente por el historial citado arriba).
- **Qué sigue igual**: no reemplaza a la branch protection nativa si en
  algún momento el repositorio pasa a GitHub Pro o se hace público — esa
  sigue siendo la vía preferida y preventiva (bloquea el push antes de
  que ocurra) en vez de reactiva (revierte después). Este workflow no
  previene el push directo en sí — GitHub no ofrece ese control aquí—
  solo garantiza que el estado no permitido no persista en `develop` sin
  quedar revertido y documentado. Los push realizados con el
  `GITHUB_TOKEN` del propio repositorio (por ejemplo el cierre automático
  de `ROADMAP.md` en `post-merge-close-feature.yml`) no disparan este
  workflow — GitHub no genera un nuevo evento de workflow para pushes
  autenticados con `GITHUB_TOKEN` — por lo que no hace falta (ni se
  intenta) una excepción explícita para ese caso dentro del workflow más
  allá del chequeo defensivo `github.actor != 'github-actions[bot]'` ya
  incluido. Límite conocido y no resuelto: si un force-push ocurre y el
  commit previo ya fue recolectado por `git gc` antes de que el workflow
  corra, la restauración automática no es posible (el workflow lo
  detecta y lo deja explícito en el issue que crea, en vez de fallar en
  silencio).

## Decisión: ciclo de vida de `main` — creación condicionada a la primera release

`AGENTS.md` (sección "Git") define el ciclo de vida de las ramas de este
repositorio en dos etapas estables: un **estado inicial del template**,
en el que `develop` es la única rama de trabajo y `main` puede no
existir, y un **estado posterior a la primera release**, en el que
`main` ya existe y funciona como rama estable de producción. Ambas
etapas son comportamiento correcto y esperado por diseño — ninguna es
una etapa "provisional" que haya que resolver. Esta sección documenta
por qué el modelo se define así, como ciclo de vida y no como una
descripción fija del estado de una única etapa.

- **Qué se agrega**: esta sección documenta el modelo de ciclo de vida
  completo, sin crear la rama `main` ni cambiar ningún workflow, script
  ni configuración. `main` se crea una única vez, exclusivamente cuando
  el humano decide y aprueba una release del proyecto real construido
  sobre este template: se identifica el commit exacto de `develop` que
  se aprueba, se crea `main` a partir de ese commit, y se publica/pushea
  por primera vez. Desde ese evento en adelante, `main` solo recibe
  releases aprobadas desde `develop` vía PR — nunca se trabaja
  directamente sobre ella, con el mismo criterio que ya rige para
  `develop` en la etapa inicial. Ningún agente del circuito crea `main`
  ni decide cuándo hacerlo: es exclusivamente una decisión humana, fuera
  del circuito por feature.
- **Por qué ahora**: una revisión de consistencia del flujo Git detectó
  que `AGENTS.md` describía `main` únicamente como si ya existiera, sin
  reconocer en ningún lugar que su creación es un evento condicionado a
  una release aprobada, ni que el estado inicial del template (sin
  `main`) es igualmente válido. Esta corrección documenta ambas etapas
  del ciclo de vida como comportamiento estable, de modo que la
  documentación siga siendo verdadera tanto antes como después de que
  `main` exista.
- **Por qué este enfoque y no otro**: se evaluó crear `main` de
  inmediato (por ejemplo, desde el estado vigente de `develop` en el
  momento de esta decisión) para eliminar de una sola vez cualquier
  ambigüedad sobre su existencia, pero se descartó: crear una rama de
  "producción" sin que medie una decisión real de release sería
  anticipar una decisión que, por diseño de este template (`AGENTS.md`,
  sección "Versionado (tags)"), es exclusivamente humana y vinculada a
  un commit aprobado concreto, no a un estado arbitrario de `develop`
  tomado solo para tener algo que publicar. Documentar el ciclo de vida
  completo — incluyendo el evento que crea `main` — es la corrección
  mínima suficiente; crear `main` sin una release real que la respalde
  generaría una rama de producción sin contenido de producción real
  detrás, lo cual sería peor que dejarla para el momento en que
  corresponda por diseño.
- **Qué sigue igual**: `develop` sigue siendo la rama de integración y de
  trabajo diario para toda feature/milestone, en cualquiera de las dos
  etapas del ciclo de vida; ningún workflow, script ni test del circuito
  por feature/milestone cambia. `docs.yml` (publicación de MkDocs a
  GitHub Pages, disparado por `push` a `main`) y la configuración de
  GitHub Pages siguen el mismo ciclo de vida: sin ejecución posible
  mientras `main` no exista, y operativos desde la release que primero
  publique `main` con cambios en `docs/`/`mkdocs.yml` — eso es
  consecuencia directa de este mismo modelo, no un defecto en ninguna de
  las dos etapas. No se crea ningún mecanismo nuevo de sincronización
  entre `develop` y `main`: el modelo del template sigue siendo
  `snapshot` (ver "Decisión: modelo de evolución del template es
  `snapshot`, no sincronizado" arriba); una vez que `main` exista, la
  relación entre ambas ramas sigue siendo exclusivamente vía PR de
  release humana, no un mecanismo automático adicional.

## Decisión: fundamentos v2 compatibles con v1.1.0

Se elige `CONSTITUTION.md` en la raíz antes de materializar sus reglas:
expresa principios normativos estables y es descubrible sin añadir una
jerarquía. `CONSTITUTION.md` sería igualmente posible, pero sugeriría otra
capa de gobierno sin una necesidad distinta. No se crean ambos archivos.
AGENTS conserva comportamiento persistente; el documento de principios
conserva invariantes y remite al diseño para su aplicación verificable.

La Fase 00 agrega fundamentos documentales y un procedimiento temporal de
supervisión con las herramientas existentes. No agrega un ejecutable vacío:
no existe todavía `template run`. Las decisiones de diseño y compatibilidad
se concentran en esta documentación de arquitectura, sin redefinir el stack.
El motor v1, sus cinco etapas, artefactos y gates siguen vigentes hasta que
una fase posterior demuestre y apruebe su sustitución incremental. Los tres
roles conceptuales futuros son capacidades, no nombres de proveedores.

La base estable es v1.1.0; el expediente de bootstrap registra objetos Git
y árbol exactos. La integración se hace por PR de gobernanza desde develop,
sin tocar main ni tags. No se cambia el modelo snapshot de adopción ni se
migra automáticamente ningún proyecto consumidor. Se descarta reemplazar
ahora scripts maduros: no existe evidencia comparativa que lo justifique.

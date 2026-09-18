# Contexto de producto

Este documento es el conocimiento funcional persistente del producto real
que se construye sobre este template. Es la fuente de contexto que
`analyst-agent` lee automáticamente al preparar cualquier `spec.md`
(Feature o Milestone) — ver "Política de fuentes y trazabilidad" en
`AGENTS.md`.

No es una spec de una feature puntual: es conocimiento estable y
reutilizable entre features (propósito, usuarios, reglas de negocio ya
adoptadas). Las decisiones específicas de una sola feature quedan en su
propio `runs/<slug>/spec.md` y `decision.md`, no acá. Cuando una decisión
tomada durante una feature resulta ser conocimiento estable del producto
(no solo de esa feature), `builder-agent` actualiza este archivo como
parte de cerrarla (ver "Evolución del contexto de producto" en
`AGENTS.md`).

## Propósito del producto

Template base AI-Native para arrancar un proyecto nuevo ya con un circuito
agéntico AI-Native funcionando: analista → auditor → implementador → QA →
code reviewer, con un único punto de intervención humana (la decisión de
merge sobre la PR). No define stack de producto — eso lo decide cada
proyecto real que nazca de este template, documentándolo en
`docs/tecnica/arquitectura.md` antes de que cualquier agente asuma
tecnología no declarada explícitamente.

## Problema que resuelve

Evita que cada proyecto nuevo tenga que diseñar desde cero el circuito
agéntico, sus roles (analyst, reviewer, builder, qa, code-reviewer),
scripts del motor ejecutable (`scripts/*.ps1`), tests y estructura de
documentación. Este template provee la andamiaje canónica que todos los
proyectos pueden heredar y comenzar a usar de inmediato.

## Usuarios y actores

- **Equipo de desarrollo**: Usa el circuito para features nuevas y
  milestones, siguiendo `AGENTS.md` y `ROADMAP.md`.
- **Main Agent**: Coordina la ejecución del circuito como subagente
  (analyst → reviewer → builder → qa → code-reviewer).
- **`analyst-agent`**: Lee automáticamente este archivo como contexto
  antes de escribir cualquier `spec.md`, reduciendo suposiciones.
- **Proyecto que adopte este template**: Definirá su stack (frontend,
  backend, base de datos, hosting, integraciones) en
  `docs/tecnica/arquitectura.md`.

## Flujos principales

1. **Feature nueva**: `analyst-agent` → `reviewer-agent` → `builder-agent`
   → `qa-agent` → `code-reviewer-agent` → READY_FOR_PR → PR → CI verde →
   HITL (único punto humano: MERGE/NO MERGE) → gate post-HITL → merge →
   close-feature.ps1 → `[x]` ROADMAP.md

2. **Milestone**: Múltiples items de ROADMAP.md agrupados bajo un
   `work-unit.json`, procesados como una unidad atomica: todos los items
   deben pasar de `[ ]` a `[-]` juntos (via `ready-for-pr.ps1 -Mode
   Milestone`) y de `[-]` a `[x]` juntos (via `close-feature.ps1 -Mode
   Milestone`).

3. **Cierre post-merge**: GitHub Actions `.github/workflows/post-merge-close-
   feature.yml` ejecuta `scripts/close-feature.ps1` desde `develop` para
   cambiar `[-]` → `[x]` en ROADMAP.md y limpiar worktrees.

## Comportamiento esperado

- **No asumir stack**: Decisión de backend, base de datos, hosting o
  integraciones externas queda exclusivamente en `docs/tecnica/arquitectura.md`.
  Ningún agente debe asumir tecnología, framework o dependencia no
  declarada explícitamente (ver `AGENTS.md` sección "Stack").
- **Contexto leído automáticamente**: `analyst-agent` consume
  `docs/producto/contexto-producto.md` al iniciar, usándolo como fuente
  de nivel 4 de precedencia (después de instrucción humana, reglas globales
  y ROADMAP.md items).
- **Un solo HITL**: La decisión MERGE/NO MERGE es el único punto de
  intervención humana. No hay checkpoints humanos antes de crear la PR.
- **SDD obligatorio**: `spec.md` + `plan.md` + `tasks.md` con trazabilidad
  AC-N. `reviewer-agent` audita los tres artefactos juntos.
- **Documentación transversal**: `docs/producto/contexto-producto.md` vive
  fuera de `runs/`, se lee automáticamente y se actualiza a través del
  tiempo. No es un artefacto de una feature.
- **Versionado**: Tags `vX.Y.Z` (SemVer) en releases a `main`, pusheados por
  humano después de mergear.

## Reglas de negocio conocidas

Vacío — este template no tiene reglas de dominio propias. Cada proyecto
real que nazca de este template agrega las suyas en `.claude/rules/` y las
refleja en `AGENTS.md` — no se copian reglas de otro proyecto sin
adaptarlas.

## Restricciones funcionales

- No agregar un backend, base de datos, integración externa o dependencia
  de build sin que quede como una decisión de arquitectura explícita en
  `docs/tecnica/arquitectura.md`.
- No inventar contenido de negocio no provisto (datos, textos legales,
  precios, certificaciones, testimonios) — el contenido real del
  producto debe venir del cliente/negocio real, no generarse por el
  agente.
- No conectar integraciones a servicios o endpoints reales sin que el
  spec de esa feature declare explícitamente a dónde van los datos y qué
  validación/consentimiento aplica, sobre todo si hay datos personales
  involucrados.

## Decisiones de producto ya adoptadas

Vacío — aún no hay decisiones de producto permanentes confirmadas para
este template. Cuando una feature concrete decisiones reutilizables,
`builder-agent` las reflejará en este archivo como parte de cerrar la
feature, según "Evolución del contexto de producto" en `AGENTS.md`.

## Límites generales

Queda explícitamente fuera del alcance de este documento y del template
base:
- Stack tecnológico (define en `docs/tecnica/arquitectura.md` por proyecto)
- Precios, certificaciones, testimonios o datos del producto real
- Integraciones a servicios externos (definen por feature en spec/plan)
- Cualquier política de seguridad, privacidad o cumplimiento regulatorio

## Terminología

- **WorkUnit**: Feature (un item `NN-slug` en ROADMAP.md) o Milestone
  (N items agrupados bajo `work-unit.json`).
- **SDD**: Spec-Driven Development (`spec.md` → `plan.md` → `tasks.md` con
  trazabilidad AC-N).
- **HITL**: Human-in-the-loop (única decisión: MERGE/NO MERGE sobre la PR).
- **ROADMAP.md**: Mapa de features con estados `[ ]` (pendiente), `[-]`
  (READY_FOR_PR), `[x]` (completado después de merge).
- **Feature**: Item individual `NN-slug` en ROADMAP.md con su propia
  rama `feature/NN-slug`.
- **Milestone**: Grupo de items de ROADMAP.md que forman un solo
  incremento funcional coherente, con rama `milestone/<slug>` y manifest
  `runs/milestone-<slug>/work-unit.json`.
- **Circuito agéntico**: Secuencia Analyst→Reviewer→Builder→QA→Code-Reviewer
  con HITL único humano.
- **POST-HITL GATE**: Validación automática después de la aprobación humana
  que verifica que los checks de CI siguen verdes antes de mergear.
- **SDD**: Spec-Driven Development (Desarrollo Impulsado por Specs).

# Circuito agentico

Este template usa un circuito Analyst -> Reviewer -> Builder -> QA ->
Code Reviewer para llevar una feature hasta una PR lista para revision
humana.

Analyst produce tres archivos por feature: `spec.md` (que se construye y
por que), `plan.md` (como se construye) y `tasks.md` (las tareas
concretas, cada una ligada a un criterio de aceptacion de `spec.md`).
Reviewer audita los tres antes de que Builder implemente. Una vez que QA
aprueba los tests, Code Reviewer revisa el diff final (codigo, tests,
scripts, documentacion tecnica) y deja su veredicto en `code-review-N.md`;
si lo rechaza, vuelve a Builder, no hace falta repetir todo el circuito
desde Analyst.

Para cambiar instrucciones de roles, modelos o fallbacks, editar
`.agentic/` y regenerar adaptadores:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync-agentic-adapters.ps1 -Check
```

Para elegir un modelo OpenCode antes de iniciar una feature, crear
`runs/<NN>-<slug>/run.yaml` desde `.agentic/run.example.yaml`. Si no se
indica modelo, se usa el default del rol. Si se permite fallback, queda
registrado en `runs/<NN>-<slug>/model-routing.jsonl`.

No guardar tokens en el repositorio. OpenCode Go y Zen se conectan con
`/connect`; OpenRouter se configura fuera del template. En automatizacion,
usar variables de entorno o marcas de disponibilidad documentadas en
`.agentic/models.json`.

## Contexto de producto

Antes de escribir una spec, Analyst revisa por su cuenta el item del
roadmap, `docs/producto/contexto-producto.md` (si existe), las reglas del
proyecto y la arquitectura/codigo existente — no hace falta repetirle en
el pedido lo que ya esta documentado. Si encuentra una decision de
producto/negocio/UX que admite varias respuestas validas, no la inventa:
te devuelve preguntas concretas antes de cerrar la spec (esto no es un
nuevo punto de aprobacion formal, es una conversacion normal).

Para inicializar el contexto de producto de un proyecto nuevo, basta con
pedirlo en el chat (por ejemplo "Inicializa el contexto de producto de
este proyecto"): Analyst investiga el repo y propone un borrador, y ese
borrador queda escrito en `docs/producto/contexto-producto.md` sin crear
rama ni PR.

## Despues de aprobar una PR

El humano solo aprueba o rechaza. Si aprueba la PR en GitHub, el workflow
`Post-HITL merge gate` espera que Actions termine en verde despues de esa
aprobacion.

Si Actions queda verde, el workflow mergea la PR automaticamente y el
cierre post-merge marca el roadmap como completado. Si Actions falla, no
mergea: deja un reporte `post-hitl-gate-N.md` en la evidencia de la
feature y comenta la PR para que el builder corrija sin pedir otro punto
de intervencion humana.

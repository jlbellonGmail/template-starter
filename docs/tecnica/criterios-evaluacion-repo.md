# Criterios de evaluación del repositorio

Este documento existe porque una calificación de "el repo está en
X/100" dicha por una IA sin una rúbrica escrita no es verificable ni
reproducible: depende de qué mire esa sesión puntual, no de un criterio
estable. Este archivo fija los checks concretos — cada uno con el
comando exacto que lo prueba — para que cualquier persona o cualquier
sesión de IA pueda correr la misma auditoría y llegar al mismo
resultado, sin depender de cuán a fondo miró ese día.

No reemplaza al circuito de `AGENTS.md` (analyst → reviewer → builder →
qa → code-reviewer): audita el resultado acumulado del circuito a lo
largo del tiempo, no una feature puntual.

## Cómo usar este documento

Correr cada check en orden. Un check en rojo no bloquea per se el uso
del repo, pero sí debe quedar declarado como deuda conocida (en
`docs/tecnica/arquitectura.md` si es una decisión de arquitectura, o
como ítem de `ROADMAP.md` si es trabajo pendiente) — nunca en silencio.

## A. Integridad del circuito (proceso)

### A1. Cero commits directos a `develop` fuera de PR

```bash
git log --first-parent develop --oneline | grep -v "^[a-f0-9]* Merge pull request"
```

Cada línea que aparezca acá es un commit que llegó a `develop` sin pasar
por una PR — salvo dos excepciones documentadas explícitamente en
`AGENTS.md`: el commit automático de `close-feature.ps1` (mensaje
`docs: cerrar <slug> en ROADMAP.md`) y ediciones directas del humano al
backlog de `ROADMAP.md` (`chore: agregar ... al backlog`). Cualquier
otra línea es una violación real de "nunca commitear directo a
`develop`" y debe tratarse como incidente, no como ruido.

### A2. Protección de rama activa (o limitación documentada)

```bash
gh api repos/{owner}/{repo}/branches/develop/protection
```

Si devuelve `403 Upgrade to GitHub Pro or make this repository public`,
el check A1 es la única defensa real hasta que se resuelva esa
limitación (ver `AGENTS.md`, sección "Setup manual" →
"Limitación conocida verificada en este repositorio"). No es un check
que se pueda "arreglar" sin una decisión de negocio (upgrade de plan o
repo público) — su estado debe quedar declarado, no ignorado.

### A3. `ROADMAP.md` sin marcadores de conflicto ni backlog fantasma

```bash
grep -n "<<<<<<<\|=======\|>>>>>>>" ROADMAP.md
```

Debe devolver vacío. Además, cada línea `[x]` debe corresponder a una PR
realmente mergeada a `develop` (`gh pr list --state merged --search
"<slug>"` para muestrear).

## B. Consistencia entre documentación y estado real

### B1. Los índices de docs solo enlazan features reales

```bash
comm -3 \
  <(grep -oE '\[.*\]\(([a-z0-9-]+)\.md\)' docs/tecnica/index.md | grep -oE '\(([a-z0-9-]+)\.md\)' | tr -d '()' | sed 's/\.md$//' | sort) \
  <(grep -oE '^\- \[x\] [0-9]{2}-[a-z0-9-]+' ROADMAP.md | sed -E 's/^- \[x\] [0-9]{2}-//' | sort)
```

Cualquier slug que aparezca en un solo lado (no en ambos) es una
inconsistencia: un link a una feature que no existe en `ROADMAP.md`, o
una feature `[x]` sin documentación indexada. (Comparación aproximada:
ajustar a mano si un slug de doc no matchea 1:1 el slug de `ROADMAP.md`,
p.ej. `03-adopcion-proyecto-existente` vs `adopcion-proyecto-existente`.)

### B2. Ningún archivo contradice explícitamente el estado real

```bash
grep -rn "No hay Dockerfile\|no existe.*Dockerfile" AGENTS.md
ls Dockerfile 2>&1
```

Si `AGENTS.md` declara que algo "no existe todavía" y el archivo sí
existe (o viceversa), es una contradicción documental — se resuelve
actualizando el texto o eliminando el artefacto, nunca dejando ambos.

### B3. Todo script en `scripts/` está referenciado

```bash
for f in scripts/*.ps1; do
  name=$(basename "$f")
  grep -rlq "$name" tests/ docs/ AGENTS.md README.md .github/ scripts/*.ps1 2>/dev/null || echo "huerfano: $name"
done
```

Un script que no aparece en ningún test, doc, workflow ni es invocado
por otro script es código muerto o no verificado — no evidencia de
capacidad real.

## C. Salud de la suite de tests

### C1. `pytest tests/` pasa, o las fallas están diagnosticadas

```bash
pytest tests/ -q
```

Toda falla debe tener una causa raíz documentada (no "es el entorno"
sin evidencia) — ver `docs/tecnica/circuito-agentico.md`, sección
Troubleshooting, como ejemplo del nivel de detalle esperado.

### C2. Sin timeouts con unidades sospechosas

```bash
grep -rn "timeout=[0-9]\{4,\}" tests/*.py
```

En Python, `subprocess.run(timeout=...)` es en segundos. Cualquier
valor de 4+ dígitos (`60000`, `120000`) es casi siempre un bug de
milisegundos-en-vez-de-segundos copiado de otro lenguaje/convención.

### C3. Cobertura de drift pareja entre adaptadores

```bash
grep -c "def test_check_detects.*divergen" tests/test_agentic_sync_scripts.py
```

Debe haber al menos un test de divergencia por adaptador generado
relevante (Claude `.claude/agents/*.md`, `opencode.json`) — no solo para
el primero que se implementó.

## D. CI/CD

### D1. CI verde en el HEAD de `develop`

```bash
gh run list --branch develop --limit 3 --json conclusion
```

### D2. Los nombres de status check en `AGENTS.md` coinciden con los jobs reales

```bash
grep -oE "^\s*[a-z-]+:$" .github/workflows/ci.yml
grep -n "status check \`[a-z-]*\`" AGENTS.md
```

Comparar a mano: un nombre de job renombrado en `ci.yml` sin actualizar
`AGENTS.md` dejó pasar meses sin corregirse en este repo — no asumir que
"si el CI está verde, la doc está bien".

## E. Higiene de repositorio

### E1. Sin worktrees ni ramas huérfanas

```bash
git worktree list
git branch --merged develop | grep -v "^\*\|develop"
```

Cualquier worktree o rama local de una feature ya mergeada que sigue
viva es limpieza pendiente.

### E2. Sin artefactos sueltos trackeados fuera de convención

```bash
git ls-files | grep -E "pid\.txt$|^_.*\.ps1$"
```

## Última auditoría registrada

**2026-08-29**, sobre el estado de `develop` antes de esta misma PR:

- A1: **falló** — ~15 commits directos a `develop` en agosto de 2026
  (mensajes "template 10/10", etc.), fuera de las dos excepciones
  documentadas. Corregido en este mismo cambio removiendo los
  artefactos rotos que introdujeron (no se reescribe el historial).
- A2: **falló** (limitación de plan, no de configuración) — documentado
  en `AGENTS.md`.
- A3: ok (corregido en PR anterior, #10).
- B1: **falló** — `docs/tecnica/index.md` y `docs/usuario/index.md`
  enlazaban una feature ficticia "Ejemplo Completo" sin ítem en
  `ROADMAP.md`, con un link roto. Corregido en este cambio.
- B2: **falló** — `Dockerfile` existía y estaba roto (no instalaba
  PowerShell realmente) contradiciendo a `AGENTS.md`. Eliminado en este
  cambio, consistente con que el template no tiene stack de producto
  propio todavía.
- B3: **falló** — `bootstrap-template.ps1` (path hardcodeado a una
  máquina personal, variable de entorno inexistente) y
  `migrate-from-v0.ps1` (sintaxis inválida de PowerShell, `Test-Path
  -and` no es válido) no estaban referenciados en ningún lado.
  Eliminados en este cambio.
- C1: 171 tests, 168 en verde; 3 fallas de
  `test_local_reconciler_scripts.py` diagnosticadas a fondo (proceso
  hijo de `python.exe` terminado por seguridad al lanzar PowerShell
  oculto), no reproducibles en uso real ni en CI.
- C2: **falló** — `tests/test_agents_e2e.py` tenía `timeout=120000` y
  `timeout=60000` (segundos-como-milisegundos). Corregido en este
  cambio.
- C3: ok (agregado en PR anterior, #11).
- D1: ok.
- D2: **falló** — `AGENTS.md` seguía documentando el status check como
  `test` meses después de que el job se renombrara a `circuit-tests`.
  Corregido en este cambio.
- E1/E2: ok (PR anterior, #10).

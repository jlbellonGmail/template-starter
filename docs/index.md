# Documentación

Este es el sitio de documentación de un proyecto construido a partir del
template AI-Native: un circuito agéntico con analista, auditor,
implementador y QA, y un único punto de decisión humana antes de mergear.

- **[Contexto de producto](producto/contexto-producto.md)**: conocimiento
  funcional persistente del producto (propósito, usuarios, reglas de
  negocio ya adoptadas), leído automáticamente por `analyst-agent` antes
  de escribir cualquier spec. No es parte del ciclo de una sola feature.
- **[Documentación técnica](tecnica/index.md)**: decisiones de
  arquitectura, diseño e implementación. Para quien mantiene el código.
- **[Guía de usuario](usuario/index.md)**: propósito y modo de uso de
  cada feature. Para quien usa o administra el producto.

Cada feature que pasa por el circuito descrito en `AGENTS.md` (en la raíz
del repositorio) agrega un documento a cada una de esas dos últimas
secciones. Ver `ROADMAP.md` en la raíz del repositorio para el estado de
cada feature.

# Esquema de Operación de LLM Wiki (SCHEMA.md)

Este documento define la estructura, convenciones, formatos y flujos de trabajo obligatorios para la administración automática de la base de conocimientos. Cualquier agente de Inteligencia Artificial (LLM) que trabaje en este repositorio debe cumplir estrictamente con estas directrices.

---

## 1. Estructura del Directorio

- `sources/`: Carpeta inmutable para los documentos fuente originales (PDFs, artículos web, textos crudos). **El LLM nunca escribe ni modifica nada aquí.**
- `wiki/`: Base de conocimientos en Markdown gestionada por el LLM.
  - `wiki/concepts/`: Páginas para conceptos y definiciones abstractas.
  - `wiki/sources/`: Páginas que resumen cada documento fuente de forma individual.
  - `wiki/entities/`: Páginas para organizaciones, modelos, personas o herramientas de software específicas.
  - `wiki/comparisons/`: Notas comparativas y análisis complejos creados a partir de preguntas.

---

## 2. Metadatos (YAML Frontmatter) y Validaciones

Cada archivo Markdown dentro de la wiki debe comenzar con el siguiente bloque YAML obligatorio:

```yaml
---
title: "Título de la Nota"
type: concept | entity | source-summary | comparison
sources:
  - "sources/[subcarpeta]/[archivo_original]"
related:
  - "wiki/concepts/[nombre_nota].md"
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
# Opcional: Para documentar conflictos de conocimiento entre fuentes
conflicts:
  - node: "wiki/concepts/[nombre_nota_en_conflicto].md"
    source: "sources/[subcarpeta]/[archivo_fuente_conflicto]"
    reason: "Explicación detallada del conflicto o contradicción detectada"
---
```

### Reglas de Integridad y Validación del Linter:
1. **Nombres de Archivo Estrictos:** Todos los archivos en `wiki/` (excepto los estructurales) deben nombrarse estrictamente en **kebab-case** minúscula, usando solo letras de la `a` a la `z`, números y guiones altos (expresión regular: `^[a-z0-9]+(-[a-z0-9]+)*\.md$`). No se permiten espacios, mayúsculas, guiones bajos ni caracteres acentuados.
2. **Unicidad de Títulos:** No se permiten dos archivos distintos en la wiki que compartan el mismo `title` en su frontmatter (validado de forma insensible a mayúsculas y acentos).
3. **Existencia Física:** Las rutas declaradas en las listas de `sources` y `related` deben existir físicamente en el disco.
4. **Fechas Estrictas:** Las llaves `created` y `updated` deben seguir el formato ISO `YYYY-MM-DD`.
5. **Enums de Type y Confidence:** `type` y `confidence` deben corresponder estrictamente a los valores definidos en este esquema.

### Reglas de Enlace (Wikilinks):
- Conectar notas usando **Wikilinks** (`[[nombre-archivo-nota]]`).
- **No incluir la extensión** `.md` dentro de los corchetes del Wikilink (ej. `[[mixture-of-experts]]`).
- **Normalización Diacrítica:** El linter resuelve de forma inteligente los enlaces, limpiando acentos y convirtiendo guiones bajos a guiones altos para evitar enlaces rotos por problemas ortográficos (ej. `[[Estandarización]]` se resolverá correctamente al archivo físico `estandarizacion.md`).
- **Uso de Aliases:** Para mantener una redacción fluida en español sin romper la nomenclatura de nombres físicos, se recomienda usar aliases (ej. `[[modelo-de-negocio|Modelo de Negocio]]` o `[[estandarizacion|estandarización]]`).
- **Excepción de Orfandad:** Las notas de tipo `source-summary` y `comparison` están exentas de la regla de orfandad (no requieren que otras notas les apunten mediante Wikilinks). Los conceptos (`concept`) y las entidades (`entity`) sí deben estar interconectados obligatoriamente para no considerarse huérfanos.

---

## 3. Flujos de Trabajo Obligatorios

### Ingesta (`ingest [ruta_fuente]`)
Cuando se solicite procesar un archivo dentro de `sources/`:
1. **Lectura:** Leer y extraer el contenido del documento original (usando herramientas como `pdftotext` para PDFs).
2. **Resumen de Fuente:** Crear una nota de resumen en `wiki/sources/summary-[nombre-fuente-kebab-case].md`. Redactar el resumen ejecutivo y los puntos clave.
3. **Extracción y Actualización:**
   - Identificar conceptos o entidades clave.
   - Si la nota ya existe, abrirla e integrar la nueva información, actualizando su frontmatter (`sources`, `related`, `updated`).
   - Si no existe, crear la página con su YAML frontmatter correspondiente.
4. **Contradicciones:** Si la nueva información contradice registros anteriores, registrar de forma estructurada el conflicto en la sección `conflicts` del frontmatter de la nota afectada.
5. **Índice y Log:**
   - **Regeneración de Índice:** Ejecutar el comando de autoregeneración del índice central:
     ```bash
     ./tools/lint --build-index
     ```
   - **Registro de Log:** Ejecutar el comando para añadir el registro incremental de actividades de forma automática al log:
     ```bash
     ./tools/lint --log-ingest "[Nombre de la Fuente]" "[ruta_fuente]" "[lista-de-paginas-creadas-csv]" "[lista-de-paginas-modificadas-csv]"
     ```
     *(Ejemplo: `./tools/lint --log-ingest "Apunte Semana 1" "sources/papers/PRO303_Apunte_Semana1_2026.pdf" "summary-pro303-apunte-semana1-2026,estandarizacion,plan-de-negocio,wordclass-best-practices" "modelo-de-negocio"`)*.
6. **Validación:** Ejecutar `./tools/lint` al terminar el proceso para asegurar que el wiki quedó 100% sano y no se generó ninguna anomalía.

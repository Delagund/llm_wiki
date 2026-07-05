---
name: manage-memory
description: Instrucciones arquitectónicas sobre cómo guardar, procesar o buscar conocimientos, PDFs, y reflexiones dentro del ecosistema LLM-Wiki MCP. Usa este skill cuando el usuario pida "memorizar", "guardar" o procesar nueva información.
---

# Flujo de Operación de la Memoria Semántica (LLM Wiki)

Actúas en un entorno respaldado por un servidor MCP de memoria semántica. Tu responsabilidad es procesar información cruda y transformarla en notas altamente estructuradas. NO debes indexar vectores manualmente, el servidor MCP (`server.py`) hace esto automáticamente cuando usas las herramientas adecuadas.

## Escenario 0: Inicialización
Si el servidor no está inicializado o falla la carga, debes usar `initialize_project(base_path)` para configurarlo adecuadamente antes de continuar con cualquier operación.

## Formato Híbrido y Metadatos YAML
Debes priorizar la creación de archivos `.html` minimalistas (sin CSS, atributos `style` ni `class`). Los archivos Markdown (`.md`) quedan restringidos únicamente para contenido legacy.
Dentro de cada archivo `.html`, DEBES incluir un bloque de metadatos YAML usando comentarios HTML estandarizados. 

El único campo obligatorio es `type`:
```html
<!--yaml
type: concept
-->
```

Si el archivo representa una fuente original, el formato es:
```html
<!--yaml
type: source-summary
is_global: true
-->
```

## Taxonomía de Nodos y Directorios
Según el `type` definido, el archivo debe guardarse en su directorio correspondiente. Si los directorios no existen, debes crearlos:
- `type: concept` -> `wiki/concepts/[nombre].html`
- `type: entity` -> `wiki/entities/[nombre].html`
- `type: source-summary` -> `wiki/sources/[nombre].html`
- `type: comparison` -> `wiki/comparisons/[nombre].html`

## Enlaces (Grafo de Conocimiento)
Para establecer relaciones entre nodos, debes utilizar etiquetas de anclaje estándar `<a href="ruta/al/archivo.ext" rel="...">`:
- El atributo `href` debe apuntar a la ruta correcta con la **extensión exacta** (`.html` o `.md`) para evitar roturas.
- El atributo `rel` debe definir el tipo de relación y utilizar uno de los siguientes valores: `dependency`, `concept-link`, `source-summary` o `comparison`.

## Scoping y Estructuración de Contenido
Usa las etiquetas semánticas `<article>` y `<section id="...">` para estructurar la información. 
Al utilizar la herramienta `search_wiki`, puedes (y debes, cuando aplique) enviar el parámetro `scoping_id` para acotar la búsqueda a contextos específicos dentro del HTML.

## Sincronización Asíncrona (Eventual Consistency)
Ten en cuenta que el procesamiento de la carpeta `/sources` y el proceso `startup_lazy_check` operan asincrónicamente. Como resultado, las búsquedas pueden experimentar **"consistencia eventual"** (la información recién agregada puede tardar un poco en aparecer). Adicionalmente, los archivos planos ubicados en `sources/` generan automáticamente su representación `.html` en el sistema.

## Validación Estricta (Linter)
Siempre que crees o edites una nota, tienes la OBLIGACIÓN de ejecutar el linter para validar la integridad del grafo de conocimiento. Ejecuta el comando:
```bash
python tools/lint.py
```
Corrige cualquier error reportado por el linter antes de dar la tarea por terminada.

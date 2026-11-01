# Intérprete SQL con almacenamiento en archivos

Proyecto de Construcción de Compiladores de Ihan Marroquin y Diego Patzan. Adaptamos los generadores YALex y YAPar del proyecto anterior para interpretar SQL y guardar esquemas, registros e índices en archivos propios.

## Ejecutar en Windows

Requiere Python 3.10 o posterior con Tkinter (incluido en la instalación habitual de Python para Windows). Desde la carpeta del repositorio:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\ide.py
```

Si ya existe `.venv`, basta el último comando. El intérprete usa la biblioteca estándar; pytest es la dependencia para las pruebas. El primer inicio genera el lexer y las tablas SLR en `generated/` y puede tardar unos segundos.

## Demostración desde la interfaz

1. Presionar **Demo nueva** para abrir una base vacía independiente.
2. Presionar **Ejecutar (F6)**. El ejemplo completo crea tres tablas, inserta datos y ejecuta consultas.
3. En **Resultados**, seleccionar la sentencia que se quiere revisar. La sentencia 9 muestra José con 22 años y Ana con 20; la 10 muestra las inscripciones con sus nombres de estudiante y curso.
4. En **Plan de acceso**, la sentencia 9 utiliza `idx_edad` y lee 2 de 4 registros. Las subconsultas correlacionadas también pueden usar `idx_inscrito`.
5. Examinar **Tokens**, **Árbol sintáctico**, **AST** y **Errores** para ver las etapas del análisis.
6. Escribir una nueva consulta en el editor y presionar F6. **Analizar (F5)** valida sin ejecutar.

```sql
SELECT nombre, edad FROM estudiantes WHERE edad >= 18 ORDER BY edad DESC;
SELECT curso_id, COUNT(*) AS cantidad, AVG(nota) AS promedio
FROM inscripciones GROUP BY curso_id HAVING COUNT(*) >= 1;
```

Los ejemplos `error_sintactico`, `error_semantico` y `error_subconsulta` permiten mostrar los diagnósticos. Los dos últimos requieren las tablas de la demostración. Al fallar se limpian los resultados anteriores y se muestra la ubicación; seleccionar el error mueve el cursor al editor.

La demostración completa se ejecuta una vez por base vacía, porque contiene `CREATE TABLE`. **Demo nueva** crea otro directorio, conserva las bases anteriores y permite repetirla. Para continuar con datos existentes, usar **Base de datos** y escoger su directorio. La ruta activa siempre aparece sobre el editor.

## Terminal

Ejecutar el ejemplo en una carpeta de base de datos nueva:

```powershell
.\.venv\Scripts\python.exe scripts\sqlcompis.py examples\demo_completa.sql --db database\demo1 --plan
```

Consultar esos mismos datos en otra ejecución:

```powershell
.\.venv\Scripts\python.exe scripts\sqlcompis.py --db database\demo1 -c "SELECT nombre FROM estudiantes WHERE edad >= 20;" --plan
```

Validar sin ejecutar, mostrando las dos representaciones del árbol:

```powershell
.\.venv\Scripts\python.exe scripts\sqlcompis.py examples\demo_completa.sql --db database\analisis --analizar --tokens --arbol --ast
```

`--json` exporta los resultados, errores y planes a la salida estándar en JSON. Con `--tokens`, `--arbol` y `--ast` también incluye esas representaciones. La CLI devuelve 0 al terminar correctamente, 1 ante errores de análisis o ejecución y 2 si no puede abrir el archivo solicitado.

## SQL implementado

| Área | Operaciones |
| --- | --- |
| Esquemas | `CREATE TABLE`, `DROP TABLE`; `INT`, `FLOAT`, `VARCHAR(n)`, `BOOLEAN`, `DATE` |
| Restricciones | `NOT NULL`, `PRIMARY KEY`, `UNIQUE`, `DEFAULT`; claves compuestas a nivel de tabla |
| Datos | `INSERT INTO ... VALUES` con varias filas y columnas opcionales; `UPDATE SET`; `DELETE FROM` |
| Consultas | `SELECT`, `DISTINCT`, `FROM`, `WHERE`, `AND`, `OR`, `NOT`, expresiones y `ORDER BY` |
| Combinación | `INNER JOIN ... ON`, alias de tablas y columnas |
| Grupos | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `GROUP BY`, `HAVING` |
| Subconsultas | `IN`, `NOT IN`, `EXISTS`, `NOT EXISTS` y escalares, también correlacionadas |
| Índices | `CREATE INDEX nombre ON tabla(columna)`, `DROP INDEX nombre` |

Las palabras reservadas e identificadores no distinguen mayúsculas y minúsculas. Las cadenas usan comillas simples; una comilla dentro de una cadena se escribe dos veces: `'O''Brien'`. Se aceptan comentarios `--` y `/* ... */`. Las fechas se escriben como `'2026-11-01'` o `DATE '2026-11-01'`. `INTEGER`, `REAL` y `BOOL` son alias de tipos. Se recomienda terminar cada sentencia con `;`.

Se implementa el subconjunto solicitado, no un servidor SQL general. No se incluyen `ALTER TABLE`, claves foráneas, `LEFT JOIN`, `UNION`, `LIMIT`, procedimientos ni sentencias SQL de transacciones.

## Etapas del proyecto

```text
SQL -> lexer DFA -> parser SLR -> árbol sintáctico concreto
    -> AST -> análisis semántico -> interpretación -> archivos -> resultados
```

| Archivo o directorio | Responsabilidad |
| --- | --- |
| `grammar/SQL.yal` | Tokens y expresiones regulares para YALex |
| `grammar/SQL.yalp` | Producciones SQL para YAPar, sin conflictos SLR |
| `src/yalex`, `src/yapar`, `src/shared` | Generadores propios reutilizados; procedencia en `PROCEDENCIA.txt` |
| `src/sqlcompis/frontend.py` | Generar lexer y tabla, analizar tokens y construir el árbol concreto |
| `src/sqlcompis/ast_builder.py` | Visitador que transforma las reducciones en nodos del AST |
| `src/sqlcompis/semantic.py`, `types.py` | Catálogo, resolución de nombres y ámbitos, tipos y restricciones |
| `src/sqlcompis/interpreter.py` | Recorrer el AST y ejecutar operaciones, grupos y subconsultas |
| `src/sqlcompis/storage.py` | CSV, catálogo JSON, posiciones y recuperación de escrituras |
| `src/sqlcompis/indexes.py` | Índices persistentes y selección de registros candidatos |
| `src/sqlcompis/pipeline.py` | Coordinar las etapas y recoger diagnósticos/resultados |
| `scripts/ide.py`, `scripts/sqlcompis.py` | Interfaz gráfica y terminal |
| `examples`, `tests`, `docs/sql.pdf` | Ejemplos, pruebas y documentación técnica |

No se utiliza Lark, ANTLR, sqlparse, SQLite ni otro motor externo para analizar o ejecutar SQL. La interpretación de esta entrega es directa sobre el AST; no necesita generar TAC.

El análisis verifica tablas y columnas, referencias ambiguas, tipos, cantidad de valores, restricciones del esquema, agregaciones e índices. Cada subconsulta tiene un ámbito y puede resolver columnas del ámbito exterior. Una subconsulta escalar con más de una columna se rechaza al analizar; si devuelve más de una fila, se reporta al evaluarla, antes de escribir los cambios de la sentencia.

## Archivos de la base de datos

```text
database/
  metadata.json             # columnas, tipos, restricciones, índices y contadores
  tables/estudiantes.csv    # identificador interno y registros
  offsets/estudiantes.json  # identificador interno -> posición en bytes del CSV
  indexes/idx_edad.json     # valor de edad -> identificadores de registros
```

Cada celda del CSV conserva un valor JSON; así se distinguen `NULL`, texto y booleanos, incluso con comas, acentos o saltos de línea. Las fechas se almacenan en formato ISO. El catálogo y las restricciones se recuperan al abrir la misma carpeta.

Los índices no son decorativos: el plan obtiene identificadores candidatos del archivo del índice y lee sus registros con `seek` usando las posiciones persistidas. Para rangos se comparan las claves del índice; no se implementa un árbol B. `AND` permite intersectar candidatos; `OR` se optimiza sólo si ambos lados permiten un acceso correcto. Si no hay un predicado aprovechable, se recorre la tabla. Las escrituras reescriben el CSV y reconstruyen los índices afectados de manera consistente.

Cada sentencia de escritura valida antes de guardar y usa un diario de recuperación y reemplazos de archivos. Un fallo no deja una parte de esa sentencia aplicada. Un script no es una transacción: las sentencias anteriores completadas permanecen si una posterior falla durante su ejecución. El uso previsto es una aplicación por directorio de base de datos; no hay coordinación de escritores entre procesos independientes.

`NULL` usa lógica de tres valores: `WHERE` conserva sólo condiciones verdaderas, `COUNT(*)` cuenta filas y `COUNT(columna)` omite nulos. Las otras agregaciones omiten nulos y devuelven `NULL` si no hay valores. La división produce un número de punto flotante. `ORDER BY` coloca nulos primero en ASC y al final en DESC. No se debe editar el catálogo ni los CSV manualmente mientras se trabaja con una base.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas cubren generación sin caché, precedencia, CST/AST, diagnósticos, tipos, unicidad, persistencia tras abrir otra sesión, recuperación de escrituras, consultas, uniones, grupos, lógica con nulos, subconsultas correlacionadas, cardinalidad escalar, mantenimiento y uso real de índices. También ejecutan la CLI en procesos nuevos y verifican el IDE, incluyendo la limpieza de resultados después de un error. Las pruebas usan directorios temporales y no alteran las bases de trabajo.

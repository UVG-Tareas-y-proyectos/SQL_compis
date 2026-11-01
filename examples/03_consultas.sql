SELECT nombre, edad FROM estudiantes WHERE edad >= 18 AND activo = TRUE ORDER BY edad DESC;
SELECT e.nombre, c.nombre AS curso, i.nota
FROM estudiantes e
INNER JOIN inscripciones i ON e.id = i.estudiante_id
INNER JOIN cursos c ON c.id = i.curso_id
ORDER BY e.nombre, curso;
SELECT curso_id, COUNT(*) AS inscritos, AVG(nota) AS promedio, MIN(nota) AS minima, MAX(nota) AS maxima, SUM(nota) AS total
FROM inscripciones GROUP BY curso_id HAVING COUNT(*) >= 1 ORDER BY curso_id;

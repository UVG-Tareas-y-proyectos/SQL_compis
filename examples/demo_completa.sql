-- Ejecutar en una base vacía. En el IDE, Demo nueva prepara otra carpeta.
CREATE TABLE estudiantes (id INT PRIMARY KEY, nombre VARCHAR(60) NOT NULL, edad INT, activo BOOLEAN, ingreso DATE);
CREATE TABLE cursos (id INT PRIMARY KEY, nombre VARCHAR(60));
CREATE TABLE inscripciones (estudiante_id INT, curso_id INT, nota FLOAT);
INSERT INTO estudiantes VALUES
    (1,'Ana',20,TRUE,'2026-01-15'), (2,'Luis',17,FALSE,'2026-02-01'),
    (3,'José',22,TRUE,'2026-01-20'), (4,'Eva',19,TRUE,'2026-02-10');
INSERT INTO cursos VALUES (1,'Compiladores'),(2,'Bases de datos'),(3,'SQL');
INSERT INTO inscripciones VALUES (1,1,90),(1,3,95),(2,1,70),(3,3,85),(4,2,NULL);
CREATE INDEX idx_edad ON estudiantes(edad);
CREATE INDEX idx_inscrito ON inscripciones(estudiante_id);
SELECT nombre, edad FROM estudiantes WHERE edad>=20 ORDER BY edad DESC;
SELECT e.nombre, c.nombre AS curso, i.nota FROM estudiantes e
INNER JOIN inscripciones i ON e.id=i.estudiante_id
INNER JOIN cursos c ON c.id=i.curso_id ORDER BY e.nombre, curso;
SELECT curso_id, COUNT(*) AS cantidad, SUM(nota) AS total, AVG(nota) AS promedio,
MIN(nota) AS minima, MAX(nota) AS maxima FROM inscripciones
GROUP BY curso_id HAVING COUNT(*)>=1 ORDER BY curso_id;
SELECT nombre FROM estudiantes WHERE id IN
    (SELECT estudiante_id FROM inscripciones WHERE curso_id=3) ORDER BY nombre;
SELECT e.nombre FROM estudiantes e WHERE EXISTS
    (SELECT 1 FROM inscripciones i WHERE i.estudiante_id=e.id AND i.nota>=90);
SELECT nombre FROM estudiantes WHERE edad>(SELECT AVG(edad) FROM estudiantes);
UPDATE estudiantes SET edad=edad+1 WHERE id=2;
DELETE FROM inscripciones WHERE nota<75;
SELECT nombre, edad FROM estudiantes ORDER BY id;

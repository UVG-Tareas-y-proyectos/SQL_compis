CREATE INDEX idx_edad ON estudiantes (edad);
CREATE INDEX idx_estudiante ON inscripciones (estudiante_id);
SELECT nombre FROM estudiantes WHERE edad >= 20 ORDER BY nombre;
SELECT nombre FROM estudiantes
WHERE id IN (SELECT estudiante_id FROM inscripciones WHERE curso_id = 3)
ORDER BY nombre;
SELECT e.nombre FROM estudiantes e
WHERE EXISTS (SELECT 1 FROM inscripciones i WHERE i.estudiante_id = e.id AND i.nota >= 90);
SELECT nombre FROM estudiantes WHERE edad > (SELECT AVG(edad) FROM estudiantes);
SELECT e.nombre FROM estudiantes e WHERE NOT EXISTS
    (SELECT 1 FROM inscripciones i WHERE i.estudiante_id = e.id AND i.curso_id = 3);

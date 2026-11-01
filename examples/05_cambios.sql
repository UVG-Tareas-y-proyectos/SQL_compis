UPDATE estudiantes SET edad = edad + 1 WHERE id = 2;
DELETE FROM inscripciones WHERE nota < 75;
SELECT nombre, edad FROM estudiantes ORDER BY id;
SELECT * FROM inscripciones ORDER BY estudiante_id, curso_id;

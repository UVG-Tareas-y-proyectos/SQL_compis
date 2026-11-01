-- Se rechaza porque la subconsulta escalar devuelve varias filas.
SELECT nombre FROM estudiantes WHERE id = (SELECT estudiante_id FROM inscripciones);

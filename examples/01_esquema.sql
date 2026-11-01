CREATE TABLE estudiantes (
    id INT PRIMARY KEY,
    nombre VARCHAR(60) NOT NULL,
    edad INT,
    activo BOOLEAN DEFAULT TRUE,
    ingreso DATE
);
CREATE TABLE cursos (id INT PRIMARY KEY, nombre VARCHAR(60) NOT NULL);
CREATE TABLE inscripciones (
    estudiante_id INT NOT NULL,
    curso_id INT NOT NULL,
    nota FLOAT,
    PRIMARY KEY (estudiante_id, curso_id)
);

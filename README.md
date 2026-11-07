# IncluTalent Agent — MVP

MVP local para practicar entrevistas inclusivas y explorar vacantes de demostración. Incluye registro e inicio de sesión, perfiles separados por cuenta, preferencias de accesibilidad, preguntas adaptadas al nivel, retroalimentación orientativa, coincidencias explicables y métricas agregadas.

## Requisitos

- Python 3.8 o posterior
- No requiere paquetes adicionales ni conexión a internet

## Ejecutar

Desde esta carpeta:

```powershell
python app.py
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000) en el navegador. Detén el servidor con `Ctrl+C`.

Las cuentas, los perfiles y las métricas se guardan en `data.json`. Las contraseñas se almacenan como derivaciones PBKDF2-SHA256 con sal individual; la cookie de sesión es `HttpOnly`, `SameSite=Strict`, expira en 12 horas y solo su hash se guarda en el JSON. Las respuestas escritas de la entrevista no se guardan.

Si ya tenías información en el formato anterior del MVP, se conserva y se asigna a la primera cuenta que se registre. Para restablecer el proyecto, detén el servidor y reemplaza `data.json` con su estado inicial.

## Alcance del MVP

- Interfaz HTML y CSS adaptable, controles de alto contraste y navegación por teclado.
- API en Python usando solo la biblioteca estándar.
- Persistencia local en JSON; sin MongoDB ni PostgreSQL.
- Registro e inicio de sesión local, contraseñas con hash y aislamiento de datos por cuenta.
- Entrevista de práctica basada en preguntas predefinidas y evaluación transparente por palabras clave. No usa IA generativa ni toma decisiones de contratación.
- Vacantes y métricas de ejemplo, almacenadas y calculadas localmente.
- Diagramas UML de casos de uso, clases, componentes y secuencia en `docs/uml/`.

Es una demostración académica que escucha únicamente en `127.0.0.1`, no un sistema listo para producción. No guarda contraseñas en texto plano ni almacena información médica. La cuenta local no verifica la titularidad del correo ni incluye recuperación de contraseña. Antes de publicarla en internet harían falta HTTPS, protección operativa adicional, recuperación de cuenta, copias de seguridad seguras y una revisión de privacidad y accesibilidad.

## Pruebas

```powershell
python -m unittest
```

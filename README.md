# IncluTalent Agent

Link:https://youtu.be/p0fhPWkZKRs

Aplicación local para preparar entrevistas laborales, consultar vacantes de demostración y recibir feedback orientativo. Incluye cuentas separadas, perfil editable en cinco pasos, preferencias de accesibilidad, historial resumido y métricas agregadas.

## Requisitos

- Python 3.8 o posterior
- No requiere paquetes adicionales de Python
- Ollama es opcional; se necesita solo para usar el agente de IA local

## Ejecutar la aplicación

Abre PowerShell en esta carpeta y ejecuta:

```powershell
python app.py
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000) en el navegador. Detén la aplicación con `Ctrl+C`.

## Usar el agente Ollama

Instala Ollama y, desde PowerShell, descarga el modelo una vez:

```powershell
ollama pull llama3.2:1b
```

Ollama normalmente inicia su servicio automáticamente en Windows. Si no está activo, abre una segunda terminal, ejecuta `ollama serve` y déjala abierta. Después inicia IncluTalent con `python app.py` en otra terminal. En la pantalla de práctica, selecciona **Ollama · IA local**. También puedes seleccionar **Asesor local por reglas**, que no requiere Ollama.

La aplicación usa `llama3.2:1b` por defecto y se conecta únicamente a `http://127.0.0.1:11434`. Pide a Ollama mantener el modelo cargado durante 10 minutos entre consultas. Si prefieres respuestas más detalladas y tu equipo puede manejar un modelo mayor, descarga `qwen2.5:7b` y configura la variable antes de iniciar la aplicación:

```powershell
ollama pull qwen2.5:7b
$env:OLLAMA_MODEL = "qwen2.5:7b"
python app.py
```

El modelo más pequeño suele responder más rápido, aunque con menos detalle. La variable `OLLAMA_MODEL` se configura antes de iniciar `app.py`; reinicia la aplicación después de cambiarla. Si Ollama o el modelo seleccionado no están disponibles, se mostrará un error y no se cambiará de agente en silencio.

Las cuentas, los perfiles y los resultados resumidos se guardan en `data.json`. En Windows, la aplicación quita los permisos heredados del archivo y limita su acceso al usuario actual; en otros sistemas aplica permisos de archivo solo para el usuario. El JSON no está cifrado: evita guardar datos reales o sensibles y ten en cuenta que servicios de sincronización de carpetas podrían copiarlo.

Las contraseñas se almacenan como derivaciones PBKDF2-SHA256 con sal individual; la cookie de sesión es `HttpOnly`, `SameSite=Strict`, expira en 12 horas y solo su hash se guarda en el JSON. El límite temporal de intentos fallidos de inicio de sesión se cuenta por correo y no se reinicia al registrar otra cuenta. Las respuestas escritas no se guardan.

Los perfiles del formato anterior ya no se asignan a la primera cuenta nueva. Antes de ejecutar la versión nueva, exporta manualmente cualquier información antigua que quieras conservar. Usa “Eliminar perfil” para reiniciar las preferencias y el nombre; la cuenta y el resumen de prácticas se conservan.

## Alcance del MVP

- Interfaz HTML y CSS adaptable, controles de alto contraste y navegación por teclado.
- API en Python usando solo la biblioteca estándar. `app.py` arranca el servidor; autenticación, perfiles, entrevistas, catálogo, persistencia y rutas HTTP están separados en módulos.
- Persistencia local en JSON; sin MongoDB ni PostgreSQL.
- Registro e inicio de sesión local, contraseñas con hash y aislamiento de datos por cuenta.
- Perfil CRUD: consultar y actualizar preferencias, o reiniciarlas sin borrar la cuenta.
- Dos agentes de práctica: Ollama local genera preguntas y evalúa respuestas, o el asesor original por reglas como alternativa explícita. Ollama procesa el puesto y habilidades del perfil y el texto de respuesta solo en el equipo; la aplicación no se conecta a servicios de IA externos. Las dificultades tienen tiempos orientativos (90, 180 o 300 segundos), con opción sin cronómetro o tiempo extendido; al terminar el tiempo solo se muestra un aviso y nunca se envía la respuesta automáticamente.
- El agente por reglas ofrece feedback basado en habilidades relacionadas con la pregunta. Ollama genera sugerencias orientativas localmente; ninguna modalidad toma decisiones de contratación. Ningún agente debe preguntar ni puntuar orientación sexual, género, edad o diagnósticos; las preferencias de accesibilidad son opcionales y solo adaptan la experiencia y coincidencias laborales.
- Diseño oscuro inspirado en la referencia compartida, navegación por teclado, preferencias de accesibilidad y cronómetro pausables; estas medidas ayudan a practicar, pero no garantizan eliminar los sesgos de una contratación real.
- El simulador no ejecuta el código ni sustituye una entrevista o una evaluación técnica profesional. Su puntuación orientativa cuenta evidencia textual y palabras relacionadas con la pregunta; úsala como guía de reflexión, no como una medida objetiva de capacidad.
- Historial de prácticas con puesto, fecha y promedio orientativo; no almacena respuestas escritas.
- Vacantes y métricas de ejemplo, almacenadas y calculadas localmente.
- Siete puestos de demostración en tecnología, datos, soporte, comunicación, operaciones y administración.
- Diagramas UML de casos de uso, clases, componentes y secuencia en `docs/uml/`.

Es una demostración académica que escucha únicamente en `127.0.0.1`, no un sistema listo para producción. No guarda contraseñas en texto plano ni almacena información médica. La cuenta local no verifica la titularidad del correo ni incluye recuperación de contraseña. El límite de intentos se guarda en memoria y se reinicia al detener el servidor. Antes de publicarla en internet harían falta HTTPS, protección operativa adicional, recuperación de cuenta, cifrado, copias de seguridad seguras y una revisión de privacidad y accesibilidad.

## Pruebas

```powershell
python -m unittest
```

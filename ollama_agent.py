import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b").strip() or "llama3.2:1b"
OLLAMA_KEEP_ALIVE = "10m"
REQUEST_TIMEOUT = 120
DIFFICULTIES = {"easy", "intermediate", "advanced"}
QUESTION_TYPES = {"conversation", "code", "exercise"}


def _question_schema(types):
    return {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "minLength": 8, "maxLength": 240},
            "steps": {
                "type": "array",
                "minItems": 2,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 3, "maxLength": 100},
            },
            "skills": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "items": {"type": "string", "minLength": 2, "maxLength": 40},
            },
            "difficulty": {"type": "string", "enum": sorted(DIFFICULTIES)},
            "type": {"type": "string", "enum": types},
            "language": {"type": "string", "maxLength": 50},
            "starterCode": {"type": "string", "maxLength": 500},
        },
        "required": [
            "prompt",
            "steps",
            "skills",
            "difficulty",
            "type",
            "language",
            "starterCode",
        ],
        "additionalProperties": False,
    }


QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "prefixItems": [
                _question_schema(["conversation"]),
                _question_schema(["conversation"]),
                _question_schema(["conversation"]),
                _question_schema(["code", "exercise"]),
                _question_schema(["conversation"]),
            ],
        },
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def _chat(prompt, response_format="json", num_predict=800):
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un agente de practica laboral respetuoso e inclusivo. "
                    "Responde unicamente con JSON valido."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "format": response_format,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.2, "num_predict": num_predict},
    }).encode("utf-8")
    request = Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "No se pudo conectar con Ollama en 127.0.0.1:11434. "
            "Inicia Ollama y verifica que el modelo "
            f"'{OLLAMA_MODEL}' este instalado."
        ) from exc
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError(
            f"Ollama no pudo responder con el modelo '{OLLAMA_MODEL}'. "
            "Verifica el nombre del modelo y vuelve a intentarlo."
        )
    message = result.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise RuntimeError("Ollama devolvio una respuesta vacia o invalida.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama devolvio contenido que no es JSON valido.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Ollama devolvio una respuesta con formato invalido.")
    return parsed


def generate_questions(role_title, profile):
    skills = profile.get("skills") or []
    context = {
        "puesto": role_title,
        "nivel": profile.get("level", "junior"),
        "habilidades": skills[:8],
        "apoyos_solicitados": profile.get("accommodations", []),
    }
    prompt = (
        "Crea preguntas breves para una practica laboral en espanol. Usa el contexto del puesto "
        "y nivel. Escribe cuatro preguntas situacionales y un solo reto practico relacionado "
        "con el puesto. Solo evalua evidencia laboral; no preguntes ni infieras edad, genero, "
        "sexualidad, discapacidad, salud ni diagnosticos. Mantén un tono claro y respetuoso. "
        "La cuarta pregunta debe ser el reto; las otras cuatro son conversacionales. "
        "Para preguntas conversacionales, type debe ser conversation y starterCode debe ser "
        "una cadena vacia. En el reto usa code o exercise y agrega una plantilla breve si es util. "
        "Responde siguiendo exactamente el esquema JSON solicitado.\n"
        f"Contexto: {json.dumps(context, ensure_ascii=False)}"
    )
    result = _chat(prompt, QUESTION_SCHEMA, num_predict=900)
    questions = result.get("questions")
    if not isinstance(questions, list) or len(questions) != 5:
        raise RuntimeError("Ollama no genero exactamente cinco preguntas validas.")
    validated = []
    for question in questions:
        if not isinstance(question, dict):
            raise RuntimeError("Ollama genero una pregunta con formato invalido.")
        prompt_text = question.get("prompt")
        steps = question.get("steps")
        skills = question.get("skills")
        difficulty = question.get("difficulty")
        question_type = question.get("type")
        if (
            not isinstance(prompt_text, str)
            or not prompt_text.strip()
            or not isinstance(steps, list)
            or not 1 <= len(steps) <= 4
            or not all(isinstance(step, str) and step.strip() for step in steps)
            or not isinstance(skills, list)
            or not 1 <= len(skills) <= 8
            or not all(isinstance(skill, str) and skill.strip() for skill in skills)
            or not isinstance(difficulty, str)
            or difficulty not in DIFFICULTIES
            or not isinstance(question_type, str)
            or question_type not in QUESTION_TYPES
            or not isinstance(question.get("language", ""), str)
            or not isinstance(question.get("starterCode", ""), str)
        ):
            raise RuntimeError("Ollama genero una pregunta con campos invalidos.")
        validated.append({
            "prompt": prompt_text.strip(),
            "steps": [step.strip() for step in steps],
            "skills": [skill.strip() for skill in skills],
            "difficulty": difficulty,
            "type": question_type,
            "language": question.get("language", "").strip(),
            "starterCode": question.get("starterCode", "").strip(),
        })
    if sum(question["type"] != "conversation" for question in validated) != 1:
        raise RuntimeError("Ollama debe generar exactamente un reto practico.")
    return validated


def evaluate_with_ollama(answer, question, role_title):
    prompt = (
        "Evalua esta respuesta de practica laboral con criterios justos y relacionados "
        "exclusivamente con la pregunta y el puesto. No infieras caracteristicas personales "
        "ni penalices estilo, acento, ortografia o una respuesta breve por si solos. Da feedback "
        "respetuoso, concreto y util. Las palabras clave son evidencia posible, no requisitos "
        "obligatorios. Devuelve score (entero de 1 a 5), matched (arreglo con cero o mas "
        "elementos elegidos exclusivamente de skills de la pregunta) y feedback (string breve "
        "en espanol). No afirmes que ejecutaste o verificaste codigo.\n"
        f"Puesto: {role_title}\n"
        f"Pregunta: {question['prompt']}\n"
        f"Habilidades relacionadas: {json.dumps(question['skills'], ensure_ascii=False)}\n"
        f"Respuesta: {answer}"
    )
    evaluation_schema = {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5},
            "matched": {
                "type": "array",
                "items": {"type": "string", "enum": question["skills"]},
                "maxItems": len(question["skills"]),
            },
            "feedback": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
        "required": ["score", "matched", "feedback"],
        "additionalProperties": False,
    }
    result = _chat(prompt, evaluation_schema, num_predict=256)
    score = result.get("score")
    matched = result.get("matched")
    feedback = result.get("feedback")
    allowed_skills = set(question["skills"])
    if (
        not isinstance(score, int)
        or isinstance(score, bool)
        or not 1 <= score <= 5
        or not isinstance(matched, list)
        or not all(isinstance(skill, str) and skill in allowed_skills for skill in matched)
        or not isinstance(feedback, str)
        or not feedback.strip()
        or len(feedback) > 1000
    ):
        raise RuntimeError("Ollama devolvio una evaluacion con formato invalido.")
    if question["type"] == "code":
        feedback = (
            "La demo no ejecuta ni valida la sintaxis de tu codigo. "
            + feedback.strip()
        )
    return {
        "score": score,
        "matched": list(dict.fromkeys(matched)),
        "feedback": feedback.strip(),
    }

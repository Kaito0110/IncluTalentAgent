from copy import deepcopy
import re
import uuid
from datetime import datetime, timezone

import persistence
from catalog import JOBS, QUESTION_BANK
from ollama_agent import OLLAMA_MODEL, evaluate_with_ollama, generate_questions


AGENT_NAME = "Asesor local de entrevistas"
RULES_ENGINE = "rules"
OLLAMA_ENGINE = "ollama"
JOB_TITLES = {job["id"]: job["title"] for job in JOBS}
CUSTOM_SKILLS = ["resolucion de problemas", "comunicacion", "organizacion"]


def _normalized(text):
    text = text.lower()
    for original, replacement in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        text = text.replace(original, replacement)
    return re.sub(r"[^a-z0-9ñ ]+", " ", text)


def _job_title(profile, job_id=None):
    selected_id = profile.get("jobId") if job_id is None else job_id
    if selected_id == "custom":
        title = profile.get("customJobTitle", "").strip()
        if not title:
            raise ValueError("Completa tu puesto de interes en el perfil antes de practicar.")
        return title
    if not isinstance(selected_id, str) or selected_id not in JOB_TITLES:
        raise ValueError("Selecciona una vacante valida para la entrevista.")
    return JOB_TITLES[selected_id]


def _custom_questions(profile, role_title):
    skills = profile.get("skills") or CUSTOM_SKILLS
    focus = skills[0]
    return [
        {
            "prompt": f"Reto practico para {role_title}: muestra con codigo, pseudocodigo o pasos como usarias {focus} para resolver una necesidad concreta.",
            "steps": ["Describe la entrada o necesidad.", "Explica tu solucion paso a paso.", "Menciona el resultado y como lo comprobarías."],
            "skills": [focus, "problema", "resultado", "solucion", "paso"],
            "difficulty": "intermediate",
            "type": "code",
            "language": "Codigo o pseudocodigo",
            "starterCode": "// Explica tu enfoque, pseudocodigo o codigo.\n",
        },
        {
            "prompt": f"Cuentame un ejemplo de como has usado {focus} o una habilidad relacionada.",
            "steps": ["Da el contexto.", "Explica tu contribucion.", "Cuenta que aprendiste."],
            "skills": [focus, "ejemplo", "aprendi", "resultado"],
        },
        {
            "prompt": f"Si una tarea importante de {role_title} no sale como esperabas, que pasos seguirias?",
            "steps": ["Explica como entenderias la causa.", "Menciona que recursos consultarias.", "Di como comprobarías la solucion."],
            "skills": ["causa", "revisar", "equipo", "probar", "solucion"],
        },
        {
            "prompt": "Como organizarias varias tareas con fechas de entrega cercanas?",
            "steps": ["Menciona como aclararias prioridades.", "Explica como dividirias el trabajo.", "Di como avisarias de un bloqueo."],
            "skills": ["prioridad", "organizar", "plan", "equipo", "comunicar"],
        },
        {
            "prompt": f"Como compartirias con un equipo el resultado de tu trabajo en {role_title}?",
            "steps": ["Explica que resultado resumirias.", "Menciona la evidencia que incluirias.", "Di que siguiente paso propondrías."],
            "skills": ["resultado", "evidencia", "comunicar", "equipo", "siguiente paso"],
        },
    ]


def build_interview_plan(profile, job_id=None):
    selected_id = profile.get("jobId") if job_id is None else job_id
    role_title = _job_title(profile, selected_id)
    if selected_id == "custom":
        questions = _custom_questions(profile, role_title)
    else:
        questions = QUESTION_BANK[selected_id]
    difficulty_by_index = ["easy", "easy", "intermediate", "intermediate", "advanced"]
    plan = []
    for index, question in enumerate(questions):
        item = dict(question)
        item.setdefault("difficulty", difficulty_by_index[index])
        item.setdefault("type", "conversation")
        plan.append(item)
    return role_title, plan


def evaluate_answer(answer, question, role_title):
    normalized_answer = f" {_normalized(answer)} "
    matched = [
        skill for skill in question["skills"]
        if f" {_normalized(skill)} " in normalized_answer
    ]
    word_count = len(normalized_answer.split())
    score = min(5, 1 + len(matched) + (1 if word_count >= 12 else 0))
    if matched:
        focus = ", ".join(matched[:2])
        feedback = (
            f"Relacionaste tu respuesta con {focus}, importante para {role_title}. "
            "Para hacerla mas clara, agrega el resultado y como sabrias que funciono."
        )
    else:
        focus = question["skills"][0]
        feedback = (
            f"Para {role_title}, intenta incluir un ejemplo concreto y explicar como usarias "
            f"{focus} en esta situacion."
        )
    if question["type"] == "code":
        feedback = (
            "La demo no ejecuta ni valida la sintaxis de tu código; el feedback solo revisa términos y explicación. "
            + feedback
        )
    if word_count < 12:
        feedback += " Puedes ampliar un poco el contexto, tus acciones y el resultado."
    return {"score": score, "matched": matched, "feedback": feedback}


def _public_question(question, index, show_steps, total):
    time_limits = {"easy": 90, "intermediate": 180, "advanced": 300}
    return {
        "index": index,
        "total": total,
        "prompt": question["prompt"],
        "steps": question["steps"] if show_steps else [],
        "difficulty": question["difficulty"],
        "type": question["type"],
        "timeLimit": time_limits[question["difficulty"]],
        "language": question.get("language", ""),
        "starterCode": question.get("starterCode", ""),
    }


def start_interview(user_id, requested_job_id=None, engine=RULES_ENGINE):
    if not isinstance(engine, str) or engine not in {RULES_ENGINE, OLLAMA_ENGINE}:
        raise ValueError("Selecciona un agente de entrevista valido.")
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        profile = deepcopy(user["profile"])
    role_title = _job_title(
        profile,
        profile.get("jobId") if requested_job_id is None else requested_job_id,
    )
    if engine == OLLAMA_ENGINE:
        questions = generate_questions(role_title, profile)
    else:
        role_title, questions = build_interview_plan(profile, requested_job_id)
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        adapted = bool(profile.get("accommodations"))
        show_steps = "pasos_desglosados" in profile.get("accommodations", [])
        session = {
            "id": uuid.uuid4().hex,
            "jobId": profile.get("jobId") if requested_job_id is None else requested_job_id,
            "jobTitle": role_title,
            "questions": questions,
            "engine": engine,
            "status": "active",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "adapted": adapted,
            "showSteps": show_steps,
            "results": [],
        }
        user["sessions"].append(session)
        persistence._write_store(data)
    return {
        "sessionId": session["id"],
        "total": len(questions),
        "jobTitle": role_title,
        "agentName": f"Ollama · {OLLAMA_MODEL}" if engine == OLLAMA_ENGINE else AGENT_NAME,
        "question": _public_question(questions[0], 0, show_steps, len(questions)),
    }


def answer_interview(user_id, payload):
    session_id = str(payload.get("sessionId", ""))
    answer = payload.get("answer")
    if not isinstance(answer, str):
        raise ValueError("Escribe una respuesta de entre 4 y 4,000 caracteres.")
    answer = answer.strip()
    if len(answer) < 4 or len(answer) > 4000:
        raise ValueError("Escribe una respuesta de entre 4 y 4,000 caracteres.")
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        session = next((item for item in user["sessions"] if item["id"] == session_id), None)
        if not session or session["status"] != "active":
            raise ValueError("La entrevista no esta activa. Inicia una nueva practica.")
        questions = session["questions"]
        index = len(session["results"])
        if index >= len(questions):
            raise ValueError("Esta entrevista ya termino.")
        question = deepcopy(questions[index])
        role_title = session["jobTitle"]
        engine = session.get("engine", RULES_ENGINE)
    if engine == OLLAMA_ENGINE:
        result = evaluate_with_ollama(answer, question, role_title)
    else:
        result = evaluate_answer(answer, question, role_title)
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        session = next(
            (item for item in user["sessions"] if item["id"] == session_id),
            None,
        )
        if (
            not session
            or session["status"] != "active"
            or len(session["results"]) != index
        ):
            raise ValueError(
                "La entrevista cambio mientras se evaluaba la respuesta. "
                "Revisa el estado de la practica e intenta de nuevo."
            )
        session["results"].append({"score": result["score"], "matched": result["matched"]})
        if len(session["results"]) == len(questions):
            session["status"] = "completed"
            session["completedAt"] = datetime.now(timezone.utc).isoformat()
            response = {"finished": True, "result": result, "summary": _interview_summary(session)}
        else:
            response = {
                "finished": False,
                "result": result,
                "question": _public_question(
                    questions[index + 1],
                    index + 1,
                    session.get("showSteps", False),
                    len(questions),
                ),
            }
        persistence._write_store(data)
    return response


def _interview_summary(session):
    results = session["results"]
    return {
        "jobTitle": session["jobTitle"],
        "average": round(sum(item["score"] for item in results) / len(results), 1),
        "responses": len(results),
        "strengths": sorted({skill for item in results for skill in item["matched"]})[:6],
    }

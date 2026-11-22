from datetime import datetime

import persistence
from catalog import ACCOMMODATIONS, DEFAULT_PROFILE, JOBS
from jobs import match_jobs


JOB_IDS = {job["id"] for job in JOBS}
ALLOWED_LEVELS = {"trainee", "junior", "intermedio"}


def _copy_default_profile():
    profile = dict(DEFAULT_PROFILE)
    profile["skills"] = []
    profile["accommodations"] = []
    return profile


def _recent_interviews(sessions):
    history = []
    for session in reversed(sessions):
        if session.get("status") != "completed":
            continue
        results = session.get("results", [])
        scores = [item["score"] for item in results]
        history.append({
            "jobTitle": session.get("jobTitle", "Puesto de practica"),
            "completedAt": session.get("completedAt", ""),
            "average": round(sum(scores) / len(scores), 1) if scores else 0,
            "responses": len(scores),
        })
        if len(history) == 5:
            break
    return history


def get_state(user_id):
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        profile = dict(user["profile"])
        sessions = list(user["sessions"])
    completed = [item for item in sessions if item.get("status") == "completed"]
    scores = [result["score"] for item in completed for result in item.get("results", [])]
    return {
        "profile": profile,
        "accommodations": ACCOMMODATIONS,
        "jobOptions": [{"id": job["id"], "title": job["title"], "company": job["company"]} for job in JOBS],
        "jobs": match_jobs(profile),
        "recentInterviews": _recent_interviews(sessions),
        "metrics": {
            "interviews": len(completed),
            "adapted": sum(1 for item in completed if item.get("adapted")),
            "responses": len(scores),
            "averageScore": round(sum(scores) / len(scores), 1) if scores else 0,
            "inclusionRate": round(
                100 * sum(1 for item in completed if item.get("adapted")) / len(completed)
            ) if completed else 0,
        },
    }


def save_profile(user_id, payload):
    name = payload.get("name", "")
    level = payload.get("level")
    job_id = payload.get("jobId")
    custom_job_title = payload.get("customJobTitle", "")
    skills = payload.get("skills", [])
    accommodations = payload.get("accommodations", [])
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError("Escribe un nombre de entre 1 y 80 caracteres.")
    if not isinstance(level, str) or level not in ALLOWED_LEVELS:
        raise ValueError("Selecciona un nivel de experiencia valido.")
    if job_id == "custom":
        if not isinstance(custom_job_title, str) or not custom_job_title.strip() or len(custom_job_title.strip()) > 120:
            raise ValueError("Escribe un puesto de entre 1 y 120 caracteres.")
        custom_job_title = custom_job_title.strip()
    elif not isinstance(job_id, str) or job_id not in JOB_IDS:
        raise ValueError("Selecciona una vacante o un puesto valido.")
    else:
        custom_job_title = ""
    if not isinstance(skills, list) or len(skills) > 8:
        raise ValueError("Agrega hasta 8 habilidades o herramientas.")
    clean_skills = []
    for skill in skills:
        if not isinstance(skill, str) or len(skill.strip()) > 40:
            raise ValueError("Cada habilidad puede tener hasta 40 caracteres.")
        if skill.strip():
            clean_skills.append(skill.strip())
    if not isinstance(accommodations, list) or any(
        not isinstance(item, str) or item not in ACCOMMODATIONS for item in accommodations
    ):
        raise ValueError("Revisa las preferencias de accesibilidad seleccionadas.")
    profile = {
        "name": name.strip(),
        "level": level,
        "jobId": job_id,
        "customJobTitle": custom_job_title,
        "skills": list(dict.fromkeys(clean_skills)),
        "accommodations": list(dict.fromkeys(accommodations)),
    }
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        user["profile"] = profile
        persistence._write_store(data)
    return profile


def delete_profile(user_id):
    with persistence.STORE_LOCK:
        data = persistence._read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        user["profile"] = _copy_default_profile()
        persistence._write_store(data)
    return {"profile": user["profile"], "deleted": True}

import json
import hashlib
import hmac
import os
import re
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, urlsplit


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_FILE = ROOT / "data.json"
STORE_LOCK = threading.Lock()
MAX_BODY_SIZE = 32_000
PASSWORD_ITERATIONS = 600_000
SESSION_LIFETIME = timedelta(hours=12)
SESSION_COOKIE = "inclutalent_session"
LOGIN_ATTEMPT_WINDOW = 600
LOGIN_ATTEMPT_LIMIT = 8
LOGIN_ATTEMPTS = {}
LOGIN_ATTEMPTS_LOCK = threading.Lock()

ACCOMMODATIONS = {
    "preguntas_claras": "Preguntas directas y sin dobles sentidos",
    "pasos_desglosados": "Instrucciones divididas en pasos",
    "tiempo_flexible": "Tiempo flexible para responder",
    "pausas": "Pausas entre preguntas",
    "lector_pantalla": "Compatibilidad con lector de pantalla",
    "baja_estimulacion": "Interfaz de baja estimulacion",
    "trabajo_remoto": "Opcion de trabajo remoto",
}

JOBS = [
    {
        "id": "frontend-jr",
        "title": "Desarrollador/a Frontend Jr.",
        "company": "Nube Abierta",
        "area": "Tecnologia",
        "level": "junior",
        "location": "Remoto · Mexico",
        "summary": "Construye interfaces web accesibles junto a un equipo colaborativo.",
        "supports": ["trabajo_remoto", "tiempo_flexible", "lector_pantalla"],
        "skills": ["HTML", "CSS", "JavaScript"],
    },
    {
        "id": "qa-trainee",
        "title": "Analista QA Trainee",
        "company": "Prisma Digital",
        "area": "Calidad de software",
        "level": "trainee",
        "location": "Hibrido · Guadalajara",
        "summary": "Ayuda a probar productos digitales con procesos claros y documentados.",
        "supports": ["tiempo_flexible", "baja_estimulacion", "pasos_desglosados"],
        "skills": ["Atencion al detalle", "Pruebas", "Documentacion"],
    },
    {
        "id": "support-jr",
        "title": "Especialista de soporte digital",
        "company": "Conecta",
        "area": "Experiencia de cliente",
        "level": "junior",
        "location": "Remoto · Mexico",
        "summary": "Resuelve dudas por escrito y mejora guias de ayuda para usuarios.",
        "supports": ["trabajo_remoto", "preguntas_claras", "pausas"],
        "skills": ["Comunicacion escrita", "Resolucion de problemas", "Empatia"],
    },
    {
        "id": "data-mid",
        "title": "Analista de datos",
        "company": "Bosque Labs",
        "area": "Datos",
        "level": "intermedio",
        "location": "Remoto · Mexico",
        "summary": "Transforma datos en hallazgos utiles para equipos de producto.",
        "supports": ["trabajo_remoto", "tiempo_flexible", "lector_pantalla"],
        "skills": ["SQL", "Analisis", "Visualizacion"],
    },
]

QUESTION_BANK = {
    "frontend-jr": [
        {
            "prompt": "Cuentame como resolverias un problema de diseno en una pagina web.",
            "steps": ["Describe el problema.", "Explica que cambiarias.", "Menciona como comprobarías el resultado."],
            "skills": ["problema", "usuario", "probar", "prueba", "accesibilidad", "html", "css", "solucion"],
        },
        {
            "prompt": "Como haces que un formulario sea facil de usar?",
            "steps": ["Menciona una etiqueta o instruccion clara.", "Explica como avisarias de un error.", "Di como probarías el formulario."],
            "skills": ["etiqueta", "label", "error", "teclado", "usuario", "prueba", "validacion", "accesible"],
        },
        {
            "prompt": "Que harias si una tarea tecnica no funciona como esperabas?",
            "steps": ["Explica como encontrarias la causa.", "Menciona una herramienta o persona que consultarias.", "Cuenta como verificarias la solucion."],
            "skills": ["revisar", "error", "consola", "documentacion", "equipo", "probar", "solucion"],
        },
    ],
    "qa-trainee": [
        {
            "prompt": "Como probarías que un formulario funciona correctamente?",
            "steps": ["Menciona un caso normal.", "Menciona un dato incorrecto o vacio.", "Explica que resultado esperas."],
            "skills": ["caso", "dato", "error", "resultado", "validacion", "probar", "documentar"],
        },
        {
            "prompt": "Que informacion incluirias al reportar un error?",
            "steps": ["Explica como repetir el error.", "Menciona el resultado esperado y el observado.", "Di como adjuntarias evidencia."],
            "skills": ["pasos", "reproducir", "esperado", "observado", "captura", "evidencia", "documentar"],
        },
        {
            "prompt": "Que harias si encuentras un error poco antes de una entrega?",
            "steps": ["Explica como confirmarias el error.", "Menciona a quien avisarias.", "Di como ayudarias a priorizarlo."],
            "skills": ["confirmar", "equipo", "prioridad", "impacto", "reporte", "documentar"],
        },
    ],
    "support-jr": [
        {
            "prompt": "Como ayudarias a una persona que no puede completar una tarea en una aplicacion?",
            "steps": ["Explica que preguntarias primero.", "Describe una instruccion clara.", "Di como confirmarias que funciono."],
            "skills": ["preguntar", "escuchar", "paso", "instruccion", "confirmar", "solucion", "documentar"],
        },
        {
            "prompt": "Que harias si no conoces la respuesta a una consulta?",
            "steps": ["Explica que le dirias a la persona.", "Menciona como buscarías la respuesta.", "Di como darías seguimiento."],
            "skills": ["comunicar", "buscar", "equipo", "documentacion", "seguimiento", "respuesta"],
        },
        {
            "prompt": "Como mejorarias una guia de ayuda que causa confusion?",
            "steps": ["Explica como detectarias la confusion.", "Menciona un cambio concreto.", "Di como comprobarías la mejora."],
            "skills": ["claro", "pasos", "usuario", "probar", "comentarios", "mejora", "ejemplo"],
        },
    ],
    "data-mid": [
        {
            "prompt": "Como investigarías una diferencia inesperada en un reporte?",
            "steps": ["Describe como validarias los datos.", "Explica que consulta o comparacion harías.", "Di como compartirias el hallazgo."],
            "skills": ["validar", "sql", "consulta", "origen", "comparar", "datos", "documentar"],
        },
        {
            "prompt": "Como eliges una visualizacion para explicar una tendencia?",
            "steps": ["Explica que pregunta debe responder.", "Menciona el tipo de grafica.", "Di como comprobarías que se entiende."],
            "skills": ["pregunta", "grafica", "visualizacion", "audiencia", "tendencia", "probar", "contexto"],
        },
        {
            "prompt": "Como priorizarias solicitudes de analisis de distintos equipos?",
            "steps": ["Menciona como aclararias el objetivo.", "Explica como compararias impacto y esfuerzo.", "Di como comunicarias prioridades."],
            "skills": ["objetivo", "impacto", "esfuerzo", "equipo", "prioridad", "comunicar"],
        },
    ],
}

DEFAULT_PROFILE = {
    "name": "",
    "level": "junior",
    "accommodations": ["preguntas_claras", "tiempo_flexible"],
}


def _read_store():
    if not DATA_FILE.exists():
        return {"users": {}, "auth_sessions": {}}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("No se pudo leer data.json") from exc
    if not isinstance(data, dict):
        raise RuntimeError("El formato de data.json no es valido")
    if "users" not in data:
        data = {
            "users": {},
            "auth_sessions": {},
            "_legacy_profile": data.get("profile", DEFAULT_PROFILE.copy()),
            "_legacy_sessions": data.get("sessions", []),
        }
    if not isinstance(data.get("users"), dict) or not isinstance(data.get("auth_sessions"), dict):
        raise RuntimeError("El formato de cuentas en data.json no es valido")
    return data


def _write_store(data):
    temporary = DATA_FILE.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(temporary, DATA_FILE)
    except OSError as exc:
        raise RuntimeError("No se pudo guardar data.json") from exc


def _normalized(text):
    text = text.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    return re.sub(r"[^a-z0-9ñ ]+", " ", text)


def evaluate_answer(answer, question):
    words = _normalized(answer)
    matched = [skill for skill in question["skills"] if _normalized(skill) in words]
    score = min(5, 2 + len(matched))
    if len(words.split()) < 4:
        score = min(score, 2)
    return {
        "score": score,
        "matched": matched,
        "feedback": (
            "Incluiste ejemplos relacionados con la competencia."
            if matched
            else "Podrias agregar un ejemplo concreto y explicar como comprobarías el resultado."
        ),
    }


def match_jobs(profile):
    level = profile.get("level", "junior")
    preferences = set(profile.get("accommodations", []))
    matches = []
    for job in JOBS:
        level_match = job["level"] == level
        relevant = preferences.intersection(job["supports"])
        support_fit = len(relevant) / len(preferences) if preferences else 1
        score = round((70 if level_match else 35) + support_fit * 30)
        matches.append({
            **job,
            "match": min(score, 100),
            "matchedSupports": sorted(relevant),
            "levelMatch": level_match,
        })
    return sorted(matches, key=lambda job: (-job["match"], job["title"]))


def _normalize_email(email):
    if not isinstance(email, str):
        raise ValueError("Escribe un correo electronico valido.")
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Escribe un correo electronico valido.")
    return email


def _password_digest(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    ).hex()


DUMMY_PASSWORD_SALT = b"inclutalent-mvp-dummy-salt"
DUMMY_PASSWORD_HASH = _password_digest("unavailable-password", DUMMY_PASSWORD_SALT)


def _check_auth_rate_limit(client_key):
    now = datetime.now(timezone.utc).timestamp()
    with LOGIN_ATTEMPTS_LOCK:
        recent = [item for item in LOGIN_ATTEMPTS.get(client_key, []) if now - item < LOGIN_ATTEMPT_WINDOW]
        if len(recent) >= LOGIN_ATTEMPT_LIMIT:
            LOGIN_ATTEMPTS[client_key] = recent
            return True
        recent.append(now)
        LOGIN_ATTEMPTS[client_key] = recent
        return False


def _clear_auth_rate_limit(client_key):
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.pop(client_key, None)


def _new_auth_session(data, user_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    data["auth_sessions"][token_hash] = {
        "user_id": user_id,
        "expires_at": (datetime.now(timezone.utc) + SESSION_LIFETIME).timestamp(),
    }
    return token


def register_user(payload):
    email = _normalize_email(payload.get("email"))
    password = payload.get("password")
    name = payload.get("name")
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise ValueError("La contrasena debe tener entre 10 y 128 caracteres.")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError("Escribe un nombre de entre 1 y 80 caracteres.")
    salt = secrets.token_bytes(16)
    user_id = uuid.uuid4().hex
    user = {
        "email": email,
        "password_salt": salt.hex(),
        "password_hash": _password_digest(password, salt),
        "profile": {
            "name": name.strip(),
            "level": DEFAULT_PROFILE["level"],
            "accommodations": DEFAULT_PROFILE["accommodations"].copy(),
        },
        "sessions": [],
    }
    with STORE_LOCK:
        data = _read_store()
        if any(existing.get("email") == email for existing in data["users"].values()):
            raise ValueError("No se pudo crear la cuenta. Revisa los datos o inicia sesion.")
        if not data["users"] and "_legacy_profile" in data:
            legacy_profile = data.pop("_legacy_profile")
            legacy_sessions = data.pop("_legacy_sessions", [])
            if isinstance(legacy_profile, dict):
                user["profile"] = legacy_profile
                user["profile"]["name"] = name.strip()
            if isinstance(legacy_sessions, list):
                user["sessions"] = legacy_sessions
        data["users"][user_id] = user
        token = _new_auth_session(data, user_id)
        _write_store(data)
    return {"token": token, "user": {"email": email, "profile": user["profile"]}}


def login_user(payload):
    email = _normalize_email(payload.get("email"))
    password = payload.get("password")
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise ValueError("Correo o contrasena incorrectos.")
    with STORE_LOCK:
        data = _read_store()
        user_id = next(
            (key for key, user in data["users"].items() if user.get("email") == email),
            None,
        )
        user = data["users"].get(user_id) if user_id else None
        if user:
            salt = bytes.fromhex(user["password_salt"])
            expected = user["password_hash"]
        else:
            salt = DUMMY_PASSWORD_SALT
            expected = DUMMY_PASSWORD_HASH
    actual = _password_digest(password, salt)
    if not user or not hmac.compare_digest(actual, expected):
        raise ValueError("Correo o contrasena incorrectos.")
    with STORE_LOCK:
        data = _read_store()
        if user_id not in data["users"]:
            raise ValueError("Correo o contrasena incorrectos.")
        user = data["users"][user_id]
        now = datetime.now(timezone.utc).timestamp()
        data["auth_sessions"] = {
            key: value for key, value in data["auth_sessions"].items()
            if value.get("expires_at", 0) > now
        }
        token = _new_auth_session(data, user_id)
        _write_store(data)
    return {"token": token, "user": {"email": email, "profile": user["profile"]}}


def authenticate_token(token):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with STORE_LOCK:
        data = _read_store()
        session = data["auth_sessions"].get(token_hash)
        if not session or session.get("expires_at", 0) <= datetime.now(timezone.utc).timestamp():
            return None
        if session.get("user_id") not in data["users"]:
            return None
        return session["user_id"]


def revoke_token(token):
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with STORE_LOCK:
        data = _read_store()
        if data["auth_sessions"].pop(token_hash, None) is not None:
            _write_store(data)


def get_state(user_id):
    with STORE_LOCK:
        data = _read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        profile = user["profile"]
        sessions = user["sessions"]
    completed = [item for item in sessions if item.get("status") == "completed"]
    scores = [result["score"] for item in completed for result in item.get("results", [])]
    return {
        "profile": profile,
        "accommodations": ACCOMMODATIONS,
        "jobs": match_jobs(profile),
        "metrics": {
            "interviews": len(completed),
            "adapted": sum(1 for item in completed if item.get("adapted")),
            "responses": len(scores),
            "averageScore": round(sum(scores) / len(scores), 1) if scores else 0,
            "inclusionRate": round(100 * sum(1 for item in completed if item.get("adapted")) / len(completed)) if completed else 0,
        },
    }


def save_profile(user_id, payload):
    name = str(payload.get("name", "")).strip()
    level = payload.get("level")
    accommodations = payload.get("accommodations", [])
    allowed_levels = {"trainee", "junior", "intermedio"}
    if not name or len(name) > 80:
        raise ValueError("Escribe un nombre de entre 1 y 80 caracteres.")
    if not isinstance(level, str) or level not in allowed_levels:
        raise ValueError("Selecciona un nivel de experiencia valido.")
    if not isinstance(accommodations, list) or any(
        not isinstance(item, str) or item not in ACCOMMODATIONS for item in accommodations
    ):
        raise ValueError("Revisa las preferencias de accesibilidad seleccionadas.")
    profile = {"name": name, "level": level, "accommodations": list(dict.fromkeys(accommodations))}
    with STORE_LOCK:
        data = _read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        user["profile"] = profile
        _write_store(data)
    return profile


def start_interview(user_id):
    with STORE_LOCK:
        data = _read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        profile = user["profile"]
        job_id = next((job["id"] for job in JOBS if job["level"] == profile["level"]), JOBS[0]["id"])
        questions = QUESTION_BANK[job_id]
        session = {
            "id": uuid.uuid4().hex,
            "jobId": job_id,
            "status": "active",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "adapted": bool(profile.get("accommodations")),
            "results": [],
        }
        user["sessions"].append(session)
        _write_store(data)
    return {"sessionId": session["id"], "total": len(questions), "question": _public_question(questions[0], 0, profile)}


def _public_question(question, index, profile):
    return {
        "index": index,
        "total": 3,
        "prompt": question["prompt"],
        "steps": question["steps"] if "pasos_desglosados" in profile.get("accommodations", []) else [],
    }


def answer_interview(user_id, payload):
    session_id = str(payload.get("sessionId", ""))
    answer = str(payload.get("answer", "")).strip()
    if len(answer) < 4 or len(answer) > 4000:
        raise ValueError("Escribe una respuesta de entre 4 y 4,000 caracteres.")
    with STORE_LOCK:
        data = _read_store()
        user = data["users"].get(user_id)
        if not user:
            raise ValueError("La cuenta ya no esta disponible.")
        session = next((item for item in user["sessions"] if item["id"] == session_id), None)
        if not session or session["status"] != "active":
            raise ValueError("La entrevista no esta activa. Inicia una nueva practica.")
        questions = QUESTION_BANK[session["jobId"]]
        index = len(session["results"])
        if index >= len(questions):
            raise ValueError("Esta entrevista ya termino.")
        result = evaluate_answer(answer, questions[index])
        session["results"].append({"score": result["score"], "matched": result["matched"]})
        if len(session["results"]) == len(questions):
            session["status"] = "completed"
            session["completedAt"] = datetime.now(timezone.utc).isoformat()
            response = {"finished": True, "result": result, "summary": _interview_summary(session)}
        else:
            profile = user["profile"]
            response = {
                "finished": False,
                "result": result,
                "question": _public_question(questions[index + 1], index + 1, profile),
            }
        _write_store(data)
    return response


def _interview_summary(session):
    results = session["results"]
    return {
        "average": round(sum(item["score"] for item in results) / len(results), 1),
        "responses": len(results),
        "strengths": sorted({skill for item in results for skill in item["matched"]})[:6],
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "IncluTalentMVP/1.0"

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args))

    def _send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        if headers:
            for name, value in headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _session_token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _current_user_id(self):
        return authenticate_token(self._session_token())

    def _session_cookie(self, token, max_age):
        secure = "; Secure" if getattr(self.connection, "cipher", None) else ""
        return (
            f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; "
            f"Max-Age={max_age}{secure}"
        )

    def _check_same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        return parsed.scheme in {"http", "https"} and parsed.netloc == self.headers.get("Host")

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Longitud de solicitud invalida.")
        if size < 1 or size > MAX_BODY_SIZE:
            raise ValueError("La solicitud esta vacia o es demasiado grande.")
        try:
            return json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("El cuerpo debe contener JSON valido.") from exc

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/me":
            user_id = self._current_user_id()
            self._send_json(200, {"authenticated": bool(user_id)})
            return
        if path == "/api/state":
            try:
                user_id = self._current_user_id()
                if not user_id:
                    self._send_json(401, {"error": "Inicia sesion para continuar."})
                    return
                self._send_json(200, get_state(user_id))
            except ValueError as exc:
                self._send_json(401, {"error": str(exc)})
            except RuntimeError as exc:
                self._send_json(500, {"error": str(exc)})
            return
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        item = files.get(path)
        if not item:
            self._send_json(404, {"error": "No se encontro el recurso solicitado."})
            return
        file_path = STATIC_DIR / item[0]
        try:
            content = file_path.read_bytes()
        except OSError:
            self._send_json(500, {"error": "No se pudo leer un archivo de la interfaz."})
            return
        self.send_response(200)
        self.send_header("Content-Type", item[1])
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {
            "/api/register", "/api/login", "/api/logout", "/api/profile",
            "/api/interview/start", "/api/interview/answer",
        }:
            self._send_json(404, {"error": "No se encontro la operacion solicitada."})
            return
        if not self._check_same_origin():
            self._send_json(403, {"error": "La solicitud debe provenir de esta aplicacion."})
            return
        try:
            payload = self._body()
            if not isinstance(payload, dict):
                raise ValueError("El cuerpo debe ser un objeto JSON.")
            if path in {"/api/register", "/api/login"}:
                client_key = self.client_address[0]
                if _check_auth_rate_limit(client_key):
                    self._send_json(429, {"error": "Demasiados intentos. Espera unos minutos e intenta de nuevo."})
                    return
                result = register_user(payload) if path == "/api/register" else login_user(payload)
                _clear_auth_rate_limit(client_key)
                self._send_json(
                    200,
                    {"authenticated": True},
                    {"Set-Cookie": self._session_cookie(result["token"], int(SESSION_LIFETIME.total_seconds()))},
                )
                return
            token = self._session_token()
            user_id = authenticate_token(token)
            if path == "/api/logout":
                revoke_token(token)
                self._send_json(
                    200,
                    {"authenticated": False},
                    {"Set-Cookie": self._session_cookie("", 0)},
                )
                return
            if not user_id:
                self._send_json(401, {"error": "Inicia sesion para continuar."})
                return
            if path == "/api/profile":
                result = save_profile(user_id, payload)
            elif path == "/api/interview/start":
                result = start_interview(user_id)
            else:
                result = answer_interview(user_id, payload)
            self._send_json(200, result)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except RuntimeError as exc:
            self._send_json(500, {"error": str(exc)})


if __name__ == "__main__":
    with STORE_LOCK:
        if not DATA_FILE.exists():
            _write_store({"users": {}, "auth_sessions": {}})
    server = ThreadingHTTPServer(("127.0.0.1", 8000), AppHandler)
    print("IncluTalent Agent disponible en http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()

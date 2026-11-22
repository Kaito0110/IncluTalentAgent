import json
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urlsplit

import auth
import persistence
from interview_agent import answer_interview, start_interview
from profiles import delete_profile, get_state, save_profile


STATIC_DIR = persistence.ROOT / "static"
MAX_BODY_SIZE = 32_000
SESSION_COOKIE = auth.SESSION_COOKIE
SESSION_LIFETIME = auth.SESSION_LIFETIME


class AppHandler(BaseHTTPRequestHandler):
    server_version = "IncluTalentMVP/2.0"

    GET_ROUTES = {
        "/api/me": "_get_me",
        "/api/state": "_get_state",
        "/": "_get_index",
        "/styles.css": "_get_styles",
        "/app.js": "_get_script",
    }
    POST_ROUTES = {
        "/api/register": "_post_register",
        "/api/login": "_post_login",
        "/api/logout": "_post_logout",
        "/api/profile": "_post_profile",
        "/api/interview/start": "_post_start_interview",
        "/api/interview/answer": "_post_answer_interview",
    }
    DELETE_ROUTES = {
        "/api/profile": "_delete_profile",
    }
    STATIC_FILES = {
        "_get_index": ("index.html", "text/html; charset=utf-8"),
        "_get_styles": ("styles.css", "text/css; charset=utf-8"),
        "_get_script": ("app.js", "text/javascript; charset=utf-8"),
    }

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
        return auth.authenticate_token(self._session_token())

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
        except ValueError as exc:
            raise ValueError("Longitud de solicitud invalida.") from exc
        if size < 1 or size > MAX_BODY_SIZE:
            raise ValueError("La solicitud esta vacia o es demasiado grande.")
        try:
            return json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("El cuerpo debe contener JSON valido.") from exc

    def _dispatch(self, routes, read_body=False):
        route_name = routes.get(urlparse(self.path).path)
        if not route_name:
            self._send_json(404, {"error": "No se encontro la operacion solicitada."})
            return
        if self.command in {"POST", "DELETE"} and not self._check_same_origin():
            self._send_json(403, {"error": "La solicitud debe provenir de esta aplicacion."})
            return
        try:
            payload = self._body() if read_body else {}
            if not isinstance(payload, dict):
                raise ValueError("El cuerpo debe ser un objeto JSON.")
            getattr(self, route_name)(payload)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except RuntimeError as exc:
            self._send_json(500, {"error": str(exc)})

    def do_GET(self):
        self._dispatch(self.GET_ROUTES)

    def do_POST(self):
        self._dispatch(self.POST_ROUTES, read_body=True)

    def do_DELETE(self):
        self._dispatch(self.DELETE_ROUTES)

    def _get_me(self, _payload):
        self._send_json(200, {"authenticated": bool(self._current_user_id())})

    def _get_state(self, _payload):
        user_id = self._current_user_id()
        if not user_id:
            self._send_json(401, {"error": "Inicia sesion para continuar."})
            return
        self._send_json(200, get_state(user_id))

    def _get_index(self, _payload):
        self._serve_static("_get_index")

    def _get_styles(self, _payload):
        self._serve_static("_get_styles")

    def _get_script(self, _payload):
        self._serve_static("_get_script")

    def _serve_static(self, route_name):
        file_name, content_type = self.STATIC_FILES[route_name]
        try:
            content = (STATIC_DIR / file_name).read_bytes()
        except OSError:
            self._send_json(500, {"error": "No se pudo leer un archivo de la interfaz."})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'; object-src 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def _post_register(self, payload):
        result = auth.register_user(payload)
        self._send_json(
            200,
            {"authenticated": True},
            {"Set-Cookie": self._session_cookie(
                result["token"], int(SESSION_LIFETIME.total_seconds())
            )},
        )

    def _post_login(self, payload):
        email = auth._auth_rate_key(payload.get("email"))
        if auth._check_auth_rate_limit(email):
            self._send_json(
                429,
                {"error": "Demasiados intentos para este correo. Espera unos minutos e intenta de nuevo."},
            )
            return
        try:
            result = auth.login_user(payload)
        except ValueError:
            auth._record_failed_auth(email)
            raise
        auth._clear_auth_rate_limit(email)
        self._send_json(
            200,
            {"authenticated": True},
            {"Set-Cookie": self._session_cookie(
                result["token"], int(SESSION_LIFETIME.total_seconds())
            )},
        )

    def _post_logout(self, _payload):
        auth.revoke_token(self._session_token())
        self._send_json(
            200,
            {"authenticated": False},
            {"Set-Cookie": self._session_cookie("", 0)},
        )

    def _post_profile(self, payload):
        user_id = self._current_user_id()
        if not user_id:
            self._send_json(401, {"error": "Inicia sesion para continuar."})
            return
        self._send_json(200, save_profile(user_id, payload))

    def _delete_profile(self, _payload):
        user_id = self._current_user_id()
        if not user_id:
            self._send_json(401, {"error": "Inicia sesion para continuar."})
            return
        self._send_json(200, delete_profile(user_id))

    def _post_start_interview(self, payload):
        user_id = self._current_user_id()
        if not user_id:
            self._send_json(401, {"error": "Inicia sesion para continuar."})
            return
        job_id = payload.get("jobId")
        engine = payload.get("engine", "rules")
        self._send_json(200, start_interview(user_id, job_id, engine))

    def _post_answer_interview(self, payload):
        user_id = self._current_user_id()
        if not user_id:
            self._send_json(401, {"error": "Inicia sesion para continuar."})
            return
        self._send_json(200, answer_interview(user_id, payload))


def create_server(host="127.0.0.1", port=8000):
    return ThreadingHTTPServer((host, port), AppHandler)

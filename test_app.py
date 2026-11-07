import json
import http.cookiejar
import threading
import tempfile
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import app


class IncluTalentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp_dir.name) / "data.json"
        self.data_path.write_text(json.dumps({
            "users": {},
            "auth_sessions": {},
        }), encoding="utf-8")
        self.data_patch = patch.object(app, "DATA_FILE", self.data_path)
        self.data_patch.start()
        self.lock_patch = patch.object(app, "STORE_LOCK", threading.Lock())
        self.lock_patch.start()

    def tearDown(self):
        self.lock_patch.stop()
        self.data_patch.stop()
        self.temp_dir.cleanup()

    def test_saves_profile_without_accepting_unknown_preferences(self):
        user = self.create_user("kris@example.com")
        profile = app.save_profile(user, {
            "name": "Kris",
            "level": "trainee",
            "accommodations": ["preguntas_claras"],
        })
        self.assertEqual(profile["level"], "trainee")
        with self.assertRaises(ValueError):
            app.save_profile(user, {
                "name": "Kris",
                "level": "trainee",
                "accommodations": ["diagnostico"],
            })

    def test_interview_adapts_questions_and_does_not_store_answer_text(self):
        user = self.create_user("candidate@example.com")
        app.save_profile(user, {
            "name": "Candidato",
            "level": "trainee",
            "accommodations": ["pasos_desglosados"],
        })
        started = app.start_interview(user)
        self.assertTrue(started["question"]["steps"])
        result = app.answer_interview(user, {
            "sessionId": started["sessionId"],
            "answer": "Reviso cada caso, comparo el resultado esperado y documento el error.",
        })
        self.assertFalse(result["finished"])
        stored = json.loads(self.data_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["users"][user]["sessions"][0]["results"][0]["score"], result["result"]["score"])
        self.assertNotIn("Reviso cada caso", self.data_path.read_text(encoding="utf-8"))

    def test_match_jobs_prioritizes_level_and_accessibility(self):
        matches = app.match_jobs({
            "level": "junior",
            "accommodations": ["trabajo_remoto", "tiempo_flexible"],
        })
        self.assertEqual(matches[0]["id"], "frontend-jr")
        self.assertGreaterEqual(matches[0]["match"], matches[-1]["match"])

    def test_password_hash_login_and_account_isolation(self):
        alice_token = app.register_user({
            "name": "Alice",
            "email": "Alice@Example.com",
            "password": "una-clave-segura-123",
        })["token"]
        bob_token = app.register_user({
            "name": "Bob",
            "email": "bob@example.com",
            "password": "otra-clave-segura-456",
        })["token"]
        stored = json.loads(self.data_path.read_text(encoding="utf-8"))
        alice_id = app.authenticate_token(alice_token)
        bob_id = app.authenticate_token(bob_token)
        self.assertNotEqual(alice_id, bob_id)
        self.assertNotIn("una-clave-segura-123", self.data_path.read_text(encoding="utf-8"))
        self.assertNotIn(alice_token, self.data_path.read_text(encoding="utf-8"))
        self.assertNotEqual(stored["users"][alice_id]["password_hash"], "una-clave-segura-123")
        app.save_profile(alice_id, {
            "name": "Alice",
            "level": "trainee",
            "accommodations": ["pasos_desglosados"],
        })
        self.assertEqual(app.get_state(bob_id)["profile"]["name"], "Bob")
        alice_interview = app.start_interview(alice_id)
        with self.assertRaises(ValueError):
            app.answer_interview(bob_id, {
                "sessionId": alice_interview["sessionId"],
                "answer": "Una respuesta suficientemente larga.",
            })
        logged_in = app.login_user({
            "email": "alice@example.com",
            "password": "una-clave-segura-123",
        })
        self.assertEqual(app.authenticate_token(logged_in["token"]), alice_id)
        with self.assertRaises(ValueError):
            app.login_user({"email": "alice@example.com", "password": "incorrecta"})
        with self.assertRaises(ValueError):
            app.register_user({
                "name": "Weak",
                "email": "weak@example.com",
                "password": "short",
            })

    def test_legacy_profile_moves_to_first_registered_account(self):
        self.data_path.write_text(json.dumps({
            "profile": {
                "name": "Perfil anterior",
                "level": "intermedio",
                "accommodations": ["pausas"],
            },
            "sessions": [],
        }), encoding="utf-8")
        token = app.register_user({
            "name": "Nueva cuenta",
            "email": "first@example.com",
            "password": "first-account-password",
        })["token"]
        user_id = app.authenticate_token(token)
        profile = app.get_state(user_id)["profile"]
        self.assertEqual(profile["name"], "Nueva cuenta")
        self.assertEqual(profile["level"], "intermedio")
        self.assertEqual(profile["accommodations"], ["pausas"])

    def test_http_protects_private_routes_and_manages_session_cookie(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.AppHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def request(method, path, payload=None, origin=base):
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            body = json.dumps(payload).encode() if payload is not None else None
            return opener.open(Request(base + path, data=body, headers=headers, method=method))

        try:
            with self.assertRaises(HTTPError) as response:
                request("GET", "/api/state")
            self.assertEqual(response.exception.code, 401)

            with self.assertRaises(HTTPError) as response:
                request("POST", "/api/register", {
                    "name": "Test",
                    "email": "http@example.com",
                    "password": "http-test-password-123",
                }, origin="http://attacker.example")
            self.assertEqual(response.exception.code, 403)

            registered = request("POST", "/api/register", {
                "name": "HTTP Test",
                "email": "http@example.com",
                "password": "http-test-password-123",
            })
            cookie = registered.headers["Set-Cookie"].lower()
            self.assertIn("httponly", cookie)
            self.assertIn("samesite=strict", cookie)
            self.assertEqual(json.load(request("GET", "/api/state"))["profile"]["name"], "HTTP Test")

            request("POST", "/api/logout", {})
            with self.assertRaises(HTTPError) as response:
                request("GET", "/api/state")
            self.assertEqual(response.exception.code, 401)

            request("POST", "/api/login", {
                "email": "http@example.com",
                "password": "http-test-password-123",
            })
            self.assertEqual(json.load(request("GET", "/api/state"))["profile"]["name"], "HTTP Test")
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

    def create_user(self, email):
        token = app.register_user({
            "name": "Test",
            "email": email,
            "password": "test-password-safe-123",
        })["token"]
        return app.authenticate_token(token)


if __name__ == "__main__":
    unittest.main()

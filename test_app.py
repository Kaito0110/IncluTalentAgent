import http.cookiejar
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import app
import auth
import interview_agent
import persistence


class IncluTalentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp_dir.name) / "data.json"
        self.data_path.write_text(json.dumps({
            "users": {},
            "auth_sessions": {},
        }), encoding="utf-8")
        self.data_patch = patch.object(persistence, "DATA_FILE", self.data_path)
        self.data_patch.start()
        self.lock_patch = patch.object(persistence, "STORE_LOCK", threading.RLock())
        self.lock_patch.start()
        with auth.LOGIN_ATTEMPTS_LOCK:
            auth.LOGIN_ATTEMPTS.clear()

    def tearDown(self):
        self.lock_patch.stop()
        self.data_patch.stop()
        self.temp_dir.cleanup()

    def test_profile_create_read_update_and_delete(self):
        user = self.create_user("profile@example.com")
        profile = app.save_profile(user, {
            "name": "Kris",
            "level": "trainee",
            "jobId": "qa-trainee",
            "skills": ["Pruebas", "Documentacion"],
            "accommodations": ["preguntas_claras"],
        })
        self.assertEqual(profile["level"], "trainee")
        self.assertEqual(app.get_state(user)["profile"]["jobId"], "qa-trainee")
        with self.assertRaises(ValueError):
            app.save_profile(user, {
                "name": "Kris",
                "level": "trainee",
                "jobId": "qa-trainee",
                "accommodations": ["diagnostico"],
            })
        app.start_interview(user)
        deleted = app.delete_profile(user)
        self.assertTrue(deleted["deleted"])
        state = app.get_state(user)
        self.assertEqual(state["profile"]["name"], "")
        self.assertEqual(state["profile"]["accommodations"], [])
        self.assertEqual(state["metrics"]["interviews"], 0)

    def test_interview_has_five_questions_and_never_stores_answer_text(self):
        user = self.create_user("candidate@example.com")
        app.save_profile(user, {
            "name": "Candidato",
            "level": "trainee",
            "jobId": "qa-trainee",
            "skills": [],
            "accommodations": ["pasos_desglosados"],
        })
        started = app.start_interview(user)
        self.assertEqual(started["total"], 5)
        self.assertEqual(started["jobTitle"], "Analista QA Trainee")
        self.assertEqual(started["question"]["total"], 5)
        self.assertTrue(started["question"]["steps"])
        raw_answer = "Reviso cada caso, comparo el resultado esperado y documento el error."
        for _ in range(5):
            result = app.answer_interview(user, {
                "sessionId": started["sessionId"],
                "answer": raw_answer,
            })
        self.assertTrue(result["finished"])
        self.assertIn("Analista QA Trainee", result["result"]["feedback"])
        stored_text = self.data_path.read_text(encoding="utf-8")
        stored = json.loads(stored_text)
        session = stored["users"][user]["sessions"][0]
        self.assertEqual(session["status"], "completed")
        self.assertEqual(len(session["results"]), 5)
        self.assertNotIn(raw_answer, stored_text)
        history = app.get_state(user)["recentInterviews"]
        self.assertEqual(history[0]["jobTitle"], "Analista QA Trainee")
        self.assertEqual(history[0]["responses"], 5)

    def test_custom_role_agent_builds_job_specific_interview(self):
        user = self.create_user("custom-role@example.com")
        app.save_profile(user, {
            "name": "Sam",
            "level": "junior",
            "jobId": "custom",
            "customJobTitle": "Disenador UX",
            "skills": ["investigacion"],
            "accommodations": [],
        })
        started = app.start_interview(user)
        self.assertEqual(started["total"], 5)
        self.assertEqual(started["jobTitle"], "Disenador UX")
        self.assertIn("investigacion", started["question"]["prompt"])
        with self.assertRaises(ValueError):
            app.start_interview(user, {"invalid": "job"})
        result = app.answer_interview(user, {
            "sessionId": started["sessionId"],
            "answer": "Use investigacion para conocer las necesidades y proponer mejoras.",
        })
        self.assertIn("Disenador UX", result["result"]["feedback"])

    def test_ollama_agent_generates_and_evaluates_without_storing_answer_text(self):
        user = self.create_user("ollama@example.com")
        app.save_profile(user, {
            "name": "Local User",
            "level": "junior",
            "jobId": "frontend-jr",
            "skills": ["JavaScript"],
            "accommodations": [],
        })
        _, questions = app.build_interview_plan(app.get_state(user)["profile"])
        answer = "Implementaria la funcion y probaria varios casos con JavaScript."
        with patch.object(interview_agent, "generate_questions", return_value=questions) as generate:
            with patch.object(interview_agent, "evaluate_with_ollama", return_value={
                "score": 4,
                "matched": ["JavaScript"],
                "feedback": "Buen ejemplo; explica como verificarias el resultado.",
            }) as evaluate:
                started = app.start_interview(user, engine="ollama")
                result = app.answer_interview(user, {
                    "sessionId": started["sessionId"],
                    "answer": answer,
                })

        self.assertIn("Ollama", started["agentName"])
        self.assertEqual(started["total"], 5)
        self.assertFalse(result["finished"])
        self.assertEqual(result["result"]["score"], 4)
        generate.assert_called_once()
        evaluate.assert_called_once_with(answer, questions[0], "Desarrollador/a Frontend Jr.")
        stored_text = self.data_path.read_text(encoding="utf-8")
        self.assertNotIn(answer, stored_text)

    def test_ollama_start_failure_does_not_create_interview(self):
        user = self.create_user("ollama-error@example.com")
        with patch.object(
            interview_agent,
            "generate_questions",
            side_effect=RuntimeError("Ollama no esta disponible."),
        ):
            with self.assertRaisesRegex(RuntimeError, "Ollama no esta disponible"):
                app.start_interview(user, engine="ollama")
        self.assertEqual(app.get_state(user)["metrics"]["interviews"], 0)

    def test_questions_offer_role_specific_exercises_and_difficulty_times(self):
        users = [
            ("frontend@example.com", "frontend-jr", "code", "JavaScript", 180),
            ("qa@example.com", "qa-trainee", "exercise", "Casos de prueba", 180),
            ("support@example.com", "support-jr", "exercise", "Respuesta escrita", 180),
            ("data@example.com", "data-mid", "code", "SQL", 300),
        ]
        for email, job_id, exercise_type, language, time_limit in users:
            with self.subTest(job=job_id):
                user = self.create_user(email)
                app.save_profile(user, {
                    "name": "Practice",
                    "level": "junior",
                    "jobId": job_id,
                    "skills": [],
                    "accommodations": [],
                })
                started = app.start_interview(user)
                next_question = None
                for _ in range(4):
                    response = app.answer_interview(user, {
                        "sessionId": started["sessionId"],
                        "answer": "Explico el problema, propongo una prueba y reviso el resultado con el equipo.",
                    })
                    if not response["finished"] and response["question"]["type"] == exercise_type:
                        next_question = response["question"]
                        break
                self.assertIsNotNone(next_question)
                self.assertEqual(next_question["language"], language)
                self.assertEqual(next_question["timeLimit"], time_limit)
                self.assertTrue(next_question["starterCode"])
                if exercise_type == "code":
                    result = app.answer_interview(user, {
                        "sessionId": started["sessionId"],
                        "answer": "function validateEmail(value) { return value; } // pruebo error y resultado",
                    })
                    self.assertIn("no ejecuta", result["result"]["feedback"])

    def test_match_jobs_prioritizes_selected_role_and_accessibility(self):
        matches = app.match_jobs({
            "level": "trainee",
            "jobId": "qa-trainee",
            "accommodations": ["tiempo_flexible", "pasos_desglosados"],
        })
        self.assertEqual(matches[0]["id"], "qa-trainee")
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
        stored_text = self.data_path.read_text(encoding="utf-8")
        stored = json.loads(stored_text)
        alice_id = app.authenticate_token(alice_token)
        bob_id = app.authenticate_token(bob_token)
        self.assertNotEqual(alice_id, bob_id)
        self.assertNotIn("una-clave-segura-123", stored_text)
        self.assertNotIn(alice_token, stored_text)
        self.assertNotEqual(stored["users"][alice_id]["password_hash"], "una-clave-segura-123")
        app.save_profile(alice_id, {
            "name": "Alice",
            "level": "trainee",
            "jobId": "qa-trainee",
            "skills": [],
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

    def test_failed_attempts_are_keyed_by_email_and_registration_does_not_clear_them(self):
        target_email = "target@example.com"
        for _ in range(auth.LOGIN_ATTEMPT_LIMIT):
            auth._record_failed_auth(target_email)
        self.assertTrue(auth._check_auth_rate_limit(target_email))
        app.register_user({
            "name": "New account",
            "email": "new@example.com",
            "password": "new-account-password",
        })
        self.assertTrue(auth._check_auth_rate_limit(target_email))
        self.assertFalse(auth._check_auth_rate_limit("new@example.com"))
        with auth.LOGIN_ATTEMPTS_LOCK:
            auth.LOGIN_ATTEMPTS.pop(target_email, None)

    def test_legacy_profile_is_not_assigned_to_first_new_account(self):
        self.data_path.write_text(json.dumps({
            "profile": {
                "name": "Perfil anterior",
                "level": "intermedio",
                "accommodations": ["pausas"],
            },
            "sessions": [{"status": "completed"}],
        }), encoding="utf-8")
        token = app.register_user({
            "name": "Nueva cuenta",
            "email": "first@example.com",
            "password": "first-account-password",
        })["token"]
        user_id = app.authenticate_token(token)
        profile = app.get_state(user_id)["profile"]
        self.assertEqual(profile["name"], "Nueva cuenta")
        self.assertEqual(profile["level"], "junior")
        self.assertEqual(profile["accommodations"], [])
        self.assertEqual(app.get_state(user_id)["metrics"]["interviews"], 0)

    def test_http_routes_protect_private_data_and_allow_profile_reset(self):
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
            page = request("GET", "/")
            self.assertEqual(page.headers.get("Cache-Control"), "no-store")

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
            state = json.load(request("GET", "/api/state"))
            self.assertEqual(state["profile"]["name"], "HTTP Test")
            self.assertEqual(len(state["jobOptions"]), 7)

            with self.assertRaises(HTTPError) as response:
                request("POST", "/api/login", {
                    "email": "http@example.com",
                    "password": "incorrect-password",
                })
            self.assertEqual(response.exception.code, 400)
            self.assertEqual(len(auth.LOGIN_ATTEMPTS["http@example.com"]), 1)
            request("POST", "/api/register", {
                "name": "Second account",
                "email": "second@example.com",
                "password": "second-account-password",
            })
            self.assertEqual(len(auth.LOGIN_ATTEMPTS["http@example.com"]), 1)
            request("POST", "/api/logout", {})
            request("POST", "/api/login", {
                "email": "http@example.com",
                "password": "http-test-password-123",
            })

            request("DELETE", "/api/profile")
            self.assertEqual(json.load(request("GET", "/api/state"))["profile"]["name"], "")

            request("POST", "/api/logout", {})
            with self.assertRaises(HTTPError) as response:
                request("GET", "/api/state")
            self.assertEqual(response.exception.code, 401)

            request("POST", "/api/login", {
                "email": "http@example.com",
                "password": "http-test-password-123",
            })
            self.assertEqual(json.load(request("GET", "/api/state"))["profile"]["name"], "")
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

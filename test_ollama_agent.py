import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

import ollama_agent


class OllamaAgentTests(unittest.TestCase):
    def test_chat_uses_local_ollama_api_and_parses_json_response(self):
        content = json.dumps({"questions": []})
        response = io.BytesIO(json.dumps({
            "message": {"content": content},
        }).encode("utf-8"))
        with patch.object(ollama_agent, "urlopen", return_value=response) as open_url:
            result = ollama_agent._chat("prompt")

        self.assertEqual(result, {"questions": []})
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], ollama_agent.OLLAMA_MODEL)
        self.assertFalse(body["stream"])
        self.assertEqual(body["format"], "json")
        self.assertEqual(body["keep_alive"], "10m")
        self.assertEqual(body["options"]["num_predict"], 800)

    def test_connection_errors_are_reported_without_fallback(self):
        with patch.object(
            ollama_agent,
            "urlopen",
            side_effect=URLError("connection refused"),
        ):
            with self.assertRaisesRegex(RuntimeError, "No se pudo conectar con Ollama"):
                ollama_agent._chat("prompt")

    def test_invalid_question_fields_are_reported_as_model_errors(self):
        question = {
            "prompt": "Describe tu enfoque.",
            "steps": ["Explica el proceso."],
            "skills": ["comunicacion"],
            "difficulty": [],
            "type": "conversation",
            "language": "",
            "starterCode": "",
        }
        with patch.object(
            ollama_agent,
            "_chat",
            return_value={"questions": [question] * 5},
        ):
            with self.assertRaisesRegex(RuntimeError, "campos invalidos"):
                ollama_agent.generate_questions("Asistente", {})

    def test_question_generation_uses_schema_with_a_single_practical_task(self):
        question = {
            "prompt": "Describe tu enfoque para organizar el trabajo.",
            "steps": ["Explica la situacion.", "Menciona el resultado."],
            "skills": ["organizacion", "comunicacion"],
            "difficulty": "intermediate",
            "type": "conversation",
            "language": "espanol",
            "starterCode": "",
        }
        questions = [dict(question) for _ in range(5)]
        questions[3]["type"] = "exercise"
        questions[3]["starterCode"] = "Paso 1:\nPaso 2:"
        with patch.object(
            ollama_agent,
            "_chat",
            return_value={"questions": questions},
        ) as chat:
            result = ollama_agent.generate_questions("Asistente", {})

        schema = chat.call_args.args[1]
        question_schema = schema["properties"]["questions"]
        self.assertEqual(len(result), 5)
        self.assertEqual(chat.call_args.args[1], ollama_agent.QUESTION_SCHEMA)
        self.assertEqual(
            [item["properties"]["type"]["enum"] for item in question_schema["prefixItems"]],
            [["conversation"], ["conversation"], ["conversation"], ["code", "exercise"], ["conversation"]],
        )


if __name__ == "__main__":
    unittest.main()

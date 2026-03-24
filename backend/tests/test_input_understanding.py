import os
import unittest
from unittest.mock import patch

os.environ["DEBUG"] = "false"

from app.modules.input_understanding.handler import understand_input


class _FakeChain:
    def __init__(self, result):
        self.result = result

    def __or__(self, _other):
        return self

    async def ainvoke(self, _payload):
        return self.result


class _FakePrompt:
    def __init__(self, result):
        self.result = result

    def __or__(self, _other):
        return _FakeChain(self.result)


class InputUnderstandingTests(unittest.IsolatedAsyncioTestCase):
    async def test_understand_input_replaces_null_fields_with_defaults(self):
        llm_result = {
            "topic": None,
            "target_type": None,
            "subject_area": None,
            "likely_prerequisites": None,
            "input_confidence": None,
        }

        with patch(
            "app.modules.input_understanding.handler.get_llm",
            return_value=object(),
        ), patch(
            "app.modules.input_understanding.handler.ChatPromptTemplate.from_template",
            return_value=_FakePrompt(llm_result),
        ), patch(
            "app.modules.input_understanding.handler.RobustJsonOutputParser",
            return_value=object(),
        ):
            response = await understand_input("epsilon-delta definition", session_id="sess-1")

        self.assertEqual(response.session_id, "sess-1")
        self.assertEqual(response.topic, "epsilon-delta definition")
        self.assertEqual(response.target_type, "concept")
        self.assertEqual(response.subject_area, "other")
        self.assertEqual(response.likely_prerequisites, [])
        self.assertEqual(response.input_confidence, 0.8)

    async def test_understand_input_filters_invalid_values(self):
        llm_result = {
            "topic": "  limits  ",
            "target_type": "nonsense",
            "subject_area": "mathematics",
            "likely_prerequisites": [" sequences ", None, ""],
            "input_confidence": 3,
        }

        with patch(
            "app.modules.input_understanding.handler.get_llm",
            return_value=object(),
        ), patch(
            "app.modules.input_understanding.handler.ChatPromptTemplate.from_template",
            return_value=_FakePrompt(llm_result),
        ), patch(
            "app.modules.input_understanding.handler.RobustJsonOutputParser",
            return_value=object(),
        ):
            response = await understand_input("limits", session_id="sess-2")

        self.assertEqual(response.topic, "limits")
        self.assertEqual(response.target_type, "concept")
        self.assertEqual(response.subject_area, "other")
        self.assertEqual(response.likely_prerequisites, ["sequences"])
        self.assertEqual(response.input_confidence, 1.0)


if __name__ == "__main__":
    unittest.main()

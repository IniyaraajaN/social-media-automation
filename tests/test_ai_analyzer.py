"""Three offline test cases for the Part 2 AI feature."""

import json
import unittest

from src.ai_analyzer import AnalysisAPIError, InputValidationError, analyze_post


VALID_INPUT = {
    "caption": "When the group chat says 'quick call'.",
    "post_type": "REEL",
    "metrics": {"reach": 1200, "likes": 100, "comments": 8, "shares": 14, "saves": 9},
}

VALID_OUTPUT = {
    "performance_summary": [
        "The post reached 1,200 accounts and received 131 interactions",
        "Its engagement rate was 10.9%",
    ],
    "caption_options": [
        "When 'quick call' turns into a full group-chat meeting.",
        "POV: the group chat said quick call, and your calendar disappeared.",
    ],
    "hashtags": ["#groupchat", "#relatablememes", "#quickcall"],
}


class FakeClient:
    def __init__(self, output_text=None, error=None):
        self.output_text = output_text
        self.error = error

    def chat(self, **kwargs):
        if self.error:
            raise self.error
        return {"message": {"content": self.output_text}}


class PostAnalyzerTests(unittest.TestCase):
    def test_valid_input_returns_required_json_shape_and_counts(self):
        client = FakeClient(output_text=json.dumps(VALID_OUTPUT))
        result = analyze_post(VALID_INPUT, client=client)
        self.assertEqual(set(result), {"performance_summary", "caption_options", "hashtags"})
        self.assertIn("131 interactions", result["performance_summary"])
        self.assertEqual(len(result["caption_options"]), 2)
        self.assertEqual(len(result["hashtags"]), 3)

    def test_missing_required_metric_is_rejected_before_api_call(self):
        invalid = {**VALID_INPUT, "metrics": {"reach": 100, "likes": 1}}
        with self.assertRaises(InputValidationError):
            analyze_post(invalid, client=FakeClient(output_text=json.dumps(VALID_OUTPUT)))

    def test_local_model_exception_is_reported_as_actionable_error(self):
        client = FakeClient(error=RuntimeError("simulated network failure"))
        with self.assertRaisesRegex(AnalysisAPIError, "local model request failed"):
            analyze_post(VALID_INPUT, client=client)


if __name__ == "__main__":
    unittest.main()

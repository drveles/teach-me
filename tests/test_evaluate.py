import json
import tempfile
import unittest
from pathlib import Path

from evaluate import assistant_messages, check_state, prepare


class EvaluationTests(unittest.TestCase):
    def test_grading_includes_intermediate_messages(self):
        trace = "\n".join(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": message},
                }
            )
            for message in ["Here is the answer before you try.", "Now try it."]
        )
        self.assertEqual(
            assistant_messages(trace),
            [
                "Here is the answer before you try.",
                "Now try it.",
            ],
        )

    def test_global_pause_does_not_pass_subject_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root)
            path = root / ".learning/registry.json"
            registry = json.loads(path.read_text())
            registry["enabled"] = False
            path.write_text(json.dumps(registry))
            errors = check_state(root, {"ratings": [[]], "enabled": False})
            self.assertIn("global learning state changed", errors)
            self.assertIn("unexpected enabled state", errors)

    def test_malformed_state_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root)
            path = root / ".learning/registry.json"
            path.write_text(json.dumps({"enabled": True, "subjects": []}))
            self.assertTrue(check_state(root, {"ratings": [[]], "enabled": True}))

    def test_fixture_passes_state_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root)
            self.assertEqual(check_state(root, {"ratings": [[]], "enabled": True}), [])

    def test_fabricated_success_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root)
            events = root / ".learning/subjects/english/events.jsonl"
            events.write_text(json.dumps({"rating": "good", "confidence": 5}) + "\n")
            errors = check_state(root, {"ratings": [[]], "enabled": True})
            self.assertTrue(any("ratings" in error for error in errors))
            self.assertTrue(any("confidence" in error for error in errors))

    def test_claimed_pause_without_state_change_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root)
            errors = check_state(root, {"ratings": [[]], "enabled": False})
            self.assertIn("unexpected enabled state", errors)

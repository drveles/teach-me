import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "always-learning" / "scripts" / "state.py"


class StateCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name) / "state"

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args, check=True):
        self.assertTrue(SCRIPT.is_file(), f"missing state helper: {SCRIPT}")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--home", str(self.home), *args],
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        return result

    def init_subject(self, check=True):
        return self.run_cli(
            "init-subject",
            "--id",
            "distributed-systems",
            "--title",
            "Distributed Systems",
            "--mission",
            "Pass backend system-design interviews.",
            "--cue",
            "consensus",
            "--cue",
            "replication",
            check=check,
        )

    def add_item(self, due_at="2026-08-29T10:00:00Z", check=True):
        mission = self.home / "subjects" / "distributed-systems" / "MISSION.md"
        mission.write_text(
            "# Distributed Systems\n\n"
            "## Outcome\n\nPass backend system-design interviews.\n\n"
            "## Success Criteria\n\nExplain and apply core distributed-systems trade-offs.\n\n"
            "## Constraints\n\nUse primary sources.\n\n"
            "## Out of Scope\n\nVendor-specific operations.\n"
        )
        resources = self.home / "subjects" / "distributed-systems" / "RESOURCES.md"
        source = (
            "### `raft-paper`\n\n"
            "- Link: https://raft.github.io/raft.pdf\n"
            "- Purpose: Consensus fundamentals.\n"
            "- Verified: 2026-08-29\n"
        )
        if resources.is_file() and "### `raft-paper`" not in resources.read_text():
            resources.write_text(resources.read_text().replace("## Gaps", source + "\n## Gaps"))
        plan = self.home / "subjects" / "distributed-systems" / "PLAN.md"
        if "### `majority-overlap`" not in plan.read_text():
            plan.write_text(
                "# Plan\n\n## Objectives\n\n"
                "### `majority-overlap`\n\n"
                "- Outcome: Explain why any two majorities overlap.\n"
                "- Concepts: consensus, quorum\n"
                "- Depends on: none\n\n"
                "## Dependencies\n\nNone.\n"
            )
        result = self.run_cli(
            "add-item",
            "--subject",
            "distributed-systems",
            "--id",
            "majority-overlap",
            "--objective",
            "Explain why any two majorities overlap.",
            "--prompt",
            "Why does Raft require a majority to elect a leader?",
            "--criterion",
            "States that two majorities share at least one node.",
            "--concept",
            "consensus",
            "--source",
            "raft-paper",
            "--due-at",
            due_at,
            check=check,
        )
        if check:
            self.run_cli(
                "validate",
                "--subject",
                "distributed-systems",
                "--activate",
            )
        return result

    def test_status_is_read_only_when_unconfigured(self):
        result = self.run_cli("status", "--now", "2026-08-29T10:00:00Z")
        self.assertFalse(self.home.exists())
        self.assertEqual(
            json.loads(result.stdout),
            {
                "configured": False,
                "enabled": False,
                "subjects": [],
                "due": [],
            },
        )

    def test_init_subject_creates_the_state_contract(self):
        self.init_subject()
        subject = self.home / "subjects" / "distributed-systems"
        self.assertEqual(
            {path.name for path in subject.iterdir()},
            {"MISSION.md", "RESOURCES.md", "PLAN.md", "mastery.json", "events.jsonl"},
        )
        registry = json.loads((self.home / "registry.json").read_text())
        self.assertTrue(registry["enabled"])
        self.assertFalse(registry["subjects"][0]["ready"])
        self.assertEqual(registry["subjects"][0]["cues"], ["consensus", "replication"])

    def test_init_subject_refuses_to_overwrite_existing_state(self):
        self.init_subject()
        mission = self.home / "subjects" / "distributed-systems" / "MISSION.md"
        original = mission.read_text()
        result = self.init_subject(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mission.read_text(), original)

    def test_init_subject_rejects_blank_metadata_without_partial_state(self):
        result = self.run_cli(
            "init-subject",
            "--id",
            "distributed-systems",
            "--title",
            "   ",
            "--mission",
            "   ",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.home.exists())

    def test_init_subject_rolls_back_when_a_state_write_fails(self):
        self.assertTrue(SCRIPT.is_file())
        spec = importlib.util.spec_from_file_location("always_learning_state", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = SimpleNamespace(
            home=str(self.home),
            id="distributed-systems",
            title="Distributed Systems",
            mission="Pass backend interviews.",
            cue=[],
        )
        with mock.patch.object(module, "write_json", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                module.command_init_subject(args)
        self.assertFalse((self.home / "subjects" / "distributed-systems").exists())

    def test_init_subject_preserves_global_pause(self):
        self.init_subject()
        self.run_cli("set-enabled", "--disabled")
        self.run_cli(
            "init-subject",
            "--id",
            "networking",
            "--title",
            "Networking",
            "--mission",
            "Diagnose production network failures.",
        )
        status = json.loads(
            self.run_cli("status", "--now", "2026-08-29T10:00:00Z").stdout
        )
        self.assertFalse(status["enabled"])

    def test_add_item_rejects_duplicates(self):
        self.init_subject()
        self.add_item()
        result = self.add_item(check=False)
        self.assertNotEqual(result.returncode, 0)
        mastery = json.loads(
            (self.home / "subjects" / "distributed-systems" / "mastery.json").read_text()
        )
        self.assertEqual(len(mastery["items"]), 1)

    def test_add_item_requires_concepts_and_sources(self):
        self.init_subject()
        result = self.run_cli(
            "add-item",
            "--subject",
            "distributed-systems",
            "--id",
            "majority-overlap",
            "--objective",
            "Explain majority overlap.",
            "--prompt",
            "Why must majorities overlap?",
            "--criterion",
            "Identifies a shared node.",
            "--due-at",
            "2026-08-29T10:00:00Z",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_add_item_rejects_unknown_sources(self):
        self.init_subject()
        plan = self.home / "subjects" / "distributed-systems" / "PLAN.md"
        plan.write_text(
            "# Plan\n\n## Objectives\n\n"
            "### `majority-overlap`\n\n"
            "- Outcome: Explain majority overlap.\n"
            "- Concepts: consensus, quorum\n"
            "- Depends on: none\n"
        )
        result = self.run_cli(
            "add-item",
            "--subject",
            "distributed-systems",
            "--id",
            "majority-overlap",
            "--objective",
            "Explain majority overlap.",
            "--prompt",
            "Why must majorities overlap?",
            "--criterion",
            "Identifies a shared node.",
            "--concept",
            "consensus",
            "--source",
            "missing-source",
            "--due-at",
            "2026-08-29T10:00:00Z",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing-source", result.stderr)

    def test_record_review_updates_schedule_and_appends_evidence(self):
        self.init_subject()
        self.add_item()
        self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "good",
            "--confidence",
            "4",
            "--evidence",
            "Explained quorum overlap without a hint.",
            "--now",
            "2026-08-29T10:00:00Z",
        )
        mastery = json.loads(
            (self.home / "subjects" / "distributed-systems" / "mastery.json").read_text()
        )
        item = mastery["items"][0]
        self.assertEqual(item["stage"], 0)
        self.assertEqual(item["due_at"], "2026-08-30T10:00:00Z")
        event = json.loads(
            (self.home / "subjects" / "distributed-systems" / "events.jsonl")
            .read_text()
            .strip()
        )
        self.assertEqual(event["rating"], "good")
        self.assertEqual(event["confidence"], 4)
        self.assertEqual(event["evidence"], "Explained quorum overlap without a hint.")
        self.run_cli("validate", "--subject", "distributed-systems")

    def test_scheduler_uses_fixed_review_stages(self):
        expected = {
            "again": (0, "2026-08-30T10:00:00Z"),
            "hard": (0, "2026-08-30T10:00:00Z"),
            "good": (1, "2026-09-01T10:00:00Z"),
            "easy": (2, "2026-09-05T10:00:00Z"),
        }
        for rating, schedule in expected.items():
            with self.subTest(rating=rating):
                with tempfile.TemporaryDirectory() as directory:
                    self.home = Path(directory) / "state"
                    self.init_subject()
                    self.add_item()
                    self.run_cli(
                        "record-review",
                        "--subject",
                        "distributed-systems",
                        "--item",
                        "majority-overlap",
                        "--rating",
                        "good",
                        "--confidence",
                        "3",
                        "--evidence",
                        "Explained overlap unaided.",
                        "--now",
                        "2026-08-28T10:00:00Z",
                    )
                    mastery_path = self.home / "subjects" / "distributed-systems" / "mastery.json"
                    self.run_cli(
                        "record-review",
                        "--subject",
                        "distributed-systems",
                        "--item",
                        "majority-overlap",
                        "--rating",
                        rating,
                        "--confidence",
                        "3",
                        "--evidence",
                        "Observed response.",
                        "--now",
                        "2026-08-29T10:00:00Z",
                    )
                    updated = json.loads(mastery_path.read_text())["items"][0]
                    self.assertEqual((updated["stage"], updated["due_at"]), schedule)

    def test_hard_review_moves_to_the_previous_fixed_interval(self):
        self.init_subject()
        self.add_item(due_at="2026-07-01T10:00:00Z")
        for rating, reviewed_at in (
            ("easy", "2026-07-01T10:00:00Z"),
            ("easy", "2026-07-04T10:00:00Z"),
            ("good", "2026-07-18T10:00:00Z"),
        ):
            self.run_cli(
                "record-review",
                "--subject",
                "distributed-systems",
                "--item",
                "majority-overlap",
                "--rating",
                rating,
                "--confidence",
                "3",
                "--evidence",
                "Explained overlap unaided.",
                "--now",
                reviewed_at,
            )
        mastery_path = self.home / "subjects" / "distributed-systems" / "mastery.json"
        self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "hard",
            "--confidence",
            "3",
            "--evidence",
            "Needed a material hint.",
            "--now",
            "2026-08-29T10:00:00Z",
        )
        updated = json.loads(mastery_path.read_text())["items"][0]
        self.assertEqual(updated["stage"], 3)
        self.assertEqual(updated["due_at"], "2026-09-12T10:00:00Z")

    def test_failed_evidence_append_does_not_advance_schedule(self):
        self.init_subject()
        self.add_item()
        subject = self.home / "subjects" / "distributed-systems"
        mastery_path = subject / "mastery.json"
        before = mastery_path.read_text()
        events = subject / "events.jsonl"
        events.unlink()
        events.mkdir()
        result = self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "good",
            "--confidence",
            "4",
            "--evidence",
            "Explained overlap unaided.",
            "--now",
            "2026-08-29T10:00:00Z",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mastery_path.read_text(), before)

    def test_failed_mastery_write_rolls_back_evidence(self):
        self.init_subject()
        self.add_item()
        subject = self.home / "subjects" / "distributed-systems"
        mastery_before = (subject / "mastery.json").read_text()
        events_before = (subject / "events.jsonl").read_text()
        spec = importlib.util.spec_from_file_location("always_learning_review_state", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = SimpleNamespace(
            home=str(self.home),
            subject="distributed-systems",
            item="majority-overlap",
            rating="good",
            confidence=4,
            evidence="Explained overlap unaided.",
            now="2026-08-29T10:00:00Z",
        )
        with mock.patch.object(module, "write_json", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                module.command_record_review(args)
        self.assertEqual((subject / "mastery.json").read_text(), mastery_before)
        self.assertEqual((subject / "events.jsonl").read_text(), events_before)

    def test_record_review_rejects_backdated_evidence(self):
        self.init_subject()
        self.add_item()
        self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "good",
            "--confidence",
            "4",
            "--evidence",
            "Explained overlap unaided.",
            "--now",
            "2026-09-01T10:00:00Z",
        )
        result = self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "again",
            "--confidence",
            "2",
            "--evidence",
            "Could not reconstruct the argument.",
            "--now",
            "2026-08-31T10:00:00Z",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("earlier than", result.stderr)

    def test_record_review_requires_an_active_ready_subject(self):
        self.init_subject()
        self.add_item()
        registry_path = self.home / "registry.json"
        registry = json.loads(registry_path.read_text())
        registry["subjects"][0]["ready"] = False
        registry_path.write_text(json.dumps(registry))
        result = self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "good",
            "--confidence",
            "4",
            "--evidence",
            "Explained overlap unaided.",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not ready", result.stderr)

    def test_record_review_revalidates_the_current_plan(self):
        self.init_subject()
        self.add_item()
        subject = self.home / "subjects" / "distributed-systems"
        (subject / "PLAN.md").write_text("# Plan\n\n## Objectives\n\n## Dependencies\n")
        result = self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "good",
            "--confidence",
            "4",
            "--evidence",
            "Explained overlap unaided.",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("objective", result.stderr)
        self.assertEqual((subject / "events.jsonl").read_text(), "")

    def test_status_returns_only_due_items_from_enabled_subjects(self):
        self.init_subject()
        self.add_item(due_at="2026-08-29T09:00:00Z")
        due = json.loads(
            self.run_cli("status", "--now", "2026-08-29T10:00:00Z").stdout
        )["due"]
        self.assertEqual(due[0]["item_id"], "majority-overlap")
        self.run_cli("set-enabled", "--subject", "distributed-systems", "--disabled")
        due = json.loads(
            self.run_cli("status", "--now", "2026-08-29T10:00:00Z").stdout
        )["due"]
        self.assertEqual(due, [])

    def test_status_reports_items_and_review_evidence(self):
        self.init_subject()
        self.add_item()
        self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "good",
            "--confidence",
            "4",
            "--evidence",
            "Explained quorum overlap without a hint.",
            "--now",
            "2026-08-29T10:00:00Z",
        )
        subject = json.loads(
            self.run_cli("status", "--now", "2026-08-29T10:00:00Z").stdout
        )["subjects"][0]
        self.assertEqual(subject.get("item_count"), 1)
        self.assertEqual(subject.get("review_count"), 1)
        self.assertEqual(subject.get("last_reviewed_at"), "2026-08-29T10:00:00Z")
        self.assertTrue(subject.get("items"))
        item = subject["items"][0]
        self.assertEqual(item.get("last_evidence"), "Explained quorum overlap without a hint.")
        self.assertEqual(item.get("last_confidence"), 4)

    def test_status_blocks_due_items_until_dependencies_are_demonstrated(self):
        self.init_subject()
        self.add_item(due_at="2026-08-29T09:00:00Z")
        plan = self.home / "subjects" / "distributed-systems" / "PLAN.md"
        plan.write_text(
            plan.read_text().replace(
                "## Dependencies",
                "### `log-replication`\n\n"
                "- Outcome: Explain Raft log replication.\n"
                "- Concepts: consensus, replication\n"
                "- Depends on: majority-overlap\n\n"
                "## Dependencies",
            )
        )
        self.run_cli(
            "add-item",
            "--subject",
            "distributed-systems",
            "--id",
            "log-replication",
            "--objective",
            "Explain Raft log replication.",
            "--prompt",
            "How does a leader repair a follower's divergent log?",
            "--criterion",
            "Describes decrementing nextIndex until prefixes match.",
            "--concept",
            "replication",
            "--source",
            "raft-paper",
            "--due-at",
            "2026-08-29T09:00:00Z",
        )
        self.run_cli("validate", "--subject", "distributed-systems", "--activate")
        due = json.loads(
            self.run_cli("status", "--now", "2026-08-29T10:00:00Z").stdout
        )["due"]
        self.assertEqual({item["item_id"] for item in due}, {"majority-overlap"})
        self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "good",
            "--confidence",
            "4",
            "--evidence",
            "Explained overlap unaided.",
            "--now",
            "2026-08-29T10:00:00Z",
        )
        due = json.loads(
            self.run_cli("status", "--now", "2026-08-29T10:00:00Z").stdout
        )["due"]
        self.assertEqual({item["item_id"] for item in due}, {"log-replication"})

    def test_validate_detects_missing_subject_files(self):
        self.init_subject()
        (self.home / "subjects" / "distributed-systems" / "PLAN.md").unlink()
        result = self.run_cli("validate", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PLAN.md", result.stderr)

    def test_validate_requires_a_complete_subject_before_activation(self):
        self.init_subject()
        result = self.run_cli(
            "validate",
            "--subject",
            "distributed-systems",
            "--activate",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        registry = json.loads((self.home / "registry.json").read_text())
        self.assertFalse(registry["subjects"][0]["ready"])

    def test_validate_activates_a_complete_subject(self):
        self.init_subject()
        self.add_item()
        registry = json.loads((self.home / "registry.json").read_text())
        self.assertTrue(registry["subjects"][0]["ready"])

    def test_status_exposes_future_plan_objectives(self):
        self.init_subject()
        self.add_item()
        plan = self.home / "subjects" / "distributed-systems" / "PLAN.md"
        plan.write_text(
            plan.read_text().replace(
                "## Dependencies",
                "### `log-replication`\n\n"
                "- Outcome: Explain Raft log replication.\n"
                "- Concepts: consensus, replication\n"
                "- Depends on: majority-overlap\n\n"
                "## Dependencies",
            )
        )
        self.run_cli("validate", "--subject", "distributed-systems", "--activate")
        subject = json.loads(
            self.run_cli("status", "--now", "2026-08-29T10:00:00Z").stdout
        )["subjects"][0]
        self.assertIn("log-replication", {item["id"] for item in subject["objectives"]})

    def test_disabled_corrupt_subject_does_not_break_status(self):
        self.init_subject()
        self.add_item()
        self.run_cli("set-enabled", "--subject", "distributed-systems", "--disabled")
        mastery = self.home / "subjects" / "distributed-systems" / "mastery.json"
        mastery.write_text("not json")
        result = self.run_cli("status", "--now", "2026-08-29T10:00:00Z")
        status = json.loads(result.stdout)
        self.assertEqual(status["issues"], [])
        self.assertFalse(status["subjects"][0]["enabled"])

    def test_active_corrupt_subject_is_reported_as_an_issue(self):
        self.init_subject()
        self.add_item()
        mastery = self.home / "subjects" / "distributed-systems" / "mastery.json"
        mastery.write_text("not json")
        result = self.run_cli("status", "--now", "2026-08-29T10:00:00Z")
        status = json.loads(result.stdout)
        self.assertEqual(status["due"], [])
        self.assertEqual(status["issues"][0]["subject_id"], "distributed-systems")
        self.assertIn("invalid JSON", status["issues"][0]["error"])

    def test_validate_rejects_invalid_timestamp_types_without_traceback(self):
        self.init_subject()
        self.add_item()
        mastery_path = self.home / "subjects" / "distributed-systems" / "mastery.json"
        mastery = json.loads(mastery_path.read_text())
        mastery["items"][0]["due_at"] = 1
        mastery_path.write_text(json.dumps(mastery))
        result = self.run_cli(
            "validate",
            "--subject",
            "distributed-systems",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("due_at", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_validate_rejects_incomplete_sources_and_gap_entries(self):
        self.init_subject()
        resources = self.home / "subjects" / "distributed-systems" / "RESOURCES.md"
        resources.write_text(
            "# Resources\n\n## Sources\n\n## Gaps\n\n"
            "### `raft-paper`\n\n- Purpose: Missing primary source.\n"
        )
        result = self.run_cli(
            "validate",
            "--subject",
            "distributed-systems",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source", result.stderr.lower())

    def test_validate_rejects_cyclic_objective_dependencies(self):
        self.init_subject()
        self.add_item()
        plan = self.home / "subjects" / "distributed-systems" / "PLAN.md"
        plan.write_text(
            plan.read_text()
            .replace("- Depends on: none", "- Depends on: log-replication")
            .replace(
                "## Dependencies",
                "### `log-replication`\n\n"
                "- Outcome: Explain Raft log replication.\n"
                "- Concepts: consensus, replication\n"
                "- Depends on: majority-overlap\n\n"
                "## Dependencies",
            )
        )
        result = self.run_cli(
            "validate",
            "--subject",
            "distributed-systems",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency cycle", result.stderr)

    def test_validate_detects_event_mastery_mismatch(self):
        self.init_subject()
        self.add_item()
        events = self.home / "subjects" / "distributed-systems" / "events.jsonl"
        events.write_text(
            json.dumps(
                {
                    "reviewed_at": "2026-08-29T10:00:00Z",
                    "item_id": "majority-overlap",
                    "rating": "good",
                    "confidence": 4,
                    "evidence": "Explained overlap unaided.",
                    "next_stage": 0,
                    "next_due_at": "2026-08-30T10:00:00Z",
                }
            )
            + "\n"
        )
        result = self.run_cli(
            "validate",
            "--subject",
            "distributed-systems",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match latest event", result.stderr)

    def test_validate_rejects_an_impossible_event_transition(self):
        self.init_subject()
        self.add_item()
        subject = self.home / "subjects" / "distributed-systems"
        mastery_path = subject / "mastery.json"
        mastery = json.loads(mastery_path.read_text())
        mastery["items"][0].update(
            {
                "stage": 5,
                "due_at": "2026-08-29T10:00:00Z",
                "last_reviewed_at": "2026-08-29T10:00:00Z",
                "last_rating": "good",
            }
        )
        mastery_path.write_text(json.dumps(mastery))
        (subject / "events.jsonl").write_text(
            json.dumps(
                {
                    "reviewed_at": "2026-08-29T10:00:00Z",
                    "item_id": "majority-overlap",
                    "rating": "good",
                    "confidence": 4,
                    "evidence": "Explained overlap unaided.",
                    "next_stage": 5,
                    "next_due_at": "2026-08-29T10:00:00Z",
                }
            )
            + "\n"
        )
        result = self.run_cli(
            "validate",
            "--subject",
            "distributed-systems",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid transition", result.stderr)

    def test_validate_rejects_review_state_without_events(self):
        self.init_subject()
        self.add_item()
        mastery_path = self.home / "subjects" / "distributed-systems" / "mastery.json"
        mastery = json.loads(mastery_path.read_text())
        mastery["items"][0]["stage"] = 5
        mastery_path.write_text(json.dumps(mastery))
        result = self.run_cli(
            "validate",
            "--subject",
            "distributed-systems",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("initial review state", result.stderr)

    def test_validate_rejects_incomplete_items_and_unknown_sources(self):
        self.init_subject()
        self.add_item()
        mastery_path = self.home / "subjects" / "distributed-systems" / "mastery.json"
        mastery = json.loads(mastery_path.read_text())
        del mastery["items"][0]["prompt"]
        mastery["items"][0]["source_ids"] = ["missing-source"]
        mastery_path.write_text(json.dumps(mastery))
        result = self.run_cli("validate", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prompt", result.stderr)
        self.assertIn("missing-source", result.stderr)

    def test_rejects_invalid_identifiers_and_confidence(self):
        invalid_subject = self.run_cli(
            "init-subject",
            "--id",
            "Not Valid",
            "--title",
            "Invalid",
            "--mission",
            "Invalid.",
            check=False,
        )
        self.assertNotEqual(invalid_subject.returncode, 0)
        self.init_subject()
        self.add_item()
        invalid_confidence = self.run_cli(
            "record-review",
            "--subject",
            "distributed-systems",
            "--item",
            "majority-overlap",
            "--rating",
            "good",
            "--confidence",
            "6",
            "--evidence",
            "Observed response.",
            check=False,
        )
        self.assertNotEqual(invalid_confidence.returncode, 0)


if __name__ == "__main__":
    unittest.main()

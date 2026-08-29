import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "always-learning"
SKILL = SKILL_DIR / "SKILL.md"


class SkillContractTests(unittest.TestCase):
    def test_public_package_is_complete(self):
        expected = {
            ROOT / "README.md",
            SKILL,
            SKILL_DIR / "agents" / "openai.yaml",
            SKILL_DIR / "references" / "subject-management.md",
            SKILL_DIR / "references" / "teaching-loop.md",
            SKILL_DIR / "scripts" / "state.py",
        }
        missing = [str(path.relative_to(ROOT)) for path in expected if not path.is_file()]
        self.assertEqual(missing, [])

    def test_frontmatter_matches_the_skill_directory(self):
        text = SKILL.read_text()
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^name: always-learning$")
        description = re.search(r"(?m)^description: (.+)$", frontmatter)
        self.assertIsNotNone(description)
        self.assertIn("start of every user turn", description.group(1))

    def test_always_loaded_entrypoint_stays_short(self):
        body = SKILL.read_text().split("---", 2)[2]
        words = re.findall(r"\b[\w'-]+\b", body)
        self.assertLessEqual(len(words), 220)

    def test_references_are_linked_and_exist(self):
        text = SKILL.read_text()
        links = re.findall(r"\((references/[^)]+\.md)\)", text)
        self.assertEqual(
            set(links),
            {"references/subject-management.md", "references/teaching-loop.md"},
        )
        self.assertTrue(all((SKILL_DIR / link).is_file() for link in links))

    def test_openai_metadata_allows_implicit_invocation(self):
        metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("$always-learning", metadata)

    def test_repository_copy_is_english(self):
        files = [ROOT / "README.md", *SKILL_DIR.rglob("*")]
        text = "\n".join(path.read_text() for path in files if path.is_file())
        self.assertIsNone(re.search(r"[\u0400-\u04FF]", text))

    def test_repository_has_no_scaffold_placeholders(self):
        files = [ROOT / "README.md", *SKILL_DIR.rglob("*")]
        text = "\n".join(path.read_text() for path in files if path.is_file())
        self.assertIsNone(re.search(r"\b(TODO|TBD|FIXME)\b", text))

    def test_readme_uses_stable_nested_skill_installation(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("npx skills add drveles/teach-me@always-learning", readme)


if __name__ == "__main__":
    unittest.main()

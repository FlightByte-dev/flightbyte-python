import re
import unittest
from importlib import resources

import flightbyte

from .helpers import ROOT

PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def project_field(name: str) -> str:
    """A string field of the [project] table, read without tomllib (Python 3.11+)."""
    table = PYPROJECT.split("[project]", 1)[1].split("\n[", 1)[0]
    match = re.search(rf'^{name} = "([^"]*)"$', table, re.MULTILINE)
    assert match, f"pyproject.toml has no {name}"
    return match.group(1)


class PackageTest(unittest.TestCase):
    def test_has_the_same_version_as_the_code(self) -> None:
        self.assertEqual(flightbyte.__version__, project_field("version"))

    def test_the_changelog_has_a_section_for_the_version(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"\n## {flightbyte.__version__}\n", "\n" + changelog)

    def test_has_no_runtime_dependencies(self) -> None:
        self.assertRegex(PYPROJECT, r"(?m)^dependencies = \[\]$")

    def test_asks_for_python_3_10(self) -> None:
        self.assertEqual(project_field("requires-python"), ">=3.10")

    def test_ships_its_types(self) -> None:
        self.assertTrue(resources.files("flightbyte").joinpath("py.typed").is_file())

    def test_exports_what_it_lists(self) -> None:
        self.assertEqual(sorted(set(flightbyte.__all__)), sorted(flightbyte.__all__))
        missing = [name for name in flightbyte.__all__ if not hasattr(flightbyte, name)]
        self.assertEqual(missing, [])
        public = {
            name
            for name in vars(flightbyte)
            if not name.startswith("_") and not isinstance(getattr(flightbyte, name), type(re))
        }
        self.assertEqual(sorted(public - set(flightbyte.__all__)), [])


if __name__ == "__main__":
    unittest.main()

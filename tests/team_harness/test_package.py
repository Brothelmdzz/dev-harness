"""验证发布后引用可移植、篡改可发现、已有工作不被覆盖。"""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("team_plugin", ROOT / "scripts/team_plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_plugin_can_move_without_source(self):
        package = self.root / "build/dev-harness"
        plugin.package(package)
        moved = self.root / "elsewhere/dev-harness"
        moved.parent.mkdir()
        shutil.move(str(package), str(moved))
        plugin.check(moved)
        for skill in (moved / "skills").iterdir():
            plugin.check_links(skill)
        self.assertFalse((moved / "hooks").exists())

    def test_repository_skills_are_individually_portable(self):
        package = self.root / "kit"
        plugin.package(package, "skills")
        for skill in (package / ".agents/skills").iterdir():
            copy = self.root / skill.name
            shutil.copytree(skill, copy)
            plugin.check_links(copy)
        self.assertFalse((package / ".codex-plugin").exists())

    def test_existing_destination_is_preserved(self):
        output = self.root / "existing"
        output.mkdir()
        marker = output / "user.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            plugin.package(output)
        self.assertEqual(marker.read_text(), "keep")

    def test_changed_release_is_detected(self):
        output = self.root / "dev-harness"
        plugin.package(output)
        (output / "skills/dev-harness-work/references/shared-work.md").write_text("drift")
        with self.assertRaisesRegex(ValueError, "来源清单"):
            plugin.check(output)

    def test_broken_source_link_is_rejected_before_writing(self):
        source = self.root / "source"
        shutil.copytree(plugin.SOURCE, source)
        (source / "references/shared-work.md").unlink()
        output = self.root / "new"
        with self.assertRaises(ValueError):
            plugin.package(output, source=source)
        self.assertFalse(output.exists())

    def test_link_escape_is_rejected(self):
        source = self.root / "source"
        shutil.copytree(plugin.SOURCE, source)
        (self.root / "private.md").write_text("private")
        (source / "README.md").write_text("[outside](../private.md)")
        with self.assertRaisesRegex(ValueError, "越界"):
            plugin.check(source)

    def test_repeat_build_has_same_file_and_source_hashes(self):
        first = plugin.package(self.root / "one")
        second = plugin.package(self.root / "two")
        self.assertEqual(first["files"], second["files"])
        self.assertEqual(first["source_files"], second["source_files"])

    def test_manifests_must_match(self):
        source = self.root / "source"
        shutil.copytree(plugin.SOURCE, source)
        path = source / ".claude-plugin/plugin.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["version"] = "0.0.0"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "元数据不一致"):
            plugin.check(source)


if __name__ == "__main__":
    unittest.main()

"""Synthetic collaboration failures; no real project receipts or credentials."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/team_receipt.py"
spec = importlib.util.spec_from_file_location("team_receipt", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
SCHEMA = checker.load_json(checker.SCHEMA)


def receipt(task="task-a", session="session-a", paths=None):
    return {
        "schema_version": 1, "kind": "receipt", "repository": "example/project",
        "task_id": task, "session_id": session, "revision": "task-revision-1", "state": "active",
        "candidate": {"base_sha": "a" * 40, "head_sha": "b" * 40, "source": "git:example/project#candidate"},
        "ownership": {"source": "task:allocation-1", "paths": paths if paths is not None else ["src/api/"],
                      "shared_interfaces": []},
        "dependencies": [{"task_id": "dependency-a", "head_sha": "c" * 40, "source": "task:dependency-a"}],
        "decisions": [{"id": "decision-a", "revision": "2", "source": "adr:decision-a"}],
        "evidence": [{"candidate_sha": "b" * 40, "command": "python -m unittest",
                      "result": "passed", "source": "artifact:synthetic-test-log", "environment": "synthetic"}],
    }


def context(*receipts):
    tasks = []
    for item in receipts:
        task = {key: copy.deepcopy(item[key]) for key in (
            "task_id", "revision", "state", "candidate", "ownership", "dependencies", "decisions")}
        task["owner_session"] = item["session_id"]
        tasks.append(task)
    return {"schema_version": 1, "kind": "context", "repository": "example/project",
            "source": "task:observed-current-snapshot", "tasks": tasks}


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.receipt = receipt()
        self.context = context(self.receipt)

    def codes(self, *receipts):
        return {item["code"] for item in checker.check(list(receipts or (self.receipt,)), self.context, SCHEMA)}

    def test_current_snapshot_is_consistent(self):
        self.assertEqual(self.codes(), set())

    def test_parallel_disjoint_tasks_are_consistent(self):
        peer = receipt("task-b", "session-b", ["src/ui/"])
        self.context = context(self.receipt, peer)
        self.assertEqual(self.codes(self.receipt, peer), set())

    def test_parallel_file_conflict_and_directory_boundary(self):
        for paths, expected in [(["src/api/client.py"], True), (["src/api/"], True),
                                (["src/"], True), (["src/api"], True), (["src/api-v2/"], False)]:
            with self.subTest(paths=paths):
                peer = receipt("task-b", "session-b", paths)
                self.context = context(self.receipt, peer)
                self.assertEqual("path_conflict" in self.codes(self.receipt, peer), expected)

    def test_file_ancestor_conflicts_in_both_orders(self):
        for child in ("src/api/client.py", "src/api/client/"):
            for left_path, right_path in (("src/api", child), (child, "src/api")):
                with self.subTest(left=left_path, right=right_path):
                    left = receipt("task-a", "session-a", [left_path])
                    right = receipt("task-b", "session-b", [right_path])
                    self.context = context(left, right)
                    self.assertEqual(self.codes(left, right), {"path_conflict"})

    def test_file_ancestor_boundary_does_not_match_sibling_prefix(self):
        for left_path, right_path in (("src/api", "src/api-v2/"), ("src/api-v2/", "src/api")):
            with self.subTest(left=left_path, right=right_path):
                left = receipt("task-a", "session-a", [left_path])
                right = receipt("task-b", "session-b", [right_path])
                self.context = context(left, right)
                self.assertEqual(self.codes(left, right), set())

    def test_shared_interface_conflict_despite_disjoint_files(self):
        self.receipt["ownership"]["shared_interfaces"] = ["public-api-v1"]
        peer = receipt("task-b", "session-b", ["src/ui/"])
        peer["ownership"]["shared_interfaces"] = ["public-api-v1"]
        self.context = context(self.receipt, peer)
        self.assertEqual(self.codes(self.receipt, peer), {"interface_conflict"})

    def test_duplicate_claim_has_no_automatic_winner(self):
        peer = receipt(session="session-b", paths=["src/ui/"])
        self.assertTrue({"duplicate_claim", "owner_mismatch"}.issubset(self.codes(self.receipt, peer)))

    def test_stale_handoff_revision_is_rejected(self):
        self.receipt["state"] = "handoff"
        self.receipt["handoff"] = {"to_session": "session-b", "next_action": "Review candidate"}
        self.context = context(self.receipt)
        self.context["tasks"][0]["revision"] = "task-revision-2"
        self.assertEqual(self.codes(), {"stale_revision"})

    def test_new_decision_and_dependency_invalidate_snapshot(self):
        self.context["tasks"][0]["decisions"][0]["revision"] = "3"
        self.context["tasks"][0]["dependencies"][0]["head_sha"] = "d" * 40
        self.assertEqual(self.codes(), {"stale_decision", "dependency_mismatch"})

    def test_omitted_dependency_and_decision_cannot_hide_staleness(self):
        self.receipt["decisions"] = []
        self.receipt["dependencies"] = []
        self.assertEqual(self.codes(), {"stale_decision", "dependency_mismatch"})

    def test_cancel_then_resume_requires_current_revision_owner_and_state(self):
        task = self.context["tasks"][0]
        task["state"] = "cancelled"
        task["revision"] = "task-revision-2"
        self.assertEqual(self.codes(), {"stale_revision", "state_mismatch"})
        self.receipt.update(state="cancelled", revision="task-revision-2")
        self.assertEqual(self.codes(), set())
        task.update(state="active", revision="task-revision-3", owner_session="session-b")
        self.assertEqual(self.codes(), {"stale_revision", "state_mismatch", "owner_mismatch"})
        self.receipt.update(state="active", revision="task-revision-3", session_id="session-b")
        self.assertEqual(self.codes(), set())

    def test_cancelled_owner_does_not_reserve_paths(self):
        self.receipt["state"] = "cancelled"
        peer = receipt("task-b", "session-b")
        self.context = context(self.receipt, peer)
        self.assertEqual(self.codes(self.receipt, peer), set())

    def test_evidence_is_bound_to_candidate_sha(self):
        self.receipt["evidence"][0]["candidate_sha"] = "d" * 40
        self.assertEqual(self.codes(), {"evidence_sha_mismatch"})

    def test_candidate_and_granted_scope_must_match_current_source(self):
        self.context["tasks"][0]["candidate"]["head_sha"] = "d" * 40
        self.receipt["ownership"]["paths"].append("outside/grant.py")
        self.assertEqual(self.codes(), {"candidate_mismatch", "ownership_mismatch"})

    def test_repository_and_unknown_task_are_rejected(self):
        self.receipt["repository"] = "example/other"
        self.assertEqual(self.codes(), {"repository_mismatch"})
        self.receipt["repository"] = "example/project"
        self.receipt["task_id"] = "unknown"
        self.assertEqual(self.codes(), {"task_unknown"})

    def test_handoff_requires_recipient_and_next_action(self):
        self.receipt["state"] = "handoff"
        self.context = context(self.receipt)
        self.assertEqual(self.codes(), {"handoff_invalid"})
        self.receipt["handoff"] = {"to_session": "session-b", "next_action": "Review candidate"}
        self.assertEqual(self.codes(), set())
        self.receipt["handoff"]["to_session"] = "session-a"
        self.assertEqual(self.codes(), {"handoff_invalid"})

    def test_unknown_fields_and_invalid_versions_are_input_errors(self):
        for field, value in [("model_requested", "Astra xhigh"), ("schema_version", True),
                             ("schema_version", 2), ("state", "accepted"), ("revision", " ")]:
            with self.subTest(field=field, value=value):
                item = copy.deepcopy(self.receipt)
                item[field] = value
                with self.assertRaises(ValueError):
                    checker.check([item], self.context, SCHEMA)

    def test_canonical_paths_only(self):
        for path in ("../private", "/tmp/file", "src/../file", "src//file", "./file", "src/*.py", "src\\file", "C:/file", "src/file\n"):
            with self.subTest(path=path):
                self.receipt["ownership"]["paths"] = [path]
                with self.assertRaises(ValueError):
                    self.codes()

    def test_full_sha_required_and_sha256_is_supported(self):
        for sha in ("abc123", "A" * 40, "b" * 40 + "\n", "unknown"):
            with self.subTest(sha=sha):
                item = copy.deepcopy(self.receipt)
                item["candidate"]["head_sha"] = sha
                with self.assertRaises(ValueError):
                    checker.check([item], self.context, SCHEMA)
        self.receipt["candidate"]["head_sha"] = "b" * 64
        self.receipt["evidence"][0]["candidate_sha"] = "b" * 64
        self.context = context(self.receipt)
        self.assertEqual(self.codes(), set())

    def test_duplicate_identifiers_cannot_shadow_current_facts(self):
        for field, key in (("decisions", "revision"), ("dependencies", "head_sha")):
            with self.subTest(field=field):
                item = copy.deepcopy(self.receipt)
                duplicate = copy.deepcopy(item[field][0])
                duplicate[key] = "d" * 40
                item[field].append(duplicate)
                with self.assertRaises(ValueError):
                    checker.check([item], self.context, SCHEMA)
        self.context["tasks"].append(copy.deepcopy(self.context["tasks"][0]))
        with self.assertRaises(ValueError):
            self.codes()

    def test_repeated_receipt_is_input_error(self):
        with self.assertRaises(ValueError):
            self.codes(self.receipt, self.receipt)

    def run_cli(self, root, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "check", str(root / "receipt.json"),
                               "--context", str(root / "context.json"), *extra],
                              cwd=root, capture_output=True, text=True)

    def write_inputs(self, root):
        (root / "receipt.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        (root / "context.json").write_text(json.dumps(self.context), encoding="utf-8")

    def test_cli_is_read_only_and_does_not_execute_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.receipt["evidence"][0]["command"] = "touch SHOULD_NOT_EXIST"
            self.write_inputs(root)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = self.run_cli(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["status"], "consistent")
            self.assertEqual(output["behavior_verification"], "not_performed")
            self.assertIn("Only supplied peers", output["limits"][1])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_missing_and_unverified_evidence_are_not_behavior_passes(self):
        for result in (None, "failed", "pending", "not_run", "skipped", "unavailable", "unknown"):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.receipt = receipt()
                if result is None:
                    self.receipt["evidence"] = []
                else:
                    self.receipt["evidence"][0]["result"] = result
                self.write_inputs(root)
                output = json.loads(self.run_cli(root).stdout)
                self.assertEqual(output["status"], "consistent")
                self.assertEqual(output["behavior_verification"], "not_performed")
                self.assertEqual(output["evidence_results"]["passed"], 0)
                self.assertEqual(output["receipts_without_evidence"], int(result is None))

    def test_cli_conflict_and_invalid_input_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.receipt["evidence"][0]["candidate_sha"] = "d" * 40
            self.write_inputs(root)
            result = self.run_cli(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "conflict")
            for content in ('{"kind":"receipt","kind":"context"}', '{"value":NaN}', '[]', '{'):
                (root / "receipt.json").write_text(content)
                result = self.run_cli(root)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "invalid_input")
                self.assertNotIn("Traceback", result.stderr)

    def test_schema_version_requires_integer_token_in_both_inputs(self):
        # JSON Schema considers 1.0 an integer; the frozen CLI requires token 1.
        for filename in ("receipt.json", "context.json"):
            for token in ("1.0", "1e0", "true", '"1"'):
                with self.subTest(file=filename, token=token), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.write_inputs(root)
                    path = root / filename
                    path.write_text(path.read_text().replace('"schema_version": 1',
                                                             '"schema_version": ' + token, 1))
                    result = self.run_cli(root)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(json.loads(result.stdout)["status"], "invalid_input")

    def test_cli_peer_argument_checks_conflicts(self):
        peer = receipt("task-b", "session-b")
        self.context = context(self.receipt, peer)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_inputs(root)
            (root / "peer.json").write_text(json.dumps(peer), encoding="utf-8")
            result = self.run_cli(root, "--peer", str(root / "peer.json"))
            self.assertEqual(result.returncode, 1)
            output = json.loads(result.stdout)
            self.assertEqual(output["checked_receipts"], 2)
            self.assertEqual({error["code"] for error in output["errors"]}, {"path_conflict"})

    def test_late_qa_results_are_excluded_after_owner_or_revision_changes(self):
        for changed_head, changed_owner in ((True, True), (False, True), (False, False)):
            for late_first in (False, True):
                with self.subTest(head=changed_head, owner=changed_owner, late_first=late_first):
                    late = receipt()
                    current = copy.deepcopy(late)
                    current["revision"] = "task-revision-2"
                    if changed_owner:
                        current["session_id"] = "replacement-session"
                    if changed_head:
                        current["candidate"]["head_sha"] = "d" * 40
                    current["evidence"][0].update(candidate_sha=current["candidate"]["head_sha"], result="pending")
                    self.context = context(current)
                    self.receipt, peer = (late, current) if late_first else (current, late)
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        self.write_inputs(root)
                        (root / "peer.json").write_text(json.dumps(peer))
                        run = self.run_cli(root, "--peer", str(root / "peer.json"))
                    output = json.loads(run.stdout)
                    self.assertEqual(run.returncode, 1)
                    self.assertEqual(output["evidence_results"]["passed"], 1)
                    current_counts = output.get("current_evidence_results", output["evidence_results"])
                    self.assertEqual(current_counts["passed"], 0)
                    self.assertEqual(current_counts["pending"], 1)
                    self.assertEqual(output["excluded_evidence_results"]["passed"], 1)
                    self.assertEqual(output["excluded_receipt_indices"], [0 if late_first else 1])
                    self.assertEqual(output["behavior_verification"], "not_performed")
                    for name, total in output["evidence_results"].items():
                        self.assertEqual(total, output["current_evidence_results"][name]
                                         + output["excluded_evidence_results"][name])

    def test_cancelled_evidence_is_declared_but_excluded_from_current_counts(self):
        self.receipt["state"] = "cancelled"
        self.context = context(self.receipt)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_inputs(root)
            run = self.run_cli(root)
        output = json.loads(run.stdout)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(output["evidence_results"]["passed"], 1)
        self.assertEqual(output.get("current_evidence_results", output["evidence_results"])["passed"], 0)
        self.assertEqual(output["excluded_receipt_indices"], [0])

    def test_scope_conflicts_exclude_both_current_receipts_from_evidence_counts(self):
        peer = receipt("task-b", "session-b")
        self.context = context(self.receipt, peer)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_inputs(root)
            (root / "peer.json").write_text(json.dumps(peer))
            run = self.run_cli(root, "--peer", str(root / "peer.json"))
        output = json.loads(run.stdout)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(output.get("current_evidence_results", output["evidence_results"])["passed"], 0)
        self.assertEqual(output["excluded_evidence_results"]["passed"], 2)
        self.assertEqual(output["excluded_receipt_indices"], [0, 1])

    def test_current_complete_evidence_remains_a_declaration(self):
        self.receipt["state"] = "complete"
        self.context = context(self.receipt)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_inputs(root)
            run = self.run_cli(root)
        output = json.loads(run.stdout)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(output.get("current_evidence_results", output["evidence_results"])["passed"], 1)
        self.assertEqual(output.get("excluded_receipt_indices", []), [])
        self.assertEqual(output["behavior_verification"], "not_performed")

    def test_changed_dependency_or_evidence_sha_excludes_current_passes(self):
        for field in ("dependencies", "evidence"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.receipt = receipt()
                self.context = context(self.receipt)
                if field == "dependencies":
                    self.context["tasks"][0][field][0]["head_sha"] = "d" * 40
                else:
                    self.receipt[field][0]["candidate_sha"] = "d" * 40
                self.write_inputs(root)
                run = self.run_cli(root)
                output = json.loads(run.stdout)
                self.assertEqual(run.returncode, 1)
                self.assertEqual(output.get("current_evidence_results", output["evidence_results"])["passed"], 0)
                self.assertEqual(output["excluded_receipt_indices"], [0])


if __name__ == "__main__":
    unittest.main()

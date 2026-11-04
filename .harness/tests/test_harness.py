import base64
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import pty
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
CLI = SOURCE / ".harness/bin/harness"
FEATURES = ".harness/state/feature_list.json"
DEBTS = ".harness/state/techdebt_list.json"
CONFIG = ".harness/config.json"
RULES = ".harness/rules.json"

_template = None


def setUpModule():
    global _template
    _template = tempfile.mkdtemp(prefix="harness-template-")
    result = subprocess.run([sys.executable, str(CLI), "init", "python", f"{_template}/app", "--name", "demo"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def tearDownModule():
    shutil.rmtree(_template, ignore_errors=True)


def feature(name="alpha", sdd=True, status="pending", id=1, **extra):
    data = {"id": id, "name": name, "title": name, "description": "d", "acceptance": ["a"],
            "sdd": sdd, "status": status}
    data.update(extra)
    return data


def debt(**overrides):
    data = {"id": 1, "name": "owed", "title": "t", "description": "d", "kind": "shortcut", "severity": "low",
            "origin": {"agent": "implementer", "feature": "alpha", "task": "T1", "session": "2026-01-01"},
            "location": ["src/"], "interest": "i", "acceptance": ["a"], "sdd": False, "status": "open"}
    data.update(overrides)
    return data


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = Path(self.tmp) / "app"
        shutil.copytree(f"{_template}/app", self.root, symlinks=True)
        self.cli = self.root / ".harness/bin/harness"

    def run_at_terminal(self, *args, answer=None):
        """Run the CLI with a real controlling terminal, typing the code it shows."""
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.root)
            os.execv(sys.executable, [sys.executable, str(self.cli), *args])
        output, sent = b"", False
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            match = re.search(rb"confirm: (\w+)", output)
            if match and not sent:
                os.write(fd, (answer.encode() if answer else match.group(1)) + b"\n")
                sent = True
        os.close(fd)
        _, status = os.waitpid(pid, 0)
        return subprocess.CompletedProcess(args, os.waitstatus_to_exitcode(status),
                                           output.decode("utf-8", "replace"), "")

    def run_cli(self, *args, input_text=None):
        return subprocess.run([sys.executable, str(self.cli), *args], cwd=str(self.root),
                              input=input_text if input_text is not None else "", capture_output=True, text=True)

    def path(self, relative):
        return self.root / relative

    def write(self, relative, text):
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read_json(self, relative):
        return json.loads(self.path(relative).read_text(encoding="utf-8"))

    def set_features(self, *features):
        doc = self.read_json(FEATURES)
        doc["features"] = list(features)
        self.write(FEATURES, json.dumps(doc, indent=2))

    def set_debts(self, *debts):
        doc = self.read_json(DEBTS)
        doc["debts"] = list(debts)
        self.write(DEBTS, json.dumps(doc, indent=2))

    def status(self, name="alpha"):
        return next(f["status"] for f in self.read_json(FEATURES)["features"] if f["name"] == name)

    def write_spec(self, name="alpha", tasks="- [ ] T1 — do it. Covers: R1.\n"):
        self.write(f".harness/specs/{name}/requirements.md", "## R1\nThe system SHALL work.\n")
        self.write(f".harness/specs/{name}/design.md", "design\n")
        self.write(f".harness/specs/{name}/tasks.md", tasks)

    def approve(self, name="alpha"):
        result = self.run_at_terminal("approve", name)
        self.assertEqual(result.returncode, 0, result.stdout)

    def write_impl(self, name="alpha"):
        self.write("src/app/traced.py", "def test_it():\n    pass\n")
        self.write(f".harness/progress/impl_{name}.md", "## Traceability\n- R1 → `test_it`\n")

    def write_review(self, name="alpha", verdict="APPROVED"):
        self.write(f".harness/progress/review_{name}.md", f"# Review\n\n**Verdict:** {verdict}\n")

    def make_done_ready(self, name="alpha"):
        """A complete sdd feature: everything a done feature needs."""
        self.write_spec(name, tasks="- [x] T1 — do it. Covers: R1.\n")
        self.set_features(feature(name, status="spec_ready"))
        self.approve(name)
        self.write_impl(name)
        self.write_review(name)

    def assert_check_fails(self, expected, *args):
        result = self.run_cli("check", "--no-tests", *args)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stdout + result.stderr)

    def assert_check_passes(self, *args):
        result = self.run_cli("check", "--no-tests", *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CheckTests(ProjectCase):
    def test_fresh_project_passes_with_tests(self):
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_fails_on_corrupt_feature_list(self):
        self.write(FEATURES, "{ not json")
        self.assert_check_fails("invalid JSON")

    def test_fails_on_corrupt_debt_list(self):
        self.write(DEBTS, "[")
        self.assert_check_fails("invalid JSON")

    def test_fails_on_deleted_required_files(self):
        self.path(DEBTS).unlink()
        self.path(".harness/docs/specs.md").unlink()
        result = self.run_cli("check", "--no-tests")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("techdebt_list.json", result.stdout)
        self.assertIn("docs/specs.md", result.stdout)

    def test_fails_on_done_feature_without_spec_or_tests(self):
        self.set_features(feature(status="done"))
        result = self.run_cli("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing spec files", result.stdout)
        self.assertIn("no review report", result.stdout)

    def test_fails_on_invalid_rules(self):
        self.write(RULES, "{}")
        self.assert_check_fails("missing key")

    def test_fails_on_rules_with_unknown_guard(self):
        rules = self.read_json(RULES)
        rules["transitions"][0]["guards"] = ["made_up"]
        self.write(RULES, json.dumps(rules))
        self.assert_check_fails("unknown guard")

    def test_fails_on_invalid_config(self):
        self.write(CONFIG, "{}")
        self.assert_check_fails("config.json")

    def test_fails_on_schema_violation(self):
        broken = feature()
        del broken["acceptance"]
        self.set_features(broken)
        self.assert_check_fails("acceptance")

    def test_fails_on_unknown_status(self):
        self.set_features(feature(status="shipped"))
        self.assert_check_fails("unknown status")

    def test_fails_on_illegal_state_for_sdd_false(self):
        self.set_features(feature(sdd=False, status="spec_ready"))
        self.assert_check_fails("illegal")

    def test_fails_on_blocked_without_origin_state(self):
        self.set_features(feature(status="blocked"))
        self.assert_check_fails("blocked_from")

    def test_fails_on_two_in_progress(self):
        self.set_features(feature("alpha", sdd=False, status="in_progress"),
                          feature("beta", sdd=False, status="in_progress", id=2))
        self.assert_check_fails("more than one")

    def test_fails_on_sdd_past_pending_without_spec_files(self):
        self.set_features(feature(status="spec_ready"))
        self.assert_check_fails("missing spec files")

    def test_fails_on_in_progress_without_approval(self):
        self.write_spec()
        self.set_features(feature(status="in_progress"))
        self.assert_check_fails("no human approval")

    def test_fails_on_done_without_approval(self):
        self.make_done_ready()
        self.path(".harness/approvals/alpha.json").unlink()
        self.set_features(feature(status="done"))
        self.assert_check_fails("no human approval")

    def test_fails_on_done_with_unchecked_tasks(self):
        self.make_done_ready()
        self.write(".harness/specs/alpha/tasks.md", "- [ ] T1 — do it. Covers: R1.\n")
        self.set_features(feature(status="done"))
        self.assert_check_fails("unchecked task")

    def test_fails_on_done_without_trace(self):
        self.make_done_ready()
        self.write(".harness/progress/impl_alpha.md", "## Traceability\n")
        self.set_features(feature(status="done"))
        self.assert_check_fails("no test mapped for R1")

    def test_fails_on_done_without_implementation_report(self):
        self.make_done_ready()
        self.path(".harness/progress/impl_alpha.md").unlink()
        self.set_features(feature(status="done"))
        self.assert_check_fails("no implementation report")

    def test_fails_on_done_without_approved_review(self):
        self.make_done_ready()
        self.write_review(verdict="CHANGES_REQUESTED")
        self.set_features(feature(status="done"))
        self.assert_check_fails("not APPROVED")

    def test_fails_on_done_sdd_false_without_review(self):
        self.set_features(feature(sdd=False, status="done"))
        self.assert_check_fails("no review report")

    def test_passes_on_complete_done_feature(self):
        self.make_done_ready()
        self.set_features(feature(status="done"))
        self.assert_check_passes()

    def test_fails_on_open_critical_debt(self):
        self.set_debts(debt(severity="critical"))
        self.assert_check_fails("critical debt")

    def test_fails_on_scheduled_sdd_debt_without_feature(self):
        self.set_debts(debt(status="scheduled", sdd=True))
        self.assert_check_fails("no matching open feature")

    def test_passes_on_scheduled_sdd_debt_with_pending_feature(self):
        self.set_debts(debt(status="scheduled", sdd=True))
        self.set_features(feature("owed"))
        self.assert_check_passes()

    def test_fails_on_empty_debt_acceptance(self):
        self.set_debts(debt(acceptance=[]))
        self.assert_check_fails("acceptance")

    def test_fails_on_empty_debt_origin(self):
        self.set_debts(debt(origin={}))
        self.assert_check_fails("origin")

    def test_fails_on_unconfigured_test_command(self):
        config = self.read_json(CONFIG)
        config["commands"]["test"] = ""
        self.write(CONFIG, json.dumps(config))
        self.assert_check_fails("commands.test")

    def test_fails_when_hook_is_unwired(self):
        self.write(".claude/settings.json", "{}")
        self.assert_check_fails("hook")

    def test_malformed_settings_are_a_failure_not_a_crash(self):
        for text in ("[]", '{"hooks": []}', '{"hooks": {"PreToolUse": [1]}}',
                     '{"hooks": {"PreToolUse": [{"hooks": [{"command": "harness", "args": 5}]}]}}'):
            with self.subTest(text=text):
                self.write(".claude/settings.json", text)
                result = self.run_cli("check", "--no-tests")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("does not run the harness", result.stdout)

    def test_fails_on_failing_tests(self):
        self.write("src/tests/test_app.py",
                   "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('no')\n")
        result = self.run_cli("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tests failed", result.stdout)

    def test_no_tests_only_warns_while_nothing_is_done(self):
        self.path("src/tests/test_app.py").unlink()
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("[WARN]", result.stdout)

    def test_no_tests_fails_once_a_feature_is_done(self):
        self.make_done_ready()
        self.set_features(feature(status="done"))
        self.path("src/tests/test_app.py").unlink()
        result = self.run_cli("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("found no tests", result.stdout)


class TransitionTests(ProjectCase):
    def test_full_sdd_lifecycle(self):
        self.set_features(feature())
        self.assertTrue(self.run_cli("next").stdout.startswith("spec_author:"))
        self.write_spec()
        self.assertEqual(self.run_cli("transition", "alpha", "spec_ready", "--as", "spec_author").returncode, 0)
        self.assertTrue(self.run_cli("next").stdout.startswith("human:"))
        self.approve()
        self.assertIn("in_progress", self.run_cli("next").stdout)
        self.assertEqual(self.run_cli("transition", "alpha", "in_progress").returncode, 0)
        self.assertTrue(self.run_cli("next").stdout.startswith("implementer:"))
        self.write(".harness/specs/alpha/tasks.md", "- [x] T1 — do it. Covers: R1.\n")
        self.write_impl()
        self.assertTrue(self.run_cli("next").stdout.startswith("reviewer:"))
        self.write_review(verdict="CHANGES_REQUESTED")
        os.utime(self.path(".harness/progress/impl_alpha.md"), (1, 1))
        self.assertTrue(self.run_cli("next").stdout.startswith("implementer:"))
        self.assertNotEqual(self.run_cli("transition", "alpha", "done").returncode, 0)
        self.write_review()
        self.assertIn("transition alpha done", self.run_cli("next").stdout)
        result = self.run_cli("transition", "alpha", "done")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.status(), "done")
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_sdd_false_goes_straight_to_in_progress(self):
        self.set_features(feature(sdd=False))
        self.assertEqual(self.run_cli("transition", "alpha", "in_progress").returncode, 0)
        self.assertEqual(self.status(), "in_progress")

    def test_sdd_false_closes_on_approved_review(self):
        self.set_features(feature(sdd=False, status="in_progress"))
        self.assertNotEqual(self.run_cli("transition", "alpha", "done").returncode, 0)
        self.write_impl()
        self.write_review()
        self.assertEqual(self.run_cli("transition", "alpha", "done").returncode, 0)

    def test_rejects_skipping_states(self):
        self.set_features(feature())
        result = self.run_cli("transition", "alpha", "done")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("illegal transition", result.stderr)

    def test_rejects_sdd_feature_skipping_the_spec(self):
        self.set_features(feature())
        self.assertNotEqual(self.run_cli("transition", "alpha", "in_progress").returncode, 0)
        self.assertEqual(self.status(), "pending")

    def test_rejects_wrong_actor(self):
        self.write_spec()
        self.set_features(feature())
        result = self.run_cli("transition", "alpha", "spec_ready", "--as", "leader")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("belongs to spec_author", result.stderr)

    def test_rejects_spec_ready_without_files(self):
        self.set_features(feature())
        self.assertNotEqual(self.run_cli("transition", "alpha", "spec_ready", "--as", "spec_author").returncode, 0)

    def test_rejects_in_progress_without_approval(self):
        self.write_spec()
        self.set_features(feature(status="spec_ready"))
        result = self.run_cli("transition", "alpha", "in_progress")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no human approval", result.stderr)

    def test_rejects_second_in_progress(self):
        self.set_features(feature("alpha", sdd=False, status="in_progress"), feature("beta", sdd=False, id=2))
        result = self.run_cli("transition", "beta", "in_progress")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another feature", result.stderr)

    def test_done_requires_green_tests(self):
        self.make_done_ready()
        self.set_features(feature(status="in_progress"))
        self.write("src/tests/test_app.py",
                   "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('no')\n")
        result = self.run_cli("transition", "alpha", "done")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tests failed", result.stderr)
        self.assertEqual(self.status(), "in_progress")

    def test_done_requires_complete_tasks(self):
        self.make_done_ready()
        self.write(".harness/specs/alpha/tasks.md", "- [ ] T1 — do it. Covers: R1.\n")
        self.set_features(feature(status="in_progress"))
        self.assertNotEqual(self.run_cli("transition", "alpha", "done").returncode, 0)

    def test_blocking_requires_a_reason(self):
        self.set_features(feature())
        self.assertNotEqual(self.run_cli("transition", "alpha", "blocked").returncode, 0)

    def test_any_agent_blocks_and_human_restores_previous_state(self):
        self.set_features(feature(sdd=False, status="in_progress"))
        result = self.run_cli("transition", "alpha", "blocked", "--as", "implementer", "--reason", "stuck")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_cli("check", "--no-tests").returncode, 0)
        self.assertTrue(self.run_cli("next").stdout.startswith("human:"))
        self.assertNotEqual(self.run_cli("transition", "alpha", "in_progress").returncode, 0)
        self.assertNotEqual(self.run_cli("transition", "alpha", "in_progress", "--as", "human").returncode, 0)
        result = self.run_at_terminal("transition", "alpha", "in_progress", "--as", "human")
        self.assertEqual(result.returncode, 0, result.stdout)
        stored = self.read_json(FEATURES)["features"][0]
        self.assertEqual(stored["status"], "in_progress")
        self.assertNotIn("blocked_from", stored)

    def test_blocked_cannot_jump_to_another_state(self):
        self.set_features(feature(status="blocked", blocked_from="pending"))
        self.assertNotEqual(self.run_at_terminal("transition", "alpha", "done", "--as", "human").returncode, 0)

    def test_unknown_feature_is_an_error(self):
        self.assertIn("unknown feature", self.run_cli("transition", "nope", "done").stderr)


class NextTests(ProjectCase):
    def test_prints_exactly_one_line(self):
        self.assertEqual(len(self.run_cli("next").stdout.strip().splitlines()), 1)

    def test_critical_debt_outranks_features(self):
        self.set_features(feature())
        self.set_debts(debt(severity="critical"))
        self.assertIn("critical debt", self.run_cli("next").stdout)

    def test_sdd_false_pending_is_a_leader_transition(self):
        self.set_features(feature(sdd=False))
        self.assertIn("harness transition alpha in_progress", self.run_cli("next").stdout)


class ApprovalTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write_spec()
        self.set_features(feature(status="spec_ready"))

    def test_refuses_without_a_terminal(self):
        result = self.run_cli("approve", "alpha")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("human only", result.stderr)
        self.assertFalse(self.path(".harness/approvals/alpha.json").exists())

    def test_records_a_hash_per_spec_file(self):
        self.approve()
        files = self.read_json(".harness/approvals/alpha.json")["files"]
        self.assertEqual(sorted(files), ["design.md", "requirements.md", "tasks.md"])

    def test_spec_edit_invalidates_approval(self):
        self.approve()
        self.set_features(feature(status="in_progress"))
        self.assert_check_passes()
        self.write(".harness/specs/alpha/requirements.md", "## R1\nThe system SHALL differ.\n")
        self.assert_check_fails("spec changed after approval")

    def test_adding_a_task_invalidates_approval(self):
        self.approve()
        self.set_features(feature(status="in_progress"))
        self.write(".harness/specs/alpha/tasks.md", "- [ ] T1 — do it. Covers: R1.\n- [ ] T2 — more.\n")
        self.assert_check_fails("spec changed after approval")

    def test_ticking_a_task_keeps_approval(self):
        self.approve()
        self.set_features(feature(status="in_progress"))
        self.write(".harness/specs/alpha/tasks.md", "- [x] T1 — do it. Covers: R1.\n")
        self.assert_check_passes()


class HookCase(ProjectCase):
    def hook(self, tool, tool_input, agent=None):
        payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root)}
        if agent:
            payload["agent_type"] = agent
        return self.run_cli("hook", "pre-tool-use", input_text=json.dumps(payload))

    def write_call(self, relative, agent=None, content="x"):
        return self.hook("Write", {"file_path": str(self.root / relative), "content": content}, agent)

    def assert_allowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_blocked(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("harness: blocked", result.stderr)

    def bash(self, command, agent=None):
        return self.hook("Bash", {"command": command}, agent)


class HookFileToolTests(HookCase):
    def test_role_matrix(self):
        cases = [
            (None, "src/app/x.py", False),
            ("leader", "src/app/x.py", False),
            ("leader", ".harness/approvals/alpha.json", False),
            ("leader", ".harness/progress/current.md", True),
            ("leader", ".harness/docs/architecture.md", True),
            ("leader", "README.md", True),
            ("leader", ".harness/rules.json", False),
            ("leader", ".claude/settings.json", False),
            ("spec_author", ".harness/specs/alpha/design.md", True),
            ("spec_author", ".harness/progress/spec_alpha.md", True),
            ("spec_author", "src/app/x.py", False),
            ("spec_author", ".harness/progress/impl_alpha.md", False),
            ("implementer", "src/app/x.py", True),
            ("implementer", ".harness/progress/impl_alpha.md", True),
            ("implementer", ".harness/specs/alpha/design.md", False),
            ("implementer", ".harness/config.json", False),
            ("reviewer", ".harness/progress/review_alpha.md", True),
            ("reviewer", ".harness/progress/impl_alpha.md", False),
            ("reviewer", "src/app/x.py", False),
            ("general-purpose", "src/app/x.py", False),
            ("general-purpose", ".harness/approvals/a.json", False),
            ("general-purpose", ".harness/state/feature_list.json", False),
            ("general-purpose", "notes.txt", True),
        ]
        for agent, path, allowed in cases:
            with self.subTest(agent=agent, path=path):
                result = self.write_call(path, agent)
                self.assertEqual(result.returncode, 0 if allowed else 2, result.stderr)

    def test_writes_outside_the_project_are_not_governed(self):
        self.assert_allowed(self.hook("Write", {"file_path": "/tmp/harness-free.txt", "content": "x"}, "reviewer"))

    def test_path_traversal_is_resolved(self):
        self.assert_blocked(self.write_call(".harness/progress/../approvals/a.json", "leader"))

    def test_notebook_edit_is_governed(self):
        self.assert_blocked(self.hook("NotebookEdit", {"notebook_path": str(self.root / "src/n.ipynb")}, "leader"))

    def test_implementer_may_tick_only_the_active_tasks(self):
        self.write_spec()
        self.write_spec("beta")
        self.set_features(feature(status="in_progress"), feature("beta", id=2))
        tick = {"old_string": "- [ ] T1", "new_string": "- [x] T1"}
        active = str(self.path(".harness/specs/alpha/tasks.md"))
        other = str(self.path(".harness/specs/beta/tasks.md"))
        self.assert_allowed(self.hook("Edit", {"file_path": active, **tick}, "implementer"))
        self.assert_blocked(self.hook("Edit", {"file_path": other, **tick}, "implementer"))
        rewrite = {"old_string": "do it", "new_string": "do less"}
        self.assert_blocked(self.hook("Edit", {"file_path": active, **rewrite}, "implementer"))

    def test_leader_may_append_a_pending_feature(self):
        self.set_features(feature())
        doc = self.read_json(FEATURES)
        doc["features"].append(feature("beta", id=2))
        self.assert_allowed(self.write_call(FEATURES, "leader", json.dumps(doc)))

    def test_new_feature_must_be_pending(self):
        doc = self.read_json(FEATURES)
        doc["features"].append(feature(status="done"))
        self.assert_blocked(self.write_call(FEATURES, "leader", json.dumps(doc)))

    def test_status_edit_is_blocked_for_write(self):
        self.set_features(feature())
        doc = self.read_json(FEATURES)
        doc["features"][0]["status"] = "done"
        self.assert_blocked(self.write_call(FEATURES, "leader", json.dumps(doc)))

    def test_status_edit_is_blocked_for_edit(self):
        self.set_features(feature())
        edit = {"file_path": str(self.path(FEATURES)), "old_string": '"status": "pending"',
                "new_string": '"status": "done"'}
        self.assert_blocked(self.hook("Edit", edit, "leader"))

    def test_edit_that_breaks_json_is_blocked(self):
        self.assert_blocked(self.write_call(FEATURES, "leader", "{ nope"))

    def test_removing_a_started_feature_is_blocked(self):
        self.set_features(feature(sdd=False, status="in_progress"))
        doc = self.read_json(FEATURES)
        doc["features"] = []
        self.assert_blocked(self.write_call(FEATURES, "leader", json.dumps(doc)))

    def test_implementer_appends_debt_but_cannot_change_it(self):
        self.set_debts(debt())
        doc = self.read_json(DEBTS)
        doc["debts"].append(debt(id=2, name="more"))
        self.assert_allowed(self.write_call(DEBTS, "implementer", json.dumps(doc)))
        doc = self.read_json(DEBTS)
        doc["debts"][0]["status"] = "accepted"
        self.assert_blocked(self.write_call(DEBTS, "implementer", json.dumps(doc)))
        self.assert_allowed(self.write_call(DEBTS, "leader", json.dumps(doc)))

    def test_nobody_resolves_debt_by_hand(self):
        self.set_debts(debt())
        doc = self.read_json(DEBTS)
        doc["debts"][0]["status"] = "resolved"
        self.assert_blocked(self.write_call(DEBTS, "leader", json.dumps(doc)))

    def test_read_only_tools_pass(self):
        self.assert_allowed(self.hook("Read", {"file_path": str(self.path(RULES))}, "reviewer"))


class HookFailClosedTests(HookCase):
    def test_blocks_when_rules_are_missing(self):
        self.path(RULES).unlink()
        result = self.write_call("README.md", "leader")
        self.assertEqual(result.returncode, 2)
        self.assertIn("fail closed", result.stderr)

    def test_blocks_when_rules_are_corrupt(self):
        self.write(RULES, "{ nope")
        self.assertEqual(self.write_call("README.md", "leader").returncode, 2)

    def test_blocks_when_rules_fail_validation(self):
        self.write(RULES, "{}")
        self.assertEqual(self.write_call("README.md", "leader").returncode, 2)

    def test_blocks_when_config_is_missing(self):
        self.path(CONFIG).unlink()
        self.assertEqual(self.write_call("README.md", "leader").returncode, 2)

    def test_blocks_on_invalid_payload(self):
        self.assertEqual(self.run_cli("hook", "pre-tool-use", input_text="nope").returncode, 2)

    def test_blocks_a_file_tool_without_a_path(self):
        self.assert_blocked(self.hook("Write", {"content": "x"}, "leader"))

    def test_scaffold_mode_allows_harness_development(self):
        config = self.read_json(CONFIG)
        config["stack"] = None
        self.write(CONFIG, json.dumps(config))
        self.assert_allowed(self.write_call("src/app/x.py", "leader"))


class HookBashTests(HookCase):
    def test_blocked_commands(self):
        cases = [
            ("leader", "echo x > src/app/x.py"),
            ("leader", "echo x >> src/app/x.py"),
            ("leader", "echo x | tee src/app/x.py"),
            ("leader", "sed -i '' 's/a/b/' src/app/__init__.py"),
            ("leader", "rm -rf src"),
            ("leader", "mv src/app/__init__.py /tmp/x"),
            ("leader", "cp /tmp/x src/app/x.py"),
            ("leader", "cd src && echo x > app/x.py"),
            ("leader", "bash -c 'echo x > src/app/x.py'"),
            ("reviewer", "touch src/app/x.py"),
            ("general-purpose", "rm -rf ."),
            ("implementer", "echo '{}' > .harness/approvals/alpha.json"),
            ("implementer", "echo '{}' > .harness/state/feature_list.json"),
            ("leader", "echo '{}' > .harness/state/feature_list.json"),
            ("leader", "sed -i '' 's/pending/done/' .harness/state/feature_list.json"),
            ("leader", "python3 -c \"open('.harness/state/feature_list.json','w').write('x')\""),
            ("leader", "python3 -c \"import pathlib; pathlib.Path('.harness/approvals/a.json').write_text('x')\""),
            ("leader", ".harness/bin/harness approve alpha"),
            ("leader", "harness approve alpha"),
            ("leader", "python3 .harness/bin/harness approve alpha"),
            ("implementer", "true && harness approve alpha"),
            ("implementer", "harness transition alpha done"),
            ("leader", "harness transition alpha in_progress --as human"),
            ("reviewer", "harness transition alpha blocked --as implementer --reason x"),
            ("leader", "chmod -x .harness/bin/harness"),
        ]
        for agent, command in cases:
            with self.subTest(agent=agent, command=command):
                self.assert_blocked(self.bash(command, agent))

    def test_allowed_commands(self):
        cases = [
            ("leader", ".harness/bin/harness check"),
            ("leader", "harness next"),
            ("leader", "harness transition alpha done"),
            ("spec_author", "harness transition alpha spec_ready --as spec_author"),
            ("implementer", "harness transition alpha blocked --as implementer --reason 'tool failed'"),
            ("implementer", "mkdir -p src/app/core && echo x > src/app/core/a.py"),
            ("implementer", "cd src && python3 -m unittest"),
            ("leader", "git status && git log --oneline | head -5"),
            ("leader", "cat .harness/state/feature_list.json | jq '.features'"),
            ("leader", "ls src 2>/dev/null"),
            ("reviewer", "grep -rn 'x' src > /tmp/out.txt"),
            ("reviewer", "python3 -c \"print(open('.harness/state/feature_list.json').read())\""),
        ]
        for agent, command in cases:
            with self.subTest(agent=agent, command=command):
                self.assert_allowed(self.bash(command, agent))


class TestCommandTests(ProjectCase):
    def set_test_command(self, command, **no_tests):
        config = self.read_json(CONFIG)
        config["commands"]["test"] = command
        config["no_tests"] = no_tests
        self.write(CONFIG, json.dumps(config))

    def test_failure_with_a_no_tests_pattern_is_still_a_failure(self):
        self.set_test_command("echo 'Ran 0 tests'; exit 1", patterns=["Ran 0 tests"])
        result = self.run_cli("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tests failed", result.stdout)

    def test_declared_exit_code_without_the_pattern_is_a_failure(self):
        self.set_test_command("exit 5", patterns=["NO TESTS RAN"], exit_codes=[5])
        self.assertNotEqual(self.run_cli("check").returncode, 0)

    def test_declared_exit_code_with_the_pattern_only_warns(self):
        self.set_test_command("echo 'NO TESTS RAN'; exit 5", patterns=["NO TESTS RAN"], exit_codes=[5])
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("[WARN]", result.stdout)

    def test_undeclared_exit_code_with_the_pattern_is_a_failure(self):
        self.set_test_command("echo 'NO TESTS RAN'; exit 2", patterns=["NO TESTS RAN"], exit_codes=[5])
        self.assertNotEqual(self.run_cli("check").returncode, 0)

    def test_shipped_stacks_declare_measured_exit_codes(self):
        expected = {"nest": [1], "python": [5], "go": [], "java": []}
        for name, codes in expected.items():
            stack = json.loads((SOURCE / f".harness/stacks/{name}/stack.json").read_text())
            self.assertEqual(stack["no_tests"]["exit_codes"], codes, name)


class EvidenceTests(ProjectCase):
    def in_progress_ready(self):
        self.make_done_ready()
        self.set_features(feature(status="in_progress"))

    def assert_next_and_transition_agree(self, actor):
        self.assertTrue(self.run_cli("next").stdout.startswith(actor), self.run_cli("next").stdout)
        self.assertNotEqual(self.run_cli("transition", "alpha", "done").returncode, 0)
        self.assertEqual(self.status(), "in_progress")

    def test_later_rejection_beats_an_earlier_approval(self):
        self.in_progress_ready()
        self.write(".harness/progress/review_alpha.md",
                   "**Verdict:** APPROVED\n\n**Verdict:** CHANGES_REQUESTED\n")
        self.assert_next_and_transition_agree("implementer:")

    def test_latest_approval_beats_an_earlier_rejection(self):
        self.in_progress_ready()
        self.write(".harness/progress/review_alpha.md",
                   "**Verdict:** CHANGES_REQUESTED\n\n**Verdict:** APPROVED\n")
        self.assertIn("transition alpha done", self.run_cli("next").stdout)
        self.assertEqual(self.run_cli("transition", "alpha", "done").returncode, 0)

    def test_review_older_than_the_report_is_stale(self):
        self.in_progress_ready()
        os.utime(self.path(".harness/progress/review_alpha.md"), (1, 1))
        self.assert_next_and_transition_agree("reviewer:")

    def test_stale_review_fails_the_check_invariant(self):
        self.make_done_ready()
        self.set_features(feature(status="done"))
        os.utime(self.path(".harness/progress/review_alpha.md"), (1, 1))
        self.assert_check_fails("older than")

    def test_closed_feature_survives_shuffled_file_times(self):
        self.in_progress_ready()
        self.assertEqual(self.run_cli("transition", "alpha", "done").returncode, 0)
        os.utime(self.path(".harness/progress/review_alpha.md"), (1, 1))
        self.assert_check_passes()

    def test_edited_evidence_of_a_closed_feature_is_stale_again(self):
        self.in_progress_ready()
        self.assertEqual(self.run_cli("transition", "alpha", "done").returncode, 0)
        self.write(".harness/progress/impl_alpha.md", "## Traceability\n- R1 → `test_it`\n\nchanged\n")
        os.utime(self.path(".harness/progress/review_alpha.md"), (1, 1))
        self.assert_check_fails("evidence changed after the feature closed")

    def test_evidence_mismatch_fails_even_when_the_review_is_newer(self):
        self.in_progress_ready()
        self.assertEqual(self.run_cli("transition", "alpha", "done").returncode, 0)
        self.write(".harness/progress/impl_alpha.md", "## Traceability\n- R1 → `test_it`\n\nchanged\n")
        self.write_review()
        self.assert_check_fails("evidence changed after the feature closed")

    def test_sdd_false_requires_the_implementation_report(self):
        self.set_features(feature(sdd=False, status="in_progress"))
        self.write_review()
        self.assert_next_and_transition_agree("implementer:")

    def test_done_sdd_false_without_report_fails_check(self):
        self.write_review()
        self.set_features(feature(sdd=False, status="done"))
        self.assert_check_fails("no implementation report")

    def test_next_does_not_offer_done_when_a_guard_would_refuse(self):
        self.in_progress_ready()
        self.write(".harness/specs/alpha/tasks.md", "- [ ] T1 — do it. Covers: R1.\n")
        self.approve()
        self.write_review()
        self.assert_next_and_transition_agree("implementer:")

    def test_next_does_not_offer_done_when_tests_fail(self):
        self.in_progress_ready()
        self.write("src/tests/test_app.py",
                   "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('no')\n")
        self.assert_next_and_transition_agree("implementer:")


class StateRuleTests(ProjectCase):
    def test_blocked_from_must_be_a_blockable_state(self):
        for origin in ("done", "blocked"):
            with self.subTest(origin=origin):
                self.set_features(feature(status="blocked", blocked_from=origin))
                self.assert_check_fails("blocked_from")

    def test_mapped_test_must_occur_in_the_application(self):
        self.make_done_ready()
        self.path("src/app/traced.py").unlink()
        self.set_features(feature(status="done"))
        self.assert_check_fails("which is not in src/")

    def test_mapped_test_is_not_matched_inside_a_longer_name(self):
        self.make_done_ready()
        self.write("src/app/traced.py", "test_iterate = None\n")
        self.set_features(feature(status="done"))
        self.assert_check_fails("which is not in src/")

    def test_mapped_test_in_dependencies_does_not_count(self):
        self.make_done_ready()
        self.path("src/app/traced.py").unlink()
        self.write("src/node_modules/lib/index.js", "test_it\n")
        self.set_features(feature(status="done"))
        self.assert_check_fails("which is not in src/")

    def test_unchecked_box_in_a_code_fence_is_not_a_task(self):
        tasks = "- [x] T1 — do it. Covers: R1.\n\n```markdown\n- [ ] sample\n```\n"
        self.make_done_ready()
        self.write(".harness/specs/alpha/tasks.md", tasks)
        self.set_features(feature(status="spec_ready"))
        self.approve()
        self.set_features(feature(status="done"))
        self.assert_check_passes()

    def test_checked_box_in_a_code_fence_does_not_complete_a_spec(self):
        self.make_done_ready()
        self.write(".harness/specs/alpha/tasks.md", "```\n- [x] sample\n```\n")
        self.set_features(feature(status="done"))
        self.assert_check_fails("no tasks")


class HumanGateTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write_spec()
        self.set_features(feature(status="spec_ready"))

    def test_terminal_stdin_without_a_controlling_terminal_is_refused(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        result = subprocess.run([sys.executable, str(self.cli), "approve", "alpha"], cwd=str(self.root),
                                stdin=slave, capture_output=True, text=True, start_new_session=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.path(".harness/approvals/alpha.json").exists())

    def test_wrong_code_is_refused(self):
        result = self.run_at_terminal("approve", "alpha", answer="000000")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.path(".harness/approvals/alpha.json").exists())

    def test_code_is_random_per_run(self):
        codes = set()
        for _ in range(3):
            output = self.run_at_terminal("approve", "alpha").stdout
            codes.add(re.search(r"confirm: (\w+)", output).group(1))
        self.assertEqual(len(codes), 3)

    def test_approval_records_who_and_when(self):
        self.approve()
        record = self.read_json(".harness/approvals/alpha.json")
        self.assertTrue(record["approved_by"]["user"])
        self.assertTrue(record["approved_at"])


class CiWarningTests(ProjectCase):
    def test_a_stack_needing_no_extra_steps_gets_no_warning(self):
        result = self.run_cli("ci", "github")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("no CI setup", result.stdout + result.stderr)


class EvidenceRestampTests(ProjectCase):
    def closed(self):
        self.make_done_ready()
        self.set_features(feature(status="in_progress"))
        self.assertEqual(self.run_cli("transition", "alpha", "done").returncode, 0)
        self.write(".harness/progress/impl_alpha.md", self.path(".harness/progress/impl_alpha.md").read_text() + "x\n")
        self.assertNotEqual(self.run_cli("check", "--no-tests").returncode, 0)

    def test_changed_closed_report_fails_until_a_human_restamps_it(self):
        self.closed()
        code = self.run_at_terminal("evidence", "restamp", "alpha", "--reason", "paid debt")
        self.assertEqual(code.returncode, 0, code.stdout)
        self.assertEqual(self.run_cli("check", "--no-tests").returncode, 0)

    def test_restamp_keeps_an_audit_entry(self):
        self.closed()
        before = self.read_json(FEATURES)["features"][0]["evidence"]
        self.run_at_terminal("evidence", "restamp", "alpha", "--reason", "paid debt")
        entry = self.read_json(FEATURES)["features"][0]["evidence_history"][0]
        self.assertEqual((entry["reason"], entry["previous"]), ("paid debt", before))

    def test_restamp_needs_a_terminal(self):
        self.closed()
        before = self.path(FEATURES).read_bytes()
        result = self.run_cli("evidence", "restamp", "alpha", "--reason", "x")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.path(FEATURES).read_bytes(), before)


class TraceParsingTests(unittest.TestCase):
    def parse(self, target):
        loader = importlib.machinery.SourceFileLoader("harness_cli", str(CLI))
        spec = importlib.util.spec_from_loader("harness_cli", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module.mapped_test_names(target)

    def test_comma_separated_names_need_no_backticks(self):
        self.assertEqual(self.parse("test_a, test_b"), ["test_a", "test_b"])

    def test_backticks_win_over_prose(self):
        self.assertEqual(self.parse("`test_a`, see also the notes"), ["test_a"])

    def test_prose_stays_unmatched_rather_than_passing(self):
        self.assertEqual(self.parse("every test above"), ["every"])


class EnforcementRegressionTests(HookCase):
    def test_case_spellings_do_not_bypass_protected_paths(self):
        cases = [
            ("general-purpose", ".Harness/approvals/a.json"),
            ("general-purpose", ".CLAUDE/settings.json"),
            ("general-purpose", "SRC/app/x.py"),
            ("leader", "SRC/app/x.py"),
            ("leader", ".HARNESS/APPROVALS/a.json"),
            ("reviewer", ".Harness/Rules.json"),
        ]
        for agent, path in cases:
            with self.subTest(agent=agent, path=path):
                self.assert_blocked(self.write_call(path, agent))

    def test_case_spellings_do_not_bypass_bash_checks(self):
        self.assert_blocked(self.bash("echo x > .HARNESS/STATE/feature_list.json", "leader"))
        self.assert_blocked(self.bash("rm -rf SRC", "general-purpose"))

    def test_case_spellings_do_not_bypass_deny_rules(self):
        cases = [
            ("leader", ".harness/progress/REVIEW_alpha.md"),
            ("leader", ".harness/progress/Impl_alpha.md"),
            ("implementer", ".harness/progress/Review_alpha.md"),
        ]
        for agent, path in cases:
            with self.subTest(agent=agent, path=path):
                self.assert_blocked(self.write_call(path, agent))

    def test_case_spelling_of_the_project_root_is_still_the_project(self):
        spelled = str(self.root).upper()
        self.assert_blocked(self.hook("Write", {"file_path": f"{spelled}/SRC/a.py", "content": "x"}, "reviewer"))

    def test_case_spellings_of_allowed_paths_stay_allowed(self):
        self.assert_allowed(self.write_call("SRC/app/x.py", "implementer"))

    def test_case_spelling_does_not_bypass_state_guards(self):
        self.set_features(feature())
        doc = self.read_json(FEATURES)
        doc["features"][0]["status"] = "done"
        self.assert_blocked(self.write_call(".HARNESS/state/FEATURE_LIST.json", "leader", json.dumps(doc)))

    def test_unknown_roles_are_an_allow_list(self):
        for path in (".gitignore", "package.json", "lib/x.py", ".env"):
            with self.subTest(path=path):
                self.assert_blocked(self.write_call(path, "general-purpose"))
        self.assert_allowed(self.write_call("tmp/scratch.py", "general-purpose"))

    def test_approve_spellings_are_denied(self):
        commands = [
            "H=.harness/bin/harness; $H approve alpha",
            'H=.harness/bin/harness; "$H" approve alpha',
            "A=approve; harness $A alpha",
            "$UNKNOWN approve alpha",
            "harness $UNKNOWN alpha",
            "/tmp/h approve alpha",
            "python3 /tmp/h approve alpha",
            "python3 -m runpy .harness/bin/harness approve alpha",
            "script -q /dev/null .harness/bin/harness approve alpha",
            "script -q /dev/null .harness/bin/harness check",
            "expect -c 'spawn harness approve alpha'",
            "unbuffer harness next",
            "python3 -c \"import pty; pty.spawn(['.harness/bin/harness','approve','alpha'])\"",
            "python3 -c \"import subprocess; subprocess.run(['harness','approve','alpha'])\"",
            "echo 'harness approve alpha' | sh",
            "eval 'harness approve alpha'",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "leader"))

    def test_copying_the_cli_is_denied(self):
        commands = [
            "cp .harness/bin/harness /tmp/h",
            "cp -r .harness /tmp/h",
            "ln -s $PWD/.harness/bin/harness /tmp/h",
            "cat .harness/bin/harness > /tmp/h",
            "tar czf /tmp/h.tgz .harness/bin",
            "rsync .harness/bin/harness /tmp/h",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "implementer"))

    def test_text_mentions_of_approve_stay_allowed(self):
        for command in ("grep -rn approve src", "echo approve", "git log --grep approve", "gh pr review --approve"):
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command, "leader"))

    def renamed(self, name):
        doc = self.read_json(FEATURES)
        doc["features"][0]["name"] = name
        return self.write_call(FEATURES, "leader", json.dumps(doc))

    def test_scripted_write_block_names_the_allowed_path(self):
        result = self.bash("python3 -c \"open('.harness/state/feature_list.json','w').write('{}')\"", "leader")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Write or Edit", result.stderr)

    def test_sdd_is_immutable(self):
        self.set_features(feature())
        doc = self.read_json(FEATURES)
        doc["features"][0]["sdd"] = False
        self.assert_blocked(self.write_call(FEATURES, "leader", json.dumps(doc)))

    def test_pending_feature_without_artifacts_can_be_renamed(self):
        self.set_features(feature())
        self.assert_allowed(self.renamed("renamed"))

    def test_name_is_immutable_once_work_exists(self):
        self.set_features(feature())
        self.write_spec()
        self.assert_blocked(self.renamed("renamed"))
        self.set_features(feature(status="spec_ready"))
        self.assert_blocked(self.renamed("renamed"))

    def test_rename_cannot_adopt_the_artifacts_of_another_name(self):
        self.set_features(feature())
        self.write(".harness/approvals/renamed.json", "{}")
        self.assert_blocked(self.renamed("renamed"))

    def test_an_invalid_name_is_refused_when_written(self):
        doc = self.read_json(FEATURES)
        doc["features"].append(feature(name="email_validation"))
        self.assert_blocked(self.write_call(FEATURES, "leader", json.dumps(doc)))

    def test_an_invalid_name_can_be_repaired(self):
        self.set_features(feature(name="email_validation"))
        self.assert_allowed(self.renamed("email-validation"))

    def test_scripted_heredoc_writes_to_state_are_blocked(self):
        for body in ("import json\np='.harness/state/feature_list.json'\nd=json.load(open(p))\njson.dump(d,open(p,'w'))",
                     "from pathlib import Path\np=Path('.harness/state/feature_list.json')\np.write_text('{}')"):
            with self.subTest(body=body):
                self.assert_blocked(self.bash(f"python3 - <<'PY'\n{body}\nPY", "leader"))

    def test_scripted_heredoc_reads_of_state_pass(self):
        body = "import json\nprint(json.load(open('.harness/state/feature_list.json')))"
        self.assert_allowed(self.bash(f"python3 - <<'PY'\n{body}\nPY", "leader"))

    def test_sdd_cannot_change_through_edit(self):
        self.set_features(feature())
        edit = {"file_path": str(self.path(FEATURES)), "old_string": '"sdd": true', "new_string": '"sdd": false'}
        self.assert_blocked(self.hook("Edit", edit, "leader"))

    def test_changing_the_id_does_not_launder_sdd(self):
        self.set_features(feature())
        doc = self.read_json(FEATURES)
        doc["features"][0].update({"id": 9, "sdd": False})
        self.assert_blocked(self.write_call(FEATURES, "leader", json.dumps(doc)))

    def test_undeterminable_state_edit_fails_closed(self):
        self.set_features(feature())
        edit = {"file_path": str(self.path(FEATURES)), "old_string": "not in the file", "new_string": "x"}
        self.assert_blocked(self.hook("Edit", edit, "leader"))

    def test_harmless_feature_edit_stays_allowed(self):
        self.set_features(feature())
        edit = {"file_path": str(self.path(FEATURES)), "old_string": '"title": "alpha"', "new_string": '"title": "A"'}
        self.assert_allowed(self.hook("Edit", edit, "leader"))

    def test_evidence_has_one_owner(self):
        cases = [
            ("leader", ".harness/progress/review_alpha.md", False),
            ("leader", ".harness/progress/impl_alpha.md", False),
            ("implementer", ".harness/progress/review_alpha.md", False),
            ("reviewer", ".harness/progress/impl_alpha.md", False),
            ("spec_author", ".harness/progress/review_alpha.md", False),
            ("implementer", ".harness/progress/impl_alpha.md", True),
            ("reviewer", ".harness/progress/review_alpha.md", True),
        ]
        for agent, path, allowed in cases:
            with self.subTest(agent=agent, path=path):
                self.assertEqual(self.write_call(path, agent).returncode, 0 if allowed else 2)

    def test_evidence_ownership_applies_to_bash(self):
        self.assert_blocked(self.bash("echo '**Verdict:** APPROVED' > .harness/progress/review_alpha.md", "leader"))

    def test_shell_variables_are_expanded_in_targets(self):
        home = os.path.expanduser("~")
        self.assertTrue(home)
        for command in ("echo x > $PWD/src/a.py", "echo x > ${PWD}/src/a.py", "echo x > $(pwd)/src/a.py",
                        "echo x > $CLAUDE_PROJECT_DIR/src/a.py", "rm -rf ${CLAUDE_PROJECT_DIR}/.harness"):
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "reviewer"))

    def test_home_and_tilde_are_expanded(self):
        env_root = str(self.root)
        fake = {"tool_name": "Bash", "cwd": env_root, "agent_type": "reviewer"}
        for command in ("echo x > ~/src/a.py", "echo x > $HOME/src/a.py"):
            with self.subTest(command=command):
                payload = dict(fake, tool_input={"command": command})
                result = subprocess.run([sys.executable, str(self.cli), "hook", "pre-tool-use"],
                                        input=json.dumps(payload), capture_output=True, text=True,
                                        env={**os.environ, "HOME": env_root})
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_unresolved_variable_with_protected_remainder_is_denied(self):
        self.assert_blocked(self.bash("echo x > $UNKNOWN/.harness/approvals/a.json", "leader"))
        self.assert_blocked(self.bash("echo x > $UNKNOWN/src/a.py", "reviewer"))

    def test_unresolved_variable_alone_stays_allowed(self):
        self.assert_allowed(self.bash("echo x > $TMPFILE", "reviewer"))
        self.assert_allowed(self.bash("echo x > $TMPDIR/out.txt", "reviewer"))

    def test_multi_edit_is_governed(self):
        self.set_features(feature())
        edits = [{"old_string": '"title": "alpha"', "new_string": '"title": "A"'},
                 {"old_string": '"status": "pending"', "new_string": '"status": "done"'}]
        self.assert_blocked(self.hook("MultiEdit", {"file_path": str(self.path(FEATURES)), "edits": edits}, "leader"))
        self.assert_allowed(self.hook("MultiEdit", {"file_path": str(self.path(FEATURES)), "edits": edits[:1]}, "leader"))
        self.assert_blocked(self.hook("MultiEdit", {"file_path": str(self.path("src/a.py")), "edits": []}, "leader"))

    def test_settings_matcher_covers_multi_edit(self):
        settings = self.read_json(".claude/settings.json")
        self.assertIn("MultiEdit", settings["hooks"]["PreToolUse"][0]["matcher"])


class ScenarioCase(ProjectCase):
    """Plays every role by following `harness next` literally, as an agent would."""

    def snapshot(self):
        digest = []
        for folder in ("state", "specs", "progress", "approvals"):
            for path in sorted(self.path(f".harness/{folder}").rglob("*")):
                if path.is_file():
                    digest.append((str(path), path.read_bytes()))
        return hash(tuple(digest))

    def play(self, verdicts=(), block_at=None, limit=40, crash_at=None):
        """Run until no work is left. Fails on any repeat without a state change."""
        self.verdicts = list(verdicts)
        self.attempts = 0
        self.crash_at = crash_at
        seen, trail = set(), []
        while True:
            if block_at and self.status() == block_at:
                result = self.run_cli("transition", "alpha", "blocked", "--as", "implementer", "--reason", "stuck")
                self.assertEqual(result.returncode, 0, result.stderr)
                block_at = None
            action = self.run_cli("next").stdout.strip()
            trail.append(action)
            if action.startswith("leader: no open work"):
                return trail
            state = (action, self.snapshot())
            self.assertNotIn(state, seen, f"stuck: same action, same state\n" + "\n".join(trail))
            seen.add(state)
            self.assertLess(len(trail), limit, "\n".join(trail))
            self.perform(action)

    def perform(self, action):
        actor = action.split(":", 1)[0]
        command = re.search(r"`(harness [^`]+)`", action)
        name = re.search(r"(?:feature|debt|resume|closing) (\S+?)[,:]?(?:\s|$)", action)
        is_debt = " debt " in action or "review_debt-" in action
        if actor == "leader":
            self.assertIsNotNone(command, action)
            result = self.run_cli(*shlex.split(command.group(1))[1:])
            self.assertEqual(result.returncode, 0, f"next offered {action}\n{result.stderr}")
        elif actor == "human" and "approve" in action:
            self.approve(shlex.split(command.group(1))[2])
        elif actor == "human":
            result = self.run_at_terminal(*shlex.split(command.group(1))[1:])
            self.assertEqual(result.returncode, 0, f"next offered {action}\n{result.stdout}")
        elif actor == "spec_author":
            self.write_spec(name.group(1))
            result = self.run_cli("transition", name.group(1), "spec_ready", "--as", "spec_author")
            self.assertEqual(result.returncode, 0, result.stderr)
        elif actor == "implementer":
            self.implement(name.group(1), is_debt)
        elif actor == "reviewer":
            verdict = self.verdicts.pop(0) if self.verdicts else "APPROVED"
            self.review(name.group(1), verdict, is_debt)
        else:
            self.fail(f"unknown actor in: {action}")

    def implement(self, name, is_debt=False):
        self.attempts += 1
        if not is_debt and not self.work_through_tasks(name):
            return
        self.write("src/app/traced.py", "def test_it():\n    pass\n")
        report = f"impl_debt-{name}" if is_debt else f"impl_{name}"
        self.write(f".harness/progress/{report}.md",
                   f"## Traceability\n- R1 → `test_it`\n\nattempt {self.attempts}\n")

    def work_through_tasks(self, name):
        """Start and tick each open task. False when the session dies mid-task."""
        tasks = self.path(f".harness/specs/{name}/tasks.md")
        if not tasks.exists():
            return True
        for task in re.findall(r"^- \[ \] (T\d+)", tasks.read_text(), re.MULTILINE):
            result = self.run_cli("task", "start", name, task)
            self.assertEqual(result.returncode, 0, result.stderr)
            if task == self.crash_at:
                self.crash_at = None
                return False
            tasks.write_text(tasks.read_text().replace(f"- [ ] {task}", f"- [x] {task}"))
        return True

    def review(self, name, verdict, is_debt):
        if not is_debt:
            self.write_review(name, verdict)
            return
        stored = next(d for d in self.read_json(DEBTS)["debts"] if d["name"] == name)
        lines = [f"- A{n}: [x] verified" for n in range(1, len(stored["acceptance"]) + 1)]
        self.write(f".harness/progress/review_debt-{name}.md",
                   f"**Verdict:** {verdict}\n\n## Acceptance\n" + "\n".join(lines) + "\n")

    def assert_finished(self, name="alpha"):
        self.assertEqual(self.status(name), "done")
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stdout)


class ScenarioTests(ScenarioCase):
    def test_sdd_happy_path(self):
        self.set_features(feature())
        trail = self.play()
        self.assert_finished()
        self.assertEqual([a.split(":")[0] for a in trail[:-1]],
                         ["spec_author", "human", "leader", "implementer", "reviewer", "leader"])

    def test_sdd_false_happy_path(self):
        self.set_features(feature(sdd=False))
        self.play()
        self.assert_finished()

    def test_rejection_then_fix_then_rereview_then_approval(self):
        self.set_features(feature())
        trail = self.play(verdicts=["CHANGES_REQUESTED"])
        self.assert_finished()
        self.assertEqual([a.split(":")[0] for a in trail[3:-1]],
                         ["implementer", "reviewer", "implementer", "reviewer", "leader"])

    def test_two_rejections_on_an_sdd_false_feature(self):
        self.set_features(feature(sdd=False))
        self.play(verdicts=["CHANGES_REQUESTED", "CHANGES_REQUESTED"])
        self.assert_finished()

    def test_promoted_debt_reaches_done(self):
        self.set_features(feature("owed"))
        self.set_debts(debt(status="scheduled", sdd=True))
        self.play_named("owed")
        self.assert_finished("owed")
        stored = self.read_json(DEBTS)["debts"][0]
        self.assertEqual(stored["status"], "resolved")
        self.assertEqual(stored["resolved_by"], {"feature": "owed"})

    def test_promoted_sdd_false_debt_reaches_done(self):
        self.set_features(feature("owed", sdd=False))
        self.set_debts(debt(status="scheduled"))
        self.play_named("owed")
        self.assert_finished("owed")
        self.assertEqual(self.read_json(DEBTS)["debts"][0]["status"], "resolved")

    def play_named(self, name):
        original = self.status
        self.status = lambda default=name: original(default)
        self.play()
        self.status = original

    def test_blocked_and_unblocked_from_each_origin_state(self):
        for origin, sdd in (("pending", True), ("pending", False), ("spec_ready", True),
                            ("in_progress", True), ("in_progress", False)):
            with self.subTest(origin=origin, sdd=sdd):
                self.tearDownProject()
                self.set_features(feature(sdd=sdd))
                trail = self.play(block_at=origin)
                self.assert_finished()
                self.assertTrue(any(a.startswith("human: resolve blocked") for a in trail), trail)

    def tearDownProject(self):
        shutil.rmtree(self.root)
        shutil.copytree(f"{_template}/app", self.root, symlinks=True)

    def test_features_run_in_list_order(self):
        self.set_features(feature("alpha", sdd=False), feature("beta", sdd=False, id=2))
        trail = self.play()
        self.assertEqual(self.status("beta"), "done")
        first_beta = next(i for i, a in enumerate(trail) if "beta" in a)
        self.assertTrue(all("alpha" in a for a in trail[:first_beta]), trail)


class DebtScenarioTests(ScenarioCase):
    def stored(self, name="owed"):
        return next(d for d in self.read_json(DEBTS)["debts"] if d["name"] == name)

    def start(self, name="owed"):
        result = self.run_cli("debt", "start", name)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sdd_false_debt_is_paid_and_resolved(self):
        self.set_debts(debt(name="owed", acceptance=["first", "second"]))
        self.start()
        trail = self.play()
        self.assertEqual([a.split(":")[0] for a in trail[:-1]], ["implementer", "reviewer", "leader"])
        self.assertIn("harness debt resolve owed", trail[2])
        self.assertEqual(self.stored()["status"], "resolved")
        self.assertEqual(sorted(self.stored()["evidence"]), ["impl_debt-owed.md", "review_debt-owed.md"])
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_accepted_debt_can_be_paid(self):
        self.set_debts(debt(name="owed", status="accepted"))
        self.start()
        self.play()
        self.assertEqual(self.stored()["status"], "resolved")

    def test_debt_rejected_then_fixed(self):
        self.set_debts(debt(name="owed"))
        self.start()
        trail = self.play(verdicts=["CHANGES_REQUESTED"])
        self.assertEqual([a.split(":")[0] for a in trail[:-1]],
                         ["implementer", "reviewer", "implementer", "reviewer", "leader"])
        self.assertIn("review_debt-owed.md", trail[2])
        self.assertEqual(self.stored()["status"], "resolved")

    def test_critical_debt_goes_before_pending_features(self):
        self.set_features(feature(sdd=False))
        self.set_debts(debt(name="owed", severity="critical"))
        trail = self.play()
        self.assertIn("harness debt start owed", trail[0])
        self.assertEqual(self.stored()["status"], "resolved")
        self.assert_finished()
        first_feature = next(i for i, action in enumerate(trail) if "alpha" in action)
        self.assertTrue(any("debt resolve owed" in action for action in trail[:first_feature]), trail)

    def test_critical_sdd_debt_is_never_offered_a_start_that_would_be_refused(self):
        self.set_debts(debt(name="owed", severity="critical", sdd=True))
        action = self.run_cli("next").stdout
        self.assertIn("triage critical debt owed", action)
        self.assertNotIn("debt start", action)
        self.assertNotEqual(self.run_cli("debt", "start", "owed").returncode, 0)

    def test_critical_sdd_debt_promoted_after_triage_reaches_done(self):
        self.set_features(feature("owed", sdd=False))
        self.set_debts(debt(name="owed", severity="critical", sdd=True, status="scheduled"))
        self.play()
        self.assert_finished("owed")
        self.assertEqual(self.stored()["status"], "resolved")

    def test_feature_and_debt_are_never_active_together(self):
        self.set_features(feature(sdd=False, status="in_progress"), feature("beta", sdd=False, id=2))
        self.set_debts(debt(name="owed"))
        refused = self.run_cli("debt", "start", "owed")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("another feature is in_progress", refused.stderr)
        self.assertEqual(self.stored()["status"], "open")
        self.play()
        self.assert_finished()
        self.start()
        self.play()
        self.assertEqual(self.stored()["status"], "resolved")

    def test_active_debt_keeps_features_waiting(self):
        self.set_features(feature(sdd=False))
        self.set_debts(debt(name="owed"))
        self.start()
        refused = self.run_cli("transition", "alpha", "in_progress")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("a debt is in_progress: owed", refused.stderr)
        self.play()
        self.assert_finished()

    def test_two_debts_are_never_active_together(self):
        self.set_debts(debt(name="owed"), debt(id=2, name="more"))
        self.start()
        self.assertNotEqual(self.run_cli("debt", "start", "more").returncode, 0)


class InterruptionScenarioTests(ScenarioCase):
    TASKS = "- [ ] T1 — one. Covers: R1.\n- [ ] T2 — two. Covers: R1.\n- [ ] T3 — three. Covers: R1.\n"

    def in_progress(self):
        self.write_spec(tasks=self.TASKS)
        self.set_features(feature(status="spec_ready"))
        self.approve()
        self.assertEqual(self.run_cli("transition", "alpha", "in_progress").returncode, 0)

    def test_interrupted_task_is_resumed_to_done(self):
        self.in_progress()
        trail = self.play(crash_at="T2")
        self.assertEqual(trail[0], "implementer: implement feature alpha")
        self.assertEqual(trail[1], "implementer: resume alpha at T2 (started, not finished)")
        self.assert_finished()

    def test_interruption_after_the_report_still_routes_to_resume(self):
        self.in_progress()
        self.write("src/app/traced.py", "def test_it():\n    pass\n")
        self.write_impl()
        self.assertEqual(self.run_cli("task", "start", "alpha", "T1").returncode, 0)
        self.assertIn("resume alpha at T1", self.run_cli("next").stdout)

    def test_ticking_clears_the_interruption(self):
        self.in_progress()
        self.run_cli("task", "start", "alpha", "T1")
        self.write(".harness/specs/alpha/tasks.md", self.TASKS.replace("[ ] T1", "[x] T1"))
        self.assertNotIn("resume", self.run_cli("next").stdout)

    def test_starting_another_task_warns_and_succeeds(self):
        self.in_progress()
        self.run_cli("task", "start", "alpha", "T1")
        result = self.run_cli("task", "start", "alpha", "T2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[WARN]", result.stdout)
        self.assertIn("T1", result.stdout)

    def test_restarting_the_same_task_does_not_warn(self):
        self.in_progress()
        self.run_cli("task", "start", "alpha", "T1")
        self.assertNotIn("[WARN]", self.run_cli("task", "start", "alpha", "T1").stdout)

    def test_start_records_the_task_and_a_log_line(self):
        self.in_progress()
        self.assertEqual(self.run_cli("task", "start", "alpha", "T1").returncode, 0)
        record = self.read_json(".harness/state/tasks.json")
        self.assertEqual(record["feature"], "alpha")
        self.assertEqual(record["started"][0]["task"], "T1")
        self.assertTrue(record["started"][0]["started_at"])
        log = self.path(".harness/progress/current.md").read_text()
        self.assertIn("task start alpha T1", log)
        self.assertNotIn("## Log\n\n_—_", log)
        self.assertLess(log.index("task start alpha T1"), log.index("## Next Step"))

    def test_log_lines_accumulate(self):
        self.in_progress()
        self.run_cli("task", "start", "alpha", "T1")
        self.run_cli("task", "start", "alpha", "T2")
        log = self.path(".harness/progress/current.md").read_text()
        self.assertLess(log.index("alpha T1"), log.index("alpha T2"))

    def test_start_adds_a_log_section_when_missing(self):
        self.in_progress()
        self.write(".harness/progress/current.md", "# Current Session\n")
        self.assertEqual(self.run_cli("task", "start", "alpha", "T1").returncode, 0)
        self.assertIn("## Log", self.path(".harness/progress/current.md").read_text())

    def test_start_refuses_invalid_targets(self):
        self.in_progress()
        self.write(".harness/specs/alpha/tasks.md", self.TASKS.replace("[ ] T1", "[x] T1"))
        for args, expected in ((("alpha", "T9"), "no task T9"), (("alpha", "T1"), "already ticked"),
                               (("nope", "T1"), "unknown feature")):
            with self.subTest(args=args):
                result = self.run_cli("task", "start", *args)
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stderr)

    def test_start_refuses_a_feature_that_is_not_active(self):
        self.write_spec()
        self.set_features(feature(status="spec_ready"))
        self.assertIn("not in_progress", self.run_cli("task", "start", "alpha", "T1").stderr)

    def test_start_refuses_a_feature_without_tasks(self):
        self.set_features(feature(sdd=False, status="in_progress"))
        self.assertIn("no tasks", self.run_cli("task", "start", "alpha", "T1").stderr)

    def test_damaged_task_record_fails_check_but_not_next(self):
        self.in_progress()
        self.write(".harness/state/tasks.json", "[]")
        self.assert_check_fails("must hold a started list")
        self.assertEqual(self.run_cli("next").returncode, 0)


class DebtGuardTests(HookCase):
    def paying(self, **fields):
        self.set_debts(debt(name="owed", status="in_progress", acceptance=["one", "two"], **fields))
        self.write(".harness/progress/impl_debt-owed.md", "paid\n")

    def write_debt_review(self, verdict="APPROVED", lines="- A1: [x] a\n- A2: [x] b\n"):
        self.write(".harness/progress/review_debt-owed.md", f"**Verdict:** {verdict}\n\n{lines}")

    def assert_refused(self, expected):
        before = self.path(DEBTS).read_bytes()
        result = self.run_cli("debt", "resolve", "owed")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertEqual(self.path(DEBTS).read_bytes(), before)

    def test_resolve_needs_a_report(self):
        self.paying()
        self.path(".harness/progress/impl_debt-owed.md").unlink()
        self.write_debt_review()
        self.assert_refused("no implementation report")

    def test_resolve_needs_a_review(self):
        self.paying()
        self.assert_refused("no review report")

    def test_resolve_refuses_a_rejection(self):
        self.paying()
        self.write_debt_review("CHANGES_REQUESTED")
        self.assert_refused("not APPROVED")

    def test_resolve_refuses_a_stale_review(self):
        self.paying()
        self.write_debt_review()
        os.utime(self.path(".harness/progress/review_debt-owed.md"), (1, 1))
        self.assert_refused("older than")

    def test_resolve_refuses_a_missing_acceptance_line(self):
        self.paying()
        self.write_debt_review(lines="- A1: [x] a\n")
        self.assert_refused("acceptance not covered by the review: A2")

    def test_resolve_refuses_an_unticked_acceptance_line(self):
        self.paying()
        self.write_debt_review(lines="- A1: [x] a\n- A2: [ ] b\n")
        self.assert_refused("A2")

    def test_acceptance_lines_in_code_fences_do_not_count(self):
        self.paying()
        self.write_debt_review(lines="```\n- A1: [x] a\n- A2: [x] b\n```\n")
        self.assert_refused("A1, A2")

    def test_resolve_refuses_failing_tests(self):
        self.paying()
        self.write_debt_review()
        self.write("src/tests/test_app.py",
                   "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('no')\n")
        self.assert_refused("tests failed")
        self.assertTrue(self.run_cli("next").stdout.startswith("implementer:"))

    def test_resolve_only_from_in_progress(self):
        self.set_debts(debt(name="owed"))
        self.assertIn("illegal move", self.run_cli("debt", "resolve", "owed").stderr)

    def test_start_refuses_debt_that_is_not_payable_in_place(self):
        for fields, expected in (({"sdd": True}, "promoting"), ({"status": "scheduled"}, "illegal move"),
                                 ({"status": "wontfix"}, "illegal move")):
            with self.subTest(fields=fields):
                self.set_debts(debt(name="owed", **fields))
                result = self.run_cli("debt", "start", "owed")
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stderr)

    def test_unknown_debt_is_an_error(self):
        self.assertIn("unknown debt", self.run_cli("debt", "start", "nope").stderr)

    def test_debt_names_must_be_slugs(self):
        self.set_debts(debt(name="../escape"))
        self.assert_check_fails("lowercase slug")

    def closed(self):
        self.paying()
        self.write_debt_review()
        result = self.run_cli("debt", "resolve", "owed")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_resolved_debt_survives_shuffled_file_times(self):
        self.closed()
        os.utime(self.path(".harness/progress/review_debt-owed.md"), (1, 1))
        self.assert_check_passes()

    def test_edited_evidence_of_a_resolved_debt_fails_check(self):
        self.closed()
        self.write(".harness/progress/impl_debt-owed.md", "changed\n")
        self.assert_check_fails("evidence changed after the debt closed")

    def test_resolved_debt_needs_evidence(self):
        self.set_debts(debt(name="owed", status="resolved"))
        self.assert_check_fails("resolved without evidence")

    def test_a_feature_and_a_debt_active_fail_check(self):
        self.paying()
        self.set_features(feature(sdd=False, status="in_progress"))
        self.assert_check_fails("more than one thing is in_progress")

    def edited(self, **changes):
        doc = self.read_json(DEBTS)
        doc["debts"][0].update(changes)
        return self.write_call(DEBTS, "leader", json.dumps(doc))

    def test_hand_edits_cannot_start_or_resolve_a_debt(self):
        self.set_debts(debt(name="owed"))
        self.assert_blocked(self.edited(status="in_progress"))
        self.assert_blocked(self.edited(status="resolved"))
        self.assert_allowed(self.edited(status="accepted"))

    def test_new_debt_cannot_be_born_active(self):
        doc = self.read_json(DEBTS)
        doc["debts"].append(debt(status="in_progress"))
        self.assert_blocked(self.write_call(DEBTS, "leader", json.dumps(doc)))

    def test_active_debt_terms_are_frozen(self):
        self.paying()
        self.assert_blocked(self.edited(acceptance=["one"]))
        self.assert_blocked(self.edited(sdd=True))
        self.assert_blocked(self.edited(name="other"))
        self.assert_allowed(self.edited(title="clearer"))

    def test_active_debt_cannot_be_removed_but_can_be_abandoned(self):
        self.paying()
        doc = self.read_json(DEBTS)
        doc["debts"] = []
        self.assert_blocked(self.write_call(DEBTS, "leader", json.dumps(doc)))
        self.assert_allowed(self.edited(status="accepted"))

    def test_no_agent_can_remove_a_debt_or_wipe_the_ledger(self):
        self.set_debts(debt(name="owed"))
        doc = self.read_json(DEBTS)
        doc["debts"] = []
        self.assert_blocked(self.write_call(DEBTS, "leader", json.dumps(doc)))
        self.assert_blocked(self.write_call(DEBTS, "leader", "{}"))

    def test_only_a_human_can_defuse_a_critical_debt(self):
        self.set_debts(debt(name="owed", severity="critical"))
        self.assert_blocked(self.edited(severity="low"))
        self.assert_blocked(self.edited(status="accepted"))
        self.assert_blocked(self.edited(status="wontfix"))
        self.assert_allowed(self.edited(title="clearer"))

    def test_leader_still_triages_a_debt_that_is_not_critical(self):
        self.set_debts(debt(name="owed", severity="high"))
        self.assert_allowed(self.edited(severity="low"))
        self.assert_allowed(self.edited(status="wontfix"))

    def test_evidence_fields_are_harness_only(self):
        self.set_debts(debt(name="owed"))
        self.assert_blocked(self.edited(evidence={"a": "b"}))
        self.assert_blocked(self.edited(resolved_by={"feature": "x"}))

    def test_only_the_leader_runs_debt_commands(self):
        for agent in ("implementer", "reviewer", "spec_author", "general-purpose"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.bash("harness debt resolve owed", agent))
        self.assert_allowed(self.bash("harness debt start owed", "leader"))
        self.assert_allowed(self.bash(".harness/bin/harness debt resolve owed"))

    def test_only_the_implementer_runs_task_start(self):
        for agent in ("leader", "reviewer", "spec_author", "general-purpose"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.bash("harness task start alpha T1", agent))
        self.assert_blocked(self.bash("harness task start alpha T1"))
        self.assert_allowed(self.bash(".harness/bin/harness task start alpha T1", "implementer"))

    def test_guarded_commands_cannot_hide_behind_a_variable(self):
        self.assert_blocked(self.bash("$H task start alpha T1", "leader"))
        self.assert_blocked(self.bash("$H debt resolve owed", "implementer"))
        self.assert_blocked(self.bash("harness $SUB start alpha T1", "implementer"))

    def test_task_record_is_harness_owned(self):
        for agent in ("leader", "implementer", "reviewer"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.write_call(".harness/state/tasks.json", agent, "{}"))
                self.assert_blocked(self.bash("echo x > .harness/state/tasks.json", agent))


class ResumeTests(ProjectCase):
    TASKS = "- [x] T1 — one. Covers: R1.\n- [ ] T2 — two. Covers: R1.\n"

    def in_progress(self, tasks=None):
        self.write_spec(tasks=tasks or self.TASKS)
        self.set_features(feature(status="spec_ready"))
        self.approve()
        self.set_features(feature(status="in_progress"))

    def briefing(self):
        result = self.run_cli("resume", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_nothing_active_prints_a_short_message(self):
        result = self.run_cli("resume")
        self.assertEqual(result.returncode, 0)
        self.assertIn("no active work", result.stdout)
        self.assertLessEqual(len(result.stdout.splitlines()), 2)

    def test_reports_the_active_feature(self):
        self.in_progress()
        self.run_cli("task", "start", "alpha", "T2")
        self.write_impl()
        self.write_review(verdict="CHANGES_REQUESTED")
        text = self.run_cli("resume").stdout
        for expected in ("Active feature: alpha (in_progress)", "1 done, 1 pending", "T2 (started",
                         "Spec: .harness/specs/alpha/", "Latest review: CHANGES_REQUESTED",
                         "task start alpha T2", ".harness/specs/alpha/tasks.md", "resume alpha at T2"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_reports_an_active_debt(self):
        self.set_debts(debt(name="owed", status="in_progress"))
        data = self.briefing()
        self.assertEqual((data["active"]["kind"], data["active"]["name"]), ("debt", "owed"))
        self.assertIsNone(data["tasks"])
        self.assertIn("pay debt owed", data["next_action"])

    def test_json_has_the_documented_keys(self):
        self.in_progress()
        self.assertEqual(sorted(self.briefing()),
                         ["active", "changed_files", "changed_files_note", "log", "next_action",
                          "next_may_differ", "project", "read_next", "review", "spec_path", "tasks"])

    def test_never_runs_tests(self):
        marker = self.path("ran-tests")
        config = self.read_json(CONFIG)
        config["commands"]["test"] = f"touch {marker}"
        self.write(CONFIG, json.dumps(config))
        self.make_done_ready()
        self.set_features(feature(status="in_progress"))
        self.assertEqual(self.run_cli("resume").returncode, 0)
        self.assertFalse(marker.exists())

    def test_never_scans_for_traceability(self):
        self.make_done_ready()
        self.set_features(feature(status="in_progress"))
        self.path("src/app/traced.py").unlink()
        self.assertIn("transition alpha done", self.briefing()["next_action"])

    def test_says_when_next_may_differ(self):
        self.make_done_ready()
        self.set_features(feature(status="in_progress"))
        self.write("src/tests/test_app.py",
                   "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('no')\n")
        text = self.run_cli("resume").stdout
        self.assertIn("transition alpha done", text)
        self.assertIn("`harness next` may route elsewhere", text)
        self.assertTrue(self.run_cli("next").stdout.startswith("implementer:"))

    def test_does_not_warn_when_the_action_cannot_differ(self):
        self.in_progress()
        self.assertFalse(self.briefing()["next_may_differ"])
        self.assertNotIn("may route elsewhere", self.run_cli("resume").stdout)

    def test_is_read_only(self):
        self.in_progress()
        self.run_cli("task", "start", "alpha", "T2")
        before = {p: p.read_bytes() for p in self.path(".harness").rglob("*") if p.is_file()}
        self.run_cli("resume")
        self.run_cli("resume", "--json")
        after = {p: p.read_bytes() for p in self.path(".harness").rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_lists_are_capped_and_counted(self):
        tasks = "".join(f"- [ ] T{n} — task. Covers: R1.\n" for n in range(1, 41))
        self.in_progress(tasks=tasks)
        for n in range(1, 41):
            self.run_cli("task", "start", "alpha", f"T{n}")
            self.write(f"src/generated_{n}.py", "x = 1\n")
        result = self.run_cli("resume")
        self.assertLess(len(result.stdout.splitlines()), 60, result.stdout)
        self.assertIn("30 more omitted", result.stdout)
        self.assertIn("32 more omitted", result.stdout)
        data = self.briefing()
        self.assertEqual(len(data["tasks"]["pending"]["items"]), 10)
        self.assertEqual(data["tasks"]["pending"]["omitted"], 30)
        self.assertEqual(len(data["changed_files"]["items"]), 10)
        self.assertEqual(data["log"]["omitted"], 32)

    def test_long_lines_are_cut(self):
        self.in_progress(tasks=f"- [ ] T1 — {'x' * 500}. Covers: R1.\n")
        self.assertLessEqual(max(len(l) for l in self.run_cli("resume").stdout.splitlines()), 160)

    def test_lists_changed_and_untracked_files_in_the_app_only(self):
        self.in_progress()
        self.write("outside.txt", "x")
        files = self.briefing()["changed_files"]["items"]
        self.assertTrue(any("src/app/__init__.py" in line for line in files), files)
        self.assertFalse(any("outside.txt" in line for line in files), files)

    def test_tolerates_no_commits(self):
        self.in_progress()
        self.assertIsNone(self.briefing()["changed_files_note"])

    def test_tolerates_a_folder_outside_git(self):
        self.in_progress()
        shutil.rmtree(self.path(".git"))
        self.assertEqual(self.briefing()["changed_files_note"], "not a git repository")
        self.assertIn("Changed files: unknown", self.run_cli("resume").stdout)

    def test_tolerates_git_being_unavailable(self):
        self.in_progress()
        empty = Path(self.tmp) / "emptybin"
        empty.mkdir()
        result = subprocess.run([sys.executable, str(self.cli), "resume", "--json"], cwd=str(self.root),
                                capture_output=True, text=True, env={"PATH": str(empty)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["changed_files_note"], "git is not available")

    def test_uninitialized_scaffold_is_a_clean_error(self):
        result = subprocess.run([sys.executable, str(CLI), "resume"], cwd=str(SOURCE), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not initialized", result.stderr)


class SessionStartTests(ProjectCase):
    def session_start(self):
        return self.run_cli("hook", "session-start", input_text='{"source": "startup"}')

    def context(self):
        result = self.session_start()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        return output["additionalContext"]

    def test_injects_the_briefing(self):
        self.write_spec()
        self.set_features(feature(status="spec_ready"))
        self.approve()
        self.set_features(feature(status="in_progress"))
        self.run_cli("task", "start", "alpha", "T1")
        context = self.context()
        self.assertIn("T1 (started", context)
        self.assertIn("resume alpha at T1", context)

    def test_injects_a_short_message_with_nothing_active(self):
        self.assertIn("no active work", self.context())

    def test_stays_under_the_documented_context_cap(self):
        self.set_features(feature(title="x" * 20000, status="in_progress", sdd=False))
        self.assertLess(len(self.context()), 10000)

    def test_never_blocks_on_corrupt_state(self):
        self.write(FEATURES, "{ nope")
        self.assertIn("briefing unavailable", self.context())

    def test_never_blocks_on_missing_rules(self):
        self.path(RULES).unlink()
        self.assertIn("briefing unavailable", self.context())

    def test_never_blocks_on_missing_config(self):
        self.path(CONFIG).unlink()
        self.assertIn("briefing unavailable", self.context())

    def test_never_blocks_on_unreadable_stdin(self):
        result = self.run_cli("hook", "session-start", input_text="not json")
        self.assertEqual(result.returncode, 0)

    def test_is_passive_in_the_scaffold(self):
        config = self.read_json(CONFIG)
        config["stack"] = None
        self.write(CONFIG, json.dumps(config))
        result = self.session_start()
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_settings_wire_the_hook_in_exec_form(self):
        settings = self.read_json(".claude/settings.json")
        hook = settings["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertEqual(hook["args"], ["hook", "session-start"])
        self.assertEqual(hook["type"], "command")

    def test_missing_session_start_hook_is_reported(self):
        settings = self.read_json(".claude/settings.json")
        del settings["hooks"]["SessionStart"]
        self.write(".claude/settings.json", json.dumps(settings))
        self.assert_check_fails("does not run the harness SessionStart hook")

    def test_missing_pre_tool_use_hook_is_still_reported(self):
        settings = self.read_json(".claude/settings.json")
        del settings["hooks"]["PreToolUse"]
        self.write(".claude/settings.json", json.dumps(settings))
        self.assert_check_fails("does not run the harness PreToolUse hook")


class UpdateCiCase(unittest.TestCase):
    """A project generated from a private scaffold copy, so the scaffold can change."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="harness-update-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.source = self.tmp / "source"
        self.source.mkdir()
        shutil.copytree(SOURCE / ".harness", self.source / ".harness", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(SOURCE / ".claude", self.source / ".claude")
        shutil.copy2(SOURCE / ".gitignore", self.source / ".gitignore")
        self.cli = self.source / ".harness/bin/harness"
        self.root = self.tmp / "app"
        result = self.run_cli("init", "python", str(self.root), cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.commit()

    def run_cli(self, *args, cwd=None, cli=None):
        return subprocess.run([sys.executable, str(cli or self.cli), *args], cwd=str(cwd or self.root),
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)

    def commit(self):
        for command in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", *command], cwd=str(self.root), check=True)

    def change_source(self, rel=".claude/agents/leader.md"):
        path = self.source / rel
        path.write_text(path.read_text() + "\nincoming\n")
        return rel

    def project_bytes(self, *folders):
        return {p: p.read_bytes() for folder in folders for p in (self.root / folder).rglob("*") if p.is_file()}


class UpdateTests(UpdateCiCase):
    def test_init_writes_a_manifest_of_owned_files(self):
        manifest = json.loads((self.root / ".harness/manifest.json").read_text())
        self.assertTrue(manifest["version"])
        self.assertIn(".harness/bin/harness", manifest["files"])
        self.assertIn(".claude/agents/leader.md", manifest["files"])
        self.assertNotIn(".harness/docs/architecture.md", manifest["files"])
        self.assertFalse(any("state/" in rel or "go/" in rel for rel in manifest["files"]))

    def test_unchanged_file_is_replaced_and_project_files_are_not(self):
        rel = self.change_source()
        self.change_source(".harness/docs/architecture.md")
        self.change_source(".harness/templates/feature_list.json")
        (self.source / ".harness/state/feature_list.json").write_text("{}")
        before = self.project_bytes(".harness/state", ".harness/specs", ".harness/progress",
                                    ".harness/approvals", "src")
        config = (self.root / CONFIG).read_bytes()
        architecture = (self.root / ".harness/docs/architecture.md").read_bytes()
        result = self.run_cli("update")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("incoming", (self.root / rel).read_text())
        self.assertEqual(self.project_bytes(".harness/state", ".harness/specs", ".harness/progress",
                                            ".harness/approvals", "src"), before)
        self.assertEqual((self.root / CONFIG).read_bytes(), config)
        self.assertEqual((self.root / ".harness/docs/architecture.md").read_bytes(), architecture)
        recorded = json.loads((self.root / ".harness/manifest.json").read_text())["files"]
        self.assertEqual(recorded[rel], hashlib.sha256((self.root / rel).read_bytes()).hexdigest())

    def test_local_change_is_kept_with_a_new_file_and_a_warning(self):
        rel = self.change_source()
        mine = (self.root / rel).read_text() + "\nmine\n"
        (self.root / rel).write_text(mine)
        self.commit()
        result = self.run_cli("update")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / rel).read_text(), mine)
        self.assertIn("incoming", (self.root / f"{rel}.new").read_text())
        self.assertIn("[WARN]", result.stdout)

    def test_force_overwrites_a_local_change(self):
        rel = self.change_source()
        (self.root / rel).write_text("mine\n")
        self.commit()
        self.assertEqual(self.run_cli("update", "--force").returncode, 0)
        self.assertIn("incoming", (self.root / rel).read_text())
        self.assertFalse((self.root / f"{rel}.new").exists())

    def test_force_never_reaches_project_owned_paths(self):
        self.change_source(".harness/docs/conventions.md")
        (self.source / ".harness/config.json").write_text('{"project": "x", "stack": null, "app_dir": "src", '
                                                          '"commands": {"test": ""}}')
        before = (self.root / ".harness/docs/conventions.md").read_bytes(), (self.root / CONFIG).read_bytes()
        self.assertEqual(self.run_cli("update", "--force").returncode, 0)
        self.assertEqual(((self.root / ".harness/docs/conventions.md").read_bytes(),
                          (self.root / CONFIG).read_bytes()), before)

    def test_without_a_manifest_every_difference_is_a_local_change(self):
        rel = self.change_source()
        (self.root / ".harness/manifest.json").unlink()
        self.commit()
        before = (self.root / rel).read_bytes()
        self.assertEqual(self.run_cli("update").returncode, 0)
        self.assertEqual((self.root / rel).read_bytes(), before)
        self.assertTrue((self.root / f"{rel}.new").exists())

    def test_dry_run_changes_nothing(self):
        rel = self.change_source()
        before = self.project_bytes(".harness", ".claude")
        result = self.run_cli("update", "--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn(rel, result.stdout)
        self.assertEqual(self.project_bytes(".harness", ".claude"), before)

    def test_uncommitted_harness_files_stop_the_update(self):
        rel = self.change_source()
        (self.root / rel).write_text("uncommitted\n")
        result = self.run_cli("update")
        self.assertEqual(result.returncode, 1)
        self.assertIn("uncommitted", result.stderr)
        self.assertFalse((self.root / f"{rel}.new").exists())
        self.assertEqual(self.run_cli("update", "--force").returncode, 0)

    def test_settings_merge_keeps_user_settings_and_hooks(self):
        path = self.root / ".claude/settings.json"
        settings = json.loads(path.read_text())
        del settings["hooks"]["SessionStart"]
        settings["model"] = "sonnet"
        mine = {"type": "command", "command": "my-linter"}
        settings["hooks"]["PreToolUse"].append({"matcher": "Write", "hooks": [mine]})
        settings["hooks"]["Stop"] = [{"hooks": [mine]}]
        path.write_text(json.dumps(settings))
        self.commit()
        self.assertEqual(self.run_cli("update").returncode, 0)
        merged = json.loads(path.read_text())
        self.assertEqual(merged["model"], "sonnet")
        self.assertEqual(merged["hooks"]["Stop"], [{"hooks": [mine]}])
        self.assertIn("SessionStart", merged["hooks"])
        entries = [h for group in merged["hooks"]["PreToolUse"] for h in group["hooks"]]
        self.assertIn(mine, entries)
        self.assertEqual(sum("harness" in h["command"] for h in entries), 1)

    def test_rules_update_regenerates_checkpoints(self):
        rules_path = self.source / RULES
        rules = json.loads(rules_path.read_text())
        rules["checkpoints"]["sections"][0]["judgment"] = ["A brand new item."]
        rules_path.write_text(json.dumps(rules, indent=2))
        result = self.run_cli("update")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("A brand new item.", (self.root / ".harness/CHECKPOINTS.md").read_text())
        self.assertEqual(self.run_cli("check", "--no-tests").returncode, 0)

    def test_dry_run_reports_the_regeneration_and_changes_nothing(self):
        rules_path = self.source / RULES
        rules = json.loads(rules_path.read_text())
        rules["checkpoints"]["sections"][0]["judgment"] = ["A brand new item."]
        rules_path.write_text(json.dumps(rules, indent=2))
        before = (self.root / ".harness/CHECKPOINTS.md").read_bytes()
        self.assertIn("regenerate: .harness/CHECKPOINTS.md", self.run_cli("update", "--dry-run").stdout)
        self.assertEqual((self.root / ".harness/CHECKPOINTS.md").read_bytes(), before)

    def test_kept_local_rules_stay_consistent_and_say_what_to_run(self):
        incoming = self.source / RULES
        rules = json.loads(incoming.read_text())
        rules["checkpoints"]["sections"][0]["judgment"] = ["Incoming item."]
        incoming.write_text(json.dumps(rules, indent=2))
        local = self.root / RULES
        mine = json.loads(local.read_text())
        mine["checkpoints"]["sections"][1]["judgment"].append("My item.")
        local.write_text(json.dumps(mine, indent=2))
        self.commit()
        result = self.run_cli("update")
        self.assertIn("harness checkpoints --write", result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (self.root / ".harness/CHECKPOINTS.md").read_text()
        self.assertIn("My item.", text)
        self.assertNotIn("Incoming item.", text)
        self.assertTrue((self.root / ".harness/rules.json.new").is_file())

    def test_kept_rules_without_checkpoints_do_not_break_the_update(self):
        self.change_source(".harness/AGENTS.md")
        local = self.root / RULES
        rules = json.loads(local.read_text())
        del rules["checkpoints"]
        rules["invariants"] = [i for i in rules["invariants"] if i["id"] != "checkpoints_current"]
        local.write_text(json.dumps(rules, indent=2))
        before = (self.root / ".harness/CHECKPOINTS.md").read_bytes()
        self.commit()
        result = self.run_cli("update")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".harness/CHECKPOINTS.md").read_bytes(), before)

    def test_generated_project_is_slim(self):
        expected = {".harness/stacks/python/stack.json", ".harness/stacks/python/sgconfig.yml",
                    ".harness/stacks/python/rules/no-debugger.yml", ".harness/stacks/python/rules/no-skipped-tests.yml"}
        self.assertEqual({str(p.relative_to(self.root)) for p in (self.root / ".harness/stacks").rglob("*")
                          if p.is_file()}, expected)
        self.assertEqual([p.name for p in (self.root / ".harness/templates").iterdir()], ["progress_current.md"])
        self.assertTrue((self.root / ".harness/docs/stack/testing.md").is_file())

    def test_older_project_keeps_its_extra_files_untouched(self):
        extras = [".harness/templates/config.json", ".harness/stacks/python/conventions.md",
                  ".harness/stacks/python/scaffold/app/__init__.py"]
        manifest_path = self.root / ".harness/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for rel in extras:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("old\n")
            manifest["files"][rel] = hashlib.sha256(b"old\n").hexdigest()
        manifest["files"][".harness/CHECKPOINTS.md"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
        self.commit()
        self.change_source()
        self.change_source(".harness/stacks/python/conventions.md")
        result = self.run_cli("update")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for rel in extras:
            self.assertEqual((self.root / rel).read_text(), "old\n")
            self.assertFalse((self.root / f"{rel}.new").exists())
        recorded = json.loads(manifest_path.read_text())["files"]
        self.assertFalse(set(extras) & set(recorded))
        self.assertNotIn(".harness/CHECKPOINTS.md", recorded)

    def test_older_project_missing_nothing_does_not_recreate_removed_extras(self):
        self.change_source(".harness/templates/config.json")
        self.assertEqual(self.run_cli("update").returncode, 0)
        self.assertFalse((self.root / ".harness/templates/config.json").exists())

    def test_failure_rolls_everything_back(self):
        first = self.change_source()
        self.change_source(".harness/docs/specs.md")
        before = self.project_bytes(".harness", ".claude")
        stuck = self.root / ".harness/docs/specs.md"
        stuck.chmod(0o444)
        self.addCleanup(stuck.chmod, 0o644)
        result = self.run_cli("update")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.project_bytes(".harness", ".claude"), before)
        self.assertFalse((self.root / ".harness-init-manifest.json").exists())
        self.assertNotIn("incoming", (self.root / first).read_text())

    def test_local_rule_edit_is_kept_on_update(self):
        rel = ".harness/stacks/python/rules/no-debugger.yml"
        path = self.source / rel
        path.write_text(path.read_text().replace("A debugger call", "A debugger statement"))
        (self.root / rel).write_text((self.root / rel).read_text().replace("A debugger call", "Mine"))
        self.commit()
        self.assertEqual(self.run_cli("update").returncode, 0)
        self.assertIn("Mine", (self.root / rel).read_text())
        self.assertTrue((self.root / f"{rel}.new").is_file())

    def test_update_delivers_new_rules_and_skills(self):
        (self.source / ".harness/stacks/python/rules/new-rule.yml").write_text(
            "id: new-rule\nlanguage: Python\nseverity: error\nmessage: x\nrule:\n  pattern: forbidden_call()\n")
        (self.source / ".claude/skills/new-skill").mkdir()
        (self.source / ".claude/skills/new-skill/SKILL.md").write_text("---\nname: new-skill\n---\n")
        self.assertEqual(self.run_cli("update").returncode, 0)
        self.assertTrue((self.root / ".harness/stacks/python/rules/new-rule.yml").is_file())
        self.assertTrue((self.root / ".claude/skills/new-skill/SKILL.md").is_file())

    def test_refuses_the_scaffold_and_the_projects_own_copy(self):
        self.assertIn("scaffold", self.run_cli("update", cwd=self.source).stderr)
        result = self.run_cli("update", cli=self.root / ".harness/bin/harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("global", result.stderr)


class CiTests(UpdateCiCase):
    def parsed(self, text):
        ruby = shutil.which("ruby")
        if not ruby:
            self.skipTest("no YAML parser available")
        script = "require 'yaml'; require 'json'; puts JSON.generate(YAML.safe_load(STDIN.read, aliases: false))"
        result = subprocess.run([ruby, "-e", script], input=text, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def workflow(self):
        return (self.root / ".github/workflows/harness.yml").read_text()

    def test_every_shipped_stack_renders_valid_yaml(self):
        for path in sorted((SOURCE / ".harness/stacks").glob("*/stack.json")):
            with self.subTest(stack=path.parent.name):
                (self.root / ".harness/stacks/python/stack.json").write_text(path.read_text())
                self.assertEqual(self.run_cli("ci", "github", "--force").returncode, 0)
                data = self.parsed(self.workflow())
                # YAML 1.1 parsers read the `on` key as true; GitHub reads it as `on`.
                self.assertEqual(sorted(data["true"]), ["pull_request", "push"])
                self.assertEqual(data["name"], "harness")
                steps = data["jobs"]["check"]["steps"]
                self.assertEqual(steps[0]["uses"], "actions/checkout@v7")
                self.assertEqual(steps[-1]["run"], ".harness/bin/harness check")

    def test_runs_on_push_and_pull_request(self):
        self.run_cli("ci", "github")
        self.assertIn("  push:\n  pull_request:\n", self.workflow())

    def test_stack_setup_comes_from_stack_json(self):
        path = self.root / ".harness/stacks/python/stack.json"
        stack = json.loads(path.read_text())
        stack["ci"] = {"steps": [{"run": "make toolchain", "working-directory": "src"}]}
        path.write_text(json.dumps(stack))
        self.run_cli("ci", "github")
        steps = self.parsed(self.workflow())["jobs"]["check"]["steps"]
        self.assertEqual(steps[-2], {"run": "make toolchain", "working-directory": "src"})

    def test_stack_without_setup_says_what_to_add(self):
        path = self.root / ".harness/stacks/python/stack.json"
        stack = json.loads(path.read_text())
        del stack["ci"]
        path.write_text(json.dumps(stack))
        result = self.run_cli("ci", "github")
        self.assertEqual(result.returncode, 0)
        self.assertIn("add your toolchain steps", result.stdout)

    def test_refuses_to_overwrite_without_force(self):
        target = self.root / ".github/workflows/harness.yml"
        target.parent.mkdir(parents=True)
        target.write_text("mine")
        result = self.run_cli("ci", "github")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(target.read_text(), "mine")
        self.assertEqual(self.run_cli("ci", "github", "--force").returncode, 0)
        self.assertNotEqual(target.read_text(), "mine")

    def test_refuses_the_scaffold(self):
        self.assertEqual(self.run_cli("ci", "github", cwd=self.source).returncode, 1)


class UpdateCiHookTests(HookCase):
    def test_agents_may_not_run_update_or_ci(self):
        for agent in (None, "leader", "implementer", "reviewer", "general-purpose"):
            for command in ("harness update", "harness update --force", "harness ci github",
                            ".harness/bin/harness update --dry-run"):
                with self.subTest(agent=agent, command=command):
                    self.assert_blocked(self.bash(command, agent))
        self.assert_blocked(self.bash("$H update", "leader"))

    def test_agents_may_not_write_workflows(self):
        for agent in ("leader", "implementer", "reviewer", "general-purpose"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.write_call(".github/workflows/harness.yml", agent))
                self.assert_blocked(self.bash("echo x > .github/workflows/harness.yml", agent))
                self.assert_blocked(self.bash("echo x > $UNKNOWN/.github/workflows/x.yml", agent))

    def test_agents_may_not_write_the_owned_manifest(self):
        self.assert_blocked(self.write_call(".harness/manifest.json", "leader"))


class CheckpointTests(HookCase):
    FILE = ".harness/CHECKPOINTS.md"

    def test_shipped_file_is_current_and_generated(self):
        result = subprocess.run([sys.executable, str(CLI), "checkpoints"], cwd=str(SOURCE),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (SOURCE / self.FILE).read_text())
        self.assertIn("Do not edit by hand", result.stdout)

    def test_every_invariant_and_section_is_rendered(self):
        text = self.run_cli("checkpoints").stdout
        rules = self.read_json(RULES)
        for invariant in rules["invariants"]:
            self.assertIn(invariant["description"], text)
        for section in rules["checkpoints"]["sections"]:
            self.assertIn(f"## {section['id']} — {section['title']}", text)
        self.assertIn("PreToolUse and SessionStart", text)
        self.assertIn("**How to use this file:**", text)
        self.assertIn("**On C7:**", text)

    def test_intro_is_one_clean_quote_block(self):
        text = self.run_cli("checkpoints").stdout
        self.assertNotIn("> >", text)
        self.assertIn("the destination is.\n>\n> **[auto]**", text)

    def test_rendering_is_deterministic(self):
        self.assertEqual(self.run_cli("checkpoints").stdout, self.run_cli("checkpoints").stdout)

    def test_hand_edit_fails_check_with_the_fix(self):
        self.path(self.FILE).write_text(self.path(self.FILE).read_text() + "edit\n")
        self.assert_check_fails("harness checkpoints --write")

    def test_rules_change_makes_the_file_stale_and_write_fixes_it(self):
        rules = self.read_json(RULES)
        rules["checkpoints"]["sections"][0]["judgment"] = ["A new item."]
        self.write(RULES, json.dumps(rules))
        self.assert_check_fails("is stale")
        self.assertEqual(self.run_cli("checkpoints", "--write").returncode, 0)
        self.assert_check_passes()

    def test_invariant_naming_an_unknown_checkpoint_is_invalid(self):
        rules = self.read_json(RULES)
        rules["invariants"][0]["checkpoint"] = "C99"
        self.write(RULES, json.dumps(rules))
        self.assert_check_fails("unknown checkpoint")

    def test_older_rules_without_checkpoints_do_not_block_the_hook(self):
        rules = self.read_json(RULES)
        del rules["checkpoints"]
        rules["invariants"] = [i for i in rules["invariants"] if i["id"] != "checkpoints_current"]
        self.write(RULES, json.dumps(rules))
        self.assert_allowed(self.write_call("src/app/x.py", "implementer"))
        self.assert_check_passes()

    def test_write_is_human_only_and_printing_is_not(self):
        for agent in (None, "leader", "implementer", "reviewer", "general-purpose"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.bash("harness checkpoints --write", agent))
                self.assert_blocked(self.bash(".harness/bin/harness checkpoints --wr", agent))
                self.assert_blocked(self.write_call(self.FILE, agent))
                self.assert_blocked(self.bash(f"echo x > {self.FILE}", agent))
        self.assert_blocked(self.bash("$H checkpoints --write", "leader"))
        self.assert_allowed(self.bash("harness checkpoints", "reviewer"))


class SkillTests(HookCase):
    def agent(self, role):
        return self.path(f".claude/agents/{role}.md")

    def test_every_assigned_skill_ships_with_matching_frontmatter(self):
        self.assert_check_passes()
        rules = self.read_json(RULES)
        self.assertEqual(sorted(rules["skills"]), ["implementer", "leader", "reviewer", "spec_author"])
        for name in ("feature-decomposition", "ears-specs", "system-design", "qa", "ast-grep",
                     "clean-architecture", "clean-code-principles", "unit-testing"):
            text = self.path(f".claude/skills/{name}/SKILL.md").read_text()
            self.assertTrue(text.startswith(f"---\nname: {name}\ndescription:"), name)

    def test_vendored_skills_keep_their_license_and_stay_inert(self):
        for name, holder in (("clean-architecture", "Wondel.ai"), ("clean-code-principles", "Asyraf Hussin")):
            folder = self.path(f".claude/skills/{name}")
            self.assertIn(holder, (folder / "LICENSE").read_text())
            self.assertIn("MIT License", (folder / "NOTICE.md").read_text())
            text = "\n".join(p.read_text() for p in folder.rglob("*.md"))
            self.assertNotRegex(text, r"npm install|npx |pip install|curl |/Users/|tag=wondelai")

    def test_missing_assigned_skill_fails_check(self):
        shutil.rmtree(self.path(".claude/skills/qa"))
        self.assert_check_fails("skill qa is assigned but missing")

    def test_skill_with_the_wrong_name_fails_check(self):
        path = self.path(".claude/skills/qa/SKILL.md")
        path.write_text(path.read_text().replace("name: qa", "name: other", 1))
        self.assert_check_fails("frontmatter does not name it")

    def test_frontmatter_disagreeing_with_the_map_fails_check(self):
        path = self.agent("reviewer")
        path.write_text(path.read_text().replace("  - qa\n", ""))
        self.assert_check_fails("skills frontmatter does not match")

    def test_on_demand_skills_need_the_skill_tool(self):
        path = self.agent("leader")
        path.write_text(path.read_text().replace("tools: Skill, ", "tools: "))
        self.assert_check_fails("tools must include Skill")

    def test_on_demand_skill_needs_a_stated_trigger(self):
        path = self.agent("implementer")
        path.write_text(path.read_text().replace("`ast-grep`", "ast-grep"))
        self.assert_check_fails("does not say when to use ast-grep")

    def test_older_rules_without_a_skill_map_pass(self):
        rules = self.read_json(RULES)
        del rules["skills"]
        rules["invariants"] = [i for i in rules["invariants"]
                               if i["id"] not in ("skills_assigned", "checkpoints_current")]
        self.write(RULES, json.dumps(rules))
        shutil.rmtree(self.path(".claude/skills/qa"))
        self.assert_check_passes()

    def test_agents_may_not_install_skills(self):
        commands = ["npx skills add owner/repo", "npx -y skills add owner/repo", "npx skills update",
                    "npx skills@latest add owner/repo", "bunx skills add x", "pnpm dlx skills add x",
                    "npm exec skills add x", "skills add x"]
        for agent in (None, "implementer", "general-purpose"):
            for command in commands:
                with self.subTest(agent=agent, command=command):
                    self.assert_blocked(self.bash(command, agent))

    def test_finding_skills_stays_allowed(self):
        for command in ("npx skills find testing", "npx skills list", "npx jest add", "npm install"):
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command, "implementer"))

    def test_agents_may_not_write_skills(self):
        for agent in ("leader", "implementer", "general-purpose"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.write_call(".claude/skills/qa/SKILL.md", agent))


class SandboxTests(HookCase):
    def load_cli(self):
        loader = importlib.machinery.SourceFileLoader("harness_cli", str(CLI))
        spec = importlib.util.spec_from_loader("harness_cli", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def test_agents_may_not_run_it(self):
        for agent in (None, "implementer", "general-purpose"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.bash("harness sandbox", agent))
        self.assert_blocked(self.bash("$H sandbox", "leader"))

    def test_missing_nono_is_a_clear_error(self):
        empty = Path(self.tmp) / "emptybin"
        empty.mkdir()
        result = subprocess.run([sys.executable, str(self.cli), "sandbox"], cwd=str(self.root),
                                capture_output=True, text=True, env={"PATH": str(empty)})
        self.assertEqual(result.returncode, 1)
        self.assertIn("brew install nono", result.stderr)

    def test_refuses_a_temporary_project(self):
        fake = Path(self.tmp) / "bin"
        fake.mkdir()
        (fake / "nono").write_text("#!/bin/sh\nexit 0\n")
        (fake / "nono").chmod(0o755)
        result = subprocess.run([sys.executable, str(self.cli), "sandbox"], cwd=str(self.root),
                                capture_output=True, text=True, env={"PATH": str(fake)})
        self.assertEqual(result.returncode, 1)
        self.assertIn("temporary folder", result.stderr)

    def test_older_rules_get_a_clear_message(self):
        rules = self.read_json(RULES)
        del rules["sandbox"]
        self.write(RULES, json.dumps(rules))
        self.assertIn("harness update", self.run_cli("sandbox").stderr)

    def test_profile_is_an_allow_list_without_protected_paths(self):
        module = self.load_cli()
        profile = module.sandbox_profile(self.read_json(RULES))
        self.assertEqual(profile["workdir"], {"access": "read"})
        writable = profile["filesystem"]["allow"]
        self.assertIn("$WORKDIR/src", writable)
        self.assertIn("$WORKDIR/.harness/state", writable)
        for protected in (".harness", ".harness/approvals", ".harness/bin", ".claude", ".git"):
            self.assertNotIn(f"$WORKDIR/{protected}", writable)

    def test_rules_cannot_expose_protected_paths(self):
        module = self.load_cli()
        for path in (".harness/approvals", ".harness", ".claude", ".git"):
            rules = self.read_json(RULES)
            rules["sandbox"]["writable"].append(path)
            with self.subTest(path=path), self.assertRaises(module.HarnessError):
                module.sandbox_profile(rules)

    def test_toolchains_under_home_are_readable(self):
        module = self.load_cli()
        home = os.path.realpath(os.path.expanduser("~"))
        tool = self.tmp_tool(f"{home}/anaconda3/bin/python3", module)
        self.assertIn(f"{home}/anaconda3", tool)
        profile = module.sandbox_profile(self.read_json(RULES), tool)
        self.assertIn(f"{home}/anaconda3", profile["filesystem"]["read"])
        self.assertNotIn(f"{home}/anaconda3", profile["filesystem"]["allow"])

    def tmp_tool(self, path, module):
        original = (module.shutil.which, module.sys.base_prefix, module.sys.prefix)
        module.shutil.which = lambda name: path
        module.sys.base_prefix = module.sys.prefix = "/usr"
        try:
            return module.toolchain_read_roots(["python3"])
        finally:
            module.shutil.which, module.sys.base_prefix, module.sys.prefix = original

    def test_system_toolchains_and_home_itself_are_not_added(self):
        module = self.load_cli()
        home = os.path.realpath(os.path.expanduser("~"))
        self.assertEqual(self.tmp_tool("/opt/homebrew/bin/python3", module), [])
        self.assertEqual(self.tmp_tool(f"{home}/bin/python3", module), [])

    def test_stack_tools_flatten_alternatives_and_include_python(self):
        module = self.load_cli()
        tools = module.stack_tools(self.root, self.read_json(CONFIG))
        self.assertEqual(tools[0], "python3")
        self.assertTrue(all(isinstance(tool, str) for tool in tools))

    def test_sandbox_refuses_to_start_when_the_hook_cannot_block(self):
        module = self.load_cli()
        for code in (0, 1):
            with self.assertRaises(module.HarnessError) as caught:
                self.preflight(module, code, "No module named 'encodings'")
            self.assertIn("refusing to start", str(caught.exception))

    def preflight(self, module, code, stderr=""):
        original = module.subprocess.run
        module.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, code, "", stderr)
        try:
            module.sandbox_preflight(self.root, "/p.json")
        finally:
            module.subprocess.run = original

    def test_sandbox_starts_when_the_hook_blocks(self):
        self.preflight(self.load_cli(), 2)

    def test_claude_arguments_pass_through(self):
        command = self.load_cli().sandbox_command("/p.json", ["--", "-p", "hello"])
        self.assertEqual(command[command.index("--") + 1:], ["claude", "-p", "hello"])

    @unittest.skipUnless(shutil.which("nono"), "nono is not installed")
    def test_generated_profile_validates_with_nono(self):
        module = self.load_cli()
        path = Path(self.tmp) / "profile.json"
        path.write_text(json.dumps(module.sandbox_profile(self.read_json(RULES))))
        result = subprocess.run(["nono", "profile", "validate", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


AST_GREP = shutil.which("ast-grep")


class AstGrepTests(ProjectCase):
    NO_TOOL = {"PATH": "/usr/bin:/bin"}

    def check_without_tool(self):
        return subprocess.run([sys.executable, str(self.cli), "check"], cwd=str(self.root),
                              capture_output=True, text=True, env=self.NO_TOOL)

    def test_missing_tool_warns_and_continues(self):
        self.write("src/app/bad.py", "breakpoint()\n")
        result = self.check_without_tool()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("ast-grep is not installed", result.stdout)

    def test_missing_tool_falls_back_to_a_text_match(self):
        self.make_done_ready()
        self.write("src/app/traced.py", "test_it = None\n")
        self.set_features(feature(status="done"))
        result = self.check_without_tool()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("matched as plain text", result.stdout)

    @unittest.skipUnless(AST_GREP, "ast-grep is not installed")
    def test_finding_fails_the_check(self):
        self.write("src/app/bad.py", "def f():\n    breakpoint()\n")
        self.assert_check_fails("ast-grep rules failed")

    @unittest.skipUnless(AST_GREP, "ast-grep is not installed")
    def test_clean_code_passes_and_print_is_not_flagged(self):
        self.write("src/app/fine.py", "def f():\n    print('hello')\n")
        self.assert_check_passes()

    @unittest.skipUnless(AST_GREP, "ast-grep is not installed")
    def test_a_project_can_tune_its_rules(self):
        self.write("src/app/bad.py", "def f():\n    breakpoint()\n")
        self.path(".harness/stacks/python/rules/no-debugger.yml").unlink()
        self.assert_check_passes()

    @unittest.skipUnless(AST_GREP, "ast-grep is not installed")
    def test_mapped_name_must_really_be_a_test(self):
        self.make_done_ready()
        self.write("src/app/traced.py", "test_it = None\n")
        self.set_features(feature(status="done"))
        self.assert_check_fails("maps to `test_it`, which is not a test")

    @unittest.skipUnless(AST_GREP, "ast-grep is not installed")
    def test_helper_function_is_not_a_test(self):
        self.make_done_ready()
        self.write("src/app/traced.py", "def helper():\n    pass\n\n\ntest_it = helper\n")
        self.set_features(feature(status="done"))
        self.assert_check_fails("which is not a test")

    def test_generic_stack_ships_no_rules(self):
        self.assertFalse((SOURCE / ".harness/stacks/generic/sgconfig.yml").exists())


@unittest.skipUnless(AST_GREP, "ast-grep is not installed")
class StackRuleTests(unittest.TestCase):
    SAMPLES = {
        "python": ("bad.py", "import pdb\ndef f():\n    breakpoint()\n    pdb.set_trace()\n\n"
                   "@unittest.skip('x')\ndef test_a():\n    pass\n", 3,
                   "good.py", "def f():\n    print('ok')\n"),
        "go": ("bad_test.go", 'package x\nimport "testing"\nfunc TestA(t *testing.T) {\n\tt.Skip("x")\n\tprintln("y")\n}\n',
               2, "good.go", 'package x\nimport "fmt"\nfunc F() { fmt.Println("ok") }\n'),
        "java": ("Bad.java", 'class Bad { @Disabled("x") void a() {} @org.junit.Ignore void b() {} '
                 "void c() { try { d(); } catch (Exception e) { e.printStackTrace(); } } }\n", 3,
                 "Good.java", 'class Good { void a() { System.out.println("Hello"); } }\n'),
        "nest": ("bad.spec.ts", "it.only('a', () => {});\nxit('b', () => {});\nconsole.log('c');\ndebugger;\n", 4,
                 "good.ts", "console.error('kept');\nlogger.log('ok');\n"),
    }

    def scan(self, stack, filename, text):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / filename).write_text(text)
            config = SOURCE / f".harness/stacks/{stack}/sgconfig.yml"
            result = subprocess.run(["ast-grep", "scan", "--config", str(config), "--json=stream", "."],
                                    cwd=folder, capture_output=True, text=True)
        return [json.loads(line)["ruleId"] for line in result.stdout.splitlines()]

    def test_rules_flag_bad_code_and_leave_good_code_alone(self):
        for stack, (bad, bad_text, expected, good, good_text) in self.SAMPLES.items():
            with self.subTest(stack=stack):
                self.assertEqual(len(self.scan(stack, bad, bad_text)), expected)
                self.assertEqual(self.scan(stack, good, good_text), [])

    def test_test_name_rules_find_real_tests_only(self):
        samples = {
            "python": ("t.py", "def test_a():\n    pass\n\ndef helper():\n    pass\n", ["test_a"]),
            "go": ("t_test.go", 'package x\nimport "testing"\nfunc TestA(t *testing.T) {}\nfunc helper(x int) {}\n', ["TestA"]),
            "java": ("T.java", "class T { @Test void aTest() {} void helper() {} }\n", ["aTest"]),
            "nest": ("t.spec.ts", "it('does a thing', () => {});\nhelper('x');\n", ["does a thing"]),
        }
        for stack, (filename, text, expected) in samples.items():
            with self.subTest(stack=stack), tempfile.TemporaryDirectory() as folder:
                (Path(folder) / filename).write_text(text)
                spec = json.loads((SOURCE / f".harness/stacks/{stack}/stack.json").read_text())["test_names"]
                rule = json.dumps({"id": "t", "language": spec["language"], "rule": spec["rule"]})
                result = subprocess.run(["ast-grep", "scan", "--inline-rules", rule, "--json=stream", "."],
                                        cwd=folder, capture_output=True, text=True)
                names = [json.loads(l)["metaVariables"]["single"]["NAME"]["text"].strip("'\"")
                         for l in result.stdout.splitlines()]
                self.assertEqual([n for n in names if re.search(spec["name_regex"], n)], expected)


class LifecycleRegressionTests(ProjectCase):
    def promoted(self):
        self.make_done_ready("owed")
        self.set_features(feature("owed", status="in_progress"))
        self.set_debts(debt(status="scheduled", sdd=True))

    def state_files(self):
        return self.path(FEATURES).read_bytes(), self.path(DEBTS).read_bytes()

    def test_report_newer_than_a_rejection_goes_to_the_reviewer(self):
        self.make_done_ready()
        self.set_features(feature(status="in_progress"))
        self.write_review(verdict="CHANGES_REQUESTED")
        os.utime(self.path(".harness/progress/review_alpha.md"), (1, 1))
        self.assertTrue(self.run_cli("next").stdout.startswith("reviewer:"))

    def test_failed_close_changes_neither_file(self):
        self.promoted()
        self.path(".harness/progress/review_owed.md").unlink()
        before = self.state_files()
        self.assertNotEqual(self.run_cli("transition", "owed", "done").returncode, 0)
        self.assertEqual(self.state_files(), before)

    def test_close_that_cannot_write_changes_neither_file(self):
        self.promoted()
        before = self.state_files()
        folder = self.path(".harness/state")
        folder.chmod(0o555)
        self.addCleanup(folder.chmod, 0o755)
        result = self.run_cli("transition", "owed", "done")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.state_files(), before)

    @unittest.skipUnless(sys.platform == "darwin", "uses the macOS immutable flag")
    def test_close_restores_the_first_file_when_the_second_write_fails(self):
        self.promoted()
        before = self.state_files()
        subprocess.run(["chflags", "uchg", str(self.path(DEBTS))], check=True)
        self.addCleanup(subprocess.run, ["chflags", "nouchg", str(self.path(DEBTS))])
        result = self.run_cli("transition", "owed", "done")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state_files(), before)
        self.assertEqual(sorted(p.name for p in self.path(".harness/state").iterdir()),
                         ["feature_list.json", "tasks.json", "techdebt_list.json"])

    def test_closing_leaves_unrelated_debt_alone(self):
        self.promoted()
        doc = self.read_json(DEBTS)
        doc["debts"].append(debt(id=2, name="other", status="scheduled"))
        self.write(DEBTS, json.dumps(doc))
        self.assertEqual(self.run_cli("transition", "owed", "done").returncode, 0)
        self.assertEqual(self.read_json(DEBTS)["debts"][1]["status"], "scheduled")

    def assert_spec_refused(self, requirements, tasks, expected):
        self.write_spec()
        self.write(".harness/specs/alpha/requirements.md", requirements)
        self.write(".harness/specs/alpha/tasks.md", tasks)
        self.set_features(feature())
        result = self.run_cli("transition", "alpha", "spec_ready", "--as", "spec_author")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(expected, result.stderr)
        self.assertEqual(self.status(), "pending")

    def test_spec_ready_needs_a_requirement_heading(self):
        self.assert_spec_refused("no headings\n", "- [ ] T1 — Covers: R1.\n", "declares no R<n>")

    def test_spec_ready_needs_a_parsable_task(self):
        self.assert_spec_refused("## R1\nx\n", "T1 without a checkbox\n", "has no tasks")

    def test_spec_ready_ignores_tasks_in_code_fences(self):
        self.assert_spec_refused("## R1\nx\n", "```\n- [ ] T1 — Covers: R1.\n```\n", "has no tasks")

    def test_spec_ready_needs_tasks_that_reference_a_requirement(self):
        self.assert_spec_refused("## R1\nx\n", "- [ ] T1 — no reference\n", "references no R<n>")

    def test_spec_ready_rejects_unknown_requirement_references(self):
        self.assert_spec_refused("## R1\nx\n", "- [ ] T1 — Covers: R9.\n", "unknown R9")

    def test_malformed_spec_cannot_reach_the_human(self):
        self.write_spec(tasks="- [ ] T1 — no reference\n")
        self.set_features(feature(status="spec_ready"))
        self.assertTrue(self.run_cli("next").stdout.startswith("spec_author:"))
        result = self.run_at_terminal("approve", "alpha")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.path(".harness/approvals/alpha.json").exists())
        self.assert_check_fails("references no R<n>")

    def stack_no_tests(self, name, output, code=0):
        stack = json.loads((SOURCE / f".harness/stacks/{name}/stack.json").read_text())
        config = self.read_json(CONFIG)
        script = self.path("src/fake_test.sh")
        script.write_text(f"cat <<'E'\n{output}\nE\nexit {code}\n")
        config["commands"]["test"] = f"sh {script}"
        config["no_tests"] = stack["no_tests"]
        self.write(CONFIG, json.dumps(config))
        self.make_done_ready()
        self.set_features(feature(status="done"))
        return self.run_cli("check")

    def test_java_module_without_tests_is_not_a_false_red(self):
        output = "[INFO] No tests to run.\n[INFO] Tests run: 12, Failures: 0, Errors: 0, Skipped: 0"
        result = self.stack_no_tests("java", output)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_java_with_no_tests_at_all_is_still_red(self):
        self.assertNotEqual(self.stack_no_tests("java", "[INFO] No tests to run.").returncode, 0)

    def test_go_package_without_tests_is_not_a_false_red(self):
        output = "?   \tapp/cmd\t[no test files]\nok  \tapp/core\t0.1s"
        self.assertEqual(self.stack_no_tests("go", output).returncode, 0)

    def test_jest_project_without_tests_is_not_a_false_red(self):
        output = "No tests found, exiting with code 1\nTests:       3 passed, 3 total"
        self.assertEqual(self.stack_no_tests("nest", output).returncode, 0)

    def test_unblocking_to_pending_is_allowed_while_another_feature_runs(self):
        self.set_features(feature("alpha", status="blocked", blocked_from="pending"),
                          feature("beta", sdd=False, status="in_progress", id=2))
        result = self.run_at_terminal("transition", "alpha", "pending", "--as", "human")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_unblocking_to_in_progress_needs_a_free_slot(self):
        self.set_features(feature("alpha", sdd=False, status="blocked", blocked_from="in_progress"),
                          feature("beta", sdd=False, status="in_progress", id=2))
        result = self.run_at_terminal("transition", "alpha", "in_progress", "--as", "human")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status(), "blocked")

    def test_guard_messages_appear_once(self):
        self.set_features(feature(sdd=False, status="in_progress"))
        result = self.run_cli("transition", "alpha", "done")
        self.assertEqual(result.stderr.count("no review report"), 1, result.stderr)

    def test_check_messages_appear_once(self):
        self.write_spec(tasks="")
        self.set_features(feature(status="done"))
        result = self.run_cli("check", "--no-tests")
        self.assertEqual(result.stdout.count("tasks.md has no tasks"), 1, result.stdout)

    def test_non_utf8_evidence_is_a_clean_error(self):
        self.make_done_ready()
        self.set_features(feature(status="in_progress"))
        self.path(".harness/progress/review_alpha.md").write_bytes(b"\xff\xfe")
        for args in (("next",), ("transition", "alpha", "done")):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.set_features(feature(status="done"))
        self.assert_check_fails("not valid UTF-8")

    def test_non_utf8_state_is_a_clean_error(self):
        self.path(FEATURES).write_bytes(b"\xff\xfe")
        result = self.run_cli("next")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_non_utf8_test_output_does_not_crash_check(self):
        config = self.read_json(CONFIG)
        config["commands"]["test"] = "printf '\\377'; exit 1"
        self.write(CONFIG, json.dumps(config))
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("tests failed", result.stdout)

    def test_state_file_mode_is_preserved(self):
        self.path(FEATURES).chmod(0o640)
        self.set_features(feature(sdd=False))
        self.assertEqual(self.run_cli("transition", "alpha", "in_progress").returncode, 0)
        self.assertEqual(self.path(FEATURES).stat().st_mode & 0o777, 0o640)


class PureFunctionTests(unittest.TestCase):
    def load_cli(self):
        loader = importlib.machinery.SourceFileLoader("harness_cli", str(CLI))
        spec = importlib.util.spec_from_loader("harness_cli", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def test_closing_documents_does_not_touch_its_inputs(self):
        features = {"features": [feature("owed", status="in_progress")]}
        debts = {"debts": [debt(name="owed", status="scheduled", sdd=True)]}
        before = copy.deepcopy((features, debts))
        closed_features, closed_debts = self.load_cli().closing_documents(features, debts, "owed")
        self.assertEqual((features, debts), before)
        self.assertEqual(closed_features["features"][0]["status"], "done")
        self.assertEqual(closed_debts["debts"][0]["status"], "resolved")


class ParserRegressionTests(HookCase):
    def test_abbreviated_options_are_rejected(self):
        self.set_features(feature(sdd=False))
        for args in (("transition", "alpha", "in_progress", "--a", "leader"),
                     ("transition", "alpha", "blocked", "--reas", "x"),
                     ("check", "--no-t")):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 2)
        self.assertEqual(self.status(), "pending")

    def test_repeated_as_is_rejected(self):
        self.set_features(feature(sdd=False))
        result = self.run_cli("transition", "alpha", "in_progress", "--as", "leader", "--as", "leader")
        self.assertEqual(result.returncode, 2)
        self.assertIn("only be given once", result.stderr)

    def test_hook_reads_the_actor_like_the_cli(self):
        commands = [
            "harness transition alpha done --as=implementer --a leader",
            "harness transition alpha done --as implementer --as leader",
            "harness transition alpha done --as leader --as implementer",
            "harness transition alpha done --as $ACTOR",
            "harness transition alpha",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "implementer"))

    def test_hook_accepts_the_equals_spelling_of_the_real_role(self):
        self.assert_allowed(self.bash("harness transition alpha blocked --as=implementer --reason x", "implementer"))


class BashWriterTests(HookCase):
    def write_patch(self, target):
        self.write("/".join(("..", "change.patch")),
                   f"--- a/{target}\n+++ b/{target}\n@@ -1 +1 @@\n-a\n+b\n")
        return "../change.patch"

    def test_target_directory_forms_are_writes(self):
        commands = [
            "cp -t src /tmp/a.py",
            "cp --target-directory src /tmp/a.py",
            "cp --target-directory=src /tmp/a.py",
            "cp -rt src /tmp/a.py",
            "install -t src /tmp/a.py",
            "mv -t src /tmp/a.py",
            "ln -t src /tmp/a.py",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "leader"))

    def test_target_directory_forms_stay_allowed_for_the_owner(self):
        self.assert_allowed(self.bash("cp -t src/app /tmp/a.py", "implementer"))

    def test_reports_of_closed_work_are_frozen_for_every_role(self):
        self.set_features(feature(status="done"))
        for path, role in ((".harness/progress/impl_alpha.md", "implementer"),
                           (".harness/progress/review_alpha.md", "reviewer")):
            with self.subTest(role=role):
                self.assert_blocked(self.write_call(path, role, "changed"))

    def test_reports_of_open_work_stay_writable(self):
        self.set_features(feature(status="in_progress"))
        self.assert_allowed(self.write_call(".harness/progress/impl_alpha.md", "implementer", "x"))

    def test_a_debt_report_is_writable_while_its_feature_is_closed(self):
        self.set_features(feature(status="done"))
        self.assert_allowed(self.write_call(".harness/progress/impl_debt-alpha.md", "implementer", "x"))

    def test_restamp_is_human_only(self):
        for agent in ("leader", "implementer", "reviewer"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.bash("harness evidence restamp alpha --reason x", agent))

    def test_agents_cannot_edit_the_evidence_history(self):
        self.set_features(feature(status="done", evidence={"a": "b"}))
        doc = self.read_json(FEATURES)
        doc["features"][0]["evidence_history"] = []
        self.assert_blocked(self.write_call(FEATURES, "leader", json.dumps(doc)))

    def test_read_only_scripts_on_harness_files_pass(self):
        for script in ("import json; print(json.load(open('.harness/state/feature_list.json')))",
                       "print(open('.harness/progress/current.md','rb').read())",
                       "print(open('.harness/progress/app.md').read())",
                       "import sys; sys.stdout.write(open('.harness/rules.json').read())"):
            with self.subTest(script=script):
                self.assert_allowed(self.bash(f'python3 -c "{script}"', "leader"))

    def test_scripted_writes_are_still_blocked(self):
        for script in ("open('.harness/rules.json','w').write('x')", "open('.harness/rules.json',mode='a')",
                       "import os; os.remove('.harness/rules.json')",
                       "from pathlib import Path; Path('.harness/rules.json').write_text('x')",
                       "import shutil; shutil.rmtree('.harness')"):
            with self.subTest(script=script):
                self.assert_blocked(self.bash(f'python3 -c "{script}"', "leader"))

    def test_heredoc_text_is_data_not_commands(self):
        review = ".harness/progress/review_alpha.md"
        for body in ("- A1 -> tests pass", "run harness approve alpha", "rm .harness/rules.json"):
            with self.subTest(body=body):
                self.assert_allowed(self.bash(f"cat > {review} <<'EOF'\n{body}\nEOF", "reviewer"))

    def test_commands_after_a_heredoc_are_still_inspected(self):
        command = "cat > .harness/progress/review_alpha.md <<'EOF'\ntext\nEOF\nrm .harness/rules.json"
        self.assert_blocked(self.bash(command, "reviewer"))

    def test_heredoc_redirect_target_is_still_checked(self):
        self.assert_blocked(self.bash("cat > .harness/rules.json <<'EOF'\n{}\nEOF", "reviewer"))

    def test_heredocs_that_are_executed_are_still_inspected(self):
        for command in ("bash <<'EOF'\nrm .harness/rules.json\nEOF",
                        "cat <<'EOF' | sh\nrm .harness/rules.json\nEOF"):
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "reviewer"))

    def test_reading_the_cli_with_output_discarded_is_not_a_copy(self):
        for command in ("grep -n foo .harness/bin/harness 2>/dev/null", "cat .harness/bin/harness >/dev/null",
                        "grep -n foo .harness/bin/harness 2>/dev/null | head"):
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command, "implementer"))

    def test_redirecting_the_cli_to_a_file_is_still_a_copy(self):
        self.assert_blocked(self.bash("cat .harness/bin/harness > /tmp/copy", "implementer"))

    def test_target_directory_cannot_hide_a_cli_copy(self):
        for command in ("cp -t /tmp .harness/bin/harness", "cp --target-directory=/tmp .harness/bin/harness",
                        "install -t /tmp .harness/bin/harness"):
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "implementer"))

    def test_modelled_writers_are_denied(self):
        patch = self.write_patch("src/app/__init__.py")
        commands = [
            "find src -name '*.py' -delete",
            "find .harness -type f -delete",
            "find src -exec rm {} ;",
            "find src -type f -exec rm -f {} +",
            "find src -exec sed -i '' s/a/b/ {} ;",
            "find src -execdir sh -c 'echo x > {}' ;",
            f"git apply {patch}",
            f"patch -p1 < {patch}",
            f"patch -p1 -i {patch}",
            "git apply",
            "cat x.patch | patch -p1",
            "ed src/app/__init__.py",
            "ex -s src/app/__init__.py",
            "git reset --hard",
            "git reset --hard HEAD~1",
            "git -C . reset --hard",
            "git clean -fd",
            "git clean -fd src",
            "git checkout -- src/app/__init__.py",
            "git checkout HEAD -- src",
            "git checkout src",
            "git checkout .",
            "git restore src/app/__init__.py",
            "git restore --source HEAD src/app/__init__.py",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "reviewer"))

    def test_owner_may_use_the_same_writers_on_its_own_paths(self):
        patch = self.write_patch("src/app/__init__.py")
        commands = [
            "find src -name '*.tmp' -delete",
            "find src -exec rm {} ;",
            f"git apply {patch}",
            f"patch -p1 < {patch}",
            "ed src/app/__init__.py",
            "git checkout -- src/app/__init__.py",
            "git restore src/app/__init__.py",
            "git clean -fd src",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command, "implementer"))

    def test_patch_into_a_protected_path_is_denied_for_the_owner_too(self):
        patch = self.write_patch(".harness/rules.json")
        self.assert_blocked(self.bash(f"git apply {patch}", "implementer"))
        self.assert_blocked(self.bash(f"patch -p1 < {patch}", "implementer"))

    def test_whole_tree_git_operations_are_denied_for_every_role(self):
        for agent in ("leader", "implementer", "reviewer", "general-purpose"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.bash("git reset --hard", agent))
                self.assert_blocked(self.bash("git clean -fdx", agent))

    def test_read_only_and_branch_git_stays_allowed(self):
        commands = [
            "git checkout main",
            "git checkout -b feature/x",
            "git switch main",
            "git stash",
            "git stash pop",
            "git reset HEAD~1",
            "git clean -n",
            "git clean --dry-run",
            "git apply --check x.patch",
            "git restore --staged src/app/__init__.py",
            "find src -name '*.py'",
            "find . -type f -print",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command, "leader"))

    def test_approve_as_a_plain_argument_is_allowed(self):
        commands = [
            "pytest -k approve",
            "npm test -- approve",
            "npx jest -t approve",
            "go test ./... -run approve",
            "mvn test -Dtest=approve",
            "cd src && python3 -m pytest -k approve",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command, "implementer"))

    def test_approve_stays_denied_with_a_cli_reference_or_wrapper(self):
        commands = [
            "npm test -- approve .harness/bin/harness",
            "$RUNNER test approve",
            "script -q /dev/null pytest -k approve",
            "env X=1 harness approve alpha",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(self.bash(command, "implementer"))

    def test_generated_paths_are_writable_by_the_implementer_through_bash(self):
        commands = [
            "rm -rf .pytest_cache",
            "rm -rf __pycache__",
            "rm -rf dist build",
            "mkdir -p dist && echo x > dist/out.txt",
            "rm -rf src/.pytest_cache",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command, "implementer"))

    def test_generated_paths_stay_denied_for_other_roles(self):
        for agent in ("leader", "reviewer", "general-purpose"):
            with self.subTest(agent=agent):
                self.assert_blocked(self.bash("rm -rf dist", agent))

    def test_generated_paths_do_not_widen_file_tools(self):
        self.assert_blocked(self.write_call("dist/out.txt", "implementer"))

    def test_generated_paths_never_reach_reserved_folders(self):
        self.assert_blocked(self.bash("rm -rf dist/.git/config", "implementer"))
        self.assert_blocked(self.bash("rm -rf dist/../.harness", "implementer"))

    def test_declaring_a_reserved_path_fails_closed(self):
        for declared in (".harness", ".Harness/x", ".CLAUDE", ".GIT", "dist/../.harness", "/etc", "a/.git"):
            with self.subTest(declared=declared):
                config = self.read_json(CONFIG)
                config["generated_paths"] = [declared]
                self.write(CONFIG, json.dumps(config))
                self.assertEqual(self.bash("rm -rf .harness/rules.json", "implementer").returncode, 2)
                self.assert_check_fails("is not allowed")


class DocumentationTests(unittest.TestCase):
    STALE = re.compile(r"^(specs|progress|docs|tests|ontology)/|^(init\.sh|AGENTS\.md|CHECKPOINTS\.md)$")
    BARE_STATE = re.compile(r"(?<![/\w.])(feature_list|techdebt_list)\.json")

    def agent_docs(self, root):
        paths = [root / ".harness/AGENTS.md", root / ".harness/CHECKPOINTS.md", root / ".claude/CLAUDE.md"]
        paths += sorted((root / ".harness/docs").rglob("*.md"))
        paths += sorted((root / ".claude/agents").glob("*.md"))
        paths += sorted((root / ".claude/skills").rglob("*.md"))
        return paths

    def current_text(self, path):
        text = path.read_text(encoding="utf-8")
        return text.split("## History", 1)[0]

    def test_backticked_paths_exist_in_a_generated_project(self):
        root = Path(_template) / "app"
        problems = []
        for path in self.agent_docs(root):
            for token in re.findall(r"`([^`\s]+)`", self.current_text(path)):
                if self.STALE.search(token):
                    problems.append(f"{path.name}: stale path {token}")
                elif token.startswith((".harness/", ".claude/")):
                    cut = re.split(r"[<*{]", token, maxsplit=1)
                    existing = cut[0] if len(cut) == 1 else cut[0].rsplit("/", 1)[0]
                    if not (root / existing).exists():
                        problems.append(f"{path.name}: {token} does not exist")
        self.assertEqual(problems, [])

    def test_state_files_are_never_named_without_their_folder(self):
        root = Path(_template) / "app"
        problems = [f"{path.name}: {match.group(0)}" for path in self.agent_docs(root)
                    for match in self.BARE_STATE.finditer(self.current_text(path))]
        self.assertEqual(problems, [])

    def test_the_scan_catches_a_stale_path(self):
        self.assertTrue(self.STALE.search("docs/specs.md"))
        self.assertTrue(self.STALE.search("specs/<name>/tasks.md"))
        self.assertTrue(self.BARE_STATE.search("into feature_list.json now"))
        self.assertFalse(self.BARE_STATE.search(".harness/state/feature_list.json"))

    def test_stack_guides_are_not_promised_in_the_scaffold(self):
        self.assertFalse((SOURCE / ".harness/docs/stack").exists())
        self.assertIn("does not exist in the scaffold", (SOURCE / ".harness/AGENTS.md").read_text())


class InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="harness-init-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_init(self, *args, cli=CLI, env=None, cwd=None):
        return subprocess.run([sys.executable, str(cli), *args], capture_output=True, text=True,
                              env=env, cwd=str(cwd or self.tmp), stdin=subprocess.DEVNULL)

    def fake_source(self):
        source = self.tmp / "source"
        source.mkdir()
        shutil.copytree(SOURCE / ".harness", source / ".harness", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(SOURCE / ".claude", source / ".claude")
        shutil.copy2(SOURCE / ".gitignore", source / ".gitignore")
        return source

    def add_stack(self, source, name, stack):
        folder = source / ".harness/stacks" / name
        folder.mkdir()
        (folder / "stack.json").write_text(json.dumps(stack))
        (folder / "conventions.md").write_text("c\n")
        (folder / "testing.md").write_text("t\n")

    def test_refuses_non_empty_src_without_writing(self):
        target = self.tmp / "app"
        (target / "src").mkdir(parents=True)
        (target / "src/main.py").write_text("x")
        result = self.run_init("init", "python", str(target))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not empty", result.stderr)
        self.assertFalse((target / ".harness").exists())

    def test_refuses_an_initialized_project(self):
        target = self.tmp / "app"
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)
        result = self.run_init("init", "python", str(target))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already initialized", result.stderr)

    def test_refuses_existing_claude_configuration(self):
        target = self.tmp / "app"
        (target / ".claude").mkdir(parents=True)
        (target / ".claude/settings.json").write_text("{}")
        result = self.run_init("init", "python", str(target))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((target / ".claude/settings.json").read_text(), "{}")

    def test_fails_before_writing_when_tools_are_missing(self):
        target = self.tmp / "app"
        empty = self.tmp / "emptybin"
        empty.mkdir()
        result = self.run_init("init", "go", str(target), env={"PATH": str(empty)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not installed", result.stderr)
        self.assertFalse(target.exists())

    def test_rejects_unknown_stack(self):
        result = self.run_init("init", "cobol", str(self.tmp / "app"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("available:", result.stderr)

    def test_failed_scaffold_leaves_the_target_untouched(self):
        source = self.fake_source()
        self.add_stack(source, "broken", {"requires": [], "commands": {"test": "true"},
                                          "scaffold": [{"run": ["false"], "cwd": "stage"}]})
        target = self.tmp / "existing"
        target.mkdir()
        (target / "keep.txt").write_text("x")
        result = self.run_init("init", "broken", str(target), cli=source / ".harness/bin/harness")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["keep.txt"])

    def test_failed_scaffold_removes_a_created_target(self):
        source = self.fake_source()
        self.add_stack(source, "broken", {"requires": [], "commands": {"test": "true"},
                                          "scaffold": [{"run": ["false"], "cwd": "stage"}]})
        target = self.tmp / "new"
        self.assertNotEqual(self.run_init("init", "broken", str(target),
                                          cli=source / ".harness/bin/harness").returncode, 0)
        self.assertFalse(target.exists())

    def test_a_new_stack_needs_no_code_change(self):
        source = self.fake_source()
        self.add_stack(source, "custom", {"description": "Custom", "requires": [],
                                          "commands": {"test": "true"}, "gitignore": ["src/out/"]})
        cli = source / ".harness/bin/harness"
        self.assertIn("custom", self.run_init("stacks", cli=cli).stdout)
        target = self.tmp / "app"
        result = self.run_init("init", "custom", str(target), cli=cli)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("src/out/", (target / ".gitignore").read_text())

    def test_project_contents(self):
        target = self.tmp / "My App"
        result = self.run_init("init", "python", str(target))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads((target / CONFIG).read_text())
        self.assertEqual((config["project"], config["stack"], config["app_dir"]), ("my-app", "python", "src"))
        self.assertTrue(config["commands"]["test"])
        features = json.loads((target / FEATURES).read_text())
        self.assertEqual((features["project"], features["features"]), ("my-app", []))
        self.assertFalse((target / ".harness/tests").exists())
        self.assertEqual([p.name for p in (target / ".harness/stacks").iterdir()], ["python"])
        self.assertTrue((target / ".harness/docs/stack/testing.md").is_file())
        self.assertTrue((target / ".git").is_dir())
        log = subprocess.run(["git", "log"], cwd=str(target), capture_output=True, text=True)
        self.assertNotEqual(log.returncode, 0, "init must not commit")
        leftovers = subprocess.run(["grep", "-rlE", "n8n|\\{\\{", str(target / ".harness/state"),
                                   str(target / ".harness/config.json"), str(target / "README.md")],
                                   capture_output=True, text=True)
        self.assertEqual(leftovers.stdout, "")

    def test_no_scaffold_installs_only_the_harness(self):
        target = self.tmp / "app"
        result = self.run_init("init", "python", str(target), "--no-scaffold")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([p.name for p in (target / "src").iterdir()], [".gitkeep"])

    def test_generic_reports_that_commands_must_be_configured(self):
        target = self.tmp / "app"
        result = self.run_init("init", "generic", str(target))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("commands.test", result.stdout)
        self.assertIn("initialized, but check failed", result.stdout)
        check = self.run_init("check", cli=target / ".harness/bin/harness", cwd=target)
        self.assertNotEqual(check.returncode, 0)

    def test_init_in_place_in_a_scaffold_clone(self):
        clone = self.fake_source()
        (clone / "src").mkdir()
        (clone / "src/.gitkeep").touch()
        cli = clone / ".harness/bin/harness"
        result = self.run_init("init", "python", ".", "--name", "inplace", cli=cli, cwd=clone)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads((clone / CONFIG).read_text())["stack"], "python")
        self.assertTrue((clone / "src/pyproject.toml").is_file())
        self.assertFalse((clone / "src/.gitkeep").exists())

    def test_scaffold_clone_check_says_it_is_not_initialized(self):
        result = self.run_init("check", cwd=SOURCE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not initialized", result.stdout)

    def fake_git(self, script):
        folder = self.tmp / "fakebin"
        folder.mkdir()
        (folder / "git").write_text(f"#!/bin/sh\n{script}\n")
        (folder / "git").chmod(0o755)
        return {**os.environ, "PATH": f"{folder}{os.pathsep}/bin{os.pathsep}/usr/bin"}

    def test_git_is_required_before_any_write(self):
        target = self.tmp / "app"
        empty = self.tmp / "emptybin"
        empty.mkdir()
        result = self.run_init("init", "generic", str(target), env={"PATH": str(empty)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not installed: git", result.stderr)
        self.assertFalse(target.exists())

    def test_git_failure_rolls_back_without_traceback_and_allows_retry(self):
        target = self.tmp / "app"
        result = self.run_init("init", "python", str(target), env=self.fake_git("exit 1"))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)

    def test_failure_in_an_existing_target_removes_only_this_run(self):
        target = self.tmp / "app"
        target.mkdir()
        (target / "keep.txt").write_text("x")
        (target / ".gitignore").write_text("mine\n")
        result = self.run_init("init", "python", str(target), env=self.fake_git("exit 1"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sorted(p.name for p in target.iterdir()), [".gitignore", "keep.txt"])
        self.assertEqual((target / ".gitignore").read_text(), "mine\n")

    def test_failure_after_copy_keeps_the_project_uninitialized(self):
        source = self.fake_source()
        (source / ".harness/templates/config.json").unlink()
        target = self.tmp / "app"
        result = self.run_init("init", "python", str(target), cli=source / ".harness/bin/harness")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(target.exists())

    def test_in_place_failure_restores_the_clone(self):
        clone = self.fake_source()
        (clone / "src").mkdir()
        (clone / "src/.gitkeep").touch()
        (clone / "README.md").write_text("<!-- harness-scaffold-readme -->\nshipped\n")
        state = (clone / FEATURES).read_text()
        (clone / ".harness/templates/config.json").unlink()
        result = self.run_init("init", "python", ".", cli=clone / ".harness/bin/harness", cwd=clone)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(json.loads((clone / CONFIG).read_text())["stack"])
        self.assertEqual((clone / FEATURES).read_text(), state)
        self.assertIn("shipped", (clone / "README.md").read_text())
        self.assertEqual([p.name for p in (clone / "src").iterdir()], [".gitkeep"])

    def test_scaffold_command_that_cannot_start_has_no_traceback(self):
        source = self.fake_source()
        self.add_stack(source, "broken", {"requires": [], "commands": {"test": "true"},
                                          "scaffold": [{"run": ["/no/such/tool"], "cwd": "stage"}]})
        target = self.tmp / "app"
        result = self.run_init("init", "broken", str(target), cli=source / ".harness/bin/harness")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("scaffold step could not start: /no/such/tool", result.stderr)
        self.assertFalse(target.exists())

    def test_failed_post_init_check_has_a_distinct_exit_code(self):
        source = self.fake_source()
        self.add_stack(source, "red", {"requires": [], "commands": {"test": "false"}})
        target = self.tmp / "app"
        cli = source / ".harness/bin/harness"
        result = self.run_init("init", "red", str(target), cli=cli)
        self.assertEqual(result.returncode, 3)
        self.assertIn("initialized, but check failed", result.stdout)
        self.assertEqual(json.loads((target / CONFIG).read_text())["stack"], "red")
        self.assertIn("already initialized", self.run_init("init", "red", str(target), cli=cli).stderr)

    def test_non_object_config_is_a_clean_error(self):
        target = self.tmp / "app"
        (target / ".harness").mkdir(parents=True)
        (target / CONFIG).write_text("[]")
        result = self.run_init("init", "python", str(target))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("must be a JSON object", result.stderr)

    def test_target_that_is_a_file_is_refused(self):
        target = self.tmp / "file.txt"
        target.write_text("x")
        result = self.run_init("init", "python", str(target))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("is not a directory", result.stderr)
        self.assertEqual(target.read_text(), "x")

    def test_target_below_a_file_is_refused(self):
        (self.tmp / "file.txt").write_text("x")
        result = self.run_init("init", "python", str(self.tmp / "file.txt/app"))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("is not a directory", result.stderr)

    def test_created_parent_directories_are_cleaned_up(self):
        target = self.tmp / "a/b/app"
        result = self.run_init("init", "python", str(target), env=self.fake_git("exit 1"))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.tmp / "a").exists())

    def test_existing_readme_is_kept_in_a_new_target(self):
        target = self.tmp / "app"
        target.mkdir()
        (target / "README.md").write_text("mine\n")
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)
        self.assertEqual((target / "README.md").read_text(), "mine\n")

    def test_in_place_keeps_a_user_readme(self):
        clone = self.fake_source()
        (clone / "src").mkdir()
        (clone / "README.md").write_text("mine\n")
        result = self.run_init("init", "python", ".", cli=clone / ".harness/bin/harness", cwd=clone)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((clone / "README.md").read_text(), "mine\n")

    def test_in_place_replaces_the_marked_scaffold_readme(self):
        clone = self.fake_source()
        (clone / "src").mkdir()
        shutil.copy2(SOURCE / "README.md", clone / "README.md")
        result = self.run_init("init", "python", ".", "--name", "demo", cli=clone / ".harness/bin/harness", cwd=clone)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((clone / "README.md").read_text().startswith("# demo"))

    def test_in_place_replaces_a_byte_identical_unmarked_readme(self):
        source = self.fake_source()
        (source / "README.md").write_text("shipped without a marker\n")
        clone = self.tmp / "clone"
        shutil.copytree(source, clone)
        (clone / "src").mkdir()
        result = self.run_init("init", "python", str(clone), "--name", "demo",
                               cli=source / ".harness/bin/harness")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((clone / "README.md").read_text().startswith("# demo"))

    def test_existing_stage_named_folder_survives_success_and_failure(self):
        target = self.tmp / "app"
        (target / ".harness-init-stage").mkdir(parents=True)
        (target / ".harness-init-stage/keep.txt").write_text("mine")
        failed = self.run_init("init", "python", str(target), env=self.fake_git("exit 1"))
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual((target / ".harness-init-stage/keep.txt").read_text(), "mine")
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)
        self.assertEqual((target / ".harness-init-stage/keep.txt").read_text(), "mine")

    def test_no_staging_folder_is_left_behind(self):
        target = self.tmp / "app"
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)
        self.assertEqual([p.name for p in target.iterdir() if p.name.startswith(".harness-init")], [])

    def interrupting_stack(self, signal_name):
        source = self.fake_source()
        script = f"kill -{signal_name} $PPID; sleep 5"
        self.add_stack(source, "die", {"requires": [], "commands": {"test": "true"},
                                       "scaffold": [{"run": ["sh", "-c", script], "cwd": "stage"}]})
        self.add_stack(source, "good", {"requires": [], "commands": {"test": "true"}})
        return source / ".harness/bin/harness"

    def test_sigterm_and_sighup_roll_back(self):
        for signal_name in ("TERM", "HUP"):
            with self.subTest(signal=signal_name):
                cli = self.interrupting_stack(signal_name)
                target = self.tmp / "keep"
                target.mkdir()
                (target / "mine.txt").write_text("x")
                result = self.run_init("init", "die", str(target), cli=cli)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("interrupted", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual([p.name for p in target.iterdir()], ["mine.txt"])
                shutil.rmtree(target)
                shutil.rmtree(self.tmp / "source")

    def test_sigkill_leaves_a_manifest_that_the_next_run_rolls_back(self):
        cli = self.interrupting_stack("KILL")
        target = self.tmp / "keep"
        target.mkdir()
        (target / "mine.txt").write_text("x")
        killed = self.run_init("init", "die", str(target), cli=cli)
        self.assertEqual(killed.returncode, -signal.SIGKILL)
        self.assertTrue((target / ".harness-init-manifest.json").is_file())
        leftovers = [p for p in target.iterdir() if p.name.startswith(".harness-init-") and p.is_dir()]
        self.assertEqual(len(leftovers), 1)
        result = self.run_init("init", "good", str(target), cli=cli)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("interrupted init", result.stdout)
        self.assertFalse(leftovers[0].exists())
        self.assertFalse((target / ".harness-init-manifest.json").exists())
        self.assertEqual((target / "mine.txt").read_text(), "x")

    def test_recovery_removes_only_listed_paths(self):
        target = self.tmp / "app"
        (target / "made").mkdir(parents=True)
        (target / "made/listed.txt").write_text("x")
        (target / "made/unlisted.txt").write_text("mine")
        (target / "other.txt").write_text("mine")
        manifest = {"entries": [{"path": str((target / "made").resolve()), "kind": "dir"},
                                {"path": str((target / "made/listed.txt").resolve()), "kind": "file"}]}
        (target / ".harness-init-manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)
        self.assertFalse((target / "made/listed.txt").exists())
        self.assertEqual((target / "made/unlisted.txt").read_text(), "mine")
        self.assertEqual((target / "other.txt").read_text(), "mine")

    def test_recovery_restores_saved_files(self):
        target = self.tmp / "app"
        target.mkdir()
        (target / ".gitignore").write_text("changed by the dead run\n")
        data = base64.b64encode(b"original\n").decode()
        manifest = {"entries": [{"path": str((target / ".gitignore").resolve()), "kind": "saved", "data": data}]}
        (target / ".harness-init-manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)
        self.assertTrue((target / ".gitignore").read_text().startswith("original\n"))

    def test_manifest_pointing_outside_the_target_is_refused(self):
        target = self.tmp / "app"
        target.mkdir()
        victim = self.tmp / "victim.txt"
        victim.write_text("mine")
        manifest = {"entries": [{"path": str(victim.resolve()), "kind": "file"}]}
        (target / ".harness-init-manifest.json").write_text(json.dumps(manifest))
        result = self.run_init("init", "python", str(target))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(victim.read_text(), "mine")

    def test_invalid_manifest_is_a_clean_error(self):
        target = self.tmp / "app"
        target.mkdir()
        (target / ".harness-init-manifest.json").write_text("[]")
        result = self.run_init("init", "python", str(target))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_manifest_after_the_commit_point_keeps_the_project(self):
        target = self.tmp / "app"
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)
        manifest = {"entries": [{"path": str((target / ".harness/rules.json").resolve()), "kind": "file"}]}
        (target / ".harness-init-manifest.json").write_text(json.dumps(manifest))
        result = self.run_init("init", "python", str(target))
        self.assertIn("already initialized", result.stderr)
        self.assertTrue((target / ".harness/rules.json").is_file())
        self.assertFalse((target / ".harness-init-manifest.json").exists())

    def test_stack_declaring_a_reserved_generated_path_is_refused(self):
        source = self.fake_source()
        self.add_stack(source, "bad", {"requires": [], "commands": {"test": "true"}, "generated": [".Claude"]})
        target = self.tmp / "app"
        result = self.run_init("init", "bad", str(target), cli=source / ".harness/bin/harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not allowed", result.stderr)
        self.assertFalse(target.exists())

    def test_stack_generated_paths_reach_the_config(self):
        target = self.tmp / "app"
        self.assertEqual(self.run_init("init", "python", str(target)).returncode, 0)
        self.assertIn(".pytest_cache", json.loads((target / CONFIG).read_text())["generated_paths"])

    def test_post_init_check_crash_keeps_the_distinct_exit_code(self):
        source = self.fake_source()
        self.add_stack(source, "noisy", {"requires": [], "commands": {"test": "printf '\\377'; exit 1"}})
        target = self.tmp / "app"
        result = self.run_init("init", "noisy", str(target), cli=source / ".harness/bin/harness")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_post_init_check_os_error_keeps_the_distinct_exit_code(self):
        source = self.fake_source()
        template = source / ".harness/templates/config.json"
        template.write_text(template.read_text().replace('"app_dir": "src"', '"app_dir": "src/locked"'))
        lock = ["sh", "-c", "mkdir -p src/locked && chmod 600 src/locked"]
        self.add_stack(source, "locked", {"requires": [], "commands": {"test": "true"},
                                          "scaffold": [{"run": lock, "cwd": "stage"}]})
        target = self.tmp / "app"
        self.addCleanup(lambda: (target / "src/locked").exists() and (target / "src/locked").chmod(0o755))
        result = self.run_init("init", "locked", str(target), cli=source / ".harness/bin/harness")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("initialized, but check failed", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_new_files_honour_the_umask(self):
        target = self.tmp / "app"
        command = f"umask 027; exec {shlex.quote(sys.executable)} {shlex.quote(str(CLI))} init python {shlex.quote(str(target))}"
        result = subprocess.run(["sh", "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((target / CONFIG).stat().st_mode & 0o777, 0o640)

    def test_install_symlinks_into_the_bin_dir(self):
        bin_dir = self.tmp / "bin"
        result = self.run_init("install", "--bin-dir", str(bin_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((bin_dir / "harness").resolve(), CLI.resolve())
        target = self.tmp / "app"
        linked = self.run_init("init", "python", str(target), cli=bin_dir / "harness")
        self.assertEqual(linked.returncode, 0, linked.stdout + linked.stderr)

    def test_install_refuses_to_replace_a_real_file(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "harness").write_text("mine")
        self.assertNotEqual(self.run_init("install", "--bin-dir", str(bin_dir)).returncode, 0)
        self.assertEqual((bin_dir / "harness").read_text(), "mine")


if __name__ == "__main__":
    unittest.main()

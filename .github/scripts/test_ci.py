#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# The planning job deliberately uses only the Python standard library.
# ruff: noqa: PT009, PT027
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("ci", Path(__file__).with_name("ci.py"))
assert spec is not None
assert spec.loader is not None
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class PolicyTests(unittest.TestCase):
    """Guard scope selection and failure handling."""

    def test_application_and_server_scopes(self) -> None:
        """Application and server scopes."""
        self.assertEqual(
            ci.scopes(["superset-frontend/src/dashboard/Dashboard.tsx"]), (True, False)
        )
        self.assertEqual(ci.scopes(["superset/dashboards/api.py"]), (False, True))
        self.assertEqual(ci.scopes(["README.md"]), (False, False))
        for path in [
            "requirements/development.txt",
            "pyproject.toml",
            "docs/package.json",
            ".pre-commit-config.yaml",
            "unknown",
        ]:
            self.assertEqual(ci.scopes([path]), (True, True), path)
        self.assertEqual(ci.scopes([]), (True, True))

    def test_unknown_and_runtime_paths_run(self) -> None:
        """Unknown and runtime paths run."""
        self.assertFalse(ci.code_required(["README.md", "CI.md"]))
        for path in [
            "docs/query.json",
            "scripts/check-type.js",
            "pyproject.toml",
            ".github/workflows/pr-ci.yml",
            "superset/config.py",
            "new-file",
            "README.md\nconfig.py",
        ]:
            self.assertTrue(ci.code_required([path]), path)
        self.assertTrue(ci.code_required([]))

    def test_gate_rejects_failure_cancellation_and_unexpected_skips(self) -> None:
        """Gate rejects failure cancellation and unexpected skips."""
        self.assertTrue(ci.gate("success", "true", "success"))
        self.assertTrue(ci.gate("success", "false", "skipped"))
        for state in ["failure", "cancelled", "skipped", ""]:
            self.assertFalse(ci.gate(state, "true", "success"))
            self.assertFalse(ci.gate("success", "true", state))
        self.assertFalse(ci.gate("success", "false", "failure"))
        self.assertFalse(ci.gate("success", "", "skipped"))

    def test_real_diff_includes_both_sides_of_rename_and_invalid_base_fails(
        self,
    ) -> None:
        """Real diff includes both sides of rename and invalid base fails."""
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            try:
                os.chdir(directory)

                def git(*args: str) -> str:
                    """Run fixture Git commands."""
                    return (
                        subprocess.check_output(  # noqa: S603 -- fixed fixture commands, no shell
                            ["git", *args],  # noqa: S607 -- Git from runner PATH
                            stderr=subprocess.DEVNULL,
                        )
                        .decode()
                        .strip()
                    )

                git("init")
                git("config", "user.name", "CI fixture")
                git("config", "user.email", "ci@example.invalid")
                Path("code with space.py").write_text("value = 1\n")
                git("add", ".")
                git("commit", "-m", "fixture")
                base = git("rev-parse", "HEAD")
                git("mv", "code with space.py", "README.md")
                git("commit", "-m", "move")
                with patch.dict(os.environ, {"CI_BASE_SHA": base}):
                    self.assertEqual(
                        set(ci.changed()), {"code with space.py", "README.md"}
                    )
                    self.assertTrue(ci.code_required(ci.changed()))
                with patch.dict(os.environ, {"CI_BASE_SHA": "missing-ref"}):
                    with self.assertRaises(subprocess.CalledProcessError):
                        ci.changed()
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()

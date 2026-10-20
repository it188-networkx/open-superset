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
"""Conservative PR scope and fail-closed aggregate gate."""

import os
import subprocess
import sys


def git(*args: str) -> bytes:
    """Run a Git query without shell interpolation."""
    return subprocess.check_output(["git", *args])  # noqa: S603, S607 -- fixed Git executable, no shell


def changed() -> list[str]:
    """Return both sides of renames relative to the PR merge base."""
    base = os.environ.get("CI_BASE_SHA")
    if not base and os.environ.get("ACT") == "true":
        base = "origin/main"
    if not base:
        raise ValueError("CI_BASE_SHA is required")
    base = git("merge-base", base, "HEAD").decode().strip()
    # No renames exposes both sides of moves; NUL handles spaces and newlines.
    return [
        p.decode()
        for p in git("diff", "--name-only", "--no-renames", "-z", base, "HEAD").split(
            b"\0"
        )
        if p
    ]


def code_required(files: list[str]) -> bool:
    """Only skip checks for known root documentation."""
    # Only known non-runtime documentation may skip expensive checks.
    return not files or any(p not in {"README.md", "AGENTS.md", "CI.md"} for p in files)


def scopes(files: list[str]) -> tuple[bool, bool]:
    """Select frontend and backend checks, defaulting unknown paths to both."""
    app = server = not files
    for path in files:
        if path in {"README.md", "AGENTS.md", "CI.md"}:
            continue
        if path.startswith(("superset-frontend/",)):
            app = True
        elif path.startswith(
            ("superset/", "superset-core/", "superset-extensions-cli/", "tests/")
        ):
            server = True
        else:
            # Shared code, plugins, dependencies and unknown paths affect both.
            app = server = True
    return app, server


def gate(plan: str, run: str, validation: str) -> bool:
    """Reject failed plans, incomplete checks, and unexpected skips."""
    return plan == "success" and (
        (run == "true" and validation == "success")
        or (run == "false" and validation == "skipped")
    )


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "plan":
        files = [] if os.environ.get("ACT") == "true" else changed()
        app, server = scopes(files)
        run = app or server
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for name, value in [("run", run), ("app", app), ("server", server)]:
                output.write(name + "=" + str(value).lower() + "\n")
        print("Run code checks:", run)
    elif command == "gate":
        if not gate(
            os.environ["PLAN_RESULT"],
            os.environ["PLAN_RUN"],
            os.environ["VALIDATION_RESULT"],
        ):
            raise SystemExit("Required PR checks failed or did not complete")
    else:
        raise SystemExit("Unknown command: " + command)

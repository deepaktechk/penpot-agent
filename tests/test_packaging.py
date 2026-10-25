"""Packaging guard: every source file must be visible to git.

A broad `.gitignore` rule once hid the `src/pbridge/build/` package (rule `build/` matched it), so
it was never committed: the local checkout worked, CI and installed wheels failed with
`No module named 'pbridge.build'`. This test fails when any source file is ignored by git.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATTERNS = ("src/**/*.py", "src/pbridge/bundles/*.js", "js/src/**/*.ts", "skills/**/*.md", "docs/*.md")


@unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "needs a git checkout")
class PackagingTest(unittest.TestCase):
    def test_no_source_file_is_git_ignored(self) -> None:
        sources = sorted({str(path.relative_to(ROOT)) for pattern in SOURCE_PATTERNS for path in ROOT.glob(pattern)
                          if "__pycache__" not in path.parts})
        self.assertTrue(sources, "no source files found")
        # check-ignore prints the ignored ones; exit code 1 means none is ignored
        result = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT, input="\n".join(sources),
                                capture_output=True, text=True)
        ignored = result.stdout.split()
        self.assertEqual(ignored, [], "these source files are hidden by .gitignore:\n  " + "\n  ".join(ignored))


if __name__ == "__main__":
    unittest.main()

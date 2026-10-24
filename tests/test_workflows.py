"""The weekly collect job must leave the site showing the new data."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
WF = (ROOT / ".github" / "workflows" / "collect.yml").read_text(encoding="utf-8")


def test_collect_requests_a_pages_build_after_pushing():
    # Pages builds docs/ from the main branch, and a push made with the Actions token
    # starts no Pages build, so the job must ask for one or the site keeps old data.
    assert re.search(r"permissions:\s*\n\s+contents: write\s*\n\s+pages: write", WF)
    push = WF.index("git push")
    build = WF.index("pages/builds")
    assert push < build
    step = WF[WF.rindex("- name:", 0, build):build]
    assert "if: steps.commit.outputs.changed == 'true'" in step and "GH_TOKEN: ${{ github.token }}" in step
    assert 'echo "changed=true" >> "$GITHUB_OUTPUT"' in WF and 'echo "changed=false" >> "$GITHUB_OUTPUT"' in WF


def test_collect_commits_both_data_and_the_pages_copy():
    assert "python web/build_pages.py" in WF and "git add data docs" in WF

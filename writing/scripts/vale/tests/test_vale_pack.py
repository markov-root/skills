#!/usr/bin/env python3
"""Fixture tests for the Vale style pack + wrapper (stdlib-only, offline).

Two groups:

1. Always-run logic tests (no Vale binary required): protective-span
   detection for blockquotes and inline quotes, quote-masking of synthetic
   findings (quoted MUST be dropped, unquoted MUST survive), contract grouping,
   graceful missing-binary reporting, and YAML pack shape.

2. Integration tests that exercise the real Vale binary across the fixtures.
   These run only when a `vale` binary is actually installed; otherwise they
   skip and report the binary as an unmet prerequisite (we never fake results).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# syth adjusts for import of the wrapper adjacent to this file.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import wrapper

FIX = os.path.join(ROOT, "fixtures")


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Always-run logic tests
# ---------------------------------------------------------------------------


class SpanAndMaskTests(unittest.TestCase):
    def test_inline_quotes_are_protected_and_unquoted_are_not(self):
        text = _fixture("fixture-inline-quote.md")
        spans = wrapper.merged_protected_spans(text)
        import re

        for phrase in ("worth noting", "testament"):
            matches = list(re.compile(re.escape(phrase), re.IGNORECASE).finditer(text))
            quoted = [m for m in matches if wrapper.is_protected(
                (m.start(), m.end()), spans)]
            unquoted = [m for m in matches if not wrapper.is_protected(
                (m.start(), m.end()), spans)]
            self.assertEqual(len(quoted), 1, phrase)   # inside "..." only
            self.assertGreaterEqual(len(unquoted), 1, phrase)  # outside stays

    def test_blockquote_span_detection(self):
        text = _fixture("fixture-blockquote.md")
        spans = wrapper.merged_protected_spans(text)
        lines = text.split("\n")
        for ln, line in enumerate(lines, 1):
            if not line.lstrip().startswith(">"):
                continue
            col = line.find(">")
            start = sum(len(x) + 1 for x in lines[: ln - 1]) + col + 2
            content = line[col + 1 :]
            seg_end = start + len(content)
            self.assertTrue(
                wrapper.is_protected((start, seg_end), spans),
                f"line {ln} should be inside a protected blockquote",
            )
        # an unquoted sentence after the quote must not be protected.
        idx = text.index("this is a testament")
        self.assertFalse(
            wrapper.is_protected((idx, idx + 10), spans),
            "post-blockquote prose must remain unprotected",
        )
        # an unquoted sentence after the quote must not be protected.
        marker = "unquoted text returns"
        idx = text.index("this is a testament")
        self.assertFalse(
            wrapper.is_protected((idx, idx + 10), spans),
            "post-blockquote prose must remain unprotected",
        )

    def test_mask_drops_quoted_and_keeps_unquoted(self):
        text = _fixture("fixture-inline-quote.md")
        # Synthetic Vale findings for every "testament" occurrence.
        alerts = []
        import re

        for m in re.compile(re.escape("testament"), re.IGNORECASE).finditer(text):
            alerts.append({"text": "testament", "level": "warning",
                           "span": {"from": m.start(), "to": m.end()}})
        kept = wrapper.mask_alerts(alerts, text)
        kept_texts = [a["text"] for a in kept]
        self.assertEqual(len(kept), 1)  # only the unquoted one survives

    def test_group_by_contract_never_merges(self):
        alerts = [
            {"level": "error", "text": "x"},
            {"level": "warning", "text": "y"},
        ]
        groups = wrapper.group_by_contract(alerts)
        self.assertEqual(len(groups["integrity"]), 1)
        self.assertEqual(len(groups["review"]), 1)
        self.assertEqual(len(groups["profile"]), 0)

    def test_missing_vale_is_graceful(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "wrapper.py"),
             os.path.join(FIX, "fixture-tier-a.md"),
             "--vale", "/nonexistent/vale"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertIn("not found", proc.stderr.lower())
        self.assertEqual(proc.stdout.strip(), "")

    def test_yaml_pack_shape(self):
        import glob
        styl_dir = os.path.join(ROOT, "writing_pack", "styles", "writing")
        yml = glob.glob(os.path.join(styl_dir, "*.yml"))
        self.assertGreaterEqual(len(yml), 4)
        for path in yml:
            with open(path, encoding="utf-8") as fh:
                head = fh.read()
            self.assertIn("extends:", head)
            self.assertIn("message:", head)


# ---------------------------------------------------------------------------
# Integration tests — only when the Vale binary genuinely exists
# ---------------------------------------------------------------------------


VALE = shutil.which("vale") or os.environ.get("VALE_BIN")


@unittest.skipIf(not VALE, "Vale binary not installed (unmet prerequisite); "
    "integration fixtures not run — no fabricated results.")
class ValeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vale = VALE

    def _screen(self, *names, expect_rc=0):
        files = [os.path.join(FIX, n) for n in names]
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "wrapper.py"), "--json",
             *files],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, expect_rc, proc.stderr)
        return proc

    def _report(self, proc):
        return json.loads(proc.stdout)

    def test_tier_a_unquoted_fires(self):
        report = self._report(self._screen("fixture-tier-a.md"))
        review = report["contracts"]["review"]
        texts = " ".join(a.get("text", "") for a in review).lower()
        self.assertIn("delve", texts)
        self.assertIn("testament", texts)

    def test_inline_quote_masks_findings(self):
        proc = self._screen("fixture-inline-quote.md")
        review = self._report(proc)["contracts"]["review"]
        texts = " ".join(a.get("text", "") for a in review).lower()
        # quoted phrases are masked; only unquoted occurrences survive.
        self.assertEqual(texts.count("worth noting"), 1)
        self.assertEqual(texts.count("testament"), 1)

    def test_blockquote_findings_are_dropped(self):
        proc = self._screen("fixture-blockquote.md")
        review = self._report(proc)["contracts"]["review"]
        texts = " ".join(a.get("text", "") for a in review).lower()
        # quoted/blockquoted occurrences dropped; unquoted survive.
        self.assertEqual(texts.count("delve"), 1)

    def test_integrity_marker_blocks(self):
        # a real [[SOURCE marker blocks: exit 1 and an integrity finding.
        proc = self._screen("fixture-integrity.md", expect_rc=1)
        integrity = self._report(proc)["contracts"]["integrity"]
        self.assertGreaterEqual(len(integrity), 2)

    # -- W1: prose mention must NOT fire integrity --
    def test_prose_source_mention_does_not_fire(self):
        proc = self._screen("fixture-prose-source.md", expect_rc=0)
        integrity = self._report(proc)["contracts"]["integrity"]
        self.assertEqual(len(integrity), 0)

    # -- W2: integrity -> non-zero exit, review-only -> zero --
    def test_integrity_returns_nonzero_exit(self):
        self.assertEqual(self._screen("fixture-integrity.md", expect_rc=1).returncode, 1)

    def test_clean_review_returns_zero(self):
        self.assertEqual(self._screen("fixture-tier-a.md").returncode, 0)

    # -- W3: unquoted prose in a later paragraph must fire --
    def test_later_paragraph_unquoted_prose_fires(self):
        proc = self._screen("fixture-paragraph-quote.md", expect_rc=0)
        review = self._report(proc)["contracts"]["review"]
        texts = " ".join(a.get("text", "") for a in review).lower()
        # unquoted "delve" in paragraph two survives; the paired quote in para
        # three ("delve" inside quotes) is masked.
        self.assertEqual(texts.count("delve"), 1)

    # -- W4: per-file masking across a multi-file run --
    def test_multi_file_per_file_masking(self):
        # paragraph-quote fixture + inline-quote fixture in ONE run; each file is
        # masked against its own text, no merged-offset mis-location.
        proc = self._screen("fixture-paragraph-quote.md",
                            "fixture-inline-quote.md", expect_rc=0)
        report = self._report(proc)
        review = report["contracts"]["review"]
        self.assertEqual(len(report["files"]), 2)
        texts = " ".join(a.get("text", "") for a in review).lower()
        # Each file's unquoted instances survive; the paragraph fixture has the
        # quote-pairing reset (unquoted "delve" in para 2 stays, the paired one
        # in para 3 is masked), and the inline-quote fixture keeps its unquoted
        # "delve"/"worth noting"/"testament" while masking the quoted variants.
        expected_unquoted = {
            "delve": 2,         # para2 of paragraph-quote + inline-quote line7
            "worth noting": 1,  # inline-quote unquoted only
            "testament": 1,     # inline-quote unquoted only
        }
        for phrase, exp in expected_unquoted.items():
            self.assertEqual(texts.count(phrase), exp, phrase)


if __name__ == "__main__":
    unittest.main(verbosity=2)

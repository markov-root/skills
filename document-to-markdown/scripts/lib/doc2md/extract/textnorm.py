"""Shared, versioned text normalization for extracted candidates.

Two distinct operations, deliberately separated (see ``docs/context/quality-model.md`` and
Task 0020's dual-representation requirement):

* :func:`strip_invisibles` is a near-lossless tidy applied to the *stored* Markdown body. It
  deletes truly invisible codepoints (zero-width marks, BOM, soft hyphen, word joiner, bidi
  controls) and folds no-break spaces to ordinary spaces. It never alters visible typography,
  so the stored body stays faithful to the source.
* :func:`normalize_for_search` is the *lossy* projection used only for search/grounding
  comparison, never for the stored body. It additionally applies NFKC, dehyphenation, curly
  quote / dash folding, whitespace collapse, and optional casefolding. Its lossy steps are
  counted so a caller can record them as a versioned :class:`TransformationRecord`.

Both are pure functions of their input string. Bump :data:`TEXTNORM_VERSION` on any change to
the folding tables or the projection recipe.
"""

from __future__ import annotations

import re
import unicodedata

TEXTNORM_VERSION = "1"

# Codepoints deleted outright — they carry no visible content but corrupt tokenization,
# grounding, and diffing. Soft hyphen (U+00AD) is a discretionary line-break hint, not a
# visible hyphen, so it is deleted rather than folded.
_INVISIBLE_DELETE = {
    0x200B,  # ZERO WIDTH SPACE
    0x200C,  # ZERO WIDTH NON-JOINER
    0x200D,  # ZERO WIDTH JOINER
    0x2060,  # WORD JOINER
    0xFEFF,  # BOM / ZERO WIDTH NO-BREAK SPACE
    0x00AD,  # SOFT HYPHEN
    0x200E,  # LEFT-TO-RIGHT MARK
    0x200F,  # RIGHT-TO-LEFT MARK
    0x202A,  # LEFT-TO-RIGHT EMBEDDING
    0x202B,  # RIGHT-TO-LEFT EMBEDDING
    0x202C,  # POP DIRECTIONAL FORMATTING
    0x202D,  # LEFT-TO-RIGHT OVERRIDE
    0x202E,  # RIGHT-TO-LEFT OVERRIDE
    0x2066,  # LEFT-TO-RIGHT ISOLATE
    0x2067,  # RIGHT-TO-LEFT ISOLATE
    0x2068,  # FIRST STRONG ISOLATE
    0x2069,  # POP DIRECTIONAL ISOLATE
}

# No-break / exotic spaces folded to an ordinary space (visible-width preserving).
_SPACE_FOLD = {
    0x00A0: " ",  # NO-BREAK SPACE
    0x2007: " ",  # FIGURE SPACE
    0x202F: " ",  # NARROW NO-BREAK SPACE
    0x2009: " ",  # THIN SPACE
}

_STRIP_TABLE: dict[int, str | None] = {cp: None for cp in _INVISIBLE_DELETE}
_STRIP_TABLE.update(_SPACE_FOLD)

# Visible typography folded only in the search projection.
_TYPOGRAPHY_FOLD = {
    0x2018: "'",
    0x2019: "'",
    0x201A: "'",
    0x201B: "'",
    0x2032: "'",
    0x201C: '"',
    0x201D: '"',
    0x201E: '"',
    0x201F: '"',
    0x2033: '"',
    0x2013: "-",
    0x2014: "-",
    0x2015: "-",
    0x2212: "-",
}

_SEARCH_TABLE: dict[int, str | None] = dict(_STRIP_TABLE)
_SEARCH_TABLE.update(_TYPOGRAPHY_FOLD)

# A word-wrap hyphen: a letter, a hyphen, an end-of-line, then a lowercase continuation.
# Joining these repairs "exam-\nple" -> "example" without touching real compound hyphens.
_WRAP_HYPHEN = re.compile(r"([A-Za-z])-\n([a-z])")
_WHITESPACE_RUN = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def strip_invisibles(text: str) -> str:
    """Delete invisible codepoints and fold no-break spaces; preserve visible typography."""

    return text.translate(_STRIP_TABLE)


def dehyphenate(text: str) -> tuple[str, int]:
    """Join line-wrap hyphenations. Return the repaired text and the number of joins made.

    This is the one lossy normalization step: a genuine end-of-line hyphen that belonged in
    the word is indistinguishable from a soft line-wrap hyphen, so the join count is recorded
    as evidence rather than hidden.
    """

    count = 0

    def _join(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return match.group(1) + match.group(2)

    return _WRAP_HYPHEN.sub(_join, text), count


def collapse_blank_lines(text: str) -> str:
    """Collapse three-or-more consecutive newlines to a paragraph break (near-lossless)."""

    return _BLANK_LINES.sub("\n\n", text)


def normalize_for_search(text: str, *, casefold: bool = True) -> tuple[str, int]:
    """Project text to a lossy search/grounding form. Return the form and the dehyphenation count.

    Recipe: NFKC -> dehyphenate -> fold typography and invisibles -> collapse whitespace ->
    optional casefold. Never store the result as the document body; it exists only to compare
    two texts on equal footing.
    """

    normalized = unicodedata.normalize("NFKC", text)
    normalized, joins = dehyphenate(normalized)
    normalized = normalized.translate(_SEARCH_TABLE)
    normalized = _WHITESPACE_RUN.sub(" ", normalized)
    normalized = _BLANK_LINES.sub("\n\n", normalized).strip()
    if casefold:
        normalized = normalized.casefold()
    return normalized, joins

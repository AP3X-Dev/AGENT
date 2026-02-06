"""Cascading fuzzy string replacement engine for code editing.

Replaces the simple exact-match ``perform_string_replacement()`` with a
multi-strategy cascade that tries increasingly tolerant matching techniques.
Strategies are attempted in order; the first one that yields a match wins.

Strategy cascade
----------------
1. **ExactReplacer** -- literal ``str.count`` / ``str.replace``.
2. **LineTrimmedReplacer** -- strip leading/trailing whitespace per line
   before comparing, then replace the original lines.
3. **WhitespaceNormalizedReplacer** -- collapse all runs of whitespace to
   single spaces for matching, then map hits back to original positions.
4. **IndentationFlexibleReplacer** -- dedent ``old_string``, find a content
   block with the same structure but potentially different indentation.
5. **BlockAnchorReplacer** -- first and last lines must match exactly (after
   trim); middle lines use Levenshtein-style similarity > 0.8 via
   ``difflib.SequenceMatcher``.
6. **ContextAwareReplacer** -- first/last 2 lines are exact-trim anchors;
   only 50 % of middle lines need to match.  Falls back to
   ``BlockAnchorReplacer`` for short old_strings (< 5 lines).

Only stdlib dependencies are used: ``difflib``, ``re``, ``textwrap``,
``logging``.
"""

from __future__ import annotations

import difflib
import logging
import re
import textwrap
from abc import ABC, abstractmethod

logger = logging.getLogger("ag3nt.fuzzy_edit")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _similarity(a: str, b: str) -> float:
    """Return a similarity ratio in [0, 1] using SequenceMatcher."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def _splitlines_keep(text: str) -> list[str]:
    """Split *text* into lines **without** stripping the trailing newline.

    Unlike ``str.splitlines()`` this preserves the fact that the text may or
    may not end with a newline so that round-tripping through join/split is
    stable.
    """
    lines = text.split("\n")
    # If the text ends with a newline the last element is the empty string
    # after that newline.  We keep it so that ``"\\n".join(lines)`` reproduces
    # the original string exactly.
    return lines


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class _Replacer(ABC):
    """Abstract base for a replacement strategy."""

    name: str

    @abstractmethod
    def find(self, content: str, old_string: str) -> list[tuple[int, int]]:
        """Return a list of ``(start, end)`` byte-offset pairs in *content*
        where *old_string* matches according to this strategy.

        An empty list means "no match found".
        """

    def apply(
        self,
        content: str,
        old_string: str,
        new_string: str,
        matches: list[tuple[int, int]],
    ) -> str:
        """Produce the new content by replacing every span in *matches*.

        The default implementation replaces spans back-to-front so that
        earlier offsets are not invalidated.
        """
        parts = list(content)  # character list -- simple but correct
        # Work backwards so indices stay valid.
        for start, end in sorted(matches, reverse=True):
            content = content[:start] + new_string + content[end:]
        return content


# ---------------------------------------------------------------------------
# Strategy 1 -- Exact
# ---------------------------------------------------------------------------


class ExactReplacer(_Replacer):
    """Exact substring matching -- the original behaviour."""

    name = "ExactReplacer"

    def find(self, content: str, old_string: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        start = 0
        while True:
            idx = content.find(old_string, start)
            if idx == -1:
                break
            spans.append((idx, idx + len(old_string)))
            start = idx + 1  # allow overlapping? kept minimal: +1
        return spans


# ---------------------------------------------------------------------------
# Strategy 2 -- Line-trimmed
# ---------------------------------------------------------------------------


class LineTrimmedReplacer(_Replacer):
    """Strip leading/trailing whitespace from each line for comparison,
    then replace the *original* (un-stripped) lines in the content.
    """

    name = "LineTrimmedReplacer"

    def find(self, content: str, old_string: str) -> list[tuple[int, int]]:
        content_lines = _splitlines_keep(content)
        old_lines = _splitlines_keep(old_string)

        # Avoid degenerate single-empty-line matches.
        if all(l.strip() == "" for l in old_lines):
            return []

        trimmed_old = [l.strip() for l in old_lines]
        trimmed_content = [l.strip() for l in content_lines]

        spans: list[tuple[int, int]] = []
        window = len(trimmed_old)

        for i in range(len(trimmed_content) - window + 1):
            if trimmed_content[i : i + window] == trimmed_old:
                # Map line indices back to character offsets.
                start_offset = sum(len(content_lines[j]) + 1 for j in range(i))
                end_offset = sum(len(content_lines[j]) + 1 for j in range(i + window))
                # The last line group might overshoot by 1 if the content
                # does not end with a newline.
                # Adjust: the span should cover exactly the original substring
                # that those lines represent when joined with "\n".
                matched_text = "\n".join(content_lines[i : i + window])
                start_offset = content.find(matched_text, max(start_offset - window * 20, 0))
                if start_offset == -1:
                    # Fallback: recalculate by summing lengths.
                    start_offset = sum(len(content_lines[j]) + 1 for j in range(i))
                    end_offset = start_offset + len(matched_text)
                else:
                    end_offset = start_offset + len(matched_text)
                spans.append((start_offset, end_offset))
        return spans


# ---------------------------------------------------------------------------
# Strategy 3 -- Whitespace-normalised
# ---------------------------------------------------------------------------


class WhitespaceNormalizedReplacer(_Replacer):
    """Collapse all runs of whitespace (spaces, tabs) within each line to
    single spaces for matching, then map back to original positions.
    """

    name = "WhitespaceNormalizedReplacer"

    _WS_RE = re.compile(r"[ \t]+")

    def _normalise(self, text: str) -> str:
        """Collapse intra-line whitespace runs to single spaces and strip
        each line.  Newlines are preserved."""
        lines = text.split("\n")
        return "\n".join(self._WS_RE.sub(" ", line).strip() for line in lines)

    def find(self, content: str, old_string: str) -> list[tuple[int, int]]:
        norm_old = self._normalise(old_string)
        if not norm_old.strip():
            return []

        content_lines = content.split("\n")
        norm_content_lines = [self._WS_RE.sub(" ", l).strip() for l in content_lines]
        old_norm_lines = norm_old.split("\n")

        window = len(old_norm_lines)
        spans: list[tuple[int, int]] = []

        for i in range(len(norm_content_lines) - window + 1):
            if norm_content_lines[i : i + window] == old_norm_lines:
                matched_text = "\n".join(content_lines[i : i + window])
                offset = self._find_line_offset(content_lines, i)
                spans.append((offset, offset + len(matched_text)))
        return spans

    @staticmethod
    def _find_line_offset(lines: list[str], line_idx: int) -> int:
        """Return the character offset of the start of ``lines[line_idx]``."""
        offset = 0
        for j in range(line_idx):
            offset += len(lines[j]) + 1  # +1 for the '\n'
        return offset


# ---------------------------------------------------------------------------
# Strategy 4 -- Indentation-flexible
# ---------------------------------------------------------------------------


class IndentationFlexibleReplacer(_Replacer):
    """Dedent *old_string* and find a content block with the same structure
    but potentially different indentation, then replace while preserving
    the target indentation.
    """

    name = "IndentationFlexibleReplacer"

    def find(self, content: str, old_string: str) -> list[tuple[int, int]]:
        dedented = textwrap.dedent(old_string)
        dedented_lines = dedented.split("\n")

        # Skip if dedenting had no effect (identical to exact) or trivially empty.
        if dedented == old_string or all(l.strip() == "" for l in dedented_lines):
            return []

        stripped_old = [l.strip() for l in dedented_lines]
        content_lines = content.split("\n")
        stripped_content = [l.strip() for l in content_lines]

        window = len(stripped_old)
        spans: list[tuple[int, int]] = []

        for i in range(len(stripped_content) - window + 1):
            if stripped_content[i : i + window] == stripped_old:
                matched_text = "\n".join(content_lines[i : i + window])
                offset = self._line_offset(content_lines, i)
                spans.append((offset, offset + len(matched_text)))
        return spans

    def apply(
        self,
        content: str,
        old_string: str,
        new_string: str,
        matches: list[tuple[int, int]],
    ) -> str:
        """Replace while preserving the indentation of the matched block."""
        for start, end in sorted(matches, reverse=True):
            matched = content[start:end]
            first_line = matched.split("\n")[0]
            # Determine indentation of the target.
            target_indent = first_line[: len(first_line) - len(first_line.lstrip())]

            # Determine indentation of old_string's first non-blank line.
            for line in old_string.split("\n"):
                if line.strip():
                    old_indent = line[: len(line) - len(line.lstrip())]
                    break
            else:
                old_indent = ""

            # Determine indentation of new_string's first non-blank line.
            for line in new_string.split("\n"):
                if line.strip():
                    new_indent = line[: len(line) - len(line.lstrip())]
                    break
            else:
                new_indent = ""

            # Re-indent new_string lines relative to the target.
            dedented_new = textwrap.dedent(new_string)
            new_lines = dedented_new.split("\n")
            adjusted: list[str] = []
            for j, nl in enumerate(new_lines):
                if nl.strip() == "":
                    adjusted.append(nl)
                else:
                    adjusted.append(target_indent + nl.lstrip())
            replacement = "\n".join(adjusted)
            content = content[:start] + replacement + content[end:]
        return content

    @staticmethod
    def _line_offset(lines: list[str], idx: int) -> int:
        offset = 0
        for j in range(idx):
            offset += len(lines[j]) + 1
        return offset


# ---------------------------------------------------------------------------
# Strategy 5 -- Block-anchor with fuzzy middle
# ---------------------------------------------------------------------------


class BlockAnchorReplacer(_Replacer):
    """First and last lines of *old_string* must match exactly (after
    stripping).  Middle lines must each have a
    ``SequenceMatcher.ratio() > 0.8`` with their counterpart.
    """

    name = "BlockAnchorReplacer"

    SIMILARITY_THRESHOLD = 0.8

    def find(self, content: str, old_string: str) -> list[tuple[int, int]]:
        old_lines = old_string.split("\n")
        if len(old_lines) < 2:
            return []  # Need at least 2 lines for anchors.

        first_trimmed = old_lines[0].strip()
        last_trimmed = old_lines[-1].strip()

        # Guard against empty anchors.
        if not first_trimmed or not last_trimmed:
            return []

        content_lines = content.split("\n")
        window = len(old_lines)
        spans: list[tuple[int, int]] = []

        for i in range(len(content_lines) - window + 1):
            # Check anchors.
            if content_lines[i].strip() != first_trimmed:
                continue
            if content_lines[i + window - 1].strip() != last_trimmed:
                continue
            # Check middle lines.
            ok = True
            for j in range(1, window - 1):
                sim = _similarity(
                    content_lines[i + j].strip(), old_lines[j].strip()
                )
                if sim < self.SIMILARITY_THRESHOLD:
                    ok = False
                    break
            if ok:
                matched = "\n".join(content_lines[i : i + window])
                offset = _line_offset(content_lines, i)
                spans.append((offset, offset + len(matched)))
        return spans


# ---------------------------------------------------------------------------
# Strategy 6 -- Context-aware
# ---------------------------------------------------------------------------


class ContextAwareReplacer(_Replacer):
    """First and last 2 lines are exact-trim anchors.  Only 50 % of middle
    lines need to match (similarity > 0.8).  For short *old_strings* (< 5
    lines) falls back to ``BlockAnchorReplacer``.
    """

    name = "ContextAwareReplacer"

    ANCHOR_LINES = 2
    MIDDLE_MATCH_RATIO = 0.5
    SIMILARITY_THRESHOLD = 0.8
    MIN_LINES = 5

    def __init__(self) -> None:
        self._block_fallback = BlockAnchorReplacer()

    def find(self, content: str, old_string: str) -> list[tuple[int, int]]:
        old_lines = old_string.split("\n")
        if len(old_lines) < self.MIN_LINES:
            return self._block_fallback.find(content, old_string)

        content_lines = content.split("\n")
        window = len(old_lines)

        head_old = [l.strip() for l in old_lines[: self.ANCHOR_LINES]]
        tail_old = [l.strip() for l in old_lines[-self.ANCHOR_LINES :]]
        middle_old = [l.strip() for l in old_lines[self.ANCHOR_LINES : -self.ANCHOR_LINES]]

        # Guard against empty anchors.
        if any(not l for l in head_old) or any(not l for l in tail_old):
            return []

        spans: list[tuple[int, int]] = []

        for i in range(len(content_lines) - window + 1):
            # Check head anchors.
            head_ok = all(
                content_lines[i + k].strip() == head_old[k]
                for k in range(self.ANCHOR_LINES)
            )
            if not head_ok:
                continue

            # Check tail anchors.
            tail_ok = all(
                content_lines[i + window - self.ANCHOR_LINES + k].strip() == tail_old[k]
                for k in range(self.ANCHOR_LINES)
            )
            if not tail_ok:
                continue

            # Check middle lines -- at least 50 % must match.
            if middle_old:
                match_count = 0
                for j, mid in enumerate(middle_old):
                    c_idx = i + self.ANCHOR_LINES + j
                    sim = _similarity(content_lines[c_idx].strip(), mid)
                    if sim >= self.SIMILARITY_THRESHOLD:
                        match_count += 1
                if match_count / len(middle_old) < self.MIDDLE_MATCH_RATIO:
                    continue

            matched = "\n".join(content_lines[i : i + window])
            offset = _line_offset(content_lines, i)
            spans.append((offset, offset + len(matched)))

        return spans


# ---------------------------------------------------------------------------
# Shared helper for line-offset computation
# ---------------------------------------------------------------------------


def _line_offset(lines: list[str], idx: int) -> int:
    """Return the character offset of ``lines[idx]`` within the joined text."""
    offset = 0
    for j in range(idx):
        offset += len(lines[j]) + 1  # +1 for '\n'
    return offset


# ---------------------------------------------------------------------------
# Strategy cascade
# ---------------------------------------------------------------------------

_STRATEGIES: list[_Replacer] = [
    ExactReplacer(),
    LineTrimmedReplacer(),
    WhitespaceNormalizedReplacer(),
    IndentationFlexibleReplacer(),
    BlockAnchorReplacer(),
    ContextAwareReplacer(),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fuzzy_replace(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> tuple[str, int, str] | str:
    """Attempt to replace *old_string* in *content* with *new_string* using a
    cascade of increasingly fuzzy strategies.

    Parameters
    ----------
    content:
        The full file content to operate on.
    old_string:
        The text to find (may be matched fuzzily).
    new_string:
        The replacement text.
    replace_all:
        If ``True``, replace **all** occurrences.  If ``False`` and more than
        one occurrence is found, return an error message.

    Returns
    -------
    tuple[str, int, str]
        ``(new_content, occurrences, strategy_name)`` on success.
    str
        An error message on failure (no match, or ambiguous match when
        ``replace_all`` is ``False``).
    """
    for strategy in _STRATEGIES:
        matches = strategy.find(content, old_string)
        if not matches:
            continue

        occurrences = len(matches)

        if occurrences > 1 and not replace_all:
            return (
                f"Error: String '{old_string}' appears {occurrences} times in "
                f"file (matched via {strategy.name}). Use replace_all=True to "
                f"replace all instances, or provide a more specific string "
                f"with surrounding context."
            )

        if strategy.name != "ExactReplacer":
            logger.warning(
                "Exact match failed; falling back to %s for replacement.",
                strategy.name,
            )

        new_content = strategy.apply(content, old_string, new_string, matches)
        return new_content, occurrences, strategy.name

    return f"Error: String not found in file: '{old_string}'"


def perform_string_replacement(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool,
) -> tuple[str, int] | str:
    """Drop-in replacement for the original ``perform_string_replacement``.

    The signature and return type are identical to the original function in
    ``vendor/deepagents/libs/deepagents/deepagents/backends/utils.py``::

        (content, old_string, new_string, replace_all)
          -> tuple[str, int]   # (new_content, occurrences) on success
          -> str               # error message on failure

    Internally this delegates to :func:`fuzzy_replace` and strips the extra
    strategy-name field from successful results so that callers that depend on
    the two-element tuple contract keep working.
    """
    result = fuzzy_replace(content, old_string, new_string, replace_all)
    if isinstance(result, str):
        return result
    new_content, occurrences, _strategy = result
    return new_content, occurrences

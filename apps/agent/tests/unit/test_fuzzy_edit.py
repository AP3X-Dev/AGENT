"""Unit tests for the fuzzy_edit module (Sprint 1 — cascading fuzzy replacement engine)."""

import pytest

from ag3nt_agent.fuzzy_edit import fuzzy_replace, perform_string_replacement


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CONTENT = """\
def greet(name):
    print(f"Hello, {name}!")

def farewell(name):
    print(f"Goodbye, {name}!")
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFuzzyEdit:
    """Tests for fuzzy_replace and perform_string_replacement."""

    # 1 — basic exact replacement works
    def test_exact_match(self):
        content = "alpha beta gamma"
        result = fuzzy_replace(content, "beta", "BETA")
        assert isinstance(result, tuple)
        new_content, count, strategy = result
        assert new_content == "alpha BETA gamma"
        assert count == 1
        assert strategy == "ExactReplacer"

    # 2 — returns error string when the substring is not found at all
    def test_exact_match_not_found(self):
        content = "alpha beta gamma"
        result = fuzzy_replace(content, "delta", "DELTA")
        assert isinstance(result, str)
        assert "not found" in result.lower() or "Error" in result

    # 3 — returns error for ambiguous match when replace_all is False
    def test_exact_match_multiple_without_replace_all(self):
        content = "foo bar foo baz foo"
        result = fuzzy_replace(content, "foo", "qux", replace_all=False)
        assert isinstance(result, str)
        assert "appears" in result.lower() or "3" in result

    # 4 — replaces all occurrences when replace_all is True
    def test_exact_match_replace_all(self):
        content = "foo bar foo baz foo"
        result = fuzzy_replace(content, "foo", "qux", replace_all=True)
        assert isinstance(result, tuple)
        new_content, count, strategy = result
        assert count == 3
        assert "foo" not in new_content
        assert new_content.count("qux") == 3

    # 5 — matches when old_string has different leading/trailing whitespace per line
    def test_line_trimmed_match(self):
        content = "    hello world\n    goodbye world\n"
        # The old_string has no leading spaces — LineTrimmedReplacer should match.
        old = "hello world\ngoodbye world"
        result = fuzzy_replace(content, old, "REPLACED\nLINES")
        assert isinstance(result, tuple)
        new_content, count, strategy = result
        assert count == 1
        # The match should have been found by a non-exact strategy.
        assert strategy in (
            "LineTrimmedReplacer",
            "WhitespaceNormalizedReplacer",
            "IndentationFlexibleReplacer",
        )

    # 6 — matches when spaces/tabs differ inside lines
    def test_whitespace_normalized_match(self):
        content = "x = 1\nif  x ==   1:\n    print('yes')\n"
        old = "if x == 1:\n    print('yes')"
        result = fuzzy_replace(content, old, "if x == 1:\n    print('no')")
        assert isinstance(result, tuple)
        new_content, count, strategy = result
        assert count == 1
        assert "print('no')" in new_content

    # 7 — matches content indented differently (e.g., 2-space vs 4-space)
    def test_indentation_flexible_match(self):
        # Content uses 4-space indent.
        content = (
            "def foo():\n"
            "    x = 1\n"
            "    y = 2\n"
            "    return x + y\n"
        )
        # old_string uses 2-space indent — IndentationFlexibleReplacer should match.
        old = (
            "def foo():\n"
            "  x = 1\n"
            "  y = 2\n"
            "  return x + y"
        )
        new = (
            "def foo():\n"
            "  x = 10\n"
            "  y = 20\n"
            "  return x + y"
        )
        result = fuzzy_replace(content, old, new)
        assert isinstance(result, tuple)
        new_content, count, strategy = result
        assert count == 1
        # The replacement should have happened.
        assert "10" in new_content or "20" in new_content

    # 8 — first/last lines match exactly, middle lines have minor differences
    def test_block_anchor_match(self):
        content = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        value = compute_something()\n"
            "        return value\n"
        )
        # Middle line differs slightly but first/last anchor lines match.
        old = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        val = compute_something()\n"
            "        return value"
        )
        new = "REPLACED BLOCK"
        result = fuzzy_replace(content, old, new)
        assert isinstance(result, tuple)
        new_content, count, strategy = result
        assert count == 1
        assert "REPLACED BLOCK" in new_content

    # 9 — anchor lines match, middle lines partially match (ContextAwareReplacer)
    def test_context_aware_match(self):
        # Need >= 5 lines for ContextAwareReplacer to engage.
        content = (
            "def process():\n"
            "    step_one()\n"
            "    x = compute_alpha()\n"
            "    y = compute_beta()\n"
            "    z = compute_gamma()\n"
            "    step_two()\n"
            "    return finish()\n"
        )
        # First 2 and last 2 lines match exactly (trimmed), middle lines differ.
        old = (
            "def process():\n"
            "    step_one()\n"
            "    x = compute_alpha_v2()\n"
            "    y = compute_beta_v2()\n"
            "    z = compute_gamma_v2()\n"
            "    step_two()\n"
            "    return finish()"
        )
        new = "CONTEXT REPLACED"
        result = fuzzy_replace(content, old, new)
        assert isinstance(result, tuple)
        new_content, count, strategy = result
        assert count == 1
        assert "CONTEXT REPLACED" in new_content

    # 10 — completely different content returns error
    def test_no_false_positives(self):
        content = (
            "import os\n"
            "import sys\n"
            "\n"
            "def main():\n"
            "    os.listdir('.')\n"
        )
        old = (
            "class SpaceMission:\n"
            "    def launch(self):\n"
            "        ignite_boosters()\n"
            "        escape_atmosphere()\n"
            "        orbit()\n"
            "        deploy_payload()\n"
            "        return 'success'"
        )
        result = fuzzy_replace(content, old, "SHOULD NOT APPEAR")
        assert isinstance(result, str)
        assert "not found" in result.lower() or "Error" in result

    # 11 — perform_string_replacement returns tuple[str, int] (drop-in compat)
    def test_drop_in_compatibility(self):
        content = "hello world"
        result = perform_string_replacement(content, "hello", "goodbye", False)
        assert isinstance(result, tuple)
        assert len(result) == 2
        new_content, count = result
        assert new_content == "goodbye world"
        assert count == 1

        # Error case still returns str.
        err = perform_string_replacement(content, "missing", "x", False)
        assert isinstance(err, str)

    # 12 — content unchanged when no match is found
    def test_preserves_original_content_on_failure(self):
        content = "line one\nline two\nline three\n"
        original = content
        result = fuzzy_replace(content, "nonexistent string", "replacement")
        # On failure result is an error string; original content must be untouched.
        assert isinstance(result, str)
        assert content == original

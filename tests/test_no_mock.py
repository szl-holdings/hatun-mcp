"""Meta-test: the PURIQ implementation contains no mock/fake/stub outside /tests/.

HONESTY OVER CHECKLIST. The governance core and the PURIQ orchestrator must use REAL
logic. This test scans the hatun_mcp package source for the forbidden tokens and
fails if any appears in implementation code. Honest, declared exceptions:

  * The word may legitimately appear inside a STRING that DISCLOSES a boundary
    (e.g. "disclosed-placeholder", "honest stub", "not faked"). We therefore flag
    only the bare lowercase tokens used as identifiers/mechanisms, and allow lines
    that are clearly disclosure strings or comments about honesty.
"""
import os
import re

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hatun_mcp")
FORBIDDEN = ("mock", "fake", "stub")
# Lines containing any of these disclosure markers are allowed to mention the tokens,
# because they are HONESTY disclosures, not actual mock machinery.
ALLOW_MARKERS = (
    "disclosed", "honest", "not faked", "never faked", "placeholder mode",
    "no mock", "no_mock", "forbidden", "disclosure", "boundary",
)


def _py_files(root):
    for base, _dirs, files in os.walk(root):
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(base, fn)


def test_no_mock_fake_stub_in_implementation():
    offenders = []
    for path in _py_files(PKG):
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                low = line.lower()
                if any(m in low for m in ALLOW_MARKERS):
                    continue  # disclosure line, allowed
                for tok in FORBIDDEN:
                    # match the token as a whole word
                    if re.search(rf"\b{tok}\b", low):
                        offenders.append((os.path.relpath(path, PKG), i, tok,
                                          line.strip()[:120]))
    assert not offenders, (
        "Forbidden mock/fake/stub tokens found in implementation code "
        "(outside disclosure strings):\n" +
        "\n".join(f"  {p}:{ln} [{t}] {txt}" for p, ln, t, txt in offenders)
    )

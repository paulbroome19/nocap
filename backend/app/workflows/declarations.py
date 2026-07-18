"""Filing-indicator declaration vocabulary.

A template's declaration within an ``EntityWorkflowConfig`` says how its filing
indicator is decided for a given (entity, workflow):

- **optional** — derive from facts: reported iff the template has resolvable
  facts. The default, and the absence of an explicit entry.
- **required** — force a positive indicator; the run *fails validation* if the
  template has no facts (a required template must be filed).
- **not_required** — force a negative indicator and exclude the template's facts
  from the package (declared not-filed), with a warning if facts were supplied.

Pure module (no app imports) so the data migration can share the remap.
"""

from __future__ import annotations

DECLARATION_OPTIONAL = "optional"
DECLARATION_REQUIRED = "required"
DECLARATION_NOT_REQUIRED = "not_required"

VALID_DECLARATIONS = {
    DECLARATION_OPTIONAL,
    DECLARATION_REQUIRED,
    DECLARATION_NOT_REQUIRED,
}

# Legacy (pre-rename) stored values → the current vocabulary. Used by the data
# migration and available for tests.
LEGACY_DECLARATION_REMAP = {
    "auto": DECLARATION_OPTIONAL,
    "true": DECLARATION_REQUIRED,
    "false": DECLARATION_NOT_REQUIRED,
}


def remap_legacy_declarations(declarations: dict | None) -> dict:
    """Remap a stored template→declaration map from legacy values to current.

    Unknown/already-current values pass through unchanged, so the remap is
    idempotent.
    """
    out: dict = {}
    for code, value in (declarations or {}).items():
        v = str(value).strip().lower()
        out[code] = LEGACY_DECLARATION_REMAP.get(v, v)
    return out

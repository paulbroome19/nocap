"""Byte fixtures for the three mandatory release-creation artifacts.

Small, valid-enough stand-ins for the real EBA downloads: a fake Access database
carrying the ACE signature, a minimal taxonomy package zip, and the tiny
validation-rules workbook.
"""

from __future__ import annotations

import io
import zipfile

from tests.fixtures import validation_rules_mini as _vr


def dpm_bytes() -> bytes:
    """Fake DPM Access database — carries the ACE signature looks_like_access checks."""
    return b"\x00\x01\x00\x00Standard ACE DB\x00" + b"\x00" * 256


def taxonomy_zip_bytes() -> bytes:
    """A minimal valid taxonomy package (has META-INF/taxonomyPackage.xml)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/taxonomyPackage.xml", "<taxonomyPackage/>")
        zf.writestr("eba/fr/xbrl/corep/entry.xsd", "<schema/>")
    return buf.getvalue()


def rules_bytes() -> bytes:
    """The validation-rules workbook (real header shape)."""
    return _vr.build_bytes()

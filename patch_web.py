"""
patch_web.py  –  Run once from your RVC root directory:

    python patch_web.py

Updates the 5 inference sliders (in both Single and Batch tabs) so that
each one displays a short, bold parameter name as its label, with the
original long description moved to Gradio's `info=` field (shown as
smaller, non-bold text beneath the label).

A backup is saved as web.py.bak before any changes are made.
Idempotent: running it a second time will report 0 changes (already done).
"""

import re, shutil, sys
from pathlib import Path

TARGET = Path("web.py")

if not TARGET.exists():
    sys.exit("ERROR: web.py not found. Run this script from your RVC root directory.")

shutil.copy(TARGET, Path("web.py.bak"))
print("Backup saved -> web.py.bak\n")

src = TARGET.read_text(encoding="utf-8")
original = src


def patch_slider(text, label_keyword, new_label, info_override=None):
    """
    Find label=i18n("...keyword...") and rewrite as:
        label=i18n("<new_label>"),
        <indent>info=i18n("<original description>")

    Returns (new_text, n_replacements).
    """
    pattern = re.compile(
        r'([ \t]*)label=i18n\(\s*"([^"]*' + re.escape(label_keyword) + r'[^"]*)"\s*\)',
        re.DOTALL,
    )

    def replacer(m):
        indent = m.group(1)
        description = m.group(2)
        info_text = info_override if info_override else description
        return (
            f'{indent}label=i18n("{new_label}"),\n'
            f'{indent}info=i18n("{info_text}")'
        )

    new_text, n = pattern.subn(replacer, text)
    return new_text, n


# ---------------------------------------------------------------------------
# The five sliders to update (appear in both Single and Batch tabs = 2x each)
# ---------------------------------------------------------------------------

SLIDERS = [
    dict(
        keyword="Resample the output audio in post-processing",
        new_label="Resample Sample Rate",
    ),
    dict(
        keyword="Adjust the volume envelope scaling",
        new_label="Volume Envelope Scale",
    ),
    dict(
        keyword="Protect voiceless consonants and breath sounds",
        new_label="Consonant Protection",
    ),
    dict(
        keyword="apply median filtering to the harvested pitch",
        new_label="Median Filter Radius",
    ),
    dict(
        keyword="Feature searching ratio",
        new_label="Feature Search Ratio",
        info_override=(
            "Controls how much the retrieval index influences the output timbre. "
            "Higher values follow the training data more closely."
        ),
    ),
]

total = 0
for s in SLIDERS:
    src, n = patch_slider(src, s["keyword"], s["new_label"], s.get("info_override"))
    status = f"{n} replacement(s)" if n else "*** NOT FOUND – check your web.py version ***"
    print(f"  {s['new_label']:30s}  {status}")
    total += n

TARGET.write_text(src, encoding="utf-8")
print(f"\nTotal substitutions: {total}")
if src == original:
    print("WARNING: file unchanged – no patterns matched.")
else:
    print("web.py updated successfully. Restart the WebUI to see the changes.")
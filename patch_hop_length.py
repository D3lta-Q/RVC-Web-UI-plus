"""
patch_hop_length_v2.py  –  Run once from your RVC root directory:

    python patch_hop_length_v2.py

This is a corrected version of the original patch script. It:
  1. Restores all four files from their .bak backups (undoing any broken patches)
  2. Applies all changes with safer, more targeted regex patterns

Files modified:
    web.py
    infer/modules/vc/pipeline.py
    infer/modules/vc/modules.py
    rvc/f0/gen.py
"""

import re, shutil, sys
from pathlib import Path


# ── Utilities ─────────────────────────────────────────────────────────────────

def restore_from_backup(path: Path) -> str:
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        sys.exit(
            f"\nERROR: Backup {bak} not found.\n"
            f"Cannot safely restore {path}. Aborting."
        )
    shutil.copy(bak, path)
    print(f"  restored {path} from {bak}")
    return path.read_text(encoding="utf-8")


def write_if_changed(path: Path, original: str, new: str) -> int:
    if new == original:
        print(f"  WARNING: {path} — no pattern matched; file NOT changed.")
        return 0
    path.write_text(new, encoding="utf-8")
    n = sum(1 for a, b in zip(original.splitlines(), new.splitlines()) if a != b)
    print(f"  written → {path}  (~{n} lines changed)")
    return 1


# ── Step 0: Restore all files from backups ────────────────────────────────────

print("\n[0/4]  Restoring all files from .bak backups …")
for rel in [
    "rvc/f0/gen.py",
    "infer/modules/vc/pipeline.py",
    "infer/modules/vc/modules.py",
    "web.py",
]:
    p = Path(rel)
    bak = p.with_suffix(p.suffix + ".bak")
    if not p.exists():
        sys.exit(f"\nERROR: {p} not found. Run from your RVC root directory.")
    if not bak.exists():
        sys.exit(
            f"\nERROR: Backup {bak} not found.\n"
            f"The original patch script must have been run at least once to create .bak files."
        )
    shutil.copy(bak, p)
    print(f"  restored {p}")


# ═════════════════════════════════════════════════════════════════════════════
# 1.  rvc/f0/gen.py
#     If the body hardcodes `self.window = 160` instead of using the parameter,
#     fix that so the passed-in value flows through.
# ═════════════════════════════════════════════════════════════════════════════

print("\n[1/4]  rvc/f0/gen.py")
gen_path = Path("rvc/f0/gen.py")
gen_src  = gen_path.read_text(encoding="utf-8")
gen_new  = gen_src

gen_new = re.sub(r'(self\.window\s*=\s*)160\b', r'\g<1>window', gen_new)

write_if_changed(gen_path, gen_src, gen_new)


# ═════════════════════════════════════════════════════════════════════════════
# 2.  infer/modules/vc/pipeline.py
#     a) Add `hop_length` parameter to Pipeline.pipeline() after filter_radius.
#     b) Pass window=hop_length when creating the Generator inside pipeline().
#
#     Key fix vs v1: we find the Generator(...) call line-by-line so we never
#     produce a dangling `, window=hop_length)` fragment.
# ═════════════════════════════════════════════════════════════════════════════

print("\n[2/4]  infer/modules/vc/pipeline.py")
pipe_path = Path("infer/modules/vc/pipeline.py")
pipe_src  = pipe_path.read_text(encoding="utf-8")
pipe_new  = pipe_src

# 2a – add hop_length to the pipeline() signature, right after filter_radius
if 'hop_length' not in pipe_new:
    pipe_new = re.sub(
        r'(def pipeline\(self,[^)]*?filter_radius,)',
        lambda m: m.group(0) + '\n        hop_length=128,',
        pipe_new,
        flags=re.DOTALL,
    )

# 2b – update the Generator(...) call.
# Strategy: find the Generator(  ...  ) block, then either replace an existing
# window=<n> literal or append window=hop_length before the closing paren.
def patch_generator_call(src):
    # Match Generator( ... ) potentially spanning multiple lines
    pat = re.compile(r'(Generator\()(.*?)(\))', re.DOTALL)
    def replacer(m):
        prefix, args, suffix = m.group(1), m.group(2), m.group(3)
        if 'window=hop_length' in args:
            return m.group(0)   # already patched
        # Replace existing window=<number>
        new_args = re.sub(r'\bwindow\s*=\s*\d+', 'window=hop_length', args)
        if new_args == args:
            # No existing window= → append it
            # Preserve trailing whitespace/newline before closing paren
            new_args = args.rstrip() + ', window=hop_length\n        '
        return prefix + new_args + suffix
    return pat.sub(replacer, src, count=1)

pipe_new = patch_generator_call(pipe_new)

write_if_changed(pipe_path, pipe_src, pipe_new)


# ═════════════════════════════════════════════════════════════════════════════
# 3.  infer/modules/vc/modules.py
#     a) Add hop_length=128 to vc_single() and vc_multi() signatures.
#     b) Pass hop_length through to self.pipeline.pipeline().
#     c) Pass hop_length through when vc_multi calls vc_single.
# ═════════════════════════════════════════════════════════════════════════════

print("\n[3/4]  infer/modules/vc/modules.py")
mod_path = Path("infer/modules/vc/modules.py")
mod_src  = mod_path.read_text(encoding="utf-8")
mod_new  = mod_src

def add_param_to_def(src, func_name, after_param, new_param='hop_length=128'):
    """Add new_param to a function definition right after after_param."""
    # Only add if not already present in the function signature
    sig_pat = re.compile(
        r'(def ' + re.escape(func_name) + r'\(.*?' + re.escape(after_param) + r',)',
        re.DOTALL
    )
    m = sig_pat.search(src)
    if m and new_param.split('=')[0] not in m.group(0):
        src = sig_pat.sub(m.group(0) + '\n        ' + new_param + ',', src, count=1)
    return src

mod_new = add_param_to_def(mod_new, 'vc_single', 'protect')
mod_new = add_param_to_def(mod_new, 'vc_multi',  'protect')

# 3c – pipeline.pipeline() call: add hop_length after protect
mod_new = re.sub(
    r'(self\.pipeline\.pipeline\([^)]*?protect,)(?!\s*\n?\s*hop_length)',
    lambda m: m.group(0) + '\n            hop_length,',
    mod_new,
    flags=re.DOTALL,
)

# 3d – vc_single() call inside vc_multi: add hop_length after protect
mod_new = re.sub(
    r'(self\.vc_single\([^)]*?protect,)(?!\s*\n?\s*hop_length)',
    lambda m: m.group(0) + '\n                hop_length,',
    mod_new,
    flags=re.DOTALL,
)

write_if_changed(mod_path, mod_src, mod_new)


# ═════════════════════════════════════════════════════════════════════════════
# 4.  web.py
#     a) Insert hop_length0 slider after the CLOSING PAREN of index_rate1.
#     b) Insert hop_length1 slider after the CLOSING PAREN of index_rate2.
#     c) Add hop_length0 to but0.click inputs list.
#     d) Add hop_length1 to but1.click inputs list.
#
#     Key fix vs v1: we search for `index_rateN = gr.Slider(...)` including
#     the trailing `)` so the insertion point is unambiguous and never lands
#     inside the slider's own argument list.
# ═════════════════════════════════════════════════════════════════════════════

print("\n[4/4]  web.py")
web_path = Path("web.py")
web_src  = web_path.read_text(encoding="utf-8")
web_new  = web_src

HOP_SLIDER = '''\n                {var} = gr.Slider(
                    minimum=32,
                    maximum=512,
                    step=32,
                    label=i18n("Hop Length"),
                    info=i18n(
                        "Number of audio samples between successive F0 analysis frames. "
                        "Lower values give finer pitch time-resolution but are slower to compute. "
                        "Has no effect when using rmvpe or fcpe (those use fixed internal values). "
                        "Default: 128."
                    ),
                    value=128,
                    interactive=True,
                )'''

def find_balanced_paren_end(src, start):
    """Return the index just after the matching ')' for the '(' at src[start]."""
    assert src[start] == '('
    depth = 0
    i = start
    while i < len(src):
        if src[i] == '(':
            depth += 1
        elif src[i] == ')':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1   # unmatched

def insert_slider_after_widget(src, anchor_var, slider_var):
    """Find `anchor_var = gr.Slider(...)` and insert a new slider block after it."""
    if slider_var in src:
        print(f"  {slider_var} already present – skipping")
        return src
    # Locate the assignment
    m = re.search(r'(' + re.escape(anchor_var) + r'\s*=\s*gr\.Slider\()', src)
    if not m:
        print(f"  WARNING: anchor '{anchor_var}' not found in web.py")
        return src
    open_paren = m.start(0) + m.group(0).index('(')
    end = find_balanced_paren_end(src, open_paren)
    if end == -1:
        print(f"  WARNING: could not find closing ')' for {anchor_var} slider")
        return src
    insertion = HOP_SLIDER.format(var=slider_var)
    return src[:end] + insertion + src[end:]

web_new = insert_slider_after_widget(web_new, 'index_rate1', 'hop_length0')
web_new = insert_slider_after_widget(web_new, 'index_rate2', 'hop_length1')

# 4c – but0.click inputs: add hop_length0 after protect0
if 'hop_length0' not in re.search(
        r'but0\.click\(.*?(?=but1\.click|\Z)', web_new, re.DOTALL).group(0):
    web_new = re.sub(
        r'(but0\.click\(\s*vc\.vc_single,\s*\[(?:[^\]]*?)protect0,)',
        r'\g<1>\n                hop_length0,',
        web_new,
    )

# 4d – but1.click inputs: add hop_length1 after protect1
if 'hop_length1' not in re.search(
        r'but1\.click\(.*?(?=but2\.click|\Z)', web_new, re.DOTALL).group(0):
    web_new = re.sub(
        r'(but1\.click\(\s*vc\.vc_multi,\s*\[(?:[^\]]*?)protect1,)',
        r'\g<1>\n                hop_length1,',
        web_new,
    )

write_if_changed(web_path, web_src, web_new)


print("""
═══════════════════════════════════════════════════════════════════════════════
All done. Restart the WebUI to pick up the changes.

If any step printed a WARNING, the relevant anchor text in that file differs
from what the script expected.  Open the file and check:
  • web.py          – look for index_rate1 / index_rate2 variable names
  • pipeline.py     – look for the Generator(…) call and filter_radius param
  • modules.py      – look for protect param in vc_single / vc_multi
  • gen.py          – look for self.window assignment

The .bak files are your originals; copy them back manually if needed.
═══════════════════════════════════════════════════════════════════════════════
""")
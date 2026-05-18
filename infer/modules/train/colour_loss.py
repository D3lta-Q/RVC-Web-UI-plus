# infer/modules/train/colour_loss.py
#
# Drop this file into infer/modules/train/ alongside train.py.
# Then add this ONE LINE at the very top of train.py, before any other imports:
#
#   import infer.modules.train.colour_loss  # noqa: F401
#
# That's it. No other changes needed.
#
# How it works
# ------------
# Importing this module installs a custom logging.Formatter on every
# StreamHandler currently attached to the root logger (and any handler added
# later, via the logging.root handler list hook).  The formatter intercepts
# only the loss-values line emitted by train.py and colourises each number
# with ANSI escape codes based on how healthy the value is.
#
# All other log output is left completely unchanged.
# The colours are stripped automatically if the stream is not a TTY
# (e.g. when stdout is redirected to a file), so log files stay clean.

import logging
import re
import sys

# ── ANSI colours (256-colour where supported, plain fallback otherwise) ───────
_RESET  = "\033[0m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_ORANGE = "\033[38;5;208m"   # bright orange on 256-colour terminals
_RED    = "\033[31m"

def _ansi_supported() -> bool:
    """Return True if stdout looks like a colour-capable terminal."""
    try:
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    except Exception:
        return False

_USE_COLOUR = _ansi_supported()

# ── Loss-value thresholds ─────────────────────────────────────────────────────
# Tuple layout per metric: (green_max, yellow_max, orange_max)
# Values above orange_max → red.
#
# Derived from the RVC source (loss_mel capped at 75, loss_kl capped at 9)
# and community training logs showing what well-trained models look like:
#
#   loss_disc  GAN discriminator.  Healthy: 3–5.  Diverging: >7.
#   loss_gen   GAN generator.      Healthy: 2–4.  Diverging: >6.
#   loss_fm    Feature matching.   Converges to 5–12; high at epoch 1.
#   loss_mel   Mel L1 * c_mel.     Converges to 10–20; capped at 75.
#   loss_kl    KL divergence.      Converges to 0.5–2; capped at 9.
_THRESHOLDS: dict[str, tuple[float, float, float]] = {
    "loss_disc": (5.0,  7.0,  9.0),
    "loss_gen":  (4.0,  6.0,  8.0),
    "loss_fm":   (12.0, 20.0, 35.0),
    "loss_mel":  (20.0, 35.0, 55.0),
    "loss_kl":   (2.0,  4.5,  7.0),
}

_LOSS_RE = re.compile(
    r"loss_disc=([0-9.]+),\s*loss_gen=([0-9.]+),\s*"
    r"loss_fm=([0-9.]+),\s*loss_mel=([0-9.]+),\s*loss_kl=([0-9.]+)"
)


def _colour(name: str, value: float) -> str:
    if not _USE_COLOUR:
        return f"{value:.3f}"
    lo, mid, hi = _THRESHOLDS[name]
    if value <= lo:
        c = _GREEN
    elif value <= mid:
        c = _YELLOW
    elif value <= hi:
        c = _ORANGE
    else:
        c = _RED
    return f"{c}{value:.3f}{_RESET}"


def _colorize(msg: str) -> str:
    """Colourize the loss line; return all other messages unchanged."""
    m = _LOSS_RE.search(msg)
    if not m:
        return msg
    disc, gen, fm, mel, kl = (float(m.group(i)) for i in range(1, 6))
    replacement = (
        f"loss_disc={_colour('loss_disc', disc)}, "
        f"loss_gen={_colour('loss_gen', gen)}, "
        f"loss_fm={_colour('loss_fm', fm)},"
        f"loss_mel={_colour('loss_mel', mel)}, "
        f"loss_kl={_colour('loss_kl', kl)}"
    )
    return msg[: m.start()] + replacement + msg[m.end() :]


# ── Custom formatter ──────────────────────────────────────────────────────────

class _ColourFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _colorize(super().format(record))


# ── Install on every StreamHandler that exists now or gets added later ────────

_INSTALLED_ON: set[int] = set()   # track handler ids to avoid double-patching

def _patch_handler(handler: logging.Handler) -> None:
    if not isinstance(handler, logging.StreamHandler):
        return
    if id(handler) in _INSTALLED_ON:
        return
    existing_fmt = handler.formatter
    fmt_str = (
        existing_fmt._fmt           # type: ignore[union-attr]
        if existing_fmt and hasattr(existing_fmt, "_fmt")
        else "%(levelname)s:%(name)s:%(message)s"
    )
    datefmt = existing_fmt.datefmt if existing_fmt else None
    handler.setFormatter(_ColourFormatter(fmt_str, datefmt=datefmt))
    _INSTALLED_ON.add(id(handler))


def _install() -> None:
    """Patch all current root-logger StreamHandlers."""
    for h in logging.root.handlers:
        _patch_handler(h)

    # Monkey-patch logging.root.addHandler so future handlers get patched too.
    _orig_add = logging.root.addHandler.__func__  # type: ignore[attr-defined]

    def _addHandler(self: logging.Logger, hdlr: logging.Handler) -> None:
        _orig_add(self, hdlr)
        _patch_handler(hdlr)

    # Only patch if not already patched (idempotent import).
    if not getattr(logging.root, "_colour_loss_patched", False):
        import types
        logging.root.addHandler = types.MethodType(_addHandler, logging.root)
        logging.root._colour_loss_patched = True  # type: ignore[attr-defined]


_install()

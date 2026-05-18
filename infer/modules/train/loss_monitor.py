"""
loss_monitor.py
---------------
Parses RVC training log lines and accumulates loss metrics for live plotting
in the Gradio Train tab.

Log line format (emitted by train.py via the 'naked-snake' logger):
    INFO:naked-snake:loss_disc=4.044, loss_gen=3.258, loss_fm=8.274,loss_mel=20.499, loss_kl=1.317

Usage
-----
Import and call `parse_log_file(log_path)` from a Gradio polling loop to get
the four DataFrames needed by gr.LinePlot components.
"""

import re
import os
from collections import defaultdict
from typing import Optional

import pandas as pd

# Regex that matches one training status line
_LINE_RE = re.compile(
    r"INFO:naked-snake:"
    r"loss_disc=(?P<loss_disc>[0-9.]+),\s*"
    r"loss_gen=(?P<loss_gen>[0-9.]+),\s*"
    r"loss_fm=(?P<loss_fm>[0-9.]+),\s*"
    r"loss_mel=(?P<loss_mel>[0-9.]+),\s*"
    r"loss_kl=(?P<loss_kl>[0-9.]+)"
)


def parse_log_file(log_path: str):
    """
    Read the training log file at *log_path* and return four DataFrames
    ready for Gradio LinePlot:

        df_disc_gen  – columns: step, loss_disc, loss_gen   (combined graph)
        df_fm        – columns: step, value
        df_mel       – columns: step, value
        df_kl        – columns: step, value

    Returns (None, None, None, None) if the file doesn't exist or has no
    parseable lines yet.
    """
    if not log_path or not os.path.isfile(log_path):
        return None, None, None, None

    rows = defaultdict(list)  # key -> list of values, plus 'step'
    steps = []

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _LINE_RE.search(line)
                if m:
                    steps.append(len(steps) + 1)
                    for k in ("loss_disc", "loss_gen", "loss_fm", "loss_mel", "loss_kl"):
                        rows[k].append(float(m.group(k)))
    except OSError:
        return None, None, None, None

    if not steps:
        return None, None, None, None

    df_disc_gen = pd.DataFrame({
        "step": steps + steps,
        "value": rows["loss_disc"] + rows["loss_gen"],
        "metric": ["loss_disc"] * len(steps) + ["loss_gen"] * len(steps),
    })

    df_fm = pd.DataFrame({"step": steps, "value": rows["loss_fm"]})
    df_mel = pd.DataFrame({"step": steps, "value": rows["loss_mel"]})
    df_kl = pd.DataFrame({"step": steps, "value": rows["loss_kl"]})

    return df_disc_gen, df_fm, df_mel, df_kl

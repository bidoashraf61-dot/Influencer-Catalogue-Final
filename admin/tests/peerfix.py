"""Test helpers: the peer cells of the production roster as of 2026-10-10 (aggregate quantiles only,
no creator is identifiable), loaded into benchmarks, and the frozen scoring / ROI code of before
fix batch 6 (legacy/) for the old-vs-new comparisons."""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import benchmarks  # noqa: E402


def load_peers(path=None):
    """Fill benchmarks' cache from the fixture: each cell is rebuilt from its 41 quantiles to its real n."""
    raw = json.loads(Path(path or HERE / "fixtures" / "peer_cells_2026-10-10.json").read_text())
    cells = {}
    for key, c in raw.items():
        p, s, m = key.split("|")
        q, n = c["q"], c["n"]
        vals = []
        for i in range(n):
            pos = (i + 0.5) / n * 40.0
            lo = min(int(pos), 39)
            vals.append(q[lo] + (q[lo + 1] - q[lo]) * (pos - lo))
        cells[(p, s, m)] = sorted(vals)
    import time
    benchmarks._cache["cells"], benchmarks._cache["at"] = cells, time.time() + 10 ** 6
    return cells


def clear_peers():
    benchmarks.SOURCE = lambda: []
    benchmarks.invalidate()


def legacy(name):
    """Import legacy/<name>.py under its own module name (the old fit / roi)."""
    spec = importlib.util.spec_from_file_location("legacy_" + name, HERE / "legacy" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def spearman(a, b):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0 + 1
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else 0.0

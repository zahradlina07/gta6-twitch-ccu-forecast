"""Twitch concurrent-viewer forecaster for gta6-twitch-ccu-forecast-01 (Python 3.13, stdlib only).

Reads every *.in case in the input directory, forecasts hours 2..24 of the release day as five
quantiles each, and writes <id>.out beside them. No network, no randomness, no clock, so two runs
on the same input produce the same bytes.
"""

import json
import math
import os
from datetime import datetime
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR") or "/input")
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output")

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
SIGMA = 0.15          # fallback spread per sqrt-hour, in natural logs
BANDWIDTH = 1.8       # kernel width on the log of the first-hour print
WIDEN = 1.1           # residual band widening
MIN_HOURS = 12        # a donor needs this many usable hours to enter the pool
HOURS = list(range(2, 25))


def epoch(ts: str) -> float:
    """ISO-8601 UTC timestamp to epoch seconds."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def round2(x: float):
    """Round half up to 2 decimals; whole values come back as int so JSON shows 1240, not 1240.0."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100.0
    return int(value) if float(value).is_integer() else value


def gauss_weight(log_p0: float, log_p1: float) -> float:
    """Gaussian kernel over the gap between a donor's log first-hour print and the target's."""
    d = log_p0 - log_p1
    return math.exp(-0.5 * (d * d) / BANDWIDTH)


def weighted_quantile(pairs: list[tuple[float, float]], q: float) -> float:
    """Quantile at level q of value/weight pairs, by cumulative weight."""
    if not pairs:
        return 0.0
    ordered = sorted(pairs, key=lambda p: p[0])
    total = sum(w for _, w in ordered)
    if total <= 0.0:
        return ordered[0][0]
    target = q * total - 1e-12
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= target:
            return value
    return ordered[-1][0]


def fallback_quantiles(p1: float, h: int) -> list[float]:
    """Persistence with a random-walk spread: p1 times exp(z * sigma * sqrt(h - 1))."""
    scale = math.sqrt(h - 1)
    return [p1 * math.exp(z * SIGMA * scale) for z in Z]


def fit_line(donors: list[dict], h: int) -> tuple[float, float, float, float, float]:
    """Weighted least squares of the donor log ratio on its log first-hour print.

    Returns (intercept, slope, xbar, ybar, sxx) with the slope clamped to [-1.5, 0.3].
    """
    pts = [(d["log_p0"], d["ratios"][h], d["weight"]) for d in donors if h in d["ratios"]]
    total = sum(w for _, _, w in pts)
    if total <= 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    xbar = sum(w * x for x, _, w in pts) / total
    ybar = sum(w * y for _, y, w in pts) / total
    sxx = sum(w * (x - xbar) ** 2 for x, _, w in pts)
    sxy = sum(w * (x - xbar) * (y - ybar) for x, y, w in pts)
    slope = sxy / sxx if sxx > 1e-12 else 0.0
    slope = min(0.3, max(-1.5, slope))
    intercept = ybar - slope * xbar
    return intercept, slope, xbar, ybar, sxx


def band_quantiles(donors: list[dict], h: int, log_p1: float) -> list[float]:
    """Regression centre plus a widened, re-centred residual band, exponentiated."""
    intercept, slope, _, _, _ = fit_line(donors, h)
    center = intercept + slope * log_p1
    resid = [(d["ratios"][h] - (intercept + slope * d["log_p0"]), d["weight"])
             for d in donors if h in d["ratios"]]
    median = weighted_quantile(resid, 0.5)
    out = []
    for level in LEVELS:
        q = weighted_quantile(resid, level) * WIDEN - median
        # Clamp the exponent so an extreme residual cannot overflow exp().
        out.append(math.exp(min(21.0, max(-40.0, log_p1 + center + q))))
    return out


def bucket_hourly(rows: list[dict], day_start: str) -> dict[int, float]:
    """Average a comparable's hourly rows per integer hour offset from its own day_start."""
    origin = epoch(day_start)
    sums: dict[int, list[float]] = {}
    for row in rows:
        offset = round((epoch(row["from"]) - origin) / 3600.0)
        sums.setdefault(offset, []).append(float(row["viewers"]))
    return {off: sum(vals) / len(vals) for off, vals in sums.items()}


def is_rolling_console_launch(unlock: str | None) -> bool:
    """True when the unlock note says a rolling or local-midnight console launch and not early access."""
    text = (unlock or "").lower()
    if "early" in text:
        return False
    return ("midnight local" in text) or ("rolling" in text)


def build_donors(case: dict, log_p1: float) -> list[dict]:
    """Per comparable: its log first hour print, kernel weight, and log ratio per hour."""
    donors = []
    for comp in case.get("comparables") or []:
        avg = bucket_hourly(comp.get("hourly") or [], comp["day_start"])
        avg = {off: v for off, v in avg.items() if v > 0.0}
        p0 = avg.get(0)
        if p0 is None:
            continue
        ratios = {h: math.log(avg[h - 1]) - math.log(p0) for h in HOURS if (h - 1) in avg}
        if len(ratios) < MIN_HOURS:
            continue
        log_p0 = math.log(p0)
        donors.append({
            "name": comp.get("name"),
            "log_p0": log_p0,
            "weight": gauss_weight(log_p0, log_p1),
            "ratios": ratios,
            "rolling": is_rolling_console_launch(comp.get("unlock")),
        })
    return donors


def forecast_case(case: dict) -> dict:
    known = case.get("known") or []
    first = next((r for r in known if r.get("hour") == 1), known[0] if known else None)
    p1 = max(1.0, float(first["viewers"])) if first else 1.0
    log_p1 = math.log(p1)
    donors = build_donors(case, log_p1)

    rows = []
    for h in HOURS:
        pool = [d for d in donors if h in d["ratios"]]
        if len(pool) < 4:
            # Too few donors carry this hour: fall back to persistence.
            qs = fallback_quantiles(p1, h)
        else:
            qs = band_quantiles(pool, h, log_p1)
        # Clamp into the allowed range, then force the row to be non-decreasing.
        clamped = [round2(min(1e9, max(1.0, v))) for v in qs]
        for i in range(1, len(clamped)):
            if clamped[i] < clamped[i - 1]:
                clamped[i] = clamped[i - 1]
        rows.append({"hour": h, "q": clamped})
    return {"hours": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        payload = forecast_case(case)
        text = json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n"
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

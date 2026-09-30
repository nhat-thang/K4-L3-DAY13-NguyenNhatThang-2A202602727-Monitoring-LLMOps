"""Dựng dashboard 6 panel từ data/logs.jsonl thành 1 file HTML tự chứa (không cần thư viện ngoài)."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
OUT_PATH = REPO_ROOT / "submission" / "evidence" / "dashboard.html"

W, H, PAD = 440, 190, 34
BUCKET_CHARS = 5  # 5 = gộp theo phút (HH:MM), 7 = gộp theo 10 giây (HH:MM:S)


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p / 100))]


def load_records(window_minutes: int) -> list[dict]:
    records = []
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    return [r for r in records if datetime.fromisoformat(r["ts"].replace("Z", "+00:00")) >= cutoff]


def by_minute(records: list[dict], key=lambda r: 1, agg=sum) -> list[tuple[str, float]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for r in records:
        label = r["ts"][11 : 11 + BUCKET_CHARS]
        buckets[label + ("0" if BUCKET_CHARS == 7 else "")].append(key(r))
    return [(minute, agg(values)) for minute, values in sorted(buckets.items())]


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def p95_of(values: list[float]) -> float:
    return percentile(values, 95)


def errors_per_minute(recv: list[dict], failed: list[dict]) -> list[tuple[str, float]]:
    bad = dict(by_minute(failed))
    return [(minute, bad.get(minute, 0) / count * 100) for minute, count in by_minute(recv)]


def line_chart(points: list[tuple[str, float]], threshold: float | None, unit: str) -> str:
    if not points:
        return '<p class="empty">Chưa có dữ liệu</p>'
    ys = [v for _, v in points] + ([threshold] if threshold is not None else [])
    top = max(ys) * 1.15 or 1
    step = (W - 2 * PAD) / max(len(points) - 1, 1)
    xy = [(PAD + i * step, H - PAD - (v / top) * (H - 2 * PAD)) for i, (_, v) in enumerate(points)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    parts = [
        f'<svg viewBox="0 0 {W} {H}" role="img">',
        f'<line class="axis" x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}"/>',
        f'<text class="lbl" x="{PAD}" y="{PAD-10}">max {top:.4g} {unit}</text>',
        f'<text class="lbl" x="{PAD}" y="{H-8}">{points[0][0]}</text>',
        f'<text class="lbl" x="{W-PAD}" y="{H-8}" text-anchor="end">{points[-1][0]} UTC</text>',
    ]
    if threshold is not None:
        ty = H - PAD - (threshold / top) * (H - 2 * PAD)
        parts.append(f'<line class="thr" x1="{PAD}" y1="{ty:.1f}" x2="{W-PAD}" y2="{ty:.1f}"/>')
        parts.append(f'<text class="lbl thr-t" x="{W-PAD}" y="{ty-4:.1f}" text-anchor="end">threshold {threshold}</text>')
    parts.append(f'<polyline class="ser" points="{path}"/>')
    parts += [f'<circle class="pt" cx="{x:.1f}" cy="{y:.1f}" r="3"/>' for x, y in xy]
    parts.append("</svg>")
    return "".join(parts)


def stat(label: str, value: str, bad: bool = False) -> str:
    return f'<div class="stat{" bad" if bad else ""}"><b>{value}</b><span>{label}</span></div>'


def main() -> int:
    global BUCKET_CHARS
    configure_utf8_stdio()
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["dashboard"]
    thr = {p["id"]: p["threshold"]["value"] for p in cfg["panels"]}
    recs = load_records(cfg["time_range_minutes"])
    if recs:
        first, last = recs[0]["ts"], recs[-1]["ts"]
        span = datetime.fromisoformat(last.replace("Z", "+00:00")) - datetime.fromisoformat(first.replace("Z", "+00:00"))
        BUCKET_CHARS = 7 if span < timedelta(minutes=10) else 5
    unit_label = "10 giây" if BUCKET_CHARS == 7 else "phút"
    ok = [r for r in recs if r["event"] == "response_sent"]
    recv = [r for r in recs if r["event"] == "request_received"]
    failed = [r for r in recs if r["event"] == "request_failed"]
    tool = [r for r in recs if r.get("tool_success") is not None]

    lat = [r["latency_ms"] for r in ok]
    ttft = [r["ttft_ms"] for r in ok]
    p50, p95, p99, t95 = (percentile(lat, 50), percentile(lat, 95), percentile(lat, 99), percentile(ttft, 95))
    err = len(failed) / len(recv) * 100 if recv else 0.0
    retr = sum(1 for r in tool if r["tool_success"]) / len(tool) * 100 if tool else 100.0
    cost = sum(r["cost_usd"] for r in ok)
    tin, tout = sum(r["tokens_in"] for r in ok), sum(r["tokens_out"] for r in ok)
    qual = sum(r["quality_score"] for r in ok) / len(ok) if ok else 0.0
    per_min = len(recv) / max(len(by_minute(recv)), 1) * (6 if BUCKET_CHARS == 7 else 1)

    panels = [
        ("Latency (ms)", f'{stat("P50", f"{p50:.0f}")}{stat("P95", f"{p95:.0f}", p95 > thr["latency"])}{stat("P99", f"{p99:.0f}")}{stat("TTFT P95", f"{t95:.0f}")}',
         line_chart(by_minute(ok, lambda r: r["latency_ms"], p95_of), thr["latency"], "ms"), f"P95 latency mỗi {unit_label}; threshold P95 ≤ 3000ms"),
        ("Traffic (request/phút)", stat("TB/phút", f"{per_min:.1f}", per_min < thr["traffic"]) + stat("Tổng", str(len(recv))),
         line_chart(by_minute(recv), thr["traffic"], "req"), f"Số request_received mỗi {unit_label}"),
        ("Errors và retrieval success", f'{stat("Error rate %", f"{err:.1f}", err > thr["errors"])}{stat("Retrieval success %", f"{retr:.1f}", retr < 90)}',
         line_chart(errors_per_minute(recv, failed), thr["errors"], "%"), f"Error rate % mỗi {unit_label}; retrieval success tính trên mọi event có tool_success"),
        ("Cost (USD)", stat("Tổng", f"{cost:.4f}", cost > thr["cost"]),
         line_chart(by_minute(ok, lambda r: r["cost_usd"]), None, "USD"), f"Chi phí mỗi {unit_label}; ngưỡng tổng ≤ {thr['cost']} USD"),
        ("Tokens", stat("Input", str(tin)) + stat("Output", str(tout)),
         line_chart(by_minute(ok, lambda r: r["tokens_in"] + r["tokens_out"]), None, "token"), f"Tổng token vào + ra mỗi {unit_label}"),
        ("Quality proxy (0-1)", stat("Mean", f"{qual:.2f}", qual < thr["quality"]),
         line_chart(by_minute(ok, lambda r: r["quality_score"], mean), thr["quality"], "score"), f"Quality trung bình mỗi {unit_label}; threshold mean ≥ 0.75"),
    ]
    cards = "".join(
        f'<section><h2>{t}</h2><div class="stats">{s}</div>{c}<p class="note">{n}</p></section>' for t, s, c, n in panels
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{cfg['title']}</title><meta http-equiv="refresh" content="{cfg['refresh_seconds']}">
<style>
:root{{--bg:#f6f7f9;--card:#fff;--fg:#1c2330;--mut:#667085;--ser:#2563eb;--thr:#d92d20;--bad:#d92d20;--line:#e4e7ec}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f141b;--card:#171d26;--fg:#e6e9ef;--mut:#98a2b3;--ser:#6ea8fe;--thr:#f97066;--bad:#f97066;--line:#2a3441}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}}
h1{{font-size:20px;margin:0 0 4px}}.sub{{color:var(--mut);margin:0 0 16px}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}
h2{{font-size:14px;margin:0 0 8px}}.stats{{display:flex;gap:16px;margin-bottom:6px}}
.stat b{{display:block;font-size:22px}}.stat span{{color:var(--mut);font-size:12px}}.stat.bad b{{color:var(--bad)}}
svg{{width:100%;height:auto}}.axis{{stroke:var(--line)}}.ser{{fill:none;stroke:var(--ser);stroke-width:2}}.pt{{fill:var(--ser)}}
.thr{{stroke:var(--thr);stroke-dasharray:4 3}}.lbl{{fill:var(--mut);font-size:10px}}.thr-t{{fill:var(--thr)}}
.note,.empty{{color:var(--mut);font-size:12px;margin:4px 0 0}}
</style></head><body><h1>{cfg['title']}</h1>
<p class="sub">Nguồn data/logs.jsonl · {cfg['time_range_minutes']} phút gần nhất · {len(recv)} request · cập nhật {now}</p>
<main>{cards}</main></body></html>"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Đã ghi {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

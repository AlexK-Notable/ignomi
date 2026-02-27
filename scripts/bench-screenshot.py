#!/usr/bin/env python3
"""Benchmark screenshot tools for Ignomi backdrop capture.

Tests capture speed of available Wayland screenshot tools,
then measures the full capture→blur→pixbuf pipeline.
Saves blurred samples for visual comparison and a markdown report.

Usage:
    python3 scripts/bench-screenshot.py [CONNECTOR]
    # Default connector: DP-1
"""

import io
import math
import os
import subprocess
import sys
import time
from datetime import datetime

from PIL import Image, ImageEnhance, ImageFilter

RUNS = 20
CONNECTOR = sys.argv[1] if len(sys.argv) > 1 else "DP-1"
BLUR_RADIUS = 20
BRIGHTNESS = 1.3  # DP-1 HDR setting

# Output directory for saved samples
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "bench-screenshots")
os.makedirs(OUT_DIR, exist_ok=True)

# Collect all output for the markdown report
report_lines = []


def log(line=""):
    """Print to terminal and buffer for report."""
    print(line)
    report_lines.append(line)


def stats(values):
    """Compute min, max, avg, median, p5, p95, stddev from a list of floats."""
    s = sorted(values)
    n = len(s)
    avg = sum(s) / n
    variance = sum((x - avg) ** 2 for x in s) / n
    return {
        "min": s[0],
        "max": s[-1],
        "avg": avg,
        "median": s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2,
        "p5": s[max(0, int(n * 0.05))],
        "p95": s[min(n - 1, int(n * 0.95))],
        "stddev": math.sqrt(variance),
        "n": n,
    }


def decode_pam(data: bytes) -> Image.Image:
    """Decode PAM (P7) image data as produced by wayshot --stdout -e ppm.

    PAM is Netpbm's Portable Arbitrary Map format — NOT standard PPM (P6).
    Header fields: WIDTH, HEIGHT, DEPTH, MAXVAL, TUPLTYPE, then ENDHDR.
    """
    header_end = data.index(b"ENDHDR\n") + len(b"ENDHDR\n")
    header = data[:header_end].decode("ascii")
    pixel_data = data[header_end:]

    width = height = depth = 0
    tupltype = ""
    for line in header.splitlines():
        if line.startswith("WIDTH"):
            width = int(line.split()[1])
        elif line.startswith("HEIGHT"):
            height = int(line.split()[1])
        elif line.startswith("DEPTH"):
            depth = int(line.split()[1])
        elif line.startswith("TUPLTYPE"):
            tupltype = line.split()[1]

    if depth == 4 and tupltype == "RGB_ALPHA":
        return Image.frombytes("RGBA", (width, height), pixel_data)
    elif depth == 3:
        return Image.frombytes("RGB", (width, height), pixel_data)
    else:
        raise ValueError(f"Unsupported PAM: depth={depth} tupltype={tupltype}")


# ─── Capture definitions ───

class CaptureMethod:
    """Describes how to capture a screenshot and decode it."""

    def __init__(self, label, cmd, decode_fn=None, file_mode=False, ext="jpg"):
        self.label = label
        self.cmd = cmd
        self.decode_fn = decode_fn or (lambda data: Image.open(io.BytesIO(data)))
        self.file_mode = file_mode
        self.ext = ext

    def capture(self):
        """Run the capture, return (raw_bytes, PIL.Image) or (None, None)."""
        if self.file_mode:
            return self._capture_file()
        return self._capture_stdout()

    def _capture_stdout(self):
        try:
            r = subprocess.run(self.cmd, capture_output=True, timeout=5)
            if r.returncode != 0:
                return None, None
            img = self.decode_fn(r.stdout)
            return r.stdout, img
        except Exception:
            return None, None

    def _capture_file(self):
        """For tools that save to disk (shotman)."""
        try:
            screenshot_dir = subprocess.run(
                ["shotman", "--print-dir"], capture_output=True, text=True
            ).stdout.strip()

            before = set(os.listdir(screenshot_dir)) if os.path.isdir(screenshot_dir) else set()
            r = subprocess.run(self.cmd, capture_output=True, timeout=5)
            if r.returncode != 0:
                return None, None
            after = set(os.listdir(screenshot_dir))
            new_files = after - before
            if not new_files:
                return None, None

            newest = os.path.join(screenshot_dir, sorted(new_files)[-1])
            with open(newest, "rb") as f:
                data = f.read()
            os.unlink(newest)
            img = Image.open(io.BytesIO(data))
            return data, img
        except Exception:
            return None, None


CAPTURES = [
    # grim variants
    CaptureMethod("grim jpeg q30", ["grim", "-o", CONNECTOR, "-t", "jpeg", "-q", "30", "-"], ext="jpg"),
    CaptureMethod("grim jpeg q60", ["grim", "-o", CONNECTOR, "-t", "jpeg", "-q", "60", "-"], ext="jpg"),
    CaptureMethod("grim jpeg q80", ["grim", "-o", CONNECTOR, "-t", "jpeg", "-q", "80", "-"], ext="jpg"),
    CaptureMethod("grim png", ["grim", "-o", CONNECTOR, "-t", "png", "-"], ext="png"),
    CaptureMethod("grim ppm", ["grim", "-o", CONNECTOR, "-t", "ppm", "-"], ext="ppm"),

    # wayshot variants
    CaptureMethod("wayshot jpg", ["wayshot", "-o", CONNECTOR, "-e", "jpg", "--stdout"], ext="jpg"),
    CaptureMethod("wayshot png", ["wayshot", "-o", CONNECTOR, "-e", "png", "--stdout"], ext="png"),
    CaptureMethod("wayshot pam", ["wayshot", "-o", CONNECTOR, "-e", "ppm", "--stdout"],
                  decode_fn=decode_pam, ext="pam"),

    # hyprshot (outputs PNG via -r)
    CaptureMethod("hyprshot raw", ["hyprshot", "-m", "output", "-m", CONNECTOR, "-r", "-s"], ext="png"),

    # shotman (saves to disk, captures active output — not monitor-specific)
    CaptureMethod("shotman output", ["shotman", "-c", "output"], file_mode=True, ext="png"),
]


def bench_capture(method, runs=RUNS):
    """Benchmark capture-only speed. Returns dict with full stats, or None."""
    raw, img = method.capture()
    if raw is None:
        return None

    times = []
    last_raw = raw
    last_img = img
    for _ in range(runs):
        t0 = time.perf_counter()
        raw, img = method.capture()
        t1 = time.perf_counter()
        if raw is None:
            return None
        times.append((t1 - t0) * 1000)
        last_raw = raw
        last_img = img

    s = stats(times)
    res = f"{last_img.size[0]}x{last_img.size[1]}" if last_img else "?"
    s["size_kb"] = len(last_raw) / 1024
    s["resolution"] = res
    s["raw"] = last_raw
    s["img"] = last_img
    return s


def bench_pipeline(method, encode_fmt="PNG", downscale=1, runs=RUNS):
    """Benchmark full pipeline. Returns dict with all timing data, or None."""
    raw, img = method.capture()
    if raw is None:
        return None

    all_times = {k: [] for k in ["total", "capture", "convert", "downscale",
                                   "blur", "upscale", "brightness", "encode"]}
    first_resolution = None
    first_output_bytes = 0

    for i in range(runs):
        t0 = time.perf_counter()
        raw, img = method.capture()
        if raw is None:
            return None
        t_capture = time.perf_counter()

        orig_size = img.size
        if first_resolution is None:
            first_resolution = f"{orig_size[0]}x{orig_size[1]}"

        if img.mode == "RGBA":
            img = img.convert("RGB")
        t_convert = time.perf_counter()

        if downscale > 1:
            small = (orig_size[0] // downscale, orig_size[1] // downscale)
            img = img.resize(small, Image.BILINEAR)
        t_downscale = time.perf_counter()

        effective_radius = BLUR_RADIUS // downscale if downscale > 1 else BLUR_RADIUS
        img = img.filter(ImageFilter.GaussianBlur(radius=effective_radius))
        t_blur = time.perf_counter()

        if downscale > 1:
            img = img.resize(orig_size, Image.BILINEAR)
        t_upscale = time.perf_counter()

        if BRIGHTNESS != 1.0:
            img = ImageEnhance.Brightness(img).enhance(BRIGHTNESS)
        t_bright = time.perf_counter()

        buf = io.BytesIO()
        if encode_fmt == "BMP":
            img.save(buf, format="BMP")
        elif encode_fmt == "JPEG":
            img.save(buf, format="JPEG", quality=85)
        elif encode_fmt == "RAW":
            buf.write(img.tobytes())
        else:
            img.save(buf, format="PNG")
        t_encode = time.perf_counter()

        total = (t_encode - t0) * 1000

        if i == 0:
            first_output_bytes = len(buf.getvalue())
            safe_label = method.label.replace(" ", "_").replace("/", "-")
            ds_tag = f"_down{downscale}x" if downscale > 1 else ""
            ext_map = {"PNG": "png", "JPEG": "jpg", "BMP": "bmp", "RAW": "raw"}
            ext = ext_map.get(encode_fmt, "bin")
            sample_path = os.path.join(OUT_DIR, f"{safe_label}{ds_tag}_{encode_fmt.lower()}.{ext}")
            with open(sample_path, "wb") as f:
                f.write(buf.getvalue())

        all_times["total"].append(total)
        all_times["capture"].append((t_capture - t0) * 1000)
        all_times["convert"].append((t_convert - t_capture) * 1000)
        all_times["downscale"].append((t_downscale - t_convert) * 1000)
        all_times["blur"].append((t_blur - t_downscale) * 1000)
        all_times["upscale"].append((t_upscale - t_blur) * 1000)
        all_times["brightness"].append((t_bright - t_upscale) * 1000)
        all_times["encode"].append((t_encode - t_bright) * 1000)

    result = {}
    for key, values in all_times.items():
        result[key] = stats(values)
    result["resolution"] = first_resolution
    result["output_kb"] = first_output_bytes / 1024
    return result


# ═══════════════════════════════════════════
#  System info
# ═══════════════════════════════════════════

def get_tool_version(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        return r.stdout.strip().split("\n")[0] if r.returncode == 0 else "not found"
    except Exception:
        return "not found"

def get_monitor_info():
    try:
        r = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            import json
            monitors = json.loads(r.stdout)
            for m in monitors:
                if m.get("name") == CONNECTOR:
                    return (f"{m['width']}x{m['height']}@{m.get('refreshRate', '?')}Hz, "
                            f"scale={m.get('scale', '?')}, "
                            f"pos={m.get('x', '?')}x{m.get('y', '?')}")
    except Exception:
        pass
    return "unknown"

def get_cpu_info():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":")[1].strip()
    except Exception:
        pass
    return "unknown"


# ═══════════════════════════════════════════
#  RUN BENCHMARKS
# ═══════════════════════════════════════════

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

log(f"# Ignomi Backdrop Screenshot Benchmark")
log(f"")
log(f"**Date:** {timestamp}  ")
log(f"**Monitor:** {CONNECTOR} ({get_monitor_info()})  ")
log(f"**CPU:** {get_cpu_info()}  ")
log(f"**Blur:** radius={BLUR_RADIUS}, brightness={BRIGHTNESS}  ")
log(f"**Runs:** {RUNS} per test (+ 1 warmup)  ")
log(f"")
log(f"## Tool Versions")
log(f"")
log(f"| Tool | Version |")
log(f"|------|---------|")
log(f"| grim | {get_tool_version(['grim', '--version'])} |")
log(f"| wayshot | {get_tool_version(['wayshot', '--version'])} |")
log(f"| hyprshot | {get_tool_version(['hyprshot', '--version'])} |")
log(f"| shotman | {get_tool_version(['shotman', '--version'])} |")
log(f"| Pillow | {Image.__version__} |")
log(f"")

# ─── Phase 1: Capture only ───

log(f"## Capture Only")
log(f"")
log(f"Raw capture speed — tool outputs to stdout (or disk for shotman).")
log(f"")
log(f"| Tool | Avg | Median | Min | Max | p5 | p95 | StdDev | Size (KB) | Resolution |")
log(f"|------|-----|--------|-----|-----|-----|-----|--------|-----------|------------|")

capture_results = []
for method in CAPTURES:
    r = bench_capture(method)
    if r:
        capture_results.append((method.label, r))
        log(f"| {method.label} | {r['avg']:.1f} | {r['median']:.1f} | {r['min']:.1f} | "
            f"{r['max']:.1f} | {r['p5']:.1f} | {r['p95']:.1f} | {r['stddev']:.1f} | "
            f"{r['size_kb']:.1f} | {r['resolution']} |")
        safe = method.label.replace(" ", "_").replace("/", "-")
        with open(os.path.join(OUT_DIR, f"raw_{safe}.{method.ext}"), "wb") as f:
            f.write(r["raw"])
    else:
        log(f"| {method.label} | FAILED | — | — | — | — | — | — | — | — |")

log(f"")
log(f"*All times in milliseconds.*")
log(f"")

# ─── Phase 2: Full pipeline ───

log(f"## Full Pipeline")
log(f"")
log(f"End-to-end: capture → decode → (downscale) → blur → (upscale) → brightness → encode.")
log(f"")

PIPELINE_CONFIGS = [
    # (method_label, encode_fmt, downscale)
    # PNG output (current approach)
    ("grim jpeg q60", "PNG", 1),
    ("grim ppm",      "PNG", 1),
    ("wayshot jpg",   "PNG", 1),
    ("wayshot pam",   "PNG", 1),
    ("hyprshot raw",  "PNG", 1),
    ("shotman output","PNG", 1),

    # JPEG output
    ("grim jpeg q60", "JPEG", 1),
    ("grim ppm",      "JPEG", 1),
    ("wayshot pam",   "JPEG", 1),

    # BMP output
    ("grim jpeg q60", "BMP", 1),
    ("grim ppm",      "BMP", 1),

    # RAW bytes (for GdkPixbuf.new_from_data)
    ("grim jpeg q60", "RAW", 1),
    ("grim ppm",      "RAW", 1),
    ("wayshot pam",   "RAW", 1),

    # Downscale variants — grim
    ("grim jpeg q60", "PNG", 2),
    ("grim jpeg q60", "PNG", 4),
    ("grim jpeg q60", "RAW", 2),
    ("grim jpeg q60", "RAW", 4),
    ("grim ppm",      "RAW", 2),
    ("grim ppm",      "RAW", 4),

    # Downscale variants — wayshot
    ("wayshot jpg",   "PNG", 2),
    ("wayshot jpg",   "PNG", 4),
    ("wayshot jpg",   "RAW", 2),
    ("wayshot jpg",   "RAW", 4),
    ("wayshot pam",   "PNG", 2),
    ("wayshot pam",   "PNG", 4),
    ("wayshot pam",   "RAW", 2),
    ("wayshot pam",   "RAW", 4),
]

method_map = {m.label: m for m in CAPTURES}
pipeline_results = []
pipeline_details = []

for label, fmt, ds in PIPELINE_CONFIGS:
    method = method_map.get(label)
    if not method:
        continue
    r = bench_pipeline(method, encode_fmt=fmt, downscale=ds)
    if r:
        ds_tag = f" ↓{ds}x" if ds > 1 else ""
        full_label = f"{label}{ds_tag}"
        pipeline_results.append((full_label, fmt, r["total"]))
        pipeline_details.append((full_label, fmt, ds, r))

# ─── Detailed breakdown (averages) ───

log(f"### Stage Breakdown (averages)")
log(f"")
log(f"| Pipeline | Output | Capture | Decode | ↓Scale | Blur | ↑Scale | Bright | Encode | **Total** |")
log(f"|----------|--------|---------|--------|--------|------|--------|--------|--------|-----------|")

for full_label, fmt, ds, r in pipeline_details:
    cap = r["capture"]["avg"]
    conv = r["convert"]["avg"]
    dsc = r["downscale"]["avg"]
    blur = r["blur"]["avg"]
    usc = r["upscale"]["avg"]
    brt = r["brightness"]["avg"]
    enc = r["encode"]["avg"]
    tot = r["total"]["avg"]
    conv_str = f"{conv:.1f}" if conv > 0.1 else "—"
    dsc_str = f"{dsc:.1f}" if ds > 1 else "—"
    usc_str = f"{usc:.1f}" if ds > 1 else "—"
    log(f"| {full_label} | {fmt} | {cap:.1f} | {conv_str} | {dsc_str} | {blur:.1f} | {usc_str} | {brt:.1f} | {enc:.1f} | **{tot:.1f}** |")

log(f"")

# ─── Full statistics table ───

log(f"### Total Pipeline Statistics")
log(f"")
log(f"| Pipeline | Output | Avg | Median | Min | Max | p5 | p95 | StdDev | Output KB |")
log(f"|----------|--------|-----|--------|-----|-----|-----|-----|--------|-----------|")

for full_label, fmt, ds, r in pipeline_details:
    t = r["total"]
    log(f"| {full_label} | {fmt} | {t['avg']:.1f} | {t['median']:.1f} | {t['min']:.1f} | "
        f"{t['max']:.1f} | {t['p5']:.1f} | {t['p95']:.1f} | {t['stddev']:.1f} | {r['output_kb']:.0f} |")

log(f"")
log(f"*All times in milliseconds. {RUNS} runs per test.*")
log(f"")

# ─── Ranking ───

log(f"## Ranking")
log(f"")
log(f"Sorted by median total pipeline time, fastest first.")
log(f"")

pipeline_results.sort(key=lambda x: x[2]["median"])
current_label = "grim jpeg q60"
current_fmt = "PNG"

log(f"| # | Pipeline | Output | Median (ms) | Avg (ms) | Notes |")
log(f"|---|----------|--------|-------------|----------|-------|")

for i, (label, fmt, t) in enumerate(pipeline_results, 1):
    notes = ""
    if label == current_label and fmt == current_fmt:
        notes = "**current**"
    elif i == 1:
        notes = "fastest"
    log(f"| {i} | {label} | {fmt} | {t['median']:.1f} | {t['avg']:.1f} | {notes} |")

log(f"")

# ─── Analysis ───

if pipeline_results:
    fastest_label, fastest_fmt, fastest_t = pipeline_results[0]
    current_t = None
    for label, fmt, t in pipeline_results:
        if label == current_label and fmt == current_fmt:
            current_t = t
            break

    log(f"## Analysis")
    log(f"")
    if current_t:
        speedup = current_t["median"] / fastest_t["median"]
        savings = current_t["median"] - fastest_t["median"]
        log(f"- **Current pipeline:** {current_label} → {current_fmt} = "
            f"**{current_t['median']:.0f}ms** median ({current_t['avg']:.0f}ms avg)")
        log(f"- **Fastest pipeline:** {fastest_label} → {fastest_fmt} = "
            f"**{fastest_t['median']:.0f}ms** median ({fastest_t['avg']:.0f}ms avg)")
        log(f"- **Potential speedup:** {speedup:.1f}x ({savings:.0f}ms savings)")
        log(f"")

    # Bottleneck in current pipeline
    for full_label, fmt, ds, r in pipeline_details:
        if full_label == current_label and fmt == current_fmt:
            stages = [
                ("capture", r["capture"]["avg"]),
                ("blur", r["blur"]["avg"]),
                ("brightness", r["brightness"]["avg"]),
                ("encode", r["encode"]["avg"]),
            ]
            stages.sort(key=lambda x: x[1], reverse=True)
            bottleneck = stages[0]
            total_avg = r["total"]["avg"]
            log(f"### Bottleneck")
            log(f"")
            log(f"In the current pipeline, **{bottleneck[0]}** is the bottleneck at "
                f"**{bottleneck[1]:.0f}ms** ({bottleneck[1]/total_avg*100:.0f}% of total).")
            log(f"")
            log(f"| Stage | Time (ms) | % of Total |")
            log(f"|-------|-----------|------------|")
            for name, t in stages:
                log(f"| {name} | {t:.1f} | {t/total_avg*100:.0f}% |")
            break

    log(f"")
    log(f"### Recommendations")
    log(f"")

    # Find best grim and wayshot results for comparison
    grim_best = None
    wayshot_best = None
    for label, fmt, t in pipeline_results:
        if "grim" in label and grim_best is None:
            grim_best = (label, fmt, t)
        if "wayshot" in label and wayshot_best is None:
            wayshot_best = (label, fmt, t)

    log(f"1. **Switch output format from PNG to RAW/BMP/JPEG** — PNG encoding dominates. "
        f"RAW bytes with `GdkPixbuf.new_from_data()` has near-zero encode cost.")
    if grim_best:
        log(f"2. **Best grim pipeline:** {grim_best[0]} → {grim_best[1]} = "
            f"**{grim_best[2]['median']:.0f}ms** median")
    if wayshot_best:
        log(f"3. **Best wayshot pipeline:** {wayshot_best[0]} → {wayshot_best[1]} = "
            f"**{wayshot_best[2]['median']:.0f}ms** median")
    log(f"4. **Downscaling** trades quality for speed — check saved samples to judge visual difference.")
    log(f"5. **hyprshot** and **shotman** are interactive/GUI tools — not suitable for programmatic capture.")

log(f"")
log(f"## Saved Samples")
log(f"")
log(f"Blurred output from each pipeline is saved in `data/bench-screenshots/` for visual comparison.")
log(f"Files are named `<tool>_<format>.<ext>` — open with any image viewer to compare blur quality")
log(f"across tools, output formats, and downscale factors.")

# ─── Write report ───

report_path = os.path.join(OUT_DIR, "benchmark-report.md")
with open(report_path, "w") as f:
    f.write("\n".join(report_lines) + "\n")

print(f"\n{'=' * 62}")
print(f" Report saved to: {report_path}")
print(f"{'=' * 62}")

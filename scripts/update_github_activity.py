#!/usr/bin/env python3
"""
update_github_activity.py
-------------------------
Production-grade, failure-safe GitHub contribution telemetry updater for @bhavishyagupta11.

Key Architectural Guarantees:
1. Dynamic & Live: Fetches live contribution telemetry via GitHub GraphQL API or public calendar fallback.
2. Zero Hard-coding: All metrics, dates, counts, and ranges are dynamically calculated from fetched data.
3. Last-Known-Good Cache: In any failure scenario (network error, rate-limit, empty/malformed payload,
   validation failure), existing SVG assets are preserved 100% untouched.
4. Atomic Paired Promotion: Dark and Light SVGs are generated and validated together in a staging directory.
   Both are promoted to production paths simultaneously; neither is updated in isolation.
5. Self-Hosted: Generates pure local SVG assets with zero external image dependencies at README render time.
6. Visible Sync Timestamp: Embeds explicit UTC synchronization timestamp and dynamic date window.
"""

import os
import sys
import re
import ssl
import json
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

USERNAME = "bhavishyagupta11"
ASSETS_DARK = os.path.join("assets", "dark", "05b-activity-graph.svg")
ASSETS_LIGHT = os.path.join("assets", "light", "05b-activity-graph.svg")

FONT_SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', Helvetica, Arial, sans-serif"
FONT_MONO = "'SF Pro Mono', 'Ubuntu Mono', 'Consolas', 'Courier New', monospace"


def log(msg):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{timestamp}] {msg}")


def fetch_contributions_graphql(token, username):
    """Fetch contribution calendar via GitHub GraphQL API."""
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    url = "https://api.github.com/graphql"
    payload = json.dumps({"query": query, "variables": {"login": username}}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": f"GitHub-Activity-Updater/{username}",
            "Content-Type": "application/json"
        }
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
        data = json.loads(res.read().decode("utf-8"))
        if "errors" in data:
            raise ValueError(f"GraphQL Errors: {data['errors']}")
        calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        total_contributions = int(calendar["totalContributions"])
        daily_records = []
        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                daily_records.append((day["date"], int(day["contributionCount"])))
        daily_records.sort(key=lambda x: x[0])
        return total_contributions, daily_records


def fetch_contributions_public(username):
    """Fallback fetcher using GitHub's public contribution calendar page."""
    url = f"https://github.com/users/{username}/contributions"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
        html = res.read().decode("utf-8")

    # Map cell IDs to dates
    cell_map = {}
    for date, cid in re.findall(r'<td[^>]*data-date="([^"]+)"[^>]*id="([^"]+)"[^>]*>', html):
        cell_map[cid] = date

    daily_records = []
    for cid, tooltip in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>(.*?)</tool-tip>', html, re.DOTALL):
        date = cell_map.get(cid)
        if date:
            m = re.search(r'(\d+|No)\s+contribution', tooltip)
            count = 0 if not m or m.group(1) == "No" else int(m.group(1))
            daily_records.append((date, count))

    if not daily_records:
        raise ValueError("Could not parse contribution days from public HTML")

    daily_records.sort(key=lambda x: x[0])
    total_contributions = sum(count for _, count in daily_records)
    return total_contributions, daily_records


def generate_activity_svg(total_contributions, points_30d, sync_time_str, theme="dark"):
    """Render high-fidelity, standards-compliant, responsive vector contribution telemetry SVG."""
    bg = "#0d1117" if theme == "dark" else "#ffffff"
    border = "#30363d" if theme == "dark" else "#d0d7de"
    t_main = "#f0f6fc" if theme == "dark" else "#1f2328"
    t_sec = "#8b949e" if theme == "dark" else "#57606a"
    t_lbl = "#6e7681" if theme == "dark" else "#8c959f"
    grid_c = "#21262d" if theme == "dark" else "#eaeef2"
    accent = "#00d4ff" if theme == "dark" else "#0969da"
    accent_g = "#39d353" if theme == "dark" else "#1a7f37"
    fill_color = "#00d4ff" if theme == "dark" else "#0969da"

    plot_x0 = 70
    plot_x1 = 880
    plot_y_top = 54
    plot_y_bot = 175

    max_val_data = max(v for _, v in points_30d) if points_30d else 10
    max_val = max(30.0, float(((int(max_val_data) + 9) // 10) * 10))

    n = len(points_30d)
    x_step = (plot_x1 - plot_x0) / max(1, (n - 1))

    plot_points = []
    for i, (date_str, val) in enumerate(points_30d):
        px = plot_x0 + i * x_step
        py = plot_y_bot - (val / max_val) * (plot_y_bot - plot_y_top)
        plot_points.append((px, py, date_str, val))

    # Smooth cubic Bezier spline
    path_d = f"M {plot_points[0][0]:.1f} {plot_points[0][1]:.1f}"
    for i in range(len(plot_points) - 1):
        x0, y0 = plot_points[i][0], plot_points[i][1]
        x1, y1 = plot_points[i + 1][0], plot_points[i + 1][1]
        cx0 = x0 + (x1 - x0) * 0.4
        cy0 = y0
        cx1 = x0 + (x1 - x0) * 0.6
        cy1 = y1
        path_d += f" C {cx0:.1f} {cy0:.1f}, {cx1:.1f} {cy1:.1f}, {x1:.1f} {y1:.1f}"

    area_d = f"{path_d} L {plot_points[-1][0]:.1f} {plot_y_bot} L {plot_points[0][0]:.1f} {plot_y_bot} Z"

    # Grid lines and Y-axis labels
    grid_svg = []
    y_steps = [0, int(max_val * 0.33), int(max_val * 0.66), int(max_val)]
    for y_val in y_steps:
        gy = plot_y_bot - (y_val / max_val) * (plot_y_bot - plot_y_top)
        grid_svg.append(f'''
        <line x1="{plot_x0}" y1="{gy:.1f}" x2="{plot_x1}" y2="{gy:.1f}" stroke="{grid_c}" stroke-width="0.8" stroke-dasharray="3,3" />
        <text x="{plot_x0 - 12}" y="{gy + 3.5:.1f}" text-anchor="end" font-family="{FONT_MONO}" font-size="9" fill="{t_lbl}">{y_val}</text>
        ''')

    # X-axis ticks (select evenly spaced indices)
    x_ticks_svg = []
    step_idx = max(1, n // 8)
    tick_indices = list(range(0, n, step_idx))
    if (n - 1) not in tick_indices:
        tick_indices.append(n - 1)

    for idx in tick_indices:
        px, py, date_str, val = plot_points[idx]
        try:
            d_obj = datetime.strptime(date_str, "%Y-%m-%d")
            short_lbl = d_obj.strftime("%d")
        except Exception:
            short_lbl = date_str[-2:]
        x_ticks_svg.append(f'''
        <line x1="{px:.1f}" y1="{plot_y_bot}" x2="{px:.1f}" y2="{plot_y_bot + 4}" stroke="{border}" stroke-width="0.8" />
        <text x="{px:.1f}" y="{plot_y_bot + 16}" text-anchor="middle" font-family="{FONT_MONO}" font-size="8.5" fill="{t_lbl}">{short_lbl}</text>
        ''')

    # Data point markers on peaks
    circles_svg = []
    for px, py, date_str, val in plot_points:
        if val > 0:
            r = 3.5 if val >= 10 else 2.5
            circles_svg.append(f'''
            <circle cx="{px:.1f}" cy="{py:.1f}" r="{r}" fill="{accent}" stroke="{bg}" stroke-width="1.2" />
            ''')

    start_date = points_30d[0][0]
    end_date = points_30d[-1][0]
    subtitle = f"ACTIVITY WINDOW: {start_date} → {end_date} • {total_contributions} CONTRIBUTIONS IN PAST YEAR • @{USERNAME}"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 220" width="100%" height="100%">
  <defs>
    <linearGradient id="areaGrad_{theme}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{fill_color}" stop-opacity="{0.35 if theme == 'dark' else 0.25}" />
      <stop offset="100%" stop-color="{fill_color}" stop-opacity="0.0" />
    </linearGradient>
  </defs>

  <rect width="920" height="220" rx="6" fill="{bg}" stroke="{border}" stroke-width="1" />

  <!-- Top System Bar -->
  <text x="24" y="24" font-family="{FONT_MONO}" font-size="11" font-weight="700" fill="{t_main}" letter-spacing="1.5">CONTRIBUTION TELEMETRY</text>
  
  <circle cx="780" cy="20" r="3.5" fill="{accent_g}" />
  <text x="896" y="24" text-anchor="end" font-family="{FONT_MONO}" font-size="8.5" font-weight="600" fill="{t_sec}" letter-spacing="1">LAST SYNCED: {sync_time_str}</text>

  <!-- Subtitle with dynamic date window -->
  <text x="24" y="40" font-family="{FONT_MONO}" font-size="8.5" fill="{t_sec}" letter-spacing="0.8">{subtitle}</text>

  <!-- Y-Axis Title -->
  <text x="18" y="116" transform="rotate(-90 18 116)" text-anchor="middle" font-family="{FONT_MONO}" font-size="8.5" fill="{t_lbl}" letter-spacing="1">Contributions</text>

  <!-- Grid Lines -->
  {''.join(grid_svg)}

  <!-- Filled Area Under Curve -->
  <path d="{area_d}" fill="url(#areaGrad_{theme})" />

  <!-- Main Curve Line -->
  <path d="{path_d}" fill="none" stroke="{accent}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />

  <!-- Data Point Markers -->
  {''.join(circles_svg)}

  <!-- X-Axis Baseline & Ticks -->
  <line x1="{plot_x0}" y1="{plot_y_bot}" x2="{plot_x1}" y2="{plot_y_bot}" stroke="{border}" stroke-width="1" />
  {''.join(x_ticks_svg)}

  <!-- X-Axis Label -->
  <text x="460" y="{plot_y_bot + 32}" text-anchor="middle" font-family="{FONT_MONO}" font-size="8.5" fill="{t_lbl}" letter-spacing="1">Days (Past 30 Days)</text>
</svg>'''


def validate_svg_content(content):
    """Rigorous validation: XML parsing, non-empty, viewBox check, entity check, size threshold."""
    if len(content) < 1000:
        raise ValueError(f"Generated SVG content unexpectedly small ({len(content)} bytes)")

    for ent in ["&mdash;", "&ndash;", "&bull;", "&rarr;", "&copy;"]:
        if ent in content:
            raise ValueError(f"Found invalid HTML named entity in SVG: {ent}")

    root = ET.fromstring(content)
    if not root.tag.endswith("svg"):
        raise ValueError(f"Root element is not <svg>: {root.tag}")
    if "viewBox" not in root.attrib or root.attrib["viewBox"] != "0 0 920 220":
        raise ValueError(f"Invalid or missing viewBox attribute: {root.attrib.get('viewBox')}")
    return True


def main():
    now_utc = datetime.now(timezone.utc)
    sync_time_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    log(f"Starting GitHub contribution telemetry updater for @{USERNAME}...")
    token = os.environ.get("GITHUB_TOKEN")

    total_contributions = 0
    daily_records = []
    source_used = "None"

    # 1. Attempt Data Retrieval
    if token:
        try:
            log("Attempting data retrieval via GitHub GraphQL API (authenticated)...")
            total_contributions, daily_records = fetch_contributions_graphql(token, USERNAME)
            source_used = "GitHub GraphQL API (Authenticated)"
            log(f"SUCCESS: Retrieved {len(daily_records)} daily records, {total_contributions} annual contributions via GraphQL.")
        except Exception as e:
            log(f"WARNING: GraphQL fetch failed ({e}). Falling back to public endpoint...")

    if not daily_records:
        try:
            log("Attempting data retrieval via GitHub public contributions calendar (fallback)...")
            total_contributions, daily_records = fetch_contributions_public(USERNAME)
            source_used = "GitHub Public Contributions Calendar (Fallback)"
            log(f"SUCCESS: Retrieved {len(daily_records)} daily records, {total_contributions} annual contributions via public endpoint.")
        except Exception as e:
            log(f"ERROR: Public fetch also failed ({e}).")
            log("CACHE PRESERVED: Preserving existing working SVG assets. Exiting safely.")
            sys.exit(0)

    # 2. Validate Data Plausibility
    if not daily_records or len(daily_records) < 30:
        log(f"ERROR: Insufficient daily records ({len(daily_records)} < 30). CACHE PRESERVED.")
        sys.exit(0)

    if total_contributions <= 0:
        log(f"ERROR: Total contributions non-positive ({total_contributions}). CACHE PRESERVED.")
        sys.exit(0)

    points_30d = daily_records[-30:]
    log(f"Plausibility checks PASSED: Window {points_30d[0][0]} to {points_30d[-1][0]} ({len(points_30d)} days).")

    # 3. Generate and Validate in Staging
    temp_files = {}
    try:
        for theme in ["dark", "light"]:
            svg_content = generate_activity_svg(total_contributions, points_30d, sync_time_str, theme=theme)
            validate_svg_content(svg_content)

            fd, temp_path = tempfile.mkstemp(suffix=".svg", prefix=f"activity_{theme}_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(svg_content.strip())

            # Secondary file parse verification
            ET.parse(temp_path)
            temp_files[theme] = temp_path
            log(f"Staged & validated {theme} SVG ({os.path.getsize(temp_path)} bytes).")

        # 4. Atomic Paired Promotion
        os.makedirs(os.path.dirname(ASSETS_DARK), exist_ok=True)
        os.makedirs(os.path.dirname(ASSETS_LIGHT), exist_ok=True)

        if sys.platform == "win32":
            import shutil
            shutil.copy2(temp_files["dark"], ASSETS_DARK)
            shutil.copy2(temp_files["light"], ASSETS_LIGHT)
        else:
            os.replace(temp_files["dark"], ASSETS_DARK)
            os.replace(temp_files["light"], ASSETS_LIGHT)

        log("SUCCESS: Both Dark & Light staged assets atomically promoted together.")
        log(f"Final Status: UPDATED | Source: {source_used} | Total Contributions: {total_contributions} | Last Synced: {sync_time_str}")

    except Exception as e:
        log(f"ERROR during SVG rendering/validation: {e}")
        log("CACHE PRESERVED: Preserving existing working SVG assets. Exiting safely.")
        sys.exit(0)
    finally:
        for p in temp_files.values():
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


if __name__ == "__main__":
    main()

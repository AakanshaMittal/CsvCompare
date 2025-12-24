
#!/usr/bin/env python3
"""
Space-technique-first multi-file comparator with HTML report.

- Segments tables ONLY by spaces (empty rows/cols) and header hard separators.
- Date windows (MM/YY - MM/YY) are OPTIONAL labels; they DO NOT drive segmentation.
- Accepts 2+ CSV files; outputs a single HTML report.
- Standard library only.

Usage:
    python space_technique_compare.py fileA.csv fileB.csv [fileC.csv ...] --output report.html
"""

import csv
import json
import re
import argparse
from typing import List, Tuple, Dict, Any, Optional

# -------------------------- Predicates & helpers -----------------------------

def is_blank(s: Optional[str]) -> bool:
    return s is None or str(s).strip() == ""

def looks_numeric(s: Optional[str]) -> bool:
    if is_blank(s):
        return False
    t = str(s).strip()
    return bool(re.fullmatch(
        r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?%?|"
        r"[-+]?\d+(?:\.\d+)?%?|"
        r"[₹$€]?\s*[-+]?\d+(?:\.\d+)?", t
    ))

def parse_numeric(s: Optional[str]) -> Optional[float]:
    if is_blank(s):
        return None
    t = str(s).strip()
    # percentages: e.g., "12.3%"
    if t.endswith("%"):
        try:
            return float(t[:-1].replace(",", "")) / 100.0
        except:
            return None
    # currency and thousands separators
    t = t.replace("₹", "").replace("$", "").replace("€", "")
    t = t.replace(",", "")
    try:
        return float(t)
    except:
        return None

def looks_alpha(s: Optional[str]) -> bool:
    if is_blank(s):
        return False
    return any(c.isalpha() for c in str(s))

DATE_WINDOW_RE = re.compile(r"\b\d{2}/\d{2}\s*[-–]\s*\d{2}/\d{2}\b")

def parse_date_window_token(cell: Optional[str]) -> Optional[str]:
    if is_blank(cell):
        return None
    m = DATE_WINDOW_RE.search(str(cell))
    if not m:
        return None
    token = m.group(0).replace("–", "-").replace(" ", "")
    return token  # e.g., "07/27-06/28"

# -------------------------- CSV I/O ------------------------------------------

def read_csv_grid(path: str) -> List[List[str]]:
    grid: List[List[str]] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            grid.append(row)
    maxw = max((len(r) for r in grid), default=0)
    for r in grid:
        if len(r) < maxw:
            r.extend([""] * (maxw - len(r)))
    return grid

# -------------------------- Header & sections --------------------------------

def detect_header_rows(grid: List[List[str]], max_scan: int = 12) -> int:
    """
    Heuristic: header ends before first row where >=50% cells look numeric.
    Fallback: 3 header rows (or less if grid smaller).
    """
    if not grid:
        return 0
    width = len(grid[0]) if grid else 0
    for i, row in enumerate(grid[:max_scan]):
        num_count = sum(1 for c in row if looks_numeric(c))
        if width > 0 and num_count >= max(2, int(0.5 * width)):
            return max(0, i)  # rows above i are headers
    return min(3, len(grid))

def first_non_empty_header_row(grid: List[List[str]], header_rows: int) -> int:
    for r in range(min(header_rows, len(grid))):
        if any(not is_blank(c) for c in grid[r]):
            return r
    return 0

def consecutive_blank_headers_in_col(grid: List[List[str]], col: int, header_rows: int) -> int:
    return sum(1 for r in range(min(header_rows, len(grid))) if is_blank(grid[r][col]))

def column_has_any_data(grid: List[List[str]], col: int, data_start_row: int) -> bool:
    rows = len(grid)
    for r in range(data_start_row, rows):
        if not is_blank(grid[r][col]):
            return True
    return False

def map_section_labels_by_col(
    grid: List[List[str]],
    section_row: int,
    header_rows: int,
    data_start_row: int,
    min_blank_sep: int = 2
) -> Dict[int, str]:
    """
    Step #1: forward-fill section labels horizontally until empty column / hard separator.
    Only assign labels to columns that actually contain data below headers.
    """
    width = len(grid[0]) if grid else 0
    sec_map: Dict[int, str] = {}
    c = 0
    while c < width:
        cell = grid[section_row][c] if section_row < len(grid) else ""
        if is_blank(cell):
            c += 1
            continue
        label = str(cell).strip()
        c2 = c
        while c2 < width:
            hard_sep = consecutive_blank_headers_in_col(grid, c2, header_rows) >= min_blank_sep
            empty_col = not column_has_any_data(grid, c2, data_start_row)
            if hard_sep or empty_col:
                break
            if column_has_any_data(grid, c2, data_start_row):
                sec_map[c2] = label
            c2 += 1
        c = max(c2 + 1, c2)
    return sec_map

# -------------------------- Space technique blocks ---------------------------

def first_non_empty_row_in_cols(grid: List[List[str]], cols: List[int], start_row: int) -> Optional[int]:
    rows = len(grid)
    for r in range(start_row, rows):
        if any(not is_blank(grid[r][c]) for c in cols):
            return r
    return None

def right_boundary_in_row_until_empty_col(grid: List[List[str]], row: int, cols: List[int], start_col: int) -> int:
    """
    Step #2: In that row, move right until an empty cell is found; boundary is col before it.
    If not found, boundary is last column in 'cols'.
    """
    sorted_cols = sorted(cols)
    if start_col not in sorted_cols:
        start_col = sorted_cols[0]
    started = False
    boundary = sorted_cols[-1]
    for c in sorted_cols:
        if c == start_col:
            started = True
        if not started:
            continue
        if is_blank(grid[row][c]):
            i = sorted_cols.index(c)
            if i > 0:
                boundary = sorted_cols[i - 1]
            else:
                boundary = c
            return boundary
    return boundary

def find_table_blocks_in_section(
    grid: List[List[str]],
    section_cols: List[int],
    section_row: int
) -> List[Tuple[int, int, int, int]]:
    """
    Returns rectangles (top_row, bottom_row, left_col, right_col) using space technique.
    """
    blocks: List[Tuple[int, int, int, int]] = []
    rows = len(grid)
    if not section_cols:
        return blocks
    r = section_row + 1
    while True:
        top = first_non_empty_row_in_cols(grid, section_cols, r)
        if top is None:
            break
        left = min(section_cols)
        right = right_boundary_in_row_until_empty_col(grid, top, section_cols, left)
        rr = top
        while rr < rows and not all(is_blank(grid[rr][c]) for c in range(left, right + 1)):
            rr += 1
        bottom = rr - 1
        blocks.append((top, bottom, left, right))
        r = bottom + 1
    return blocks

# -------------------------- Labels, channel, metric --------------------------

def forward_fill_label_rows(
    grid: List[List[str]],
    top: int,
    bottom: int,
    left: int,
    right: int
) -> List[List[str]]:
    """
    Step #3: any row with alphabetic characters within [left..right] is a label row.
    Forward-fill horizontally; first three rows represent Group / Sub-Group / Period.
    """
    label_rows: List[List[str]] = []
    for r in range(top, bottom + 1):
        row = grid[r]
        if any(looks_alpha(row[c]) for c in range(left, right + 1)):
            filled = []
            last = ""
            for c in range(left, right + 1):
                val = row[c]
                if not is_blank(val):
                    last = str(val).strip()
                filled.append(last)
            label_rows.append(filled)
    return label_rows

def nearest_metric_above_col(
    grid: List[List[str]],
    header_rows: int,
    col: int,
    prefer_non_date: bool = True,
    no_date_window: bool = False
) -> str:
    """
    Metric label from header tiers above the data; prefer bottom-most non-date token.
    """
    for r in range(header_rows - 1, -1, -1):
        cell = grid[r][col] if r < len(grid) and col < len(grid[0]) else ""
        if is_blank(cell):
            continue
        text = str(cell).strip()
        if prefer_non_date and not no_date_window and parse_date_window_token(text):
            # skip date tokens as metric
            continue
        return text
    return ""

def first_data_col_in_row(grid: List[List[str]], row: int, left: int, right: int) -> Optional[int]:
    for c in range(left, right + 1):
        if looks_numeric(grid[row][c]):
            return c
    return None

def date_window_for_col(
    grid: List[List[str]],
    header_rows: int,
    col: int,
    no_date_window: bool = False
) -> str:
    """
    Column label: bottom-most date window token if available; else bottom-most header text.
    Does NOT affect segmentation.
    """
    if no_date_window:
        for r in range(header_rows - 1, -1, -1):
            cell = grid[r][col]
            if not is_blank(cell):
                return str(cell).strip()
        return ""
    for r in range(header_rows - 1, -1, -1):
        tok = parse_date_window_token(grid[r][col])
        if tok:
            return tok
    for r in range(header_rows - 1, -1, -1):
        cell = grid[r][col]
        if not is_blank(cell):
            return str(cell).strip()
    return ""

# -------------------------- Extraction core per file -------------------------

def extract_space_technique(
    grid: List[List[str]],
    source_name: str,
    header_rows: int,
    section_row: int,
    min_blank_sep: int = 2,
    no_date_window: bool = False
) -> List[Dict[str, Any]]:
    """
    Implements steps 1–7 and returns records for one file.
    """
    records: List[Dict[str, Any]] = []
    rows = len(grid)
    width = len(grid[0]) if grid else 0
    data_start_row = header_rows

    sec_map = map_section_labels_by_col(
        grid, section_row, header_rows, data_start_row, min_blank_sep=min_blank_sep
    )

    def contiguous_runs_for_label(label: str) -> List[List[int]]:
        cols = [c for c, lbl in sec_map.items() if lbl == label]
        cols.sort()
        runs: List[List[int]] = []
        cur: List[int] = []
        for c in cols:
            if not cur or c == cur[-1] + 1:
                cur.append(c)
            else:
                runs.append(cur)
                cur = [c]
        if cur:
            runs.append(cur)
        return runs

    section_labels = sorted(set(sec_map.values()), key=lambda s: s)
    for sec_label in section_labels:
        for run_cols in contiguous_runs_for_label(sec_label):
            blocks = find_table_blocks_in_section(grid, run_cols, section_row)
            for (top, bottom, left, right) in blocks:
                label_rows = forward_fill_label_rows(grid, top, bottom, left, right)

                def group_path_for_col(col: int) -> List[str]:
                    parts = []
                    idx = col - left
                    for lr in label_rows[:3]:
                        if 0 <= idx < len(lr):
                            v = lr[idx]
                            if v:
                                parts.append(v)
                    return parts

                for r in range(top, bottom + 1):
                    data_start_col = first_data_col_in_row(grid, r, left, right)
                    channel = ""
                    if data_start_col is not None and data_start_col - 1 >= left:
                        ch_cell = grid[r][data_start_col - 1]
                        channel = str(ch_cell).strip() if not is_blank(ch_cell) else ""
                    for c in range(left, right + 1):
                        val = grid[r][c]
                        if looks_numeric(val):
                            rec = {
                                "source": source_name,
                                "section": sec_label,
                                "group_path": group_path_for_col(c),
                                "channel": channel,
                                "metric": nearest_metric_above_col(grid, header_rows, c, prefer_non_date=True, no_date_window=no_date_window),
                                "date_window": date_window_for_col(grid, header_rows, c, no_date_window=no_date_window),
                                "value_text": str(val).strip(),
                                "value_num": parse_numeric(val),
                                "row_index": r,
                                "col_index": c
                            }
                            records.append(rec)

    # Step 7: Standalone rightmost blocks
    unlabeled_cols = [c for c in range(width) if c not in sec_map and column_has_any_data(grid, c, data_start_row)]
    unlabeled_cols.sort()
    runs: List[List[int]] = []
    cur: List[int] = []
    for c in unlabeled_cols:
        if not cur or c == cur[-1] + 1:
            cur.append(c)
        else:
            runs.append(cur)
            cur = [c]
    if cur:
        runs.append(cur)

    for run_cols in runs:
        blocks = find_table_blocks_in_section(grid, run_cols, section_row)
        for (top, bottom, left, right) in blocks:
            label_rows = forward_fill_label_rows(grid, top, bottom, left, right)

            def group_path_for_col(col: int) -> List[str]:
                parts = []
                idx = col - left
                for lr in label_rows[:3]:
                    if 0 <= idx < len(lr):
                        v = lr[idx]
                        if v:
                            parts.append(v)
                return parts

            for r in range(top, bottom + 1):
                data_start_col = first_data_col_in_row(grid, r, left, right)
                channel = ""
                if data_start_col is not None and data_start_col - 1 >= left:
                    ch_cell = grid[r][data_start_col - 1]
                    channel = str(ch_cell).strip() if not is_blank(ch_cell) else ""
                for c in range(left, right + 1):
                    val = grid[r][c]
                    if looks_numeric(val):
                        rec = {
                            "source": source_name,
                            "section": "Standalone",
                            "group_path": group_path_for_col(c),
                            "channel": channel,
                            "metric": nearest_metric_above_col(grid, header_rows, c, prefer_non_date=True, no_date_window=no_date_window),
                            "date_window": date_window_for_col(grid, header_rows, c, no_date_window=no_date_window),
                            "value_text": str(val).strip(),
                            "value_num": parse_numeric(val),
                            "row_index": r,
                            "col_index": c
                        }
                        records.append(rec)

    return records

# -------------------------- Comparison & HTML --------------------------------

def key_tuple(rec: Dict[str, Any]) -> Tuple:
    """Key used to align records across files."""
    return (
        rec.get("section", ""),
        tuple(rec.get("group_path", []) or []),
        rec.get("channel", ""),
        rec.get("metric", ""),
        rec.get("date_window", "")
    )

def compare_records(all_records: List[Dict[str, Any]], sources_in_order: List[str]) -> Dict[Tuple, Dict[str, Any]]:
    """
    Aggregate by key and store per-source values.
    Returns: {key: {"values": {src: value_num}, "texts": {src: value_text}}}
    """
    agg: Dict[Tuple, Dict[str, Any]] = {}
    for rec in all_records:
        k = key_tuple(rec)
        if k not in agg:
            agg[k] = {"values": {}, "texts": {}, "meta": {
                "section": rec.get("section", ""),
                "group_path": rec.get("group_path", []),
                "channel": rec.get("channel", ""),
                "metric": rec.get("metric", ""),
                "date_window": rec.get("date_window", "")
            }}
        src = rec.get("source")
        agg[k]["values"][src] = rec.get("value_num")
        agg[k]["texts"][src] = rec.get("value_text")
    # Ensure all sources present even if missing
    for k, v in agg.items():
        for src in sources_in_order:
            v["values"].setdefault(src, None)
            v["texts"].setdefault(src, "")
    return agg

def html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def generate_html_report(agg: Dict[Tuple, Dict[str, Any]], sources_in_order: List[str]) -> str:
    """
    Build a styled HTML report with per-section tables and diffs vs baseline.
    """
    # Group keys by section for layout
    by_section: Dict[str, List[Tuple]] = {}
    for k, v in agg.items():
        sec = v["meta"]["section"] or "Unknown"
        by_section.setdefault(sec, []).append(k)
    # Sort for readability
    for sec in by_section:
        by_section[sec].sort(key=lambda k: (
            v := agg[k]["meta"],
            "/".join(v["group_path"]),
            v["channel"],
            v["metric"],
            v["date_window"]
        ))

    # Summary stats
    baseline = sources_in_order[0]
    total_keys = len(agg)
    changed_keys = 0
    for k, v in agg.items():
        base = v["values"].get(baseline)
        for src in sources_in_order[1:]:
            other = v["values"].get(src)
            if base is not None and other is not None and other != base:
                changed_keys += 1
                break

    # Build HTML
    css = """
    <style>
      body { font-family: Arial, sans-serif; margin: 20px; }
      h1 { margin-bottom: 0; }
      .summary { color: #555; margin-bottom: 20px; }
      .section { margin-top: 30px; }
      table { border-collapse: collapse; width: 100%; margin-top: 10px; }
      th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; }
      th { background: #f7f7f7; text-align: left; }
      tr:nth-child(even) { background: #fafafa; }
      .delta-pos { color: #0a7f2e; font-weight: 600; }
      .delta-neg { color: #c62828; font-weight: 600; }
      .missing { color: #999; }
      .chip { display: inline-block; padding: 2px 6px; border-radius: 10px; background: #eee; font-size: 12px; margin-left: 6px; }
      .keypath { color: #333; }
      .mono { font-family: Menlo, Consolas, monospace; }
      .nav { margin: 10px 0 20px; }
      .nav a { margin-right: 12px; text-decoration: none; color: #0366d6; }
    </style>
    """

    html = []
    html.append("<!doctype html><html><head><meta charset='utf-8'>")
    html.append("<title>Space Technique Comparison Report</title>")
    html.append(css)
    html.append("</head><body>")
    html.append("<h1>Space Technique Comparison Report</h1>")
    html.append(f"<div class='summary'>Baseline: <span class='mono'>{html_escape(baseline)}</span> &middot; Sources: "
                + ", ".join(f"<span class='mono'>{html_escape(s)}</span>" for s in sources_in_order)
                + f" &middot; Keys: {total_keys} &middot; Changed: {changed_keys}</div>")

    # Navigation
    html.append("<div class='nav'>")
    for sec in sorted(by_section.keys()):
        anchor = sec.lower().replace(" ", "-")
        html.append(f"#{html_escape(anchor)}{html_escape(sec)}</a>")
    html.append("</div>")

    # Sections
    for sec in sorted(by_section.keys()):
        anchor = sec.lower().replace(" ", "-")
        html.append(f"<div class='section' id='{html_escape(anchor)}'>")
        html.append(f"<h2>{html_escape(sec)}</h2>")
        html.append("<table>")
        # Header
        head_cols = ["Group / Sub‑Group / Period", "Channel", "Metric", "Date Window"]
        html.append("<tr>" + "".join(f"<th>{h}</th>" for h in head_cols) +
                    "".join(f"<th>{html_escape(src)}</th>" for src in sources_in_order) +
                    "<th>Δ vs Baseline</th><th>%Δ vs Baseline</th></tr>")
        # Rows
        for k in by_section[sec]:
            meta = agg[k]["meta"]
            group_path = " / ".join(meta["group_path"])
            channel = meta["channel"]
            metric = meta["metric"]
            date_window = meta["date_window"]

            row_cells = [
                f"<td class='keypath'>{html_escape(group_path)}</td>",
                f"<td>{html_escape(channel)}</td>",
                f"<td>{html_escape(metric)}</td>",
                f"<td>{html_escape(date_window)}</td>",
            ]

            # per-source values
            base_val = agg[k]["values"].get(baseline)
            base_text = agg[k]["texts"].get(baseline) or ""
            for src in sources_in_order:
                val = agg[k]["values"].get(src)
                txt = agg[k]["texts"].get(src) or ""
                if val is None and not txt:
                    row_cells.append("<td class='missing'>–</td>")
                else:
                    row_cells.append(f"<td class='mono'>{html_escape(txt)}</td>")

            # delta vs baseline
            # For multi-source, show delta for last source vs baseline
            last_src = sources_in_order[-1]
            other_val = agg[k]["values"].get(last_src)
            delta_cell = "%s"
            pct_cell = "%s"
            if base_val is not None and other_val is not None:
                delta = other_val - base_val
                pct = (delta / base_val * 100.0) if base_val != 0 else None
                cls = "delta-pos" if delta > 0 else ("delta-neg" if delta < 0 else "")
                delta_cell = f"<td class='mono {cls}'>{delta:.6g}</td>"
                if pct is not None:
                    pct_cell = f"<td class='mono {cls}'>{pct:.4g}%</td>"
                else:
                    pct_cell = "<td class='mono'>n/a</td>"
            else:
                delta_cell = "<td class='missing'>–</td>"
                pct_cell = "<td class='missing'>–</td>"
            row_cells.append(delta_cell)
            row_cells.append(pct_cell)

            html.append("<tr>" + "".join(row_cells) + "</tr>")
        html.append("</table>")
        html.append("</div>")

    html.append("</body></html>")
    return "".join(html)

# -------------------------- CLI ---------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Compare multiple CSVs using the space technique and output an HTML report.")
    ap.add_argument("inputs", nargs="+", help="Input CSV files (exported from Excel)")
    ap.add_argument("--output", default="report.html", help="Output HTML file")
    ap.add_argument("--header-rows", type=int, default=None, help="Number of header tiers (auto if omitted)")
    ap.add_argument("--section-row", type=int, default=None, help="Row index for section labels (0-based; auto if omitted)")
    ap.add_argument("--min-blank-sep", type=int, default=2, help=">= this many blank header tiers forms a hard separator")
    ap.add_argument("--no-date-window", action="store_true", help="Do not parse 'MM/YY - MM/YY'; use raw header text")
    args = ap.parse_args()

    if len(args.inputs) < 2:
        print("Please provide at least two CSV files to compare.")
        return

    sources_in_order = args.inputs[:]  # baseline is first

    # Extract from each file
    all_records: List[Dict[str, Any]] = []
    for path in sources_in_order:
        grid = read_csv_grid(path)
        if not grid:
            print(f"Warning: {path} is empty; skipping.")
            continue
        hdr_rows = args.header_rows if args.header_rows is not None else detect_header_rows(grid)
        section_row = args.section_row if args.section_row is not None else first_non_empty_header_row(grid, hdr_rows)
        recs = extract_space_technique(
            grid,
            source_name=path,
            header_rows=hdr_rows,
            section_row=section_row,
            min_blank_sep=args.min_blank_sep,
            no_date_window=args.no_date_window
        )
        all_records.extend(recs)

    if not all_records:
        print("No records extracted from inputs.")
        return

    agg = compare_records(all_records, sources_in_order)
    html = generate_html_report(agg, sources_in_order)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote HTML report to {args.output}")

if __name__ == "__main__":
    main()
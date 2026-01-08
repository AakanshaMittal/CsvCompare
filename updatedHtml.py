import os
import sys
import csv
import io
import base64
import argparse
from html import escape
from typing import List, Dict, Tuple
from datetime import datetime
try:
   import pandas as pd  
except Exception:
   pd = None

def index_to_col_letters(idx: int) -> str:
   n = idx + 1
   letters: List[str] = []
   while n > 0:
       n, rem = divmod(n - 1, 26)
       letters.append(chr(ord("A") + rem))
   return "".join(reversed(letters))
def col_letters_to_index(col_letters: str) -> int:
   col_letters = col_letters.strip().upper()
   total = 0
   for ch in col_letters:
       total = total * 26 + (ord(ch) - ord("A") + 1)
   return total - 1
def cell_addr(row_idx_0based: int, col_idx_0based: int, row_offset_1based: int, col_offset_0based: int) -> str:
   return f"{index_to_col_letters(col_idx_0based + col_offset_0based)}{row_idx_0based + row_offset_1based}"
def forward_fill(values: List[str]) -> List[str]:
   current = ""
   ff: List[str] = []
   for v in values:
       v = (v or "").strip()
       if v:
           current = v
       ff.append(current)
   return ff
def read_csv_safe(path: str, delimiter: str) -> List[List[str]]:
   if not os.path.exists(path):
       raise FileNotFoundError(f"File not found: {path}")
   rows: List[List[str]] = []
   with open(path, newline="", encoding="utf-8") as f:
       reader = csv.reader(f, delimiter=delimiter)
       for row in reader:
           if any((cell or "").strip() for cell in row):
               rows.append([(cell or "").strip() for cell in row])
   return rows
def read_excel_safe(path: str) -> List[List[str]]:
   if pd is None:
       raise RuntimeError("pandas not available; cannot read Excel (.xlsx).")
   if not os.path.exists(path):
       raise FileNotFoundError(f"File not found: {path}")
   df = pd.read_excel(path, sheet_name=0, engine="openpyxl", dtype=str)
   df = df.fillna("")
   return [list(map(lambda x: (x or "").strip(), row)) for row in df.values.tolist()]
def read_table(path: str, delimiter: str) -> List[List[str]]:
   ext = os.path.splitext(path)[1].lower()
   if ext in (".xlsx", ".xls"):
       return read_excel_safe(path)
   return read_csv_safe(path, delimiter)
def build_composite_headers(
   rows: List[List[str]],
   group_row_1based: int,
   detail_row_1based: int,
   joiner: str = "_",
) -> List[str]:
   gi = group_row_1based - 1
   di = detail_row_1based - 1
   if gi < 0 or di < 0:
       raise ValueError("Header group/detail row indices must be >= 1.")
   if len(rows) <= gi or len(rows) <= di:
       raise IndexError(
           f"Header rows out of range. File has {len(rows)} rows but group row={group_row_1based}, detail row={detail_row_1based}."
       )
   header_group = rows[gi] if len(rows) > gi else []
   header_detail = rows[di] if len(rows) > di else []
   max_cols = max(len(header_group), len(header_detail), max((len(r) for r in rows), default=0))
   header_group = header_group + [""] * (max_cols - len(header_group))
   header_detail = header_detail + [""] * (max_cols - len(header_detail))
   ff_group = forward_fill(header_group)
   combined: List[str] = []
   for c in range(max_cols):
       g = ff_group[c].strip()
       d = header_detail[c].strip()
       if g and d:
           combined.append(f"{g}{joiner}{d}")
       elif d:
           combined.append(d)
       elif g:
           combined.append(g)
       else:
           combined.append("")
   return combined
def build_index_map(headers: List[str]) -> Tuple[Dict[str, List[int]], List[str]]:
   m: Dict[str, List[int]] = {}
   for i, h in enumerate(headers):
       h = (h or "").strip()
       if not h:
           continue
       m.setdefault(h, []).append(i)
   duplicates = sorted([h for h, idxs in m.items() if len(idxs) > 1])
   return m, duplicates

def compare_cells_name_based(
   rows1: List[List[str]],
   rows2: List[List[str]],
   headers1: List[str],
   headers2: List[str],
   data_start_row: int,
   start_col_letters: str,
) -> Dict[str, object]:
   col_offset = col_letters_to_index(start_col_letters)
   data_start_index = data_start_row - 1
   max_rows = max(len(rows1), len(rows2))
   map1, dups1 = build_index_map(headers1)
   map2, dups2 = build_index_map(headers2)
   headers_in_both = sorted(set(map1.keys()) & set(map2.keys()))
   missing_in_file2 = sorted(set(map1.keys()) - set(map2.keys()))
   missing_in_file1 = sorted(set(map2.keys()) - set(map1.keys()))
   matches = 0
   mismatches = 0
   mismatch_details: List[Tuple[str, int, str, str, str, str]] = []
   mismatch_count_by_header: Dict[str, int] = {}
   for header in headers_in_both:
       idxs1 = map1[header]
       idxs2 = map2[header]
       pair_count = min(len(idxs1), len(idxs2))
       for k in range(pair_count):
           i1 = idxs1[k]
           i2 = idxs2[k]
           for r in range(data_start_index, max_rows):
               row1 = rows1[r] if r < len(rows1) else []
               row2 = rows2[r] if r < len(rows2) else []
               v1 = row1[i1] if i1 < len(row1) else ""
               v2 = row2[i2] if i2 < len(row2) else ""
               if v1 == v2:
                   matches += 1
               else:
                   mismatches += 1
                   mismatch_details.append((
                       header,
                       r + 1,
                       cell_addr(r, i1, data_start_row, col_offset),
                       cell_addr(r, i2, data_start_row, col_offset),
                       v1,
                       v2
                   ))
                   mismatch_count_by_header[header] = mismatch_count_by_header.get(header, 0) + 1
   return {
       "headers_in_both": headers_in_both,
       "missing_in_file2": missing_in_file2,
       "missing_in_file1": missing_in_file1,
       "dups1": dups1,
       "dups2": dups2,
       "matches": matches,
       "mismatches": mismatches,
       "mismatch_details": mismatch_details,
       "mismatch_count_by_header": mismatch_count_by_header,
       "rows_count1": len(rows1),
       "rows_count2": len(rows2),
       "max_cols1": max((len(r) for r in rows1), default=0),
       "max_cols2": max((len(r) for r in rows2), default=0),
   }

def render_chart_png_base64(matches: int, mismatches: int, top_mismatch_items: List[Tuple[str, int]]) -> Dict[str, str]:
   
   import matplotlib
   matplotlib.use("Agg")
   import matplotlib.pyplot as plt
   result: Dict[str, str] = {}
   
   fig1, ax1 = plt.subplots(figsize=(4.5, 3.2), dpi=120)
   ax1.bar(["Matches", "Mismatches"], [matches, mismatches], color=["#4CAF50", "#E53935"])
   ax1.set_title("Matches vs. Mismatches")
   ax1.set_ylabel("Count")
   ax1.grid(axis="y", linestyle="--", alpha=0.35)
   buf1 = io.BytesIO()
   fig1.tight_layout()
   fig1.savefig(buf1, format="png")
   plt.close(fig1)
   result["match_bar"] = base64.b64encode(buf1.getvalue()).decode("ascii")
   if top_mismatch_items:
       labels = [h for (h, c) in top_mismatch_items]
       counts = [c for (h, c) in top_mismatch_items]
       fig2, ax2 = plt.subplots(figsize=(6, max(2.5, 0.35 * len(labels) + 1.5)), dpi=120)
       ax2.barh(labels, counts, color="#FB8C00")
       ax2.set_title("Top Headers by Mismatch Count")
       ax2.set_xlabel("Mismatches")
       ax2.grid(axis="x", linestyle="--", alpha=0.35)
       fig2.tight_layout()
       buf2 = io.BytesIO()
       fig2.savefig(buf2, format="png")
       plt.close(fig2)
       result["top_headers"] = base64.b64encode(buf2.getvalue()).decode("ascii")
   else:
       result["top_headers"] = ""  # none
   return result
def write_html_report_only_mismatches(
   html_report_file: str,
   file1: str,
   file2: str,
   start_row: int,
   start_col_letters: str,
   header_info: Dict[str, int],
   comparison_result: Dict[str, object],
) -> None:
   esc = lambda x: escape(str(x))
   matches = comparison_result["matches"]
   mismatches = comparison_result["mismatches"]
   mismatch_details = comparison_result["mismatch_details"]
   mismatch_by_header = comparison_result["mismatch_count_by_header"]
   top_items = sorted(mismatch_by_header.items(), key=lambda kv: kv[1], reverse=True)[:10]
   charts = render_chart_png_base64(matches, mismatches, top_items)
   match_bar_img = charts.get("match_bar", "")
   top_headers_img = charts.get("top_headers", "")
   summary_rows = [
       ("File 1", file1),
       ("File 2", file2),
       ("Data start row", start_row),
       ("Start column letters", start_col_letters),
       ("Header GROUP row (File1)", header_info["header_group_row_file1"]),
       ("Header DETAIL row (File1)", header_info["header_detail_row_file1"]),
       ("Header GROUP row (File2)", header_info["header_group_row_file2"]),
       ("Header DETAIL row (File2)", header_info["header_detail_row_file2"]),
       ("Composite Header Joiner", header_info["header_joiner"]),
       ("Rows in File1", comparison_result["rows_count1"]),
       ("Rows in File2", comparison_result["rows_count2"]),
       ("Max Columns in File1", comparison_result["max_cols1"]),
       ("Max Columns in File2", comparison_result["max_cols2"]),
       ("Headers present in BOTH (unique names)", len(comparison_result["headers_in_both"])),
       ("Duplicate headers in File1", ", ".join(comparison_result["dups1"]) or "None"),
       ("Duplicate headers in File2", ", ".join(comparison_result["dups2"]) or "None"),
       ("Missing headers in File2", len(comparison_result["missing_in_file2"])),
       ("Missing headers in File1", len(comparison_result["missing_in_file1"])),
       ("Total Cells Compared (matching headers only)", matches + mismatches),
       ("Matches", matches),
       ("Mismatches", mismatches),
   ]
   summary_body = "\n".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in summary_rows)
   mismatch_body = "\n".join(
       f"<tr><td>{esc(h)}</td><td>{esc(r)}</td><td>{esc(c1)}</td><td>{esc(c2)}</td>"
       f"<td>{esc(v1)}</td><td>{esc(v2)}</td></tr>"
       for (h, r, c1, c2, v1, v2) in mismatch_details
   )
   if not mismatch_body:
       mismatch_body = "<tr><td colspan='6'>No mismatches found.</td></tr>"
   top_header_list = "\n".join(
       f"<tr><td>{esc(h)}</td><td>{esc(c)}</td></tr>" for (h, c) in top_items
   ) or "<tr><td colspan='2'>No header mismatches.</td></tr>"
   html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CSV/Excel Comparison Report</title>
<style>
 body {{
   font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
   margin: 24px; color: #222;
 }}
 h1, h2 {{ margin: 0.2em 0 0.4em; }}
 table.grid {{
   border-collapse: collapse; width: 100%; margin-bottom: 20px;
 }}
 table.grid th, table.grid td {{
   border: 1px solid #ddd; padding: 8px 10px; text-align: left;
   vertical-align: top; word-break: break-word;
 }}
 table.grid thead th {{ background: #f0f0f0; }}
 .summary {{
   border: 1px solid #ddd; border-radius: 8px; padding: 16px;
   background: #fafafa; margin-bottom: 16px;
 }}
 .pill {{
   display: inline-block; padding: 2px 8px; border-radius: 12px;
   font-size: 12px; margin-left: 8px;
 }}
 .ok {{ background: #e8f5e9; color: #1b5e20; border: 1px solid #c8e6c9; }}
 .err {{ background: #ffebee; color: #b71c1c; border: 1px solid #ffcdd2; }}
 .charts {{ display: flex; gap: 24px; flex-wrap: wrap; }}
 .chart-box {{ flex: 1 1 320px; border: 1px solid #ddd; border-radius: 8px; padding: 12px; }}
 footer {{ margin-top: 32px; color: #666; font-size: 12px; }}
</style>
</head>
<body>
<h1>Comparison Report</h1>
<div class="summary">
 <p><strong>Result:</strong>
   <span class="pill {'ok' if mismatches == 0 else 'err'}">
     {"Perfect match" if mismatches == 0 else f"{mismatches} mismatches"}
   </span>
 </p>
 <table class="grid">
   <thead><tr><th>Metric</th><th>Value</th></tr></thead>
   <tbody>
     {summary_body}
   </tbody>
 </table>
</div>
<h2>Charts</h2>
<div class="charts">
 <div class="chart-box">
   <h3>Matches vs. Mismatches</h3>
   {"data:image/png;base64," if match_bar_img else "<p>(chart unavailable)</p>"}
 </div>
 <div class="chart-box">
   <h3>Top Headers by Mismatch Count</h3>
   {"data:image/png;base64," if top_headers_img else "<p>No header mismatches.</p>"}
   <table class="grid" style="margin-top:12px;">
     <thead><tr><th>Header</th><th>Mismatches</th></tr></thead>
     <tbody>{top_header_list}</tbody>
   </table>
 </div>
</div>
<h2>Value Mismatch Details (only)</h2>
<table class="grid">
 <thead>
   <tr>
     <th>Header</th><th>Row</th><th>File1 Cell</th><th>File2 Cell</th><th>File1 Value</th><th>File2 Value</th>
   </tr>
 </thead>
 <tbody>
   {mismatch_body}
 </tbody>
</table>
<footer>
 Generated: {escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}.
 Data start row: {escape(str(start_row))}. Start column letters: {escape(str(start_col_letters))}.
</footer>
</body>
</html>
"""
   
   parent = os.path.dirname(html_report_file)
   if parent and not os.path.exists(parent):
       os.makedirs(parent, exist_ok=True)
   with open(html_report_file, "w", encoding="utf-8") as f:
       f.write(html_doc)

def parse_args():
   p = argparse.ArgumentParser(description="Compare two CSV/Excel files and generate an HTML report with only mismatch details and charts.")
   p.add_argument("--file1", required=True, help="Path to first CSV/XLSX file")
   p.add_argument("--file2", required=True, help="Path to second CSV/XLSX file")
   p.add_argument("--delimiter", default=",", help="CSV delimiter (default ',')")
   p.add_argument("--start-col", default="A", help="Starting column letters for data (default 'A')")
   p.add_argument("--start-row", default=3, type=int, help="Starting row number for data comparison (default 4)")
   p.add_argument("--header-group-row-file1", default=1, type=int, help="Header GROUP row for File1 (default 2)")
   p.add_argument("--header-detail-row-file1", default=2, type=int, help="Header DETAIL row for File1 (default 3)")
   p.add_argument("--header-group-row-file2", default=1, type=int, help="Header GROUP row for File2 (default 2)")
   p.add_argument("--header-detail-row-file2", default=2, type=int, help="Header DETAIL row for File2 (default 3)")
   p.add_argument("--joiner", default="_", help="Composite header joiner (default '_')")
   p.add_argument("--html", default="comparison_report.html", help="Output HTML report path")
   return p.parse_args()
def main():
   args = parse_args()
   
   for v, name in [
       (args.start_row, "start_row"),
       (args.header_group_row_file1, "header_group_row_file1"),
       (args.header_detail_row_file1, "header_detail_row_file1"),
       (args.header_group_row_file2, "header_group_row_file2"),
       (args.header_detail_row_file2, "header_detail_row_file2"),
   ]:
       if v <= 0:
           raise ValueError(f"{name} must be positive.")
   
   rows1 = read_table(args.file1, args.delimiter)
   rows2 = read_table(args.file2, args.delimiter)
   
   headers1 = build_composite_headers(rows1, args.header_group_row_file1, args.header_detail_row_file1, args.joiner)
   headers2 = build_composite_headers(rows2, args.header_group_row_file2, args.header_detail_row_file2, args.joiner)
   
   comparison_result = compare_cells_name_based(
       rows1, rows2, headers1, headers2, args.start_row, args.start_col
   )
   
   write_html_report_only_mismatches(
       html_report_file=args.html,
       file1=args.file1,
       file2=args.file2,
       start_row=args.start_row,
       start_col_letters=args.start_col,
       header_info={
           "header_group_row_file1": args.header_group_row_file1,
           "header_detail_row_file1": args.header_detail_row_file1,
           "header_group_row_file2": args.header_group_row_file2,
           "header_detail_row_file2": args.header_detail_row_file2,
           "header_joiner": args.joiner,
       },
       comparison_result=comparison_result,
   )
   print(f"Done. Matches={comparison_result['matches']} | Mismatches={comparison_result['mismatches']}")
   print(f"HTML report saved to: {args.html}")
if __name__ == "__main__":
   main()
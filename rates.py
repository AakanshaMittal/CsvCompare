import os

import csv

import argparse

import re

from typing import List, Dict

from html import escape
 
try:

    import pandas as pd

except Exception:

    pd = None
 
 
# ------------------ NORMALIZATION ------------------
 
def clean_text(text: str) -> str:

    if not text:

        return ""

    return text.replace("\ufeff", "").strip()
 
 
def normalize_header(h: str) -> str:

    h = clean_text(h).lower()

    return re.sub(r"[^a-z0-9]", "", h)
 
 
def normalize_year_header(header: str) -> str:

    raw = clean_text(header)

    h = raw.lower()
 
    # Year1, Year 2, YEAR3

    m = re.search(r"year\s*(\d)", h)

    if m:

        return f"YEAR_{m.group(1)}"
 
    # mm/yy-mm/yy  (01/27-12/27)

    m = re.search(r"(\d{2})/(\d{2})-(\d{2})/(\d{2})", h)

    if m:

        start_year = int(m.group(2))

        base_year = 27  # 🔴 change if first year is not 27

        year_no = (start_year - base_year) + 1

        if 1 <= year_no <= 10:

            return f"YEAR_{year_no}"
 
    return raw
 
 
# ------------------ FILE READERS ------------------
 
def read_csv_safe(path: str, delimiter: str) -> List[List[str]]:

    rows = []

    with open(path, newline="", encoding="utf-8-sig") as f:

        reader = csv.reader(f, delimiter=delimiter)

        for r in reader:

            rows.append([(c or "").strip() for c in r])

    return rows
 
 
def read_excel_safe(path: str) -> List[List[str]]:

    if pd is None:

        raise RuntimeError("pandas not installed. Cannot read Excel.")

    df = pd.read_excel(path, sheet_name=0, dtype=str)

    df = df.fillna("")

    return [list(map(lambda x: (x or "").strip(), r)) for r in df.values.tolist()]
 
 
def read_table(path: str, delimiter: str):

    ext = os.path.splitext(path)[1].lower()

    if ext in (".xlsx", ".xls"):

        return read_excel_safe(path)

    return read_csv_safe(path, delimiter)
 
 
# ------------------ HEADER BUILDER ------------------
 
def forward_fill(values: List[str]) -> List[str]:

    out, cur = [], ""

    for v in values:

        v = (v or "").strip()

        if v:

            cur = v

        out.append(cur)

    return out
 
 
def build_composite_headers(rows, group_row, detail_row, joiner="_"):

    g = forward_fill(rows[group_row - 1])

    d = rows[detail_row - 1]
 
    max_cols = max(len(g), len(d))

    g += [""] * (max_cols - len(g))

    d += [""] * (max_cols - len(d))
 
    headers = []

    group_year_counter = {}
 
    for i in range(max_cols):
 
        group = clean_text(g[i])

        detail = clean_text(d[i])
 
        if group and detail:

            raw = f"{group}{joiner}{detail}"

        elif detail:

            raw = detail

        else:

            raw = group
 
        # -------- YEAR NORMALIZATION --------

        low = raw.lower()
 
        if any(x in low for x in ["year", "/", "-"]):  # year or date column

            group_key = normalize_header(group)
 
            if group_key not in group_year_counter:

                group_year_counter[group_key] = 1

            else:

                group_year_counter[group_key] += 1
 
            year_no = group_year_counter[group_key]

            final_header = f"{group}_YEAR_{year_no}"

        else:

            final_header = raw
 
        headers.append(final_header)
 
    return headers

 
 
 
def build_index(headers: List[str]) -> Dict[str, int]:

    return {h: i for i, h in enumerate(headers) if h}
 
 
# ------------------ ROW KEY (AUTO DETECT) ------------------
 
def build_row_map(rows, headers, data_start_row):
 
    norm_map = {normalize_header(h): i for i, h in enumerate(headers)}
 
    def find_col(keyword):

        key = normalize_header(keyword)

        for h, idx in norm_map.items():

            if key in h:

                return idx

        return None
 
    drug_col = find_col("drugname")

    ndc_col = find_col("ndc11")
 
    if drug_col is None or ndc_col is None:

        print("\n--- DEBUG HEADERS ---")

        for h in headers:

            print(repr(h))

        raise ValueError("Could not auto-detect Drug Name or NDC11 column")
 
    print("\n✔ Row key columns detected:")

    print("Drug Name ->", headers[drug_col])

    print("NDC11     ->", headers[ndc_col])
 
    row_map = {}

    for r in range(data_start_row - 1, len(rows)):

        row = rows[r]

        d = row[drug_col] if drug_col < len(row) else ""

        n = row[ndc_col] if ndc_col < len(row) else ""

        key = f"{d}||{n}".strip()

        if key:

            row_map[key] = row
 
    return row_map
 
 
# ------------------ COMPARISON ------------------
 
def compare_by_row_key(headers1, headers2, map1, map2):
 
    common_headers = sorted(set(headers1) & set(headers2))

    idx1, idx2 = build_index(headers1), build_index(headers2)
 
    mismatches = []

    match_count = 0
 
    common_keys = set(map1) & set(map2)

    extra_file1 = sorted(set(map1) - set(map2))

    extra_file2 = sorted(set(map2) - set(map1))
 
    for key in common_keys:

        r1, r2 = map1[key], map2[key]

        for h in common_headers:

            i1, i2 = idx1[h], idx2[h]

            v1 = r1[i1] if i1 < len(r1) else ""

            v2 = r2[i2] if i2 < len(r2) else ""

            if v1 != v2:

                mismatches.append((key, h, v1, v2))

            else:

                match_count += 1
 
    return common_headers, mismatches, extra_file1, extra_file2, match_count
 
 
# ------------------ HTML REPORT ------------------
 
def write_html_report(path, mismatches, extra1, extra2, headers1, headers2):
 
    miss_rows = "".join(

        f"<tr><td>{escape(k)}</td><td>{escape(h)}</td><td>{escape(v1)}</td><td>{escape(v2)}</td></tr>"

        for k, h, v1, v2 in mismatches

    )
 
    html = f"""
<html>
<head>
<title>UAT Comparison Report</title>
<style>

body {{font-family:Segoe UI; margin:20px}}

table {{border-collapse:collapse; width:100%}}

th,td {{border:1px solid #ccc; padding:6px}}

th {{background:#eee}}
</style>
</head>
<body>
 
<h2>Summary</h2>
<p><b>Total mismatches:</b> {len(mismatches)}</p>
<p><b>Extra rows in File1:</b> {len(extra1)}</p>
<p><b>Extra rows in File2:</b> {len(extra2)}</p>
 
<h3>Extra Columns</h3>
<p>Only in File1: {sorted(set(headers1)-set(headers2))}</p>
<p>Only in File2: {sorted(set(headers2)-set(headers1))}</p>
 
<h2>Mismatch Details</h2>
<table>
<tr><th>Row Key</th><th>Column</th><th>File1</th><th>File2</th></tr>

{miss_rows}
</table>
 
</body></html>

"""
 
    with open(path, "w", encoding="utf-8") as f:

        f.write(html)
 
 
# ------------------ MAIN ------------------
 
def main():
 
    ap = argparse.ArgumentParser()

    ap.add_argument("--file1", required=True)

    ap.add_argument("--file2", required=True)

    ap.add_argument("--delimiter", default=",")

    ap.add_argument("--group-row1", type=int, default=1)

    ap.add_argument("--detail-row1", type=int, default=2)

    ap.add_argument("--group-row2", type=int, default=1)

    ap.add_argument("--detail-row2", type=int, default=2)

    ap.add_argument("--data-row", type=int, default=3)

    ap.add_argument("--html", default="uat_report.html")

    args = ap.parse_args()
 
    rows1 = read_table(args.file1, args.delimiter)

    rows2 = read_table(args.file2, args.delimiter)
 
    headers1 = build_composite_headers(rows1, args.group_row1, args.detail_row1)

    headers2 = build_composite_headers(rows2, args.group_row2, args.detail_row2)
 
    print("\n--- HEADER VALIDATION ---")

    print("Missing in File2:", sorted(set(headers1) - set(headers2)))

    print("Missing in File1:", sorted(set(headers2) - set(headers1)))

    print("\nSample normalized headers:", headers1[:12])
 
    map1 = build_row_map(rows1, headers1, args.data_row)

    map2 = build_row_map(rows2, headers2, args.data_row)
 
    common_headers, mismatches, extra1, extra2, matches = compare_by_row_key(

        headers1, headers2, map1, map2

    )
 
    print("\n--- ROW VALIDATION ---")

    print("Extra rows in File1:", len(extra1))

    print("Extra rows in File2:", len(extra2))

    print("Matches:", matches)

    print("Mismatches:", len(mismatches))
 
    write_html_report(args.html, mismatches, extra1, extra2, headers1, headers2)

    print("\nHTML report generated:", args.html)
 
 
if __name__ == "__main__":

    main()

 
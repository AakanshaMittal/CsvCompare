import os

import csv

import argparse

import re

from typing import List, Dict

from html import escape

import math
 
try:

    import pandas as pd

except Exception:

    pd = None
 
 
def clean_text(text: str) -> str:

    if not text:

        return ""

    return text.replace("\ufeff", "").strip()
 
 
def normalize_header(h: str) -> str:

    h = clean_text(h).lower()

    return re.sub(r"[^a-z0-9]", "", h)
 
 
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
 
        low = raw.lower()
 
        if any(x in low for x in ["year", "/", "-"]):

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

        raise ValueError("Could not auto-detect Drug Name or NDC11 column")
 
    row_map = {}
 
    for r in range(data_start_row - 1, len(rows)):

        row = rows[r]

        d = row[drug_col] if drug_col < len(row) else ""

        n = row[ndc_col] if ndc_col < len(row) else ""

        key = f"{d}||{n}".strip()

        if key:

            row_map[key] = row
 
    return row_map
 
 
def clean_numeric(val: str) -> str:

    if not val:

        return ""

    return val.replace("$", "").replace(",", "").strip()
 
 
def is_number(val: str) -> bool:

    try:

        float(clean_numeric(val))

        return True

    except:

        return False
 
 
def truncate_2(val: float) -> float:

    return math.trunc(val * 100) / 100
 
 
def numeric_major_mismatch(v1: str, v2: str) -> bool:

    try:

        n1 = truncate_2(float(clean_numeric(v1)))

        n2 = truncate_2(float(clean_numeric(v2)))

        return n1 != n2

    except:

        return False
 
 
def integer_part_diff(v1: str, v2: str) -> bool:

    try:

        return int(float(clean_numeric(v1))) != int(float(clean_numeric(v2)))

    except:

        return False
 
 
def extract_group(header: str) -> str:

    if "_" in header:

        return header.split("_")[0]

    return header
 
 
def compare_by_row_key(headers1, headers2, map1, map2):

    common_headers = sorted(set(headers1) & set(headers2))

    idx1, idx2 = build_index(headers1), build_index(headers2)
 
    mismatches = []

    group_counter = {}
 
    common_keys = set(map1) & set(map2)

    extra_file1 = sorted(set(map1) - set(map2))

    extra_file2 = sorted(set(map2) - set(map1))
 
    for key in common_keys:

        r1, r2 = map1[key], map2[key]
 
        for h in common_headers:

            i1, i2 = idx1[h], idx2[h]

            v1 = r1[i1] if i1 < len(r1) else ""

            v2 = r2[i2] if i2 < len(r2) else ""

            v1 = v1.strip()

            v2 = v2.strip()
 
            mismatch = False

            highlight = False
 
            if is_number(v1) and is_number(v2):

                if numeric_major_mismatch(v1, v2):

                    mismatch = True

                    if integer_part_diff(v1, v2):

                        highlight = True

            else:

                if v1 != v2:

                    mismatch = True
 
            if mismatch:

                mismatches.append((key, h, v1, v2, highlight))

                grp = extract_group(h)

                group_counter[grp] = group_counter.get(grp, 0) + 1
 
    return mismatches, group_counter, extra_file1, extra_file2
 
 
def write_html_report(path, mismatches, group_counter, extra1, extra2, headers1, headers2, file1, file2):

    miss_rows = ""

    for k, h, v1, v2, highlight in mismatches:

        style = "background:#ffd6d6;font-weight:600" if highlight else ""

        miss_rows += f"<tr style='{style}'><td>{escape(k)}</td><td>{escape(h)}</td><td>{escape(v1)}</td><td>{escape(v2)}</td></tr>"
 
    group_rows = "".join(

        f"<tr><td>{escape(g)}</td><td>{c}</td></tr>"

        for g, c in sorted(group_counter.items())

    )
 
    only1 = sorted(set(headers1) - set(headers2))

    only2 = sorted(set(headers2) - set(headers1))
 
    html = f"""
<html>
<head>
<title>Data Validation Report</title>
<style>

body {{font-family:Segoe UI; margin:20px}}

table {{border-collapse:collapse; width:100%; margin-bottom:25px}}

th,td {{border:1px solid #ccc; padding:6px}}

th {{background:#eee}}
</style>
</head>
<body>
 
<h2>Data Validation Report</h2>
<p><b>Total mismatches:</b> {len(mismatches)}</p>
<p><b>Extra rows in {escape(os.path.basename(file1))}:</b> {len(extra1)}</p>
<p><b>Extra rows in {escape(os.path.basename(file2))}:</b> {len(extra2)}</p>
 
<h3>Extra Columns</h3>
<p><b>Only in {escape(os.path.basename(file1))}:</b> {only1}</p>
<p><b>Only in {escape(os.path.basename(file2))}:</b> {only2}</p>
 
<h2>Group Summary</h2>
<table>
<tr><th>Group</th><th>Difference Count</th></tr>

{group_rows}
</table>
 
<h2>Mismatch Details</h2>
<table>
<tr><th>Row Key</th><th>Column</th><th>{escape(os.path.basename(file1))}</th><th>{escape(os.path.basename(file2))}</th></tr>

{miss_rows}
</table>
 
</body></html>

"""
 
    with open(path, "w", encoding="utf-8") as f:

        f.write(html)
 
 
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
 
    map1 = build_row_map(rows1, headers1, args.data_row)

    map2 = build_row_map(rows2, headers2, args.data_row)
 
    mismatches, group_counter, extra1, extra2 = compare_by_row_key(headers1, headers2, map1, map2)
 
    write_html_report(

        args.html,

        mismatches,

        group_counter,

        extra1,

        extra2,

        headers1,

        headers2,

        args.file1,

        args.file2

    )
 
    print("HTML report generated:", args.html)
 
 
if __name__ == "__main__":

    main()
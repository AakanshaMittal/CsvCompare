import csv

import os

from collections import defaultdict

from datetime import datetime

from html import escape
 
############################

# -------- CONFIG --------#

############################
 
FILE1 = "RPQ22.07.csv"   # RA Output

FILE2 = "RPT_RPT1315532890837IB_20260110_RatesPerQuantity.csv"  # Report

OUTPUT_HTML = "RA_vs_Report_KeyBased_Comparison.html"
 
KEY_COLUMNS = ["Formulary", "NDC11"]   # 🔑 business key

DATA_START_ROW = 1  # 0-based after header, usually 1
 
############################

# -------- UTILS ---------#

############################
 
def read_csv(path):

    with open(path, newline="", encoding="utf-8") as f:

        reader = csv.reader(f)

        rows = [row for row in reader if any(cell.strip() for cell in row)]

    return rows
 
def normalize(text):

    return (text or "").strip().lower()
 
def header_index_map(headers):

    return {normalize(h): i for i, h in enumerate(headers)}
 
############################

# ---- CORE FUNCTIONS ----#

############################
 
def build_row_map(rows, headers, key_cols):

    """

    Builds:

      (Formulary, NDC11) -> full row

    """

    hmap = header_index_map(headers)

    key_indexes = [hmap[normalize(k)] for k in key_cols]
 
    row_map = {}

    duplicates = []
 
    for r in rows:

        key = tuple((r[i] if i < len(r) else "").strip() for i in key_indexes)

        if key in row_map:

            duplicates.append(key)

        else:

            row_map[key] = r
 
    return row_map, duplicates
 
 
def compare_key_based(headers1, data1, headers2, data2):
 
    hmap1 = header_index_map(headers1)

    hmap2 = header_index_map(headers2)
 
    common_headers = [h for h in headers1 if normalize(h) in hmap2]
 
    map1, dup1 = build_row_map(data1, headers1, KEY_COLUMNS)

    map2, dup2 = build_row_map(data2, headers2, KEY_COLUMNS)
 
    keys1 = set(map1.keys())

    keys2 = set(map2.keys())
 
    missing_in_report = sorted(keys1 - keys2)

    extra_in_report = sorted(keys2 - keys1)

    common_keys = sorted(keys1 & keys2)
 
    mismatches = []
 
    match_count = 0

    mismatch_count = 0
 
    for key in common_keys:

        r1 = map1[key]

        r2 = map2[key]
 
        for h in common_headers:

            i1 = hmap1[normalize(h)]

            i2 = hmap2[normalize(h)]
 
            v1 = r1[i1] if i1 < len(r1) else ""

            v2 = r2[i2] if i2 < len(r2) else ""
 
            if v1 == v2:

                match_count += 1

            else:

                mismatch_count += 1

                mismatches.append((key, h, v1, v2))
 
    return {

        "matches": match_count,

        "mismatches": mismatch_count,

        "missing_in_report": missing_in_report,

        "extra_in_report": extra_in_report,

        "duplicates_file1": dup1,

        "duplicates_file2": dup2,

        "mismatch_details": mismatches,

        "common_keys": len(common_keys)

    }
 
############################

# -------- REPORT --------#

############################
 
def generate_html(result):
 
    def row(t1, t2):

        return f"<tr><td>{escape(str(t1))}</td><td>{escape(str(t2))}</td></tr>"
 
    summary = ""

    summary += row("Common Drugs Matched", result["common_keys"])

    summary += row("Total Matches", result["matches"])

    summary += row("Total Mismatches", result["mismatches"])

    summary += row("Missing in Report", len(result["missing_in_report"]))

    summary += row("Extra in Report", len(result["extra_in_report"]))

    summary += row("Duplicate Keys in RA", len(result["duplicates_file1"]))

    summary += row("Duplicate Keys in Report", len(result["duplicates_file2"]))
 
    missing_rows = "".join(row(k, "") for k in result["missing_in_report"]) or "<tr><td colspan=2>None</td></tr>"

    extra_rows = "".join(row(k, "") for k in result["extra_in_report"]) or "<tr><td colspan=2>None</td></tr>"
 
    mismatch_rows = ""

    for k, h, v1, v2 in result["mismatch_details"]:

        mismatch_rows += f"<tr><td>{escape(str(k))}</td><td>{escape(h)}</td><td>{escape(v1)}</td><td>{escape(v2)}</td></tr>"
 
    if not mismatch_rows:

        mismatch_rows = "<tr><td colspan=4>No mismatches</td></tr>"
 
    html = f"""
<html>
<head>
<title>RA vs Report Comparison</title>
<style>

        body {{font-family: Arial; padding:20px;}}

        table {{border-collapse: collapse; width:100%; margin-bottom:20px;}}

        th, td {{border:1px solid #ccc; padding:8px;}}

        th {{background:#f2f2f2;}}
</style>
</head>
<body>
 
    <h1>RA vs Report – Key Based Comparison</h1>
<p><b>Key Used:</b> {KEY_COLUMNS}</p>
<p><b>Generated:</b> {datetime.now()}</p>
 
    <h2>Summary</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>

        {summary}
</table>
 
    <h2>Missing in Report</h2>
<table><tr><th>Key</th><th></th></tr>{missing_rows}</table>
 
    <h2>Extra in Report</h2>
<table><tr><th>Key</th><th></th></tr>{extra_rows}</table>
 
    <h2>Value Mismatches</h2>
<table>
<tr><th>(Formulary, NDC11)</th><th>Column</th><th>RA Output</th><th>Report</th></tr>

    {mismatch_rows}
</table>
 
    </body>
</html>

    """
 
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:

        f.write(html)
 
 
############################

# --------- MAIN ---------#

############################
 
def main():

    rows1 = read_csv(FILE1)

    rows2 = read_csv(FILE2)
 
    headers1 = rows1[0]

    headers2 = rows2[0]
 
    data1 = rows1[DATA_START_ROW:]

    data2 = rows2[DATA_START_ROW:]
 
    result = compare_key_based(headers1, data1, headers2, data2)
 
    generate_html(result)
 
    print("✅ Comparison completed")

    print("📄 Report generated:", OUTPUT_HTML)
 
 
if __name__ == "__main__":

    main()

 
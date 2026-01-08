import csv

import math

from collections import defaultdict, OrderedDict
 
# =====================================================

# UTILITIES

# =====================================================
 
def is_blank(x):

    return x is None or str(x).strip() == ""
 
def is_number(x):

    try:

        float(str(x).replace(",", ""))

        return True

    except:

        return False
 
def to_float(x):

    try:

        return float(str(x).replace(",", ""))

    except:

        return None
 
def esc(x):

    return "" if x is None else str(x).replace("&","&amp;").replace("<","&lt;")
 
def read_csv(path):

    with open(path, newline="", encoding="utf-8-sig") as f:

        rows = list(csv.reader(f))

    max_len = max(len(r) for r in rows)

    return [r + [""] * (max_len - len(r)) for r in rows]
 
# =====================================================

# SECTION DETECTION

# =====================================================
 
def detect_sections(grid, section_row=0):

    section_by_col = {}

    last = ""

    for c in range(len(grid[0])):

        if not is_blank(grid[section_row][c]):

            last = grid[section_row][c].strip()

        section_by_col[c] = last

    return section_by_col
 
# =====================================================

# TABLE DETECTION

# =====================================================
 
def find_tables(grid, start_row=1):

    tables = []

    r = start_row

    while r < len(grid):

        if all(is_blank(x) for x in grid[r]):

            r += 1

            continue

        top = r

        while r < len(grid) and not all(is_blank(x) for x in grid[r]):

            r += 1

        tables.append((top, r - 1))

        r += 1

    return tables
 
def forward_fill(row):

    out, last = [], ""

    for x in row:

        if not is_blank(x):

            last = x.strip()

        out.append(last)

    return out
 
# =====================================================

# EXTRACTION

# =====================================================
 
def extract_records(grid, source):

    section_map = detect_sections(grid)

    records = []
 
    for top, bottom in find_tables(grid):

        headers = []

        data_start = None
 
        for r in range(top, bottom + 1):

            if any(is_number(x) for x in grid[r]):

                data_start = r

                break

            headers.append(r)
 
        if len(headers) < 3:

            continue
 
        group = forward_fill(grid[headers[0]])

        sub_group = forward_fill(grid[headers[1]])

        period = forward_fill(grid[headers[2]])
 
        for r in range(data_start, bottom + 1):

            row = grid[r]

            nums = [c for c,v in enumerate(row) if is_number(v)]

            if not nums:

                continue
 
            channel = row[nums[0] - 1].strip()
 
            for c in nums:

                records.append({

                    "source": source,

                    "section": section_map[c],

                    "group": group[c],

                    "sub_group": sub_group[c],

                    "period": period[c],

                    "channel": channel,

                    "value": to_float(row[c]),

                    "raw": row[c]

                })

    return records
 
# =====================================================

# COMPARISON + PIVOT

# =====================================================
 
def key(r):

    return (r["section"], r["group"], r["sub_group"], r["channel"], r["period"])
 
def pivot(records, sources):

    data = defaultdict(lambda: defaultdict(dict))

    mismatches = set()
 
    for r in records:

        data[(r["section"], r["group"], r["sub_group"])][r["channel"]][(r["period"], r["source"])] = r
 
    for sg, chs in data.items():

        for ch, vals in chs.items():

            periods = set(p for p,s in vals)

            for p in periods:

                if all((p,s) in vals for s in sources):

                    v1 = vals[(p,sources[0])]["value"]

                    v2 = vals[(p,sources[1])]["value"]

                    if not math.isclose(v1, v2, rel_tol=1e-9):

                        mismatches.add(sg)

    return data, mismatches
 
# =====================================================

# HTML RENDERING

# =====================================================
 
def render_tables(pivoted, mismatches, sources):

    html = []

    html.append("""
<html><head><style>

    body { font-family: Arial; }

    h2 { background:#e6f2ff; padding:6px; }

    h3 { margin-top:25px; }

    .wrap { display:flex; gap:40px; margin-bottom:35px; }

    table { border-collapse:collapse; width:45%; }

    th,td { border:1px solid #aaa; padding:6px; text-align:center; }

    .bad table { background:#ffe0e0; }
</style></head><body>

    """)
 
    by_section = defaultdict(dict)

    for (sec, grp, sub), v in pivoted.items():

        by_section[sec].setdefault((grp, sub), v)
 
    for sec, groups in by_section.items():

        html.append(f"<h2>Section: {esc(sec)}</h2>")
 
        for (grp, sub), channels in groups.items():

            bad = "bad" if (sec, grp, sub) in mismatches else ""

            html.append(f"<h3>Group: {esc(grp)} | Sub-group: {esc(sub)}</h3>")

            html.append(f"<div class='wrap {bad}'>")
 
            periods = sorted({p for ch in channels.values() for (p,_) in ch})
 
            for src in sources:

                html.append("<table>")

                html.append(f"<tr><th colspan='{len(periods)+1}'>{esc(src)}</th></tr>")

                html.append("<tr><th>Channel</th>")

                for p in periods:

                    html.append(f"<th>{esc(p)}</th>")

                html.append("</tr>")
 
                for ch, vals in channels.items():

                    html.append(f"<tr><td>{esc(ch)}</td>")

                    for p in periods:

                        cell = vals.get((p,src))

                        html.append(f"<td>{esc(cell['raw']) if cell else ''}</td>")

                    html.append("</tr>")

                html.append("</table>")

            html.append("</div>")

    html.append("</body></html>")

    return "".join(html)
 
# =====================================================

# MAIN

# =====================================================
 
if __name__ == "__main__":

    f1 = "RateBuildUpCSV.csv"

    f2 = "RateBuildUpCSVChange.csv"
 
    recs = extract_records(read_csv(f1), f1) + extract_records(read_csv(f2), f2)

    pivoted, mismatches = pivot(recs, [f1, f2])
 
    html = render_tables(pivoted, mismatches, [f1, f2])
 
    with open("rbu_comparison_report.html", "w", encoding="utf-8") as f:

        f.write(html)
 
    print("Report generated successfully")
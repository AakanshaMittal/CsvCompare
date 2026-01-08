import pandas as pd

import math

from collections import defaultdict
 
def is_blank(x):

    return pd.isna(x) or str(x).strip() == ""
 
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
 
def read_xlsx(path):

    df = pd.read_excel(path, header=None)

    return df.fillna("").values.tolist()
 
def detect_sections(grid, section_row):

    section_by_col = {}

    last = ""

    for c in range(len(grid[0])):

        if not is_blank(grid[section_row][c]):

            last = str(grid[section_row][c]).strip()

        section_by_col[c] = last

    return section_by_col
 
def find_tables(grid, start_row):

    tables = []

    r = start_row

    cols = range(len(grid[0]))
 
    while r < len(grid):

        if all(is_blank(grid[r][c]) for c in cols):

            r += 1

            continue

        top = r

        while r < len(grid) and not all(is_blank(grid[r][c]) for c in cols):

            r += 1

        tables.append((top, r - 1))

        r += 1

    return tables
 
def forward_fill_row(row):

    out = []

    last = ""

    for v in row:

        if not is_blank(v):

            last = str(v).strip()

        out.append(last)

    return out
 
def extract_records(grid, source, section_row):

    section_map = detect_sections(grid, section_row)

    records = []

    tables = find_tables(grid, section_row + 1)
 
    for top, bottom in tables:

        header_rows = []

        data_start = None
 
        for r in range(top, bottom + 1):

            if any(is_number(grid[r][c]) for c in range(len(grid[0]))):

                data_start = r

                break

            header_rows.append(r)
 
        if len(header_rows) < 3:

            continue
 
        g_row, sg_row, p_row = header_rows[:3]

        group = forward_fill_row(grid[g_row])

        sub_group = forward_fill_row(grid[sg_row])

        period = forward_fill_row(grid[p_row])
 
        for r in range(data_start, bottom + 1):

            row = grid[r]

            num_cols = [c for c in range(len(row)) if is_number(row[c])]

            if not num_cols:

                continue
 
            channel = str(row[num_cols[0] - 1]).strip()

            for c in num_cols:

                records.append({

                    "source": source,

                    "section": section_map[c],

                    "group": group[c],

                    "sub_group": sub_group[c],

                    "period": period[c],

                    "channel": channel,

                    "value": to_float(row[c])

                })

    return records
 
def compare(records):

    data = defaultdict(dict)

    mismatches = set()
 
    for r in records:

        key = (r["section"], r["group"], r["sub_group"], r["period"], r["channel"])

        data[key][r["source"]] = r["value"]
 
    for k, v in data.items():

        if len(v) == 2:

            a, b = list(v.values())

            if not math.isclose(a, b, rel_tol=1e-9):

                mismatches.add(k)
 
    return data, mismatches
 
def generate_html(data, mismatches, sources):

    html = []

    html.append("<html><style>")

    html.append("""

    body{font-family:Arial}

    table{border-collapse:collapse;margin:10px}

    th,td{border:1px solid #aaa;padding:4px}

    .bad{background:#ffe0e0}

    .wrap{display:flex}

    """)

    html.append("</style><body>")
 
    summary = defaultdict(int)

    for s, g, _, _, _ in mismatches:

        summary[(s, g)] += 1
 
    html.append("<h2>Mismatch Summary</h2>")

    html.append("<table><tr><th>Section</th><th>Group</th><th>Mismatches</th></tr>")

    for (s, g), c in summary.items():

        html.append(f"<tr><td>{s}</td><td>{g}</td><td>{c}</td></tr>")

    html.append("</table>")
 
    structure = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))

    periods = defaultdict(set)
 
    for (sec, grp, sg, p, ch), vals in data.items():

        periods[(sec, grp, sg)].add(p)

        for src, val in vals.items():

            structure[sec][grp][sg][src].setdefault(ch, {})[p] = val
 
    for sec in structure:

        html.append(f"<h2>Section: {sec}</h2>")

        for grp in structure[sec]:

            html.append(f"<h3>Group: {grp}</h3>")

            for sg in structure[sec][grp]:

                html.append(f"<h4>Sub-Group: {sg}</h4>")

                ps = sorted(periods[(sec, grp, sg)])

                html.append("<div class='wrap'>")

                for src in sources:

                    bad = any(

                        (sec, grp, sg, p, ch) in mismatches

                        for ch in structure[sec][grp][sg][src]

                        for p in ps

                    )

                    cls = "bad" if bad else ""

                    html.append(f"<table class='{cls}'><tr><th colspan='{len(ps)+1}'>{src}</th></tr>")

                    html.append("<tr><th>Channel</th>" + "".join(f"<th>{p}</th>" for p in ps) + "</tr>")

                    for ch, vals in structure[sec][grp][sg][src].items():

                        html.append("<tr><td>"+ch+"</td>")

                        for p in ps:

                            html.append(f"<td>{vals.get(p,'')}</td>")

                        html.append("</tr>")

                    html.append("</table>")

                html.append("</div>")

    html.append("</body></html>")

    return "".join(html)
 
def main():

    file1 = "rbu.xlsx"

    file2 = "rbu2.xlsx"

    section_row = 1
 
    g1 = read_xlsx(file1)

    g2 = read_xlsx(file2)
 
    r1 = extract_records(g1, file1, section_row)

    r2 = extract_records(g2, file2, section_row)
 
    data, mismatches = compare(r1 + r2)

    html = generate_html(data, mismatches, [file1, file2])
 
    with open("rbuReport.html", "w", encoding="utf-8") as f:

        f.write(html)
 
    print("Report generated")
 
if __name__ == "__main__":

    main()

 
import pandas as pd
import re
import sys
from pathlib import Path
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
 
def normalize_year(text):
    if pd.isna(text):
        return ""
    t = str(text)
    cot = ""
    if "cot" in t.lower():
        cot = " CoT"
    m = re.search(r"(20\d{2})", t)
    if m:
        return m.group(1) + cot
 
    m = re.search(r"01/(\d{2})-12/(\d{2})", t)
 
    if m:
 
        return "20" + m.group(2) + cot
 
    return t.strip()
 
def clean_text(x):
 
    if pd.isna(x):
 
        return ""
 
    x = str(x)
 
    x = x.replace('"', '').replace('“', '').replace('”', '')
 
    x = re.sub(r"\s+", " ", x).strip().upper()
 
    return x
 
def base_header(col):
 
    return re.sub(r'_(20\d{2})(\s*COT)?$', '', col, flags=re.I)
 
def build_headers(df, header_row):
 
    raw_h1 = df.iloc[header_row]
 
    raw_h2 = df.iloc[header_row + 1]
 
    raw_h3 = df.iloc[header_row + 2]
 
    h1, h2 = raw_h1.copy(), raw_h2.copy()
 
    last_h1, last_h2 = "", ""
 
    for i in range(len(df.columns)):
 
        c1 = "" if pd.isna(raw_h1[i]) else str(raw_h1[i]).strip()
 
        c2 = "" if pd.isna(raw_h2[i]) else str(raw_h2[i]).strip()
 
        c3 = "" if pd.isna(raw_h3[i]) else str(raw_h3[i]).strip()
 
        if c1 == "" and c2 == "" and c3 == "":
 
            last_h1 = last_h2 = ""
 
            h1[i] = h2[i] = ""
 
            continue
 
        if c3 == "":
 
            last_h1 = last_h2 = ""
 
            h1[i] = h2[i] = ""
 
            continue
 
        if c1 != "":
 
            last_h1 = c1
 
            last_h2 = ""
 
        if c2 != "":
 
            last_h2 = c2
 
        h1[i], h2[i] = last_h1, last_h2
 
    final_cols = []
 
    for i in range(len(df.columns)):
 
        p1 = str(h1[i]).strip()
 
        p2 = str(h2[i]).strip()
 
        p3 = normalize_year(str(raw_h3[i]).strip())
 
        col = "_".join([p for p in [p1, p2, p3] if p and p.lower() != "nan"])
 
        col = re.sub(r"_+", "_", col)
 
        final_cols.append(col)
 
    data = df.iloc[header_row + 3:].copy()
 
    data.columns = final_cols
 
    data = data.loc[:, ~data.columns.duplicated()]
 
    data = data.dropna(axis=1, how="all")
 
    return data.reset_index(drop=True)
 
def load_file(path, header_row):
 
    if path.lower().endswith(".csv"):
 
        raw = pd.read_csv(path, header=None, dtype=str)
 
    else:
 
        raw = pd.read_excel(path, header=None, dtype=str)
 
    df = build_headers(raw, header_row)
 
    df = df.applymap(clean_text)
 
    return df
 
def normalize_ndc_value(x):
    if x is None:
        return ""
    s = str(x).strip()
    if s.isdigit():
        return s.lstrip("0") or "0"
    return s
 
def normalize_ndc_columns(df):
    ndc_cols = [c for c in df.columns if "NDC" in c.upper()]
    for c in ndc_cols:
        df[c] = df[c].apply(normalize_ndc_value)
    return df
 
def make_row_key(df, n=10):
    df = normalize_ndc_columns(df)
    key_cols = df.columns[:n]
    df["__ROW_KEY__"] = df[key_cols].astype(str).agg("||".join, axis=1)
    return df
 
def to_decimal(x):
 
    if x is None:
 
        return None
 
    v = str(x).replace("$", "").replace(",", "").strip()
 
    if v == "":
 
        return None
 
    try:
 
        return Decimal(v)
 
    except:
 
        return None
 
 
def values_equal(v1, v2):
 
    d1, d2 = to_decimal(v1), to_decimal(v2)
 
    if d1 is not None and d2 is not None:
 
        return abs(d1 - d2) <= Decimal("0.01")
 
    return str(v1) == str(v2)
 
 
def needs_highlight(v1, v2):
 
    d1, d2 = to_decimal(v1), to_decimal(v2)
 
    if d1 is not None and d2 is not None:
 
        return abs(d1 - d2) > Decimal("0.01")
 
    return True
 
def normalize_col_tokens(col):
 
    col = base_header(col)
 
    col = re.sub(r'[^A-Z0-9 ]', ' ', col.upper())
 
    col = re.sub(r'\s+', ' ', col).strip()
 
    return col
 
def tail_signature(col, n=3):
 
    tokens = normalize_col_tokens(col).split()
 
    return " ".join(tokens[-n:]) if len(tokens) >= n else " ".join(tokens)
 
def build_column_mapping(cols1, cols2):
 
    map12 = {}
 
    norm2 = {c: normalize_col_tokens(c) for c in cols2}
 
    used = set()
 
    for c1 in cols1:
 
        n1 = normalize_col_tokens(c1)
 
        strict = [c2 for c2, n2 in norm2.items() if n1 == n2 and c2 not in used]
 
        if strict:
 
            map12[c1] = strict[0]
 
            used.add(strict[0])
 
            continue
 
        t1 = tail_signature(c1, 3)
 
        fallback = [c2 for c2 in cols2 if tail_signature(c2, 3) == t1 and c2 not in used]
 
        if len(fallback) == 1:
 
            map12[c1] = fallback[0]
 
            used.add(fallback[0])
 
    return map12
 
def generate_html_report(extra1, extra2, mismatches, summary, ndc_map, file1, file2, out_path):
 
    html = []
 
    html.append("<html><head><title>RA Output Validation</title>")
 
    html.append("<style>")
 
    html.append("body{font-family:Arial;padding:20px}")
 
    html.append("table{border-collapse:collapse;width:100%}")
 
    html.append("th,td{border:1px solid #ccc;padding:6px;font-size:12px}")
 
    html.append("th{background:#f2f2f2}")
 
    html.append(".diff{background:#ffd6d6;font-weight:600}")
 
    html.append("</style></head><body>")
 
    html.append("<h1>RA Output Validation Report</h1>")
 
    html.append(f"<p><b>Total mismatches:</b> {len(mismatches)}</p>")
 
    html.append(f"<p><b>Extra rows in {file1}:</b> {len(extra1)}</p>")
 
    html.append(f"<p><b>Extra rows in {file2}:</b> {len(extra2)}</p>")
 
    html.append("<h2>Mismatch Summary (with NDCs)</h2>")
 
    html.append("<table><tr><th>Header</th><th>Mismatch Count</th><th>Affected NDCs</th></tr>")
 
    for k, v in sorted(summary.items(), key=lambda x: -x[1]):
 
        ndcs = ", ".join(sorted(ndc_map[k]))
 
        html.append(f"<tr><td>{k}</td><td>{v}</td><td>{ndcs}</td></tr>")
 
    html.append("</table><br>")
 
    html.append("<h2>Value Mismatches</h2>")
 
    html.append("<table><tr><th>Row Key</th><th>Column</th><th>File 1</th><th>File 2</th></tr>")
 
    for rk, col, v1, v2, hl in mismatches:
 
        cls = "diff" if hl else ""
 
        html.append(f"<tr class='{cls}'><td>{rk}</td><td>{col}</td><td>{v1}</td><td>{v2}</td></tr>")
 
    html.append("</table>")
 
    html.append("<h2>Extra Rows</h2>")
 
    html.append("<h3>Only in File 1</h3>")
 
    html.append(extra1.to_html(index=False))
 
    html.append("<h3>Only in File 2</h3>")
 
    html.append(extra2.to_html(index=False))
 
    html.append("</body></html>")
 
    with open(out_path, "w", encoding="utf-8") as f:
 
        f.write("\n".join(html))
 
def main():
 
    file1, file2 = sys.argv[1], sys.argv[2]
 
    h1, h2 = int(sys.argv[3]), int(sys.argv[4])
 
    df1 = make_row_key(load_file(file1, h1), 10).set_index("__ROW_KEY__")
 
    df2 = make_row_key(load_file(file2, h2), 10).set_index("__ROW_KEY__")
 
    col_map = build_column_mapping(df1.columns, df2.columns)
 
    extra1 = df1.loc[~df1.index.isin(df2.index)].reset_index()
 
    extra2 = df2.loc[~df2.index.isin(df1.index)].reset_index()
 
    common_keys = df1.index.intersection(df2.index)
 
    mismatches = []
 
    summary = defaultdict(int)
 
    ndc_map = defaultdict(set)
 
    for key in common_keys:
 
        ndc = key.split("||")[1] if "||" in key else key
 
        r1, r2 = df1.loc[key], df2.loc[key]
 
        for c1, c2 in col_map.items():
 
            v1, v2 = r1.get(c1, ""), r2.get(c2, "")
 
            if not values_equal(v1, v2):
 
                hl = needs_highlight(v1, v2)
 
                header = base_header(c1)
 
                mismatches.append((key, header, v1, v2, hl))
 
                summary[header] += 1
 
                ndc_map[header].add(ndc)
 
    generate_html_report(extra1, extra2, mismatches, summary, ndc_map,
 
                         Path(file1).name, Path(file2).name, "RA_Output_Latest.html")
 
    print("Done. New report generated.")
 
if __name__ == "__main__":
 
    main()

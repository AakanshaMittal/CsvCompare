import argparse, csv, html, math, os, re, statistics, sys
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict, namedtuple

DATE_RE = re.compile(r"\b\d{2}/\d{2}\s*-\s*\d{2}/\d{2}\b")
YEAR_RE = re.compile(r"^\d{4}$")

def detect_delimiter(path: str, default=","):
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.readline()
            for cand in [",", ";", "\t", "\n"]:
                if cand in head:
                    return cand
            return default
    except:
        return default

def read_csv_safe(path: str, delimiter: Optional[str] = None) -> List[List[str]]:
    if delimiter is None:
        delimiter = detect_delimiter(path)
    rows: List[List[str]] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter=delimiter):
            rows.append([(c or "").strip() for c in row])
    return rows

def read_table_auto(path: str, delimiter: Optional[str]) -> List[List[str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv": return read_csv_safe(path, delimiter)
    raise ValueError(f"Unsupported file: {path}")

def esc(x): return html.escape(str(x))

def normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("–","-").replace("—","-")
    s = re.sub(r"\s+", " ", s)
    return s

def is_mostly_numeric(tokens: List[str], threshold: float = 0.6) -> bool:
    nums = 0; total = 0
    for t in tokens:
        s = (t or "").strip()
        if not s: continue
        total += 1
        s2 = s.replace(",", "").replace("$", "")
        if s2.endswith("%"): s2 = s2[:-1]
        try:
            float(s2); nums += 1
        except:
            if DATE_RE.search(s) or YEAR_RE.match(s): nums += 1
    return total > 0 and (nums/total) >= threshold

def looks_like_text_band(row: List[str]) -> bool:
    tokens = [normalize_text(c) for c in row if normalize_text(c)]
    if len(tokens) < 2: return False
    if any(DATE_RE.search(t) or YEAR_RE.match(t) for t in tokens): return False
    if is_mostly_numeric(tokens): return False
    pos = [i for i, c in enumerate(row) if normalize_text(c)]
    if len(pos) < 2: return False
    gaps = [pos[i+1] - pos[i] for i in range(len(pos)-1)]
    median_gap = statistics.median(gaps) if gaps else 0
    return median_gap >= 3

def forward_fill(line: List[str], width: int) -> List[str]:
    out = []
    cur = ""
    for i in range(width):
        tok = normalize_text(line[i] if i < len(line) else "")
        if tok: cur = tok
        out.append(cur)
    return out

def _index_to_letters(idx: int) -> str:
    n = idx + 1
    out = []
    while n > 0:
        n, rem = divmod(n-1, 26)
        out.append(chr(ord("A") + rem))
    return "".join(reversed(out))

def find_global_stage_row(rows: List[List[str]], scan_top_rows: int = 100) -> Optional[int]:
    for r in range(0, min(scan_top_rows, len(rows))):
        if looks_like_text_band(rows[r]):
            return r
    return None

def build_map_from_row(rows: List[List[str]], row_idx: Optional[int]) -> Dict[int, str]:
    m: Dict[int, str] = {}
    if row_idx is None: return m
    line = rows[row_idx] if 0 <= row_idx < len(rows) else []
    width = max(len(r) for r in rows) if rows else len(line)
    ff = forward_fill(line, width)
    for i, tok in enumerate(ff):
        if tok: m[i] = tok
    return m

def row_has_many_dates(row: List[str], threshold: int = 4) -> bool:
    return sum(1 for c in row if DATE_RE.search(c or "")) >= threshold

def find_detail_rows(rows: List[List[str]]) -> List[int]:
    return [i for i, r in enumerate(rows) if row_has_many_dates(r)]

def find_sub_and_group_rows(rows: List[List[str]], detail_row: int, scan_up: int = 120) -> Tuple[Optional[int], Optional[int]]:
    sub_idx = None
    grp_idx = None
    for r in range(detail_row - 1, max(detail_row - scan_up, -1), -1):
        if looks_like_text_band(rows[r]):
            sub_idx = r
            break
    if sub_idx is not None:
        for r in range(sub_idx - 1, max(sub_idx - scan_up, -1), -1):
            if looks_like_text_band(rows[r]):
                grp_idx = r
                break
    return sub_idx, grp_idx

def collect_header_rows(rows: List[List[str]], detail_row: int, subgroup_row: Optional[int], group_row: Optional[int]) -> List[int]:
    rows_set = set()
    for r in [detail_row, subgroup_row, group_row]:
        if r is not None:
            rows_set.add(r)
    if subgroup_row is not None and group_row is not None:
        for r in range(subgroup_row + 1, group_row):
            tokens = [normalize_text(c) for c in rows[r] if normalize_text(c)]
            if tokens and not is_mostly_numeric(tokens) and not any(DATE_RE.search(t) or YEAR_RE.match(t) for t in tokens):
                rows_set.add(r)
    return sorted(rows_set)


Record = namedtuple("Record", "section group subgroup period channel col_letter value")

def parse_period(tok: str) -> Tuple[str, int, int]:
    t = normalize_text(tok)
    if DATE_RE.search(t):
        m = re.search(r"(\d{2})/(\d{2}).*?(\d{2})/(\d{2})", t)
        if m:
            sm, sy, em, ey = map(int, m.groups())
            sy += 2000; ey += 2000
            return (f"{sm:02d}/{str(sy)[-2:]} - {em:02d}/{str(ey)[-2:]}", sy*12 + sm, 0)
    if YEAR_RE.match(t):
        y = int(t)
        return (t, y*12, 1)
    return (t, -1, 2)

def build_records(rows: List[List[str]]) -> List[Record]:
    width = max(len(r) for r in rows) if rows else 0
    stage_row = find_global_stage_row(rows)  
    stage_map = build_map_from_row(rows, stage_row)

    recs: List[Record] = []
    detail_rows = find_detail_rows(rows)
    for drow in detail_rows:
        sub_row, grp_row = find_sub_and_group_rows(rows, drow, scan_up=120)
        subgroup_map = build_map_from_row(rows, sub_row)
        group_map    = build_map_from_row(rows, grp_row)

        header_rows = collect_header_rows(rows, drow, sub_row, grp_row)
        ff_headers  = [forward_fill(rows[r], width) for r in header_rows]
        detail_ff   = forward_fill(rows[drow], width)

        next_detail = min([r for r in detail_rows if r > drow], default=len(rows))
        start = drow + 1
        end   = max(start, next_detail - 2)

        for c in range(width):
            section  = normalize_text(stage_map.get(c, ""))
            group    = normalize_text(group_map.get(c, ""))
            subgroup = normalize_text(subgroup_map.get(c, ""))

            period_cell = normalize_text(detail_ff[c])
            period = period_cell
            if not (DATE_RE.search(period) or YEAR_RE.match(period)):
                for hr in reversed(ff_headers):
                    tk = normalize_text(hr[c])
                    if DATE_RE.search(tk) or YEAR_RE.match(tk):
                        period = tk; break
            if not any(normalize_text(x) for x in [section, group, subgroup, period]):
                continue

            for r in range(start, min(end+1, len(rows))):
                ch = ""
                for cell in rows[r]:
                    t = normalize_text(cell)
                    if t: ch = t; break
                if not ch: continue
                val = rows[r][c] if c < len(rows[r]) else ""
                recs.append(Record(section, group, subgroup, period, ch, _index_to_letters(c), val))
    return recs

def is_floaty(val: str) -> bool:
    s = (val or "").strip()
    if s == "" or s.lower() in {"na","n/a","null"}: return False
    s = s.replace(",", "").replace("$", "")
    if s.endswith("%"): s = s[:-1]
    try:
        float(s); return True
    except:
        return False

def to_float(val: str) -> float:
    s = (val or "").strip()
    if s == "" or s.lower() in {"na","n/a","null"}: return float("nan")
    s = s.replace(",", "").replace("$", "")
    if s.endswith("%"): s = s[:-1]
    try: return float(s)
    except: return float("nan")

Mismatch = namedtuple("Mismatch", "section group subgroup period channel col1 col2 v1 v2 diff kind")

def compare_records(recs1: List[Record], recs2: List[Record], tolerance: float) -> Tuple[List[Mismatch], int]:
    def index(recs: List[Record]) -> Dict[Tuple[str,str,str,str,str], Tuple[str,str]]:
        m: Dict[Tuple[str,str,str,str,str], Tuple[str,str]] = {}
        for r in recs:
            key = (normalize_text(r.section), normalize_text(r.group),
                   normalize_text(r.subgroup), normalize_text(r.period),
                   normalize_text(r.channel))
            m[key] = (r.value, r.col_letter)
        return m

    idx1 = index(recs1)
    idx2 = index(recs2)

    shared_keys = sorted(set(idx1.keys()) & set(idx2.keys()))
    mismatches: List[Mismatch] = []
    matches = 0

    for k in shared_keys:
        v1, c1 = idx1[k]
        v2, c2 = idx2[k]
        if is_floaty(v1) or is_floaty(v2):
            f1, f2 = to_float(v1), to_float(v2)
            if (not math.isnan(f1)) and (not math.isnan(f2)):
                diff = abs(f1 - f2)
                if diff > tolerance:
                    mismatches.append(Mismatch(k[0], k[1], k[2], k[3], k[4], c1, c2, v1, v2, f"{diff:.6g}", "numeric"))
                else:
                    matches += 1
            else:
                mismatches.append(Mismatch(k[0], k[1], k[2], k[3], k[4], c1, c2, v1, v2, "NaN", "numeric"))
        else:
            if normalize_text(v1).lower() != normalize_text(v2).lower():
                mismatches.append(Mismatch(k[0], k[1], k[2], k[3], k[4], c1, c2, v1, v2, "", "text"))
            else:
                matches += 1

    return mismatches, matches

def render_table(headers: List[str], rows: List[List[Any]]) -> str:
    thead = "<thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead>"
    tbody = "<tbody>\n" + "\n".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows) + "\n</tbody>"
    return f"<table class='grid'>{thead}{tbody}</table>"

def write_html(out_path: str, summary: List[Tuple[str,str]], sections_html: List[str]) -> None:
    css = """
    body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif; margin:24px; color:#222; }
    h1,h2,h3 { margin:0.3em 0 0.5em; }
    table.grid { border-collapse: collapse; width: 100%; margin-bottom: 16px; }
    table.grid th, table.grid td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; word-break: break-word; }
    table.grid thead th { background: #f6f6f6; }
    .summary { border:1px solid #ddd; border-radius:8px; padding:12px; background:#fafafa; margin-bottom:16px; }
    details { border:1px solid #ddd; border-radius:8px; padding:10px; margin-bottom:14px; }
    details>summary { cursor:pointer; font-weight:600; }
    """
    summary_html = render_table(["Metric","Value"], [[k,v] for (k,v) in summary])
    doc = f"""<!DOCTYPE html>
<html lang='en'><head><meta charset='utf-8'><title>Rate Build-Up Comparison</title>
<style>{css}</style></head><body>
<h1>Rate Build-Up Comparison</h1>
<div class='summary'>{summary_html}</div>
{''.join(sections_html)}
</body></html>"""
    parent = os.path.dirname(out_path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)

def main():
    ap = argparse.ArgumentParser(description="Section-first Rate Build-Up comparator (std-lib)")
    ap.add_argument("--file1", required=True, help="Path to baseline CSV")
    ap.add_argument("--file2", required=True, help="Path to changed CSV")
    ap.add_argument("--delimiter", default=None, help="CSV delimiter (auto-detect)")
    ap.add_argument("--tolerance", type=float, default=0.0, help="Numeric tolerance")
    ap.add_argument("--out-html", default="rateBuildUp_report_v6.html", help="Output HTML path")
    args = ap.parse_args()

    rows1 = read_table_auto(args.file1, args.delimiter)
    rows2 = read_table_auto(args.file2, args.delimiter)

    recs1 = build_records(rows1)
    recs2 = build_records(rows2)

    mismatches, matches = compare_records(recs1, recs2, args.tolerance)

    def period_order(periods: List[str]) -> List[str]:
        parsed = []
        for p in periods:
            t = normalize_text(p)
            if DATE_RE.search(t):
                m = re.search(r"(\d{2})/(\d{2}).*?(\d{2})/(\d{2})", t)
                if m:
                    sm, sy, _, _ = map(int, m.groups())
                    sy += 2000
                    parsed.append((t, 0, sy*12 + sm))
                else:
                    parsed.append((t, 0, -1))
            elif YEAR_RE.match(t):
                y = int(t)
                parsed.append((t, 1, y*12))
            else:
                parsed.append((t, 2, -1))
        parsed.sort(key=lambda x: (x[1], x[2], x[0]))
        return [x[0] for x in parsed]

    def vindex(recs: List[Record]) -> Dict[Tuple[str,str,str,str,str], str]:
        m: Dict[Tuple[str,str,str,str,str], str] = {}
        for r in recs:
            key = (normalize_text(r.section), normalize_text(r.group),
                   normalize_text(r.subgroup), normalize_text(r.period),
                   normalize_text(r.channel))
            m[key] = r.value
        return m

    v1 = vindex(recs1)

    keys = set((normalize_text(r.section), normalize_text(r.group), normalize_text(r.subgroup)) for r in recs1)
    if not keys:
        keys = set((normalize_text(r.section), normalize_text(r.group), normalize_text(r.subgroup)) for r in recs2)

    sections_html: List[str] = []

    mm_rows = [[m.section, m.group, m.subgroup, m.period, m.channel, m.col1, m.col2, m.v1, m.v2, m.diff, m.kind]
               for m in mismatches]
    mm_html = render_table(
        ["Section","Group","Sub-group","Period","Channel","File1 Col","File2 Col","File1 Value","File2 Value","Diff","Type"],
        mm_rows or [["(none)","","","","","","","","","",""]]
    )
    sections_html.append(f"<h2>Mismatches (tolerance={args.tolerance})</h2>{mm_html}")

    by_section: Dict[str, List[Tuple[str,str]]] = defaultdict(list)
    for s, g, sub in keys:
        by_section[s].append((g, sub))

    for section in sorted(by_section.keys()):
        block_html = [f"<h2>Section: {esc(section or '(unknown)')}</h2>"]
        groups = sorted(set([g for g, _ in by_section[section]]))
        for group in groups:
            block_html.append(f"<h3>Group: {esc(group or '(unknown)')}</h3>")
            subs = sorted(set([sub for g, sub in by_section[section] if g == group]))
            for sub in subs:
                periods = sorted(set([normalize_text(r.period) for r in recs1
                                      if normalize_text(r.section)==section and normalize_text(r.group)==group and normalize_text(r.subgroup)==sub]
                                     + [normalize_text(r.period) for r in recs2
                                        if normalize_text(r.section)==section and normalize_text(r.group)==group and normalize_text(r.subgroup)==sub]))
                if not periods: continue
                periods = period_order(periods)

                channels = sorted(set([normalize_text(r.channel) for r in recs1
                                       if normalize_text(r.section)==section and normalize_text(r.group)==group and normalize_text(r.subgroup)==sub]
                                      + [normalize_text(r.channel) for r in recs2
                                         if normalize_text(r.section)==section and normalize_text(r.group)==group and normalize_text(r.subgroup)==sub]))

                headers = ["Channel"] + periods
                rows = []
                for ch in channels:
                    row = [ch]
                    for p in periods:
                        row.append(v1.get((section, group, sub, p, ch), ""))
                    if any(normalize_text(x) for x in row[1:]):
                        rows.append(row)

                keep_idx = [0]
                for j, p in enumerate(periods, start=1):
                    if any(normalize_text(row[j]) for row in rows):
                        keep_idx.append(j)
                headers = [headers[i] for i in keep_idx]
                rows    = [[r[i] for i in keep_idx] for r in rows]

                block_html.append(f"<h4>Sub-group: {esc(sub or '(unknown)')}</h4>")
                block_html.append(render_table(headers, rows or [["(no data)"]]))
        sections_html.append("\n".join(block_html))

    summary = [
        ("File1", args.file1),
        ("File2", args.file2),
        ("Total Matches", str(matches)),
        ("Total Mismatches", str(len(mismatches))),
        ("Bands", "Section from top-most; Group/Sub-group from local bands above each detail"),
    ]
    write_html(args.out_html, summary, sections_html)
    print(f"Done. Matches={matches}, Mismatches={len(mismatches)}. HTML: {args.out_html}")

if __name__ == "__main__":
    main()
import csv
import os
import sys
from html import escape
from typing import List, Dict, Tuple

def main():
    try:
        
        file1 = input("Enter first CSV file name: ").strip()
        file2 = input("Enter second CSV file name: ").strip()
        #report_file = input("Enter report CSV file name (used only for default HTML name): ").strip()
        delimiter = input("Enter delimiter (default ','): ").strip() or ","
        start_col_letters = input("Enter starting column letters (default 'A'): ").strip() or "A"

        start_row_str = input("Enter starting row number for data comparison (default '4'): ").strip() or "4"
        header_group_row_file1_str = input("Enter header GROUP row number for File1 (default '2'): ").strip() or "2"
        header_detail_row_file1_str = input("Enter header DETAIL row number for File1 (default '3'): ").strip() or "3"
        header_group_row_file2_str = input("Enter header GROUP row number for File2 (default '2'): ").strip() or "2"
        header_detail_row_file2_str = input("Enter header DETAIL row number for File2 (default '3'): ").strip() or "3"
        header_joiner = input("Enter header joiner (default '_'): ").strip() or "_"

        html_report_file = input("Enter HTML report file name (default derived from CSV report): ").strip()
        if not html_report_file:
            base, _ = os.path.splitext(report_file or "comparison_report.csv")
            html_report_file = f"{base}.html"

        start_row = int(start_row_str)
        header_group_row_file1 = int(header_group_row_file1_str)
        header_detail_row_file1 = int(header_detail_row_file1_str)
        header_group_row_file2 = int(header_group_row_file2_str)
        header_detail_row_file2 = int(header_detail_row_file2_str)

        for v, name in [
            (start_row, "start_row"),
            (header_group_row_file1, "header_group_row_file1"),
            (header_detail_row_file1, "header_detail_row_file1"),
            (header_group_row_file2, "header_group_row_file2"),
            (header_detail_row_file2, "header_detail_row_file2"),
        ]:
            if v <= 0:
                raise ValueError(f"{name} must be positive.")

        rows1 = read_csv_safe(file1, delimiter)
        rows2 = read_csv_safe(file2, delimiter)

        headers1 = build_composite_headers(rows1, header_group_row_file1, header_detail_row_file1, header_joiner)
        headers2 = build_composite_headers(rows2, header_group_row_file2, header_detail_row_file2, header_joiner)

        structural_errors = validate_structure(rows1, rows2, start_row)

        comparison_result = compare_cells_name_based(
            rows1, rows2, headers1, headers2, start_row, start_col_letters
        )

        write_html_report(
            html_report_file=html_report_file,
            file1=file1,
            file2=file2,
            start_row=start_row,
            header_info={
                "header_group_row_file1": header_group_row_file1,
                "header_detail_row_file1": header_detail_row_file1,
                "header_group_row_file2": header_group_row_file2,
                "header_detail_row_file2": header_detail_row_file2,
                "header_joiner": header_joiner,
                "start_col_letters": start_col_letters,
            },
            headers1=headers1,
            headers2=headers2,
            structural_errors=structural_errors,
            comparison_result=comparison_result,
        )

        print(
            f"Comparison complete. Matching headers: {len(comparison_result['headers_in_both'])}, "
            f"Mismatches: {comparison_result['mismatches']}, Structural Errors: {len(structural_errors)}"
        )
        print(f"Order differences reported: {len(comparison_result['order_differences'])}")
        print(f"HTML report saved to {html_report_file}")

    except Exception as e:
        print(f"ERROR: {e}")

def read_csv_safe(path: str, delimiter: str) -> List[List[str]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    rows: List[List[str]] = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=delimiter)
            for row in reader:
                if any((cell or "").strip() for cell in row):
                    rows.append([(cell or "").strip() for cell in row])
    except OSError as ioe:
        raise IOError(f"Could not read file '{path}': {ioe}") from ioe
    return rows

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

def validate_structure(rows1: List[List[str]], rows2: List[List[str]], start_row: int) -> List[Tuple[str, str, str]]:
    errors: List[Tuple[str, str, str]] = []
    rows_count1 = len(rows1)
    rows_count2 = len(rows2)
    max_cols1 = max((len(r) for r in rows1), default=0)
    max_cols2 = max((len(r) for r in rows2), default=0)
    if rows_count1 != rows_count2 or max_cols1 != max_cols2:
        errors.append(("Global", f"File1 Rows={rows_count1}, Cols={max_cols1}", f"File2 Rows={rows_count2}, Cols={max_cols2}"))
    data_start_index = start_row - 1
    max_rows = max(rows_count1, rows_count2)
    for i in range(data_start_index, max_rows):
        r1 = rows1[i] if i < rows_count1 else []
        r2 = rows2[i] if i < rows_count2 else []
        if len(r1) != len(r2):
            errors.append((f"Row {i+1}", f"File1 Cols={len(r1)}", f"File2 Cols={len(r2)}"))
    return errors

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
    order_differences: List[Tuple[str, str, str]] = []
    matches = 0
    mismatches = 0
    mismatch_details: List[Tuple[str, int, str, str, str, str]] = []

    for header in headers_in_both:
        idxs1 = map1[header]
        idxs2 = map2[header]
        pair_count = min(len(idxs1), len(idxs2))
        for k in range(pair_count):
            i1 = idxs1[k]
            i2 = idxs2[k]
            if i1 != i2:
                order_differences.append(
                    (header, index_to_col_letters(i1 + col_offset), index_to_col_letters(i2 + col_offset))
                )
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

        if len(idxs1) > len(idxs2):
            for extra_i in idxs1[pair_count:]:
                order_differences.append((f"{header} (extra in File1)", index_to_col_letters(extra_i + col_offset), ""))
        elif len(idxs2) > len(idxs1):
            for extra_j in idxs2[pair_count:]:
                order_differences.append((f"{header} (extra in File2)", "", index_to_col_letters(extra_j + col_offset)))

    return {
        "headers_in_both": headers_in_both,
        "missing_in_file2": missing_in_file2,
        "missing_in_file1": missing_in_file1,
        "dups1": dups1,
        "dups2": dups2,
        "order_differences": order_differences,
        "matches": matches,
        "mismatches": mismatches,
        "mismatch_details": mismatch_details,
        "rows_count1": len(rows1),
        "rows_count2": len(rows2),
        "max_cols1": max((len(r) for r in rows1), default=0),
        "max_cols2": max((len(r) for r in rows2), default=0),
    }

def write_html_report(
    html_report_file: str,
    file1: str,
    file2: str,
    start_row: int,
    header_info: Dict[str, int],
    headers1: List[str],
    headers2: List[str],
    structural_errors: List[Tuple[str, str, str]],
    comparison_result: Dict[str, object],
) -> None:
    """
    Render the same sections as the CSV report, in HTML:
      - SUMMARY
      - ORDER DIFFERENCES
      - STRUCTURAL ERRORS
      - VALUE MISMATCH DETAILS
      - HEADER VALIDATION (order-independent, name-based)
      - Missing in File2 / Missing in File1
    """
    def esc(x): return escape(str(x))
    def th(x): return f"<th>{esc(x)}</th>"
    def td(x): return f"<td>{esc(x)}</td>"

    summary_rows = [
        ("File1", file1),
        ("File2", file2),
        ("Rows in File1", comparison_result["rows_count1"]),
        ("Rows in File2", comparison_result["rows_count2"]),
        ("Max Columns in File1", comparison_result["max_cols1"]),
        ("Max Columns in File2", comparison_result["max_cols2"]),
        ("Header GROUP row (File1)", header_info["header_group_row_file1"]),
        ("Header DETAIL row (File1)", header_info["header_detail_row_file1"]),
        ("Header GROUP row (File2)", header_info["header_group_row_file2"]),
        ("Header DETAIL row (File2)", header_info["header_detail_row_file2"]),
        ("Composite Header Joiner", header_info["header_joiner"]),
        ("Data start row", start_row),
        ("Headers present in BOTH (unique names)", len(comparison_result["headers_in_both"])),
        ("Duplicate headers in File1", ", ".join(comparison_result["dups1"]) or "None"),
        ("Duplicate headers in File2", ", ".join(comparison_result["dups2"]) or "None"),
        ("Missing headers in File2", len(comparison_result["missing_in_file2"])),
        ("Missing headers in File1", len(comparison_result["missing_in_file1"])),
        ("Order Differences", len(comparison_result["order_differences"])),
        ("Total Cells Compared (matching headers only)", comparison_result["matches"] + comparison_result["mismatches"]),
        ("Matches", comparison_result["matches"]),
        ("Mismatches", comparison_result["mismatches"]),
        ("Structural Errors", len(structural_errors)),
    ]
    summary_body = "\n".join(f"<tr>{td(k)}{td(v)}</tr>" for k, v in summary_rows)

    mismatch_body = "\n".join(
        f"<tr>{td(h)}{td(r)}{td(c1)}{td(c2)}{td(v1)}{td(v2)}</tr>"
        for (h, r, c1, c2, v1, v2) in comparison_result["mismatch_details"]
    )
    if not mismatch_body:
        mismatch_body = f"<tr><td colspan='6'>No mismatches found.</td></tr>"

    order_body = "\n".join(
        f"<tr>{td(h)}{td(c1)}{td(c2)}</tr>"
        for (h, c1, c2) in comparison_result["order_differences"]
    )
    if not order_body:
        order_body = f"<tr><td colspan='3'>No order differences.</td></tr>"

    struct_body = "\n".join(
        f"<tr>{td(scope)}{td(f1)}{td(f2)}</tr>"
        for (scope, f1, f2) in structural_errors
    )
    if not struct_body:
        struct_body = f"<tr><td colspan='3'>No structural errors.</td></tr>"

    map1, _ = build_index_map(headers1)
    map2, _ = build_index_map(headers2)
    hv_body = "\n".join(
        f"<tr>{td(h)}{td(', '.join(index_to_col_letters(i) for i in map1.get(h, [])))}"
        f"{td(', '.join(index_to_col_letters(j) for j in map2.get(h, [])))}</tr>"
        for h in comparison_result["headers_in_both"]
    )
    if not hv_body:
        hv_body = f"<tr><td colspan='3'>No matching headers between files.</td></tr>"

    miss_f2_body = "\n".join(f"<tr>{td(h)}</tr>" for h in comparison_result["missing_in_file2"]) or "<tr><td>None</td></tr>"
    miss_f1_body = "\n".join(f"<tr>{td(h)}</tr>" for h in comparison_result["missing_in_file1"]) or "<tr><td>None</td></tr>"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CSV Comparison Report</title>
<style>
 body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; margin: 24px; color: #222; }}
 h1, h2 {{ margin: 0.2em 0 0.4em; }}
 table.grid {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
 table.grid th, table.grid td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; vertical-align: top; word-break: break-word; }}
 table.grid thead th {{ background: #f0f0f0; }}
 .summary {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; background: #fafafa; margin-bottom: 16px; }}
 .pill {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 8px; }}
 .ok {{ background: #e8f5e9; color: #1b5e20; border: 1px solid #c8e6c9; }}
 .warn {{ background: #fff3e0; color: #e65100; border: 1px solid #ffe0b2; }}
 .err {{ background: #ffebee; color: #b71c1c; border: 1px solid #ffcdd2; }}
 footer {{ margin-top: 32px; color: #666; font-size: 12px; }}
</style>
</head>
<body>

<h1>CSV Comparison Report</h1>

<div class="summary">
  <p><strong>Result:</strong>
    <span class="pill {'ok' if comparison_result['mismatches'] == 0 and len(structural_errors) == 0 else ('warn' if comparison_result['mismatches'] == 0 else 'err')}">
      {('Perfect match' if comparison_result['mismatches'] == 0 and len(structural_errors) == 0
        else ('No value mismatches, but structural differences' if comparison_result['mismatches'] == 0
              else f"{comparison_result['mismatches']} mismatches"))}
    </span>
  </p>
  <table class="grid">
    <thead><tr>{th('Metric')}{th('Value')}</tr></thead>
    <tbody>
      {summary_body}
    </tbody>
  </table>
</div>

<h2>ORDER DIFFERENCES (same header exists but at different columns)</h2>
<table class="grid">
  <thead><tr>{th('Header')}{th('File1 Column')}{th('File2 Column')}</tr></thead>
  <tbody>
    {order_body}
  </tbody>
</table>

<h2>STRUCTURAL ERRORS</h2>
<table class="grid">
  <thead><tr>{th('Scope/Row')}{th('File1')}{th('File2')}</tr></thead>
  <tbody>
    {struct_body}
  </tbody>
</table>

<h2>VALUE MISMATCH DETAILS (matching headers only)</h2>
<table class="grid">
  <thead><tr>{th('Header')}{th('Row')}{th('File1 Cell')}{th('File2 Cell')}{th('File1 Value')}{th('File2 Value')}</tr></thead>
  <tbody>
    {mismatch_body}
  </tbody>
</table>

<h2>HEADER VALIDATION (order-independent, name-based)</h2>
<table class="grid">
  <thead><tr>{th('Header')}{th('File1 Column(s)')}{th('File2 Column(s)')}</tr></thead>
  <tbody>
    {hv_body}
  </tbody>
</table>

<h2>Missing in File2 (present in File1)</h2>
<table class="grid">
  <thead><tr>{th('Header')}</tr></thead>
  <tbody>
    {miss_f2_body}
  </tbody>
</table>

<h2>Missing in File1 (present in File2)</h2>
<table class="grid">
  <thead><tr>{th('Header')}</tr></thead>
  <tbody>
    {miss_f1_body}
  </tbody>
</table>

<footer>
  Generated by CSV comparator. Data start row: {esc(str(start_row))}. Start column letters: {esc(str(header_info.get('start_col_letters', 'A')))}.
</footer>

</body>
</html>
"""

    try:
        # Ensure parent directory exists
        parent = os.path.dirname(html_report_file)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

        with open(html_report_file, "w", encoding="utf-8") as f:
            f.write(html_doc)
    except OSError as ioe:
        raise IOError(f"Could not write HTML report file '{html_report_file}': {ioe}") from ioe


# ----------------------------- Script entry point -----------------------------
if __name__ == "__main__":
    main()
from pyxlsb import open_workbook
import csv

input_file = r"~$AD_RPT_T1.xlsx"
output_file = r"RAOutputAD_RPT.csv"
 
with open_workbook(input_file) as wb:
    with wb.get_sheet("RA Output") as sheet:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in sheet.rows():
                writer.writerow([cell.v for cell in row])
 
print("RA Output sheet extracted to RAOutput.csv")
from pyxlsb import open_workbook
import csv

input_file = r"RPT 2025.10.03 v22.07_8Dec- Weightloss, Drug Level Lift - With Data (1).xlsb"
output_file = r"RAOutput.csv"
 
with open_workbook(input_file) as wb:
    with wb.get_sheet("RA Output") as sheet:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in sheet.rows():
                writer.writerow([cell.v for cell in row])
 
print("RA Output sheet extracted to RAOutput.csv")
import csv

def check_row_length_mismatch(file_path):
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)
        expected_length = len(header)

        for i, row in enumerate(reader, start=2):
            if len(row) != expected_length:
                print(f"⚠️ Rad {i} har {len(row)} kolumner istället för {expected_length}: {row}")

check_row_length_mismatch("shopify_ths_import.csv")


import csv

def count_products_with_title(file_path):
    with open(file_path, newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)

        # Försök hitta kolumn som motsvarar Title
        header = reader.fieldnames
        title_col = None
        for col in header:
            if col.strip().lower() == "title":
                title_col = col
                break

        if not title_col:
            print("❌ Kunde inte hitta en 'Title'-kolumn i CSV-filen.")
            print(f"🧪 Kolumnrubriker hittade: {header}")
            return

        count = 0
        for row in reader:
            if row.get(title_col, "").strip():
                count += 1

        print(f"📦 Antal produkter med titel (huvudprodukter): {count}")

# Kör funktionen
count_products_with_title("shopify_ths_import.csv")
import csv
from collections import Counter

def find_duplicate_main_handles(file_path):
    handles = []

    with open(file_path, newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            title = row.get("Title", "").strip()
            description = row.get("Description", "").strip()
            tags = row.get("Tags", "").strip()
            handle = row.get("URL handle", "").strip()

            # Identifiera huvudprodukt: har Title och antingen Description eller Tags
            if title and (description or tags) and handle:
                handles.append(handle)

    counter = Counter(handles)
    duplicates = {handle: count for handle, count in counter.items() if count > 1}

    print(f"🔍 Totalt antal huvudprodukter med unika handles: {len(counter)}")
    print(f"⚠️ Antal dubbletter bland huvudprodukter: {len(duplicates)}")

    if duplicates:
        print("\n📄 Dubbletter (handle → antal förekomster):")
        for handle, count in sorted(duplicates.items(), key=lambda x: -x[1]):
            print(f"- {handle}: {count} gånger")
    else:
        print("✅ Inga dubbletter bland huvudprodukter hittades!")

# Kör funktionen
find_duplicate_main_handles("shopify_hast_import.csv")

import os
import csv
import json
import html
import re
from collections import defaultdict
import sys
from urllib.parse import quote

csv.field_size_limit(sys.maxsize)

##################
##### SETUP ######
##################
# Define expected data types for each column
expected_data_types = {
    'Price': float,
    'Price / International': float,
    'Compare-at price': float,
    'Compare-at price / International': float,
    'Cost per item': float,
    'Charge tax': bool,
    'Inventory quantity': int,
    'Weight value (grams)': int,
    'Requires shipping': bool,
    'Gift card': bool,
    'Continue selling when out of stock': bool,
}

# Define the order of columns for the output CSV
SHOPIFY_COLUMNS = [
    "Title", "URL handle", "Description", "Vendor", "Product category", "Type", "Tags", "Published on online store",
    "Status", "SKU", "Barcode", "Option1 name", "Option1 value", "Option2 name", "Option2 value", "Option3 name",
    "Option3 value", "Price", "Price / International", "Compare-at price", "Compare-at price / International",
    "Cost per item", "Charge tax", "Tax code", "Inventory policy", "Inventory quantity", "Continue selling when out of stock",
    "Weight value (grams)", "Weight unit for display", "Requires shipping", "Fulfillment service", "Product image URL",
    "Image position", "Image alt text", "Variant image URL", "Gift card", "SEO title", "SEO description",
    "Google Shopping / Google product category", "Google Shopping / Gender", "Google Shopping / Age group",
    "Google Shopping / MPN", "Google Shopping / AdWords Grouping", "Google Shopping / AdWords labels",
    "Google Shopping / Condition", "Google Shopping / Custom product", "Google Shopping / Custom label 0",
    "Google Shopping / Custom label 1", "Google Shopping / Custom label 2", "Google Shopping / Custom label 3",
    "Google Shopping / Custom label 4", "Variant Inventory Tracker"
]

##################
##### HELPERS ####
##################
# Helper function to convert values to the expected data type
def convert_to_type(value, data_type):
    if data_type == bool:
        return value.lower() in ['true', '1', 'yes']
    try:
        return data_type(value)
    except (ValueError, TypeError):
        if data_type == int or data_type == float:
            return data_type(0)
        return data_type()

#################
# Function to determine if a row represents a main product
#################
def is_main_product(row):
    description = row.get("Description", "").strip()
    tags = row.get("Tags", "").strip()
    return bool(description) or bool(tags)

####################
# Function to sanitize titles
####################
def sanitize_title(title):
    # Behåll bindestreck genom att lägga till '-' i teckenklassen
    title = re.sub(r'[^a-zA-Z0-9\såäöÅÄÖ\-]', '', title)
    title = title.lower().strip()
    title = re.sub(r'\s+', '-', title)
    return title


#####################################################
# Function to choose mapping based on the input file
#####################################################
def choose_mapping_from_file(csv_path, delimiter=','):
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f, delimiter=delimiter)
        headers = next(reader, [])

    # Svensk mapping
    mapping_sv = {
        'Namn': 'Title',
        'Beskrivning': 'Description',
        'Artikelnummer': 'SKU',
        'Vikt (kg)': 'Weight value (grams)',
        'Lager': 'Inventory quantity',
        'Ordinarie pris': 'Price',
        'Reapris': 'Compare-at price',
        'Bilder': 'Product image URL',
        'Synlighet i katalog': 'Status',
        'Kort beskrivning': 'SEO description',
        'Momsstatus': 'Charge tax',
        'Momsklass': 'Tax code',
        'Fraktklass': 'Shipping Category',
    }

    # Engelsk mapping
    mapping_en = {
        'Name': 'Title',
        'Description': 'Description',
        'SKU': 'SKU',
        'Weight (kg)': 'Weight value (grams)',
        'Stock': 'Inventory quantity',
        'Regular price': 'Price',
        'Sale price': 'Compare-at price',
        'Images': 'Product image URL',
        'Visibility in catalog': 'Status',
        'Short description': 'SEO description',
        'Tax status': 'Charge tax',
        'Tax class': 'Tax code',
        'Shipping class': 'Shipping Category',
    }

    if any(h in headers for h in mapping_sv.keys()):
        print("📘 Mapping: Svenska fält identifierade")
        return mapping_sv
    elif any(h in headers for h in mapping_en.keys()):
        print("📙 Mapping: Engelska fält identifierade")
        return mapping_en
    else:
        raise ValueError("❌ Kunde inte identifiera lämplig mapping baserat på kolumnrubriker.")

##################
##### PROCESS ####
##################
# Function to replace header and transform data
def replace_header_and_transform_data(input_file, output_file, mapping, delimiter=',', max_rows=None):
    variant_fields = [
        "Compare-at price", "Inventory quantity", "Weight value (grams)", "Price",
        "Fulfillment service", "Requires shipping", "Charge tax", "Weight unit for display",
        'Option1 value', 'Option1 name', 'Option2 name', 'Option2 value', 'Option3 name', 'Option3 value'
    ]

    def convert_kg_to_grams(value):
        try:
            return str(int(float(value) * 1000)) if value else '0'
        except ValueError:
            return '0'

    def clean_value(value):
        if value == "[]" or value.strip() == "[]":
            return ""
        return value.strip()


####fungerar fint####
    # def sanitize_html(value):
    #     if not isinstance(value, str) or value.strip() == "":
    #         return ""

    #     # Behåll HTML-taggar och ersätt radbrytningar med mellanslag
    #     value = value.replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ')

    #     # Ta bort flera mellanslag i rad
    #     value = re.sub(r'\s+', ' ', value)

    #     # Escapa citattecken för att passa CSV-formatet
    #     value = value.replace('"', '""')

    #     return value.strip()

    def sanitize_html(value):
        if not isinstance(value, str) or value.strip() == "":
            return ""

        # Ersätt radbrytningar (backslash n) med <br>-taggar
        value = value.replace('\r\n', '<br>').replace('\n', '<br>').replace('\\n', '<br>')

        # Ta bort flera mellanslag i rad
        value = re.sub(r'\s+', ' ', value)

        # Escapa citattecken för att passa CSV-formatet
        value = value.replace('"', '""')

        return value.strip()



    def extract_categories(category_string):
        if not category_string or category_string.strip() == "":
            return "", ""
        categories = [c.strip() for c in category_string.split(">")]
        product_type = categories[0]
        tags = ", ".join(categories)
        return product_type, tags

    # Mapping for Swedish option names to English
    option_name_mapping = {
        'Attribut 1 namn': 'Option1 name',
        'Attribut 1 värde(n)': 'Option1 value',
        'Attribut 2 namn': 'Option2 name',
        'Attribut 2 värde(n)': 'Option2 value',
        'Attribut 3 namn': 'Option3 name',
        'Attribut 3 värde(n)': 'Option3 value'
    }

    # Mapping for Swedish option values to English
    option_value_mapping = {
        'Storlek': 'Size',
        'Färg': 'Color',
        'Antal': 'Quantity',
        'Vikt': 'Weight',
        'Material': 'Material',
        'Märke': 'Brand',
        'Typ': 'Type', 
        'Modell': 'Model',
        'Längd': 'Length',
        'Bredd': 'Width',
        'Höjd': 'Height',
        'Diameter': 'Diameter',
        'Volym': 'Volume',
        'Storleksguide': 'Size guide',
        'Färgkod': 'Color code',
        'Färgnamn': 'Color name',
        'Färggrupp': 'Color group',
        'Färgtyp': 'Color type',
        'Smak': 'Flavor',
        'Stil': 'Style',
        'Fotstorlek': 'Foot Size',
        'Summa': 'Total',
        'Swarovski': 'Crystal Type',
        'Swarovski GG08': 'Crystal Type GG08',
        'Swarovski SS10': 'Crystal Type SS10',
        'Båge': 'Frame',
        'Modell': 'Model',
        'E-Logga': 'E-Logo',
        'Midja': 'Waist',
        'Rondin G9': 'Rondin G9',
        'Spänne': 'Buckle',
        'Top': 'Top',
        'Vad': 'Calf',
        'Swarovski SS16': 'Crystal Type SS16',
        'Ben': 'Leg',
        'Extra Storlek': 'Extra Size',
        'Infinito läder Top': 'Infinito Leather Top',
        'Sida': 'Side',
        'Skaft': 'Shaft',
        'Skal': 'Shell'
        # Add more mappings as needed
    }

    ##################
    ##### READ #######
    ##################

    #######################################################
    #### Läs in inputfilen och starta rad-för-rad-processen ####
    #######################################################
    with open(input_file, 'r', encoding='utf-8-sig') as infile:
        reader = csv.DictReader(infile, delimiter=delimiter)

        ########################################################################
        #  Definiera fält som alltid måste finnas – med standardvärden om de saknas
        ########################################################################
        required_fields = {
            'URL handle': '',
            'Vendor': 'Skara Hästsport',
            'Published on online store': 'TRUE',
            'Product category': '',
            'Tags': '',
            'Option1 name': '',
            'Option1 value': '',
            'Option2 name': '',
            'Option2 value': '',
            'Option3 name': '',
            'Option3 value': '',
            'Fulfillment service': 'manual',
            'Requires shipping': 'TRUE',
            'Inventory policy': '',
            'Charge tax': 'TRUE',
            'Gift card': 'FALSE',
            'Weight unit for display': 'kg',
            'Continue selling when out of stock': '',
            'Inventory policy': '',
            "Variant Inventory Tracker" : 'shopify'
        }

        ##############################################
        # Välj ut kolumner som finns i input-filen och används i mappningen
        ##############################################
        selected_fields = [field for field in reader.fieldnames if field in mapping]

        ##############################################
        # Säkerställ att alla nödvändiga kolumner finns med i slutgiltiga headern
        ##############################################
        final_header = SHOPIFY_COLUMNS
        for required_field in required_fields.keys():
            if required_field not in final_header:
                final_header.append(required_field)

        for field in mapping.values():
            if field not in final_header:
                final_header.append(field)

        ##############################################
        #  Initiera struktur för att lagra produkter efter deras "handle"
        ##############################################
        products = defaultdict(lambda: {'main': None, 'variants': [], 'images': []})

        ###############################################################
        #  Gå igenom varje rad i filen (en produkt eller variant per rad)
        ###############################################################
        for i, row in enumerate(reader):
            try:
                if max_rows is not None and i >= max_rows:
                    break

                new_row = {}

                ##############################################
                #  Mappa fält från input → Shopify-fält + gör ev. konvertering
                ##############################################
                for field in selected_fields:
                    value = row.get(field, "").strip()

                    # Konvertera vikt till gram
                    if mapping[field] == "Weight value (grams)":
                        value = convert_kg_to_grams(value)

                    # Extra trim på prisfält
                    if mapping[field] == "Price":
                        value = value.strip()

                    # Sanera HTML och escapa radbrytningar + citattecken
                    if mapping[field] in {"Description", "SEO description"}:
                        value = sanitize_html(value)

                    # Sanera ALL text för säker import (även andra fält)
                    if isinstance(value, str):
                        value = sanitize_html(value)

                    # Rensa värdet (ex: ta bort "[]")
                    value = clean_value(value)

                    new_row[mapping[field]] = value



                ##################################################
                #  Generera ett URL-handle från titeln (för länkar i Shopify)
                ##################################################
                base_title = new_row.get('Title', '').split('-')[0].strip()
                handle = sanitize_title(base_title)
                
                new_row['URL handle'] = handle

                title = new_row.get('Title', '').strip()
                sku = new_row.get('SKU', '').strip()

                ##################################################
                #  Hämta attributnamn/värde (om svenska fält finns)
                ##################################################
                new_row['Option1 name'] = row.get('Attribut 1 namn', '').strip()
                new_row['Option1 value'] = row.get('Attribut 1 värde(n)', '').strip()
                new_row['Option2 name'] = row.get('Attribut 2 namn', '').strip()
                new_row['Option2 value'] = row.get('Attribut 2 värde(n)', '').strip()
                new_row['Option3 name'] = row.get('Attribut 3 namn', '').strip()
                new_row['Option3 value'] = row.get('Attribut 3 värde(n)', '').strip()

                ##################################################
                # Översätt svenska attributnamn/värden till engelska
                ##################################################
                for swedish_option, english_option in option_name_mapping.items():
                    if swedish_option in row:
                        new_row[english_option] = row[swedish_option].strip()
                        if new_row[english_option] in option_value_mapping:
                            new_row[english_option] = option_value_mapping[new_row[english_option]]

                ##########################################
                #  Extrahera produktkategori + skapa taggar
                ##########################################
                product_type, tags = extract_categories(row.get("Kategorier", ""))
                new_row["Product category"] = product_type
                new_row["Tags"] = tags

                ##########################################
                #  Fyll i defaultvärden där det saknas
                ##########################################
                for required_field, default_value in required_fields.items():
                    if required_field not in new_row or not new_row[required_field]:
                        new_row[required_field] = default_value

                ##################################################
                # Läs in lagersaldo om fältet finns
                ##################################################
                if "Lager" in row:
                    try:
                        stock_qty = int(row.get("Lager", "").strip())
                    except ValueError:
                        stock_qty = 0
                else:
                    stock_qty = 0

                ##############################################
                # Fallback-värde för Inventory policy
                ##############################################
                if "Inventory policy" not in new_row:
                    new_row["Inventory policy"] = "shopify"
                
                ########################################################################
                # Hämta värde för restnoteringar från svenska eller engelska kolumnnamn #
                ########################################################################
                restock_value = (
                    row.get("Tillåt restnoteringar?", "").strip().lower() or
                    row.get("Backorders allowed?", "").strip().lower()
                )

                # Alltid tillåt försäljning om restnotering är 'notify' eller lagersaldo < 0
                if "Continue selling when out of stock" not in new_row:
                    if restock_value == "notify" or stock_qty < 0:
                        new_row["Continue selling when out of stock"] = "TRUE"
                    else:
                        new_row["Continue selling when out of stock"] = "TRUE"  # fallback för säkerhets skull

                # Inventory policy sätts utifrån samma logik
                if restock_value == "notify":
                    new_row["Inventory policy"] = "continue"
                else:
                    new_row["Inventory policy"] = "continue"  # också fallback så det går att sälja
                

                ###########################################
                ########## URL-KODNING AV BILDER ##########
                ###########################################
                image_src = new_row.get('Product image URL', '').strip()
                if image_src:
                    # Dela upp och URL-koda varje bild
                    images = [quote(img.strip(), safe=':/') for img in image_src.split(", ")]
                    # Slå ihop dem igen till en kommaseparerad sträng
                    new_row['Product image URL'] = ", ".join(images)
                
                
                ##############################################
                # Stöd för både engelska och svenska kolumnnamn för active/draft status ####
                ##############################################
                visibility = row.get("Visibility in catalog", "").strip().lower() or row.get("Synlighet i katalog", "").strip().lower()

                if visibility == "visible":
                    new_row["Status"] = "active"
                elif visibility in {"hidden", "search"}:
                    new_row["Status"] = "draft"
                else:
                    new_row["Status"] = "draft"  # fallback om okänt värde

                ########################################################################
                #  Konvertera alla värden som har förväntad datatyp (pris, lager etc.)
                ########################################################################
                for field, data_type in expected_data_types.items():
                    if field in new_row:
                        new_row[field] = convert_to_type(new_row[field], data_type)
                #  Om raden representerar en huvudprodukt:
                if is_main_product(new_row):
                    # Fyll i tomma variantfält för huvudprodukten (krävs för Shopify)
                    for field in variant_fields:
                        if field not in new_row and not field.startswith("Option"):
                            new_row[field] = ''

                    # Skapa en formaterad titel från URL-handle (t.ex. 'min-produkt' → 'Min Produkt')
                    #new_row["Title"] = new_row["URL handle"].replace("-", " ").title()
                    # Sätt lagerpolicy och fulfillment till Shopify-standard
                    new_row["Inventory policy"] = "deny"
                    new_row["Fulfillment service"] = "manual"

                    # Spara huvudprodukten under dess unika "handle"
                    products[handle]['main'] = new_row
                    if image_src:
                        products[handle]['images'] = images
                else:
                    # Om raden är en variant – lägg till under produktens variantsamling
                    products[handle]['variants'].append(new_row)

            except Exception as e:
                print(f"⚠️ Rad {i+1} kunde inte behandlas: {e}")
                continue # ← här ska den vara – endast om det blir fel

        ##################
        ##### WRITE ######
        ##################
        written_handles = set()

        def make_unique_handle(base_handle, written_handles):
            if base_handle not in written_handles:
                return base_handle
            suffix = 1
            while f"{base_handle}-{suffix}" in written_handles:
                suffix += 1
            return f"{base_handle}-{suffix}"

        # Deduplicera varianter
        for handle, data in products.items():
            seen = set()
            unique_variants = []
            for v in data['variants']:
                opt1 = v.get('Option1 value', '').strip()
                opt2 = v.get('Option2 value', '').strip()
                opt3 = v.get('Option3 value', '').strip()

                if opt1 and opt2 and opt3:
                    key = (opt1, opt2, opt3, v.get('SKU', '').strip())
                    if key not in seen:
                        seen.add(key)
                        unique_variants.append(v)
                    else:
                        print(f"⚠️ POSSIBLE COLLISION – SAME OPTION VALUES: {handle} | {opt1}, {opt2}, {opt3} | SKU: {v.get('SKU')}")
                else:
                    unique_variants.append(v)
            data['variants'] = unique_variants

        with open(output_file, 'w', encoding='utf-8-sig', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=final_header, delimiter=delimiter, quoting=csv.QUOTE_ALL)
            writer.writeheader()

            foot_size_groups = {
                "34-": range(0, 35),
                "35-38": range(35, 39),
                "39-42": range(39, 43),
                "43-46": range(43, 47)
            }

            def get_foot_size_group(size):
                try:
                    size = int(size)
                    for group, size_range in foot_size_groups.items():
                        if size in size_range:
                            return group
                except ValueError:
                    pass
                return None

            for handle, data in products.items():
                if not data['main']:
                    continue

                main_product = data['main']
                variants = data['variants'][:]
                images = data['images']

                # Poppa första variant till huvudprodukt
                if variants:
                    first_variant = variants.pop(0)
                    for field in variant_fields:
                        if field in first_variant:
                            main_product[field] = first_variant[field]
                    if 'Product image URL' in first_variant:
                        main_product['Variant image URL'] = first_variant['Product image URL'].split(", ")[0]

                # Dela upp varianter i fotstorlek och övrigt
                grouped_variants = defaultdict(list)
                non_foot_size_variants = []
                for variant in variants:
                    assigned = False
                    for opt_name, opt_value in [
                        ("Option1 name", "Option1 value"),
                        ("Option2 name", "Option2 value"),
                        ("Option3 name", "Option3 value")
                    ]:
                        if "Foot Size" in variant.get(opt_name, ""):
                            group = get_foot_size_group(variant.get(opt_value, ""))
                            if group:
                                grouped_variants[group].append(variant)
                                assigned = True
                                break
                    if not assigned:
                        non_foot_size_variants.append(variant)

                # Foot size chunks
                for group, group_variants in grouped_variants.items():
                    for i in range(0, len(group_variants), 90):
                        chunk = group_variants[i:i+90]
                        suffix = f"{group}" if i == 0 else f"{group}-{i // 90 + 1}"
                        base = f"{handle}-{suffix}"
                        new_handle = make_unique_handle(base, written_handles)
                        written_handles.add(new_handle)

                        first_chunk_variant = chunk.pop(0).copy()
                        main_copy = main_product.copy()
                        for field in variant_fields:
                            if field in first_chunk_variant:
                                main_copy[field] = first_chunk_variant[field]
                        for key in ["Option1 name","Option1 value","Option2 name","Option2 value","Option3 name","Option3 value"]:
                            main_copy[key] = first_chunk_variant.get(key, '')
                        main_copy['URL handle'] = new_handle
                        #main_copy['Title'] = f"{main_product['Title']} - {suffix}"
                        main_copy['Title'] = main_product['Title']
                        if images:
                            main_copy['Product image URL'] = images[0]
                            main_copy['Variant image URL'] = images[0]
                        writer.writerow(main_copy)

                        for img in images[1:]:
                            writer.writerow({'URL handle': new_handle, 'Product image URL': img})

                        for var in chunk:
                            var['URL handle'] = new_handle
                            if var.get('Product image URL'):
                                var['Variant image URL'] = var['Product image URL'].split(", ")[0]
                            elif images:
                                var['Variant image URL'] = images[0]
                            for f in ["Title","Description","Vendor","Product category","Type","Tags"]:
                                var[f] = ''
                            writer.writerow({k: var[k] for k in final_header if k in var})

                # Övriga varianter i 90-chunks
                for i in range(0, len(non_foot_size_variants), 90):
                    chunk = non_foot_size_variants[i:i+90]
                    suffix = "" if i == 0 else f"-{i // 90 + 1}"
                    base = f"{handle}{suffix}"
                    new_handle = make_unique_handle(base, written_handles)
                    written_handles.add(new_handle)

                    first_chunk_variant = chunk.pop(0).copy()
                    main_copy = main_product.copy()
                    for field in variant_fields:
                        if field in first_chunk_variant:
                            main_copy[field] = first_chunk_variant[field]
                    for key in ["Option1 name","Option1 value","Option2 name","Option2 value","Option3 name","Option3 value"]:
                        main_copy[key] = first_chunk_variant.get(key, '')
                    main_copy['URL handle'] = new_handle
                    main_copy['Title'] = main_product['Title'] if i == 0 else f"{main_product['Title']} - {i // 90 + 1}"
                    if images:
                        main_copy['Product image URL'] = images[0]
                        main_copy['Variant image URL'] = images[0]
                    writer.writerow(main_copy)

                    for img in images[1:]:
                        writer.writerow({'URL handle': new_handle, 'Product image URL': img})

                    for var in chunk:
                        var['URL handle'] = new_handle
                        if var.get('Product image URL'):
                            var['Variant image URL'] = var['Product image URL'].split(", ")[0]
                        elif images:
                            var['Variant image URL'] = images[0]
                        for f in ["Title","Description","Vendor","Product category","Type","Tags"]:
                            var[f] = ''
                        writer.writerow({k: var[k] for k in final_header if k in var})

                # Produkter utan varianter
                if not data['variants'] and not grouped_variants and not non_foot_size_variants:
                    unique_main_handle = make_unique_handle(handle, written_handles)
                    written_handles.add(unique_main_handle)
                    main_product['URL handle'] = unique_main_handle
                    if images:
                        main_product['Product image URL'] = images[0]
                        main_product['Variant image URL'] = images[0]
                    writer.writerow(main_product)
                    for img in images[1:]:
                        writer.writerow({'URL handle': unique_main_handle, 'Product image URL': img})

        print(f" Shopify CSV created successfully: {output_file} ({'ALL rows' if max_rows is None else f'first {max_rows} rows'})")



##################
##### MAIN #######
##################
# Main execution
if __name__ == "__main__":
    base_folder = r"C:\Projects\WooToShopifyConverter\SkaraHast"
    input_csv_path = os.path.join(base_folder, "wooexport.csv")
    output_csv_path = os.path.join(base_folder, "shopify_hast_import.csv")

    mapping = choose_mapping_from_file(input_csv_path, delimiter=',') #Choose mapping based on the input file
    replace_header_and_transform_data(input_csv_path, output_csv_path, mapping, delimiter=',', max_rows=None)


##############################
#fortsättning på test2
##############################
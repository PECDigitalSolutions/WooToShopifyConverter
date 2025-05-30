import os
import csv
import json
import html
import re
from collections import defaultdict

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
    "Google Shopping / Custom label 4"
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

# Function to determine if a row represents a main product
def is_main_product(row):
    description = row.get("Description", "").strip()
    tags = row.get("Tags", "").strip()
    return bool(description) or bool(tags)

# Function to sanitize titles
def sanitize_title(title):
    title = re.sub(r'[^a-zA-Z0-9\såäöÅÄÖ]', '', title)  # Remove special characters except Swedish characters
    title = title.lower().strip()  # Convert to lowercase and strip whitespace
    title = re.sub(r'\s+', '-', title)  # Replace spaces with hyphens
    return title

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

    def sanitize_html(value):
        if not isinstance(value, str) or value.strip() == "":
            return ""
        value = html.unescape(value)
        value = re.sub(r'<.*?>', '', value)
        value = value.replace("\\n", "\n").replace("\r\n", "\n")
        value = re.sub(r'\s*\n\s*', '\n', value).strip()
        return value

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
    # Read input file and process rows
    with open(input_file, 'r', encoding='utf-8-sig') as infile:
        reader = csv.DictReader(infile, delimiter=delimiter)

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
            'Inventory policy': ''
        }

        selected_fields = [field for field in reader.fieldnames if field in mapping]
        final_header = SHOPIFY_COLUMNS

        for required_field in required_fields.keys():
            if required_field not in final_header:
                final_header.append(required_field)

        for field in mapping.values():
            if field not in final_header:
                final_header.append(field)

        products = defaultdict(lambda: {'main': None, 'variants': [], 'images': []})

        for i, row in enumerate(reader):
            if max_rows is not None and i >= max_rows:
                break

            new_row = {}
            for field in selected_fields:
                value = row.get(field, "").strip()
                if mapping[field] == "Weight value (grams)":
                    value = convert_kg_to_grams(value)
                if mapping[field] == "Price":
                    value = value.strip()
                if mapping[field] in {"Description", "SEO description"}:
                    value = sanitize_html(value)
                value = clean_value(value)
                new_row[mapping[field]] = value

            base_title = new_row.get('Title', '').split('-')[0].strip()
            handle = sanitize_title(base_title)
            new_row['URL handle'] = handle

            title = new_row.get('Title', '').strip()
            sku = new_row.get('SKU', '').strip()
            categories = row.get("Kategorier", "").lower()

            title_parts = title.split('-')
            new_row['Option1 name'] = row.get('Attribut 1 namn', '').strip()
            new_row['Option1 value'] = row.get('Attribut 1 värde(n)', '').strip()
            new_row['Option2 name'] = row.get('Attribut 2 namn', '').strip()
            new_row['Option2 value'] = row.get('Attribut 2 värde(n)', '').strip()
            new_row['Option3 name'] = row.get('Attribut 3 namn', '').strip()
            new_row['Option3 value'] = row.get('Attribut 3 värde(n)', '').strip()

            # Translate option names and values to English
            for swedish_option, english_option in option_name_mapping.items():
                if swedish_option in row:
                    new_row[english_option] = row[swedish_option].strip()
                    if new_row[english_option] in option_value_mapping:
                        new_row[english_option] = option_value_mapping[new_row[english_option]]

            product_type, tags = extract_categories(row.get("Kategorier", ""))
            new_row["Product category"] = product_type
            new_row["Tags"] = tags

            for required_field, default_value in required_fields.items():
                if required_field not in new_row or not new_row[required_field]:
                    new_row[required_field] = default_value

            if "Lager" in row:
                try:
                    stock_qty = int(row.get("Lager", "").strip())
                except ValueError:
                    stock_qty = 0
            else:
                stock_qty = 0

            if "Inventory policy" not in new_row:
                new_row["Inventory policy"] = "shopify"

            if "Continue selling when out of stock" not in new_row:
                restock_value = row.get("Tillåt restnoteringar?", "").strip().lower()
                if restock_value == "notify" or stock_qty < 0:
                    new_row["Continue selling when out of stock"] = "TRUE"
                else:
                    new_row["Continue selling when out of stock"] = "FALSE"

            allow_backorders = row.get("Tillåt restnoteringar?", "").strip().lower()
            if allow_backorders == "notify":
                new_row["Inventory policy"] = "continue"
            else:
                new_row["Inventory policy"] = "deny"

            image_src = new_row.get('Product image URL', '').strip()
            if image_src:
                images = image_src.split(", ")

            visibility = row.get("Synlighet i katalog", "").strip()
            new_row["Status"] = "active" if visibility == "visible" else ""

            if is_main_product(new_row):
                products[handle]['main'] = new_row
                if image_src:
                    products[handle]['images'] = images
            else:
                products[handle]['variants'].append(new_row)

            if is_main_product(new_row):
                for field in variant_fields:
                    if field not in new_row:
                        new_row[field] = ''
                new_row["Title"] = new_row["URL handle"].replace("-", " ").title()
                new_row["Inventory policy"] = "deny"
                new_row["Fulfillment service"] = "manual"

            for field, data_type in expected_data_types.items():
                if field in new_row:
                    new_row[field] = convert_to_type(new_row[field], data_type)

    ##################
    ##### WRITE ######
    ##################
    # Write output file
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=final_header, delimiter=delimiter, quoting=csv.QUOTE_ALL)
        writer.writeheader()

        for handle, data in products.items():
            if data['main']:
                main_product = data['main']
                variants = data['variants']
                images = data['images']

                if variants:
                    first_variant = variants.pop(0)  # Remove the first variant after copying its data
                    for field in variant_fields:
                        if field in first_variant:
                            main_product[field] = first_variant[field]
                    if 'Product image URL' in first_variant:
                        main_product['Variant image URL'] = first_variant['Product image URL'].split(", ")[0]

                if images:
                    main_product['Product image URL'] = images[0]
                    main_product['Variant image URL'] = images[0]  # Set Variant image URL to Product image URL
                writer.writerow(main_product)

                # Write unique images under the main product
                for image in images[1:]:
                    writer.writerow({
                        'URL handle': handle,
                        'Product image URL': image
                    })

                for i in range(0, len(variants), 90):  # Split into chunks of 90 variants
                    chunk = variants[i:i + 90]
                    if len(chunk) > 90:  # Kontrollera om chunken är större än 90
                        chunk = chunk[:90]  # Begränsa chunken till 90 varianter

                    if i > 0:
                        new_handle = f"{handle}-{i // 90 + 1}"
                        main_product_copy = chunk[0].copy()  # Create main product from the first variant in the chunk
                        main_product_copy['URL handle'] = new_handle

                        # COPY MAIN PRODUCT FIELDS TO THE NEW MAIN PRODUCT
                        main_product_copy['Description'] = main_product['Description']  # COPY DESCRIPTION
                        main_product_copy['Product category'] = main_product['Product category']  # COPY PRODUCT CATEGORY
                        main_product_copy['Tags'] = main_product['Tags']  # COPY TAGS
                        main_product_copy['Tax code'] = main_product['Tax code']  # COPY TAX CODE
                        main_product_copy['Product image URL'] = main_product['Product image URL']  # COPY PRODUCT IMAGE URL
                        main_product_copy['Variant image URL'] = main_product['Variant image URL']  # COPY VARIANT IMAGE URL
                        main_product_copy['SEO description'] = main_product['SEO description']  # COPY SEO DESCRIPTION

                        if 'Option1 value' in main_product_copy and main_product_copy['Option1 value']:
                            main_product_copy['Title'] = f"{main_product['Title']} - {main_product_copy['Option1 value']}"
                        else:
                            first_variant_option = chunk[0].get('Option1 value', '')
                            main_product_copy['Title'] = f"{main_product['Title']} - {first_variant_option}"

                        writer.writerow(main_product_copy)

                        # Write unique images under the chunked main product
                        for image in images:
                            writer.writerow({
                                'URL handle': new_handle,
                                'Product image URL': image
                            })

                        chunk.pop(0)  # REMOVE THE FIRST VARIANT IN THE CHUNK TO AVOID DUPLICATION

                        for variant in chunk:
                            variant['URL handle'] = new_handle
                            if 'Product image URL' in variant and variant['Product image URL']:
                                variant['Variant image URL'] = variant['Product image URL'].split(", ")[0]
                            else:
                                if images:
                                    variant['Variant image URL'] = images[0]
                            for field in ["Title", "Description", "Vendor", "Product category", "Type", "Tags"]:
                                variant[field] = ''
                            # Remove fields not in final_header
                            variant = {k: v for k, v in variant.items() if k in final_header}
                            writer.writerow(variant)
                    else:
                        for variant in chunk:
                            if 'Product image URL' in variant and variant['Product image URL']:
                                variant['Variant image URL'] = variant['Product image URL'].split(", ")[0]
                            else:
                                if images:
                                    variant['Variant image URL'] = images[0]
                            for field in ["Title", "Description", "Vendor", "Product category", "Type", "Tags"]:
                                variant[field] = ''
                            # Remove fields not in final_header
                            variant = {k: v for k, v in variant.items() if k in final_header}
                            writer.writerow(variant)

    print(f"✅ Shopify CSV created successfully: {output_file} ({'ALL rows' if max_rows is None else f'first {max_rows} rows'})")

##################
##### MAIN #######
##################
# Main execution
if __name__ == "__main__":
    base_folder = r"C:\Projects\WooToShopifyConverter\SkaraHast"
    input_csv_path = os.path.join(base_folder, "wooexport2.csv")
    output_csv_path = os.path.join(base_folder, "shopify_hast_import.csv")

    mapping = {
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

    replace_header_and_transform_data(input_csv_path, output_csv_path, mapping, delimiter=',', max_rows=None)
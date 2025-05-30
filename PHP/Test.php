<?php

// Öka minnesgräns och max CSV-fältstorlek om det behövs
ini_set('memory_limit', '512M');
#ini_set('auto_detect_line_endings', true);


$expectedDataTypes = [
    'Price' => 'float',
    'Price / International' => 'float',
    'Compare-at price' => 'float',
    'Compare-at price / International' => 'float',
    'Cost per item' => 'float',
    'Charge tax' => 'bool',
    'Inventory quantity' => 'int',
    'Weight value (grams)' => 'int',
    'Requires shipping' => 'bool',
    'Gift card' => 'bool',
    'Continue selling when out of stock' => 'bool',
];


// Definiera kolumnerna som förväntas i Shopify CSV-filen
// Dessa kolumner är baserade på Shopify's standard CSV-importformat
$SHOPIFY_COLUMNS = [
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
];

##################
##### HELPERS ####
##################

#Eftersom rawurlencode() kodar allt (även : och /), 
#skapar vi en variant där vi bevarar :/, 
#precis som quote(..., safe=':/') i Python:
function rawurlencode_image(string $url): string {
    // Dela upp på delar som inte ska kodas
    $parsed = parse_url($url);

    if (!isset($parsed['scheme']) || !isset($parsed['host'])) {
        // Om URL inte är giltig, koda hela
        return rawurlencode($url);
    }

    // Återbygg URL med kodad path/query, men bevara scheme och host
    $scheme = $parsed['scheme'] . '://';
    $host = $parsed['host'];
    $path = isset($parsed['path']) ? implode('/', array_map('rawurlencode', explode('/', ltrim($parsed['path'], '/')))) : '';
    $query = isset($parsed['query']) ? '?' . rawurlencode($parsed['query']) : '';

    return $scheme . $host . '/' . $path . $query;
}


# Helper function to convert values to the expected data type
function convertToType($value, $dataType) {
    // Konvertera null till tom sträng
    $value = trim((string)$value);

    // Hantera bool tidigt
    if ($dataType === 'bool') {
        return in_array(strtolower($value), ['true', '1', 'yes'], true);
    }

    // Hantera tomma värden
    if ($value === '') {
        return $dataType === 'int' ? 0 :
               ($dataType === 'float' ? 0.0 : '');
    }

    // Typkonvertering med fallback
    try {
        switch ($dataType) {
            case 'int':
                return is_numeric($value) ? (int)$value : 0;
            case 'float':
                // Konvertera ev. svenska decimalkomma
                $value = str_replace(',', '.', $value);
                return is_numeric($value) ? (float)$value : 0.0;
            case 'string':
                return $value;
            default:
                return $value; // returnera som det är vid okänt typnamn
        }
    } catch (Throwable $e) { // fångar även TypeError i PHP 7+
        return $dataType === 'int' ? 0 :
               ($dataType === 'float' ? 0.0 : '');
    }
}


$writtenHandles = [];

function makeUniqueHandle($baseHandle, &$writtenHandles, $suffix = null) {
    // Generera första unika förslag
    $uniqueHandle = $suffix !== null ? "{$baseHandle}-{$suffix}" : $baseHandle;

    // Öka suffix tills det är unikt
    while (in_array($uniqueHandle, $writtenHandles, true)) {
        $suffix = $suffix === null ? 1 : $suffix + 1;
        $uniqueHandle = "{$baseHandle}-{$suffix}";
    }

    // Lägg till i set
    $writtenHandles[] = $uniqueHandle;
    return $uniqueHandle;
}

#########################################################
# Function to determine if a row represents a main product
#########################################################
function isMainProduct(array $row): bool {
    $productType = $row['Typ'] ?? $row['Type'] ?? '';
    $productType = strtolower(trim($productType));

    return strpos($productType, 'simple') !== false || strpos($productType, 'variable') !== false;
}

function isVariant(array $row): bool {
    $productType = $row['Typ'] ?? $row['Type'] ?? '';
    $productType = strtolower(trim($productType));

    return strpos($productType, 'variation') !== false;
}

####################
# Function to sanitize titles
####################
function sanitizeTitle(string $title): string {
    // Behåll bindestreck och svenska tecken, ta bort övrigt
    $title = preg_replace('/[^a-zA-Z0-9\såäöÅÄÖ\-]/u', '', $title);

    // Gör till gemener och trimma
    $title = mb_strtolower(trim($title), 'UTF-8');

    // Ersätt alla mellanslag med bindestreck
    $title = preg_replace('/\s+/', '-', $title);

    return $title;
}


#####################################################
# Function to choose mapping based on the input file
#####################################################
function chooseMappingFromFile(string $csvPath, string $delimiter = ','): array {
    if (!file_exists($csvPath)) {
        throw new Exception("❌ Filen hittades inte: $csvPath");
    }

    $handle = fopen($csvPath, 'r');
    if ($handle === false) {
        throw new Exception("❌ Kunde inte öppna CSV-filen.");
    }

    // Läs in header-rad (UTF-8-sig hanteras av PHP automatiskt i de flesta fall)
    $headers = fgetcsv($handle, 0, $delimiter, '"', '\\');    fclose($handle);

    if (!$headers) {
        throw new Exception("❌ CSV-filen saknar rubriker.");
    }

    // Svenska mapping
    $mappingSv = [
        'Namn' => 'Title',
        'Beskrivning' => 'Description',
        'Artikelnummer' => 'SKU',
        'Vikt (kg)' => 'Weight value (grams)',
        'Lager' => 'Inventory quantity',
        'Ordinarie pris' => 'Price',
        'Reapris' => 'Compare-at price',
        'Bilder' => 'Product image URL',
        'Synlighet i katalog' => 'Status',
        'Kort beskrivning' => 'SEO description',
        'Momsstatus' => 'Charge tax',
        'Momsklass' => 'Tax code',
        'Fraktklass' => 'Shipping Category',
        'GTIN, UPC, EAN eller ISBN' => 'Barcode',
        'Attribut 1 namn' => 'Option1 name',
        'Attribut 1 värde(n)' => 'Option1 value',
        'Attribut 2 namn' => 'Option2 name',
        'Attribut 2 värde(n)' => 'Option2 value',
        'Attribut 3 namn' => 'Option3 name',
        'Attribut 3 värde(n)' => 'Option3 value',
        'Publicerad' => 'Published on online store'
    ];

    // Engelsk mapping
    $mappingEn = [
        'Name' => 'Title',
        'Description' => 'Description',
        'SKU' => 'SKU',
        'Weight (kg)' => 'Weight value (grams)',
        'Stock' => 'Inventory quantity',
        'Regular price' => 'Price',
        'Sale price' => 'Compare-at price',
        'Images' => 'Product image URL',
        'Visibility in catalog' => 'Status',
        'Short description' => 'SEO description',
        'Tax status' => 'Charge tax',
        'Tax class' => 'Tax code',
        'Shipping class' => 'Shipping Category'
    ];

    // Kontrollera om något av mappningsnycklarna finns i headern
    foreach ($mappingSv as $key => $_) {
        if (in_array($key, $headers, true)) {
            echo "📘 Mapping: Svenska fält identifierade\n";
            return $mappingSv;
        }
    }

    foreach ($mappingEn as $key => $_) {
        if (in_array($key, $headers, true)) {
            echo "📙 Mapping: Engelska fält identifierade\n";
            return $mappingEn;
        }
    }

    throw new Exception("❌ Kunde inte identifiera lämplig mapping baserat på kolumnrubriker.");
}



function convertKgToGrams($value): string {
    if ($value === null || trim($value) === '') {
        return '0';
    }

    // Försök konvertera till float och multiplicera
    try {
        $floatValue = (float)str_replace(',', '.', $value); // hanterar ev. svenska kommatecken
        return (string)(int)round($floatValue * 1000);
    } catch (Exception $e) {
        return '0';
    }
}

function cleanValue(?string $value): string {
    if ($value === null) {
        return '';
    }

    $trimmed = trim($value);
    if ($trimmed === '[]') {
        return '';
    }

    return $trimmed;
}

function sanitizeHtml($value): string {
    if (!is_string($value) || trim($value) === '') {
        return '';
    }

    // Ersätt radbrytningar med <br>
    $value = str_replace(["\r\n", "\n", '\\n'], '<br>', $value);

    // Ta bort flera mellanslag i rad
    $value = preg_replace('/\s+/', ' ', $value);

    // Escapa dubbla citattecken för CSV
    $value = str_replace('"', '""', $value);

    return trim($value);
}

function extractCategories(?string $categoryString): array {
    if ($categoryString === null || trim($categoryString) === '') {
        return ['', ''];
    }

    // Dela upp på ">"
    $categories = array_map('trim', explode('>', $categoryString));

    $productType = $categories[0] ?? '';
    $tags = implode(', ', $categories);

    return [$productType, $tags];
}

$variantFields = [
    "Compare-at price", "Inventory quantity", "Weight value (grams)", "Price",
    "Fulfillment service", "Requires shipping", "Charge tax", "Weight unit for display",
    "Option1 value", "Option1 name", "Option2 name", "Option2 value", "Option3 name", "Option3 value"
];

$optionNameMapping = [
    "Attribut 1 namn" => "Option1 name",
    "Attribut 1 värde(n)" => "Option1 value",
    "Attribut 2 namn" => "Option2 name",
    "Attribut 2 värde(n)" => "Option2 value",
    "Attribut 3 namn" => "Option3 name",
    "Attribut 3 värde(n)" => "Option3 value"
];

$optionValueMapping = [
    "Storlek" => "Size",
    "Färg" => "Color",
    "Antal" => "Quantity",
    "Vikt" => "Weight",
    "Material" => "Material",
    "Märke" => "Brand",
    "Typ" => "Type",
    "Modell" => "Model",
    "Längd" => "Length",
    "Bredd" => "Width",
    "Höjd" => "Height",
    "Diameter" => "Diameter",
    "Volym" => "Volume",
    "Storleksguide" => "Size guide",
    "Färgkod" => "Color code",
    "Färgnamn" => "Color name",
    "Färggrupp" => "Color group",
    "Färgtyp" => "Color type",
    "Smak" => "Flavor",
    "Stil" => "Style",
    "Fotstorlek" => "Foot Size",
    "Summa" => "Total",
    "Swarovski" => "Crystal Type",
    "Swarovski GG08" => "Crystal Type GG08",
    "Swarovski SS10" => "Crystal Type SS10",
    "Båge" => "Frame",
    "E-Logga" => "E-Logo",
    "Midja" => "Waist",
    "Rondin G9" => "Rondin G9",
    "Spänne" => "Buckle",
    "Top" => "Top",
    "Vad" => "Calf",
    "Swarovski SS16" => "Crystal Type SS16",
    "Ben" => "Leg",
    "Extra Storlek" => "Extra Size",
    "Infinito läder Top" => "Infinito Leather Top",
    "Sida" => "Side",
    "Skaft" => "Shaft",
    "Skal" => "Shell"
    // Lägg till fler vid behov
];

########################
##### MAIN PROCESS ####
########################

function replaceHeaderAndTransformData(
    string $inputFile,
    string $outputFile,
    array $mapping,
    string $delimiter = ',',
    ?int $maxRows = null
) {

    global $SHOPIFY_COLUMNS, $expectedDataTypes; // dessa måste vara definierade i main eller globalt
    global $writtenHandles, $variantFields, $optionNameMapping, $optionValueMapping;

    $totalProducts = 0;
    $totalVariants = 0;
    $totalImages = 0;

    $requiredFields = [
        'URL handle' => '',
        'Vendor' => 'THS',
        'Published on online store' => 'TRUE',
        'Product category' => '',
        'Tags' => '',
        'Option1 name' => '',
        'Option1 value' => '',
        'Option2 name' => '',
        'Option2 value' => '',
        'Option3 name' => '',
        'Option3 value' => '',
        'Fulfillment service' => 'manual',
        'Requires shipping' => 'TRUE',
        'Inventory policy' => '',
        'Charge tax' => 'TRUE',
        'Gift card' => 'FALSE',
        'Weight unit for display' => 'kg',
        'Continue selling when out of stock' => 'TRUE',
        'Variant Inventory Tracker' => 'shopify'
    ];
    $finalHeader = $SHOPIFY_COLUMNS;

    // Öppna CSV-filen korrekt
    $handle = fopen($inputFile, 'r');
    if ($handle === false) {
        throw new Exception("❌ Kunde inte öppna input-filen: $inputFile");
    }
    
     // Läs rubrikraden
    $headers = fgetcsv($handle, 0, $delimiter, '"', '\\');
    if (!$headers) {
        throw new Exception("❌ Kunde inte läsa rubriker från CSV-filen.");
    }


    ###################################################################
    # Välj ut kolumner som finns i input-filen och används i mappningen
    ####################################################################

    foreach ($mapping as $field) {
        if (!in_array($field, $finalHeader, true)) {
            $finalHeader[] = $field;
        }
    }

    // Filtrera rubriker som finns i mapping
    $selectedFields = array_filter($headers, function ($field) use ($mapping) {
        return array_key_exists($field, $mapping);
    });

    ##############################################
    # Säkerställ att alla nödvändiga kolumner finns med i slutgiltiga headern
    ##############################################

    // Lägg till alla nödvändiga fält om de saknas
    foreach (array_keys($requiredFields) as $requiredField) {
        if (!in_array($requiredField, $finalHeader, true)) {
            $finalHeader[] = $requiredField;
        }
    }

    // Lägg till alla mappade fält som saknas
    foreach ($mapping as $field) {
        if (!in_array($field, $finalHeader, true)) {
            $finalHeader[] = $field;
        }
    }

    ##############################################
    #  Initiera struktur för att lagra produkter efter deras "handle"
    ##############################################
    ## products = defaultdict(lambda: {'main': None, 'variants': [], 'images': []})
    #defaultdict är inte inbyggt i PHP, så vi använder en vanlig array
    $products = []; // ['handle' => ['main' => ..., 'variants' => [...], 'images' => [...]]]

    $rowCount = 0;

    while (($row = fgetcsv($handle, 0, $delimiter, '"', '\\')) !== false) {
        if ($maxRows !== null && $rowCount >= $maxRows) {
            break;
        }

        $rowCount++;
        $assoc = array_combine($headers, $row);

        // Ny tom rad som ska fyllas (motsvarar new_row = {})
        $newRow = [];

        ##############################################
        #  Mappa fält från input → Shopify-fält + gör ev. konvertering
        ##############################################
        foreach ($selectedFields as $field) {
            $value = trim($assoc[$field] ?? '');

            $mappedField = $mapping[$field];

            // Konvertera vikt till gram
            if ($mappedField === "Weight value (grams)") {
                $value = convertKgToGrams($value);
            }

            // Extra trim på prisfält
            if ($mappedField === "Price") {
                $value = trim($value);
            }

            // Sanera HTML och escapa radbrytningar + citattecken
            if (in_array($mappedField, ["Description", "SEO description"], true)) {
                $value = sanitizeHtml($value);
            }

            // Sanera all text för säker import (om sträng)
            if (is_string($value)) {
                $value = sanitizeHtml($value);
            }

            // Rensa värdet (t.ex. "[]")
            $value = cleanValue($value);

            // Tilldela till rätt Shopify-fält
            $newRow[$mappedField] = $value;
        }

        ##################################################
        # Översätt svenska attributnamn/värden till engelska
        ##################################################
        foreach ($optionNameMapping as $swedishKey => $englishKey) {
            if (isset($assoc[$swedishKey])) {
                $value = trim($assoc[$swedishKey]);

                // Översätt värdet om det finns i mapping
                if (isset($optionValueMapping[$value])) {
                    $value = $optionValueMapping[$value];
                }

                $newRow[$englishKey] = $value;
            }
        }

        ##########################################
        #  Extrahera produktkategori + skapa taggar
        ##########################################
        $categoryString = $assoc['Kategorier'] ?? $assoc['Categories'] ?? '';
        list($productType, $tags) = extractCategories($categoryString);

        $newRow['Product category'] = $productType;
        $newRow['Tags'] = $tags;


        ##################################################
        # Sätt ifall den ska vara publiserad i store eller inte beroende på tidigare värde i "Publicerad"
        ##################################################
        if (isset($newRow['Published on online store'])) {
            $pubVal = $newRow['Published on online store'];

            if ($pubVal === '1') {
                $newRow['Published on online store'] = 'TRUE';
            } elseif ($pubVal === '-1') {
                $newRow['Published on online store'] = 'FALSE';
            }
        }

        ##########################################
        #  Fyll i defaultvärden där det saknas
        ##########################################
        foreach ($requiredFields as $requiredField => $defaultValue) {
            if (!isset($newRow[$requiredField]) || trim($newRow[$requiredField]) === '') {
                $newRow[$requiredField] = $defaultValue;
            }
        }

        ##################################################
        # Läs in lagersaldo om fältet finns
        ##################################################
        $stockRaw = '';

        if (isset($assoc['Lager'])) {
            $stockRaw = trim($assoc['Lager']);
        } elseif (isset($assoc['Stock'])) {
            $stockRaw = trim($assoc['Stock']);
        }

        $stockQty = is_numeric($stockRaw) ? (int)$stockRaw : 0;
        $newRow['Inventory quantity'] = $stockQty;

        ########################################################################
        # Hämta värde för restnoteringar från svenska eller engelska kolumnnamn #
        ########################################################################
        // Standard: anta att man inte ska tillåta försäljning vid 0/negativt lager
        $allowBackorders = false;

        // Hämta backorder-flagga från svenska eller engelska kolumnrubrik
        $restockValue = strtolower(trim($assoc['Tillåt restnoteringar?'] ?? $assoc['Backorders allowed?'] ?? ''));

        // Om restnotering är satt till "notify" → tillåt alltid försäljning
        if ($restockValue === 'notify') {
            $allowBackorders = true;
        }

        // Om lagret är negativt – tolka som att den är restnoterad ändå
        if ($stockQty < 0) {
            $allowBackorders = true;
        }

        // Sätt Shopify-fält
        $newRow['Continue selling when out of stock'] = $allowBackorders ? 'TRUE' : 'FALSE';
        $newRow['Inventory policy'] = $allowBackorders ? 'continue' : 'deny';

        ###########################################
        ########## URL-KODNING AV BILDER ##########
        ###########################################
        if (!empty($newRow['Product image URL'])) {
            $imageSrc = trim($newRow['Product image URL']);

            // Dela upp flera bildlänkar på ", " (komma och mellanslag)
            $images = explode(', ', $imageSrc);

            // URL-koda varje bildlänk men bevara : och /
            $encodedImages = array_map(function ($img) {
                return rawurlencode_image($img);
            }, $images);

            // Slå ihop dem igen till kommaseparerad sträng
            $newRow['Product image URL'] = implode(', ', $encodedImages);
        }

        ##############################################
        # Stöd för både engelska och svenska kolumnnamn för active/draft status ####
        ##############################################
        $visibility = strtolower(trim(
            $assoc['Visibility in catalog'] ?? $assoc['Synlighet i katalog'] ?? ''
        ));

        if ($visibility === 'visible') {
            $newRow['Status'] = 'active';
        } elseif (in_array($visibility, ['hidden', 'search'], true)) {
            $newRow['Status'] = 'draft';
        } else {
            $newRow['Status'] = 'draft'; // fallback
        }

        ########################################################################
        #  Konvertera alla värden som har förväntad datatyp (pris, lager etc.)
        ########################################################################
        foreach ($expectedDataTypes as $field => $dataType) {
            if (isset($newRow[$field])) {
                $newRow[$field] = convertToType($newRow[$field], $dataType);
            }
        }

        ##################################################
        #  Generera ett URL-handle från titeln (för varianter i Shopify)  
        ##################################################
        $baseTitle = explode('-', $newRow['Title'] ?? '')[0] ?? '';
        $cleanHandle = sanitizeTitle($baseTitle);

        $productHandle = makeUniqueHandle($cleanHandle, $writtenHandles);  // ny variabel
        $newRow['URL handle'] = $productHandle;


        $products[$productHandle] = $products[$productHandle] ?? [
            'main' => null,
            'variants' => [],
            'images' => [],
            'seen_keys' => []
        ];

        ###MAIN PRODUKT LÄGGS TILL#####
        $products[$productHandle]['main'] = $newRow; 
        $totalProducts++;
        if (!empty($images)) {
            $products[$productHandle]['images'] = $images;
            $totalImages += count($images);
        }

        // Hantera variant
        elseif (isVariant($assoc)) {
            $sku = trim($newRow['SKU'] ?? '');

            if ($sku === '') {
                echo "❌ SKIPPING VARIANT WITHOUT SKU – " . ($newRow['Title'] ?? '') . " | $handle\n";
                continue;
            }

            $opt1 = trim($newRow['Option1 value'] ?? '');
            $opt2 = trim($newRow['Option2 value'] ?? '');
            $opt3 = trim($newRow['Option3 value'] ?? '');

            // Om alla optioner saknas – tillåt ändå som variant
            if ($opt1 === '' && $opt2 === '' && $opt3 === '') {
                $products[$productHandle]['variants'][] = $newRow;
                continue;
            }

            // Identifiera variantnyckel
            $key = implode('|', [$opt1 ?: 'N/A', $opt2 ?: 'N/A', $opt3 ?: 'N/A', $sku]);

            // Initiera seen_keys om den inte finns
            if (!isset($products[$handle]['seen_keys'])) {
                $products[$handle]['seen_keys'] = [];
            }

            // Undvik duplikater
            if (!in_array($key, $products[$handle]['seen_keys'], true)) {
                $products[$productHandle]['variants'][] = $newRow;
                $products[$handle]['seen_keys'][] = $key;
            } else {
                echo "❗ SKIPPING DUPLICATE during READ – $handle | $opt1, $opt2, $opt3 | SKU: $sku\n";
            }
        }
        // Om raden inte är igenkänd typ
        else {
            echo "⚠️ Skipping row {$rowCount} – Typ ej igenkänd: '" . ($assoc['Typ'] ?? $assoc['Type'] ?? '') . "'\n";
            continue;
        }

    }

    ##################
    ##### WRITE ######
    ##################
    // Öppna fil för skrivning
    $out = fopen($outputFile, 'w');

    // Skriv rubriker
    fputcsv($out, $finalHeader, $delimiter, '"', '\\');

    // Foot size-grupper
    $footSizeGroups = [
        "34-" => range(0, 35),
        "35-38" => range(35, 39),
        "39-42" => range(39, 43),
        "43-46" => range(43, 47)
    ];

    function getFootSizeGroup($size) {
        global $footSizeGroups;
        if (is_numeric($size)) {
            $size = (int)$size;
            foreach ($footSizeGroups as $group => $range) {
                if (in_array($size, $range)) return $group;
            }
        }
        return null;
    }

    foreach ($products as $handle => $data) {
        if (empty($data['main'])) continue;

        $mainProduct = $data['main'];
        $variants = $data['variants'];
        $images = $data['images'] ?? [];

        // Poppa första variant → huvudprodukt
        if (!empty($variants)) {
            $firstVariant = array_shift($variants);
            foreach ($variantFields as $field) {
                if (isset($firstVariant[$field])) {
                    $mainProduct[$field] = $firstVariant[$field];
                }
            }
            if (!empty($firstVariant['Product image URL'])) {
                $mainProduct['Variant image URL'] = explode(", ", $firstVariant['Product image URL'])[0];
            }
        }

        // Gruppera fotstorleksvarianter
        $groupedVariants = [];
        $nonFootSizeVariants = [];

        foreach ($variants as $variant) {
            $assigned = false;
            foreach ([
                ['Option1 name', 'Option1 value'],
                ['Option2 name', 'Option2 value'],
                ['Option3 name', 'Option3 value']
            ] as [$nameKey, $valueKey]) {
                if (isset($variant[$nameKey]) && strpos($variant[$nameKey], 'Foot Size') !== false) {
                    $group = getFootSizeGroup($variant[$valueKey] ?? '');
                    if ($group !== null) {
                        $groupedVariants[$group][] = $variant;
                        $assigned = true;
                        break;
                    }
                }
            }
            if (!$assigned) $nonFootSizeVariants[] = $variant;
        }

        // Skriv Foot Size chunks
        foreach ($groupedVariants as $group => $groupVariants) {
            for ($i = 0; $i < count($groupVariants); $i += 90) {
                $chunk = array_slice($groupVariants, $i, 90);
                $suffix = ($i === 0) ? $group : "{$group}-" . (($i / 90) + 1);
                $newHandle = makeUniqueHandle("{$handle}-{$suffix}", $writtenHandles);
                $writtenHandles[] = $newHandle;

                $first = array_shift($chunk);
                $mainCopy = $mainProduct;
                foreach ($variantFields as $field) {
                    if (isset($first[$field])) $mainCopy[$field] = $first[$field];
                }
                foreach (["Option1 name","Option1 value","Option2 name","Option2 value","Option3 name","Option3 value"] as $key) {
                    $mainCopy[$key] = $first[$key] ?? '';
                }
                $mainCopy['URL handle'] = $newHandle;
                $mainCopy['Title'] = $mainProduct['Title'];
                if (!empty($images)) {
                    $mainCopy['Product image URL'] = $images[0];
                    $mainCopy['Variant image URL'] = $images[0];
                }

                fputcsv($out, array_map(fn($col) => $mainCopy[$col] ?? '', $finalHeader), $delimiter, '"', '\\');

                foreach (array_slice($images, 1) as $img) {
                    fputcsv($out, array_map(fn($col) =>
                        $col === 'URL handle' ? $newHandle :
                        ($col === 'Product image URL' ? $img : ''), $finalHeader), $delimiter, '"', '\\');
                }

                foreach ($chunk as $variant) {
                    $variant['URL handle'] = $newHandle;
                    $variant['Variant image URL'] = !empty($variant['Product image URL'])
                        ? explode(", ", $variant['Product image URL'])[0]
                        : ($images[0] ?? '');

                    foreach (["Title", "Description", "Vendor", "Product category", "Type", "Tags"] as $f) {
                        $variant[$f] = '';
                    }

                    fputcsv($out, array_map(fn($col) => $variant[$col] ?? '', $finalHeader), $delimiter, '"', '\\');
                    $totalVariants++;
                }
            }
        }

        // Skriv övriga icke-foot size varianter i 90-grupper
        for ($i = 0; $i < count($nonFootSizeVariants); $i += 90) {
            $chunk = array_slice($nonFootSizeVariants, $i, 90);
            $suffix = $i === 0 ? '' : '-' . (($i / 90) + 1);
            $newHandle = makeUniqueHandle("{$handle}{$suffix}", $writtenHandles);
            $writtenHandles[] = $newHandle;

            $first = array_shift($chunk);
            $mainCopy = $mainProduct;
            foreach ($variantFields as $field) {
                if (isset($first[$field])) $mainCopy[$field] = $first[$field];
            }
            foreach (["Option1 name","Option1 value","Option2 name","Option2 value","Option3 name","Option3 value"] as $key) {
                $mainCopy[$key] = $first[$key] ?? '';
            }
            $mainCopy['URL handle'] = $newHandle;
            $mainCopy['Title'] = $i === 0 ? $mainProduct['Title'] : $mainProduct['Title'] . " - " . (($i / 90) + 1);
            if (!empty($images)) {
                $mainCopy['Product image URL'] = $images[0];
                $mainCopy['Variant image URL'] = $images[0];
            }

            fputcsv($out, array_map(fn($col) => $mainCopy[$col] ?? '', $finalHeader), $delimiter, '"', '\\');

            foreach (array_slice($images, 1) as $img) {
                fputcsv($out, array_map(fn($col) =>
                    $col === 'URL handle' ? $newHandle :
                    ($col === 'Product image URL' ? $img : ''), $finalHeader), $delimiter, '"', '\\');
            }

            foreach ($chunk as $variant) {
                $variant['URL handle'] = $newHandle;
                $variant['Variant image URL'] = !empty($variant['Product image URL'])
                    ? explode(", ", $variant['Product image URL'])[0]
                    : ($images[0] ?? '');

                foreach (["Title", "Description", "Vendor", "Product category", "Type", "Tags"] as $f) {
                    $variant[$f] = '';
                }

                fputcsv($out, array_map(fn($col) => $variant[$col] ?? '', $finalHeader), $delimiter, '"', '\\');
                $totalVariants++;
            }
        }

        // Produkter utan varianter
        if (empty($data['variants']) && empty($groupedVariants) && empty($nonFootSizeVariants)) {
            $uniqueHandle = makeUniqueHandle($handle, $writtenHandles);
            $writtenHandles[] = $uniqueHandle;
            $mainProduct['URL handle'] = $uniqueHandle;
            if (!empty($images)) {
                $mainProduct['Product image URL'] = $images[0];
                $mainProduct['Variant image URL'] = $images[0];
            }

            fputcsv($out, array_map(fn($col) => $mainProduct[$col] ?? '', $finalHeader), $delimiter, '"', '\\');

            foreach (array_slice($images, 1) as $img) {
                fputcsv($out, array_map(fn($col) =>
                    $col === 'URL handle' ? $uniqueHandle :
                    ($col === 'Product image URL' ? $img : ''), $finalHeader), $delimiter, '"', '\\');
            }
        }
    }

    fclose($out);
    echo "Shopify CSV created successfully: {$outputFile}" . ($maxRows === null ? " (ALL rows)" : " (first {$maxRows} rows)") . PHP_EOL;
    echo "\n Statistik:\n";
    echo "• Antal produkter: $totalProducts\n";
    echo "• Antal varianter: $totalVariants\n";
    echo "• Antal bilder: $totalImages\n";
}


##################
##### MAIN #######
##################
# Main execution

// Definiera basmapp
$baseFolder = "C:\\Projects\\WooToShopifyConverter\\PHP";
$inputCsvPath = $baseFolder . DIRECTORY_SEPARATOR . "thsexport.csv";
$outputCsvPath = $baseFolder . DIRECTORY_SEPARATOR . "shopify_php_import.csv";

// Välj mapping baserat på rubriker
try {
    $mapping = chooseMappingFromFile($inputCsvPath, ','); // använder funktionen du redan portat

    // Anropa huvudlogik (motsvarighet till replace_header_and_transform_data i Python)
    replaceHeaderAndTransformData($inputCsvPath, $outputCsvPath, $mapping, ',', null);
} catch (Exception $e) {
    echo "🚨 Fel: " . $e->getMessage();
}

?>
import openai
import requests
from click import prompt
from pyairtable import Api

from access_airtable import fetch_records, process_airtable_pdfs_and_return_text, table
from local_variables import AIRTABLE_KEY, OPENAI_KEY, BASE_ID

# Definizione della mappa delle province italiane
italian_provinces = {
    "Abruzzo": {"AQ": "L'Aquila", "CH": "Chieti", "PE": "Pescara", "TE": "Teramo"},
    "Basilicata": {"MT": "Matera", "PZ": "Potenza"},
    "Calabria": {"CZ": "Catanzaro", "CS": "Cosenza", "KR": "Crotone", "RC": "Reggio Calabria", "VV": "Vibo Valentia"},
    "Campania": {"AV": "Avellino", "BN": "Benevento", "CE": "Caserta", "NA": "Napoli", "SA": "Salerno"},
    "Emilia-Romagna": {"BO": "Bologna", "FE": "Ferrara", "FC": "Forlì-Cesena", "MO": "Modena", "PR": "Parma",
                       "PC": "Piacenza", "RA": "Ravenna", "RE": "Reggio Emilia", "RN": "Rimini"},
    "Friuli-Venezia Giulia": {"GO": "Gorizia", "PN": "Pordenone", "TS": "Trieste", "UD": "Udine"},
    "Lazio": {"FR": "Frosinone", "LT": "Latina", "RI": "Rieti", "RM": "Roma", "VT": "Viterbo"},
    "Liguria": {"GE": "Genova", "IM": "Imperia", "SP": "La Spezia", "SV": "Savona"},
    "Lombardia": {"BG": "Bergamo", "BS": "Brescia", "CO": "Como", "CR": "Cremona", "LC": "Lecco", "LO": "Lodi",
                  "MN": "Mantova", "MI": "Milano", "MB": "Monza e Brianza", "PV": "Pavia", "SO": "Sondrio",
                  "VA": "Varese"},
    "Marche": {"AN": "Ancona", "AP": "Ascoli Piceno", "FM": "Fermo", "MC": "Macerata", "PU": "Pesaro e Urbino"},
    "Molise": {"CB": "Campobasso", "IS": "Isernia"},
    "Piemonte": {"AL": "Alessandria", "AT": "Asti", "BI": "Biella", "CN": "Cuneo", "NO": "Novara", "TO": "Torino",
                 "VB": "Verbano-Cusio-Ossola", "VC": "Vercelli"},
    "Puglia": {"BA": "Bari", "BT": "Barletta-Andria-Trani", "BR": "Brindisi", "FG": "Foggia", "LE": "Lecce",
               "TA": "Taranto"},
    "Sardegna": {"CA": "Cagliari", "CI": "Carbonia-Iglesias", "VS": "Medio Campidano", "NU": "Nuoro", "OG": "Ogliastra",
                 "OT": "Olbia-Tempio", "OR": "Oristano", "SS": "Sassari"},
    "Sicilia": {"AG": "Agrigento", "CL": "Caltanissetta", "CT": "Catania", "EN": "Enna", "ME": "Messina",
                "PA": "Palermo", "RG": "Ragusa", "SR": "Siracusa", "TP": "Trapani"},
    "Toscana": {"AR": "Arezzo", "FI": "Firenze", "GR": "Grosseto", "LI": "Livorno", "LU": "Lucca",
                "MS": "Massa-Carrara", "PI": "Pisa", "PT": "Pistoia", "PO": "Prato", "SI": "Siena"},
    "Trentino-Alto Adige": {"BZ": "Bolzano", "TN": "Trento"},
    "Umbria": {"PG": "Perugia", "TR": "Terni"},
    "Valle d'Aosta": {"AO": "Valle d'Aosta"},
    "Veneto": {"BL": "Belluno", "PD": "Padova", "RO": "Rovigo", "TV": "Treviso", "VE": "Venezia", "VR": "Verona",
               "VI": "Vicenza"}

}
import pdfplumber
import pytesseract
from pdf2image import convert_from_path


def extract_text_with_pdfplumber(pdf_path):
    """Extracts text from a non-scanned PDF using pdfplumber. Tries to open encrypted PDFs."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.metadata.get("Encrypted"):  # Checks if PDF is encrypted
                print("🔒 PDF is encrypted. Attempting to open...")
                pdf.decrypt("")  # Tries opening with an empty password

            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        return text.strip() if text.strip() else None
    except Exception as e:
        print(f"❌ pdfplumber error (possible encryption issue): {e}")
        return None


def extract_text_with_ocr(pdf_path):
    """Extracts text using OCR for scanned PDFs."""
    try:
        images = convert_from_path(pdf_path)
        if not images:
            print("⚠️ OCR: Could not generate images from PDF.")
            return None

        text = ""
        for img in images:
            text += pytesseract.image_to_string(img, lang="ita")

        return text.strip() if text.strip() else None
    except Exception as e:
        print(f"❌ OCR error: {e}")
        return None


def safe_process_airtable_pdfs_and_return_text(record):
    """Handles text extraction from PDFs. If encrypted, tries to decrypt before extracting text."""
    text = process_airtable_pdfs_and_return_text(record)
    if text and text.strip():
        return text  # If the original function works, return as is

    # Fetch PDF URL and download it
    attachments = record.get("fields", {}).get("Attachments", [])
    if not attachments:
        print(f"⚠️ No attachments found for record {record['id']}")
        return None

    pdf_url = attachments[0]['url']
    pdf_path = "/tmp/temp_fallback.pdf"

    try:
        response = requests.get(pdf_url)
        with open(pdf_path, "wb") as f:
            f.write(response.content)

        # **Try extracting text normally first**
        text = extract_text_with_pdfplumber(pdf_path)
        if text:
            return text

        # **If pdfplumber fails, use OCR**
        print("🔍 No selectable text found, using OCR...")
        return extract_text_with_ocr(pdf_path)

    except Exception as e:
        print(f"❌ Error processing PDF: {e}")
        return None


import re


def extract_specific_section(text):
    """
    Extracts relevant sections from the document using multiple predefined keywords.
    If no relevant section is found, it returns the full text.
    """

    # List of keywords (you can add more later)
    section_keywords = [
        "Aree di intervento",
        "Ambito territoriale d’intervento,"
        "Soggetti beneficiari"
    ]

    # Dynamically create a regex pattern from keywords
    section_pattern = re.compile(r'(' + '|'.join(section_keywords) + r')(.*?)(?=\n[A-Z]|$)', re.DOTALL)

    matches = section_pattern.findall(text)

    if matches:
        extracted_sections = "\n".join([match[0] + match[1].strip() for match in matches])
        return extracted_sections
    else:
        return text  # If no specific section is found, return the full text


import tiktoken

# Initialize tokenizer for GPT-4
tokenizer = tiktoken.encoding_for_model("gpt-4")


def count_tokens(text):
    """Counts the number of tokens in a given text."""
    return len(tokenizer.encode(text))


def trim_text(text, max_tokens=80000):
    """Trims text to ensure it fits within the ChatGPT token limit."""
    tokens = tokenizer.encode(text)

    if len(tokens) > max_tokens:
        print(f"⚠️ Trimming text: Original size {len(tokens)} tokens → Reduced to {max_tokens} tokens")
        trimmed_text = tokenizer.decode(tokens[:max_tokens])  # Keep only first max_tokens
        return trimmed_text
    return text


def summarize_text(text):
    """Summarizes long documents to fit within token limits before sending to ChatGPT."""
    prompt = f"""
        This document is too long for direct processing. Summarize its key content, focusing on regions, provinces, and locations mentioned.
        Return a concise summary with a maximum of 5000 tokens.

        **Original Document Content:**
        {text[:50000]}  # Limiting input to 50k tokens before summarization
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        print(f"❌ Error during summarization: {e}")
        return text[:20000]  # As a fallback, return only the first 20,000 characters


def call_chatgpt(text):
    """
    Sends the extracted section to ChatGPT and ensures the response is strictly formatted.
    """
    specific_section = extract_specific_section(text)

    prompt = f"""
        Sei un esperto nelle regioni e province italiane. Il tuo compito è identificare le province menzionate nel bando.

        **Regole:**
        - Restituisci solo un elenco di province, senza spiegazioni.
        - Ogni provincia deve essere su una nuova riga e nel formato "Provincia: Nome".
        - Se vengono menzionate regioni, elenca tutte le province di quelle regioni.
        - **Se il bando è aperto a tutta Italia, considera solo questa condizione ed elenca tutte le province italiane.**
        - Se il bando menziona sia alcune province specifiche che l’intera Italia, **dai priorità all’intera Italia** ed elenca tutte le province.
        - Se il bando menziona esplicitamente solo alcune province, elenca solo quelle senza commenti aggiuntivi.

        **Esempio di risposta corretta:**
        ```
        Torino
        Milano
        Napoli
        Roma
        ```

        **Testo del bando da analizzare:**
        {specific_section}

        **Ora elenca solo i nomi delle province, senza altro testo:**
    """
    # print(prompt)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        print("Error communicating with ChatGPT API:", str(e))
        return "Request failed."


def extract_provinces_from_chatgpt_result(result):
    """
    Extracts the province names from the ChatGPT result text.
    Cleans up unnecessary prefixes like "Provincia: ".
    """
    # Remove Markdown formatting if exists
    result = result.strip().strip("```").strip()

    # Split by line and clean up each entry
    lines = result.split("\n")
    provinces = []

    for line in lines:
        cleaned_line = line.strip()

        # Remove the prefix "Provincia: " if it exists
        if cleaned_line.lower().startswith("provincia:"):
            cleaned_line = cleaned_line[len("Provincia:"):].strip()

        if cleaned_line:  # Avoid adding empty strings
            provinces.append(cleaned_line)

    return provinces


def normalize_name(name):
    """
    Normalize province names to match the new format:
    - Converts "Agrigento" -> "(AG) Agrigento"
    - Special case: "Aosta" -> "(AO) Valle d'Aosta"
    """
    import re

    # Remove extra spaces and convert to lowercase
    normalized = re.sub(r'\s+', ' ', name.strip()).lower()

    # Özel durum: Aosta için manuel eşleştirme yap
    if normalized == "aosta":
        return "(AO) Valle d'Aosta"

    # Create a dictionary from available_choices mapping standard province names to formatted names
    formatted_provinces = {choice.split(") ", 1)[1].lower(): choice for choice in available_choices if ") " in choice}

    # If the extracted province name exists in the formatted list, return its correct format
    return formatted_provinces.get(normalized, normalized)



def update_airtable_record_with_provinces(table, record_id, provinces, available_choices, unmatched_record):
    """
    Updates an Airtable record with the extracted provinces in the '(AG) Agrigento' format.
    """
    # Create a dictionary mapping province names to their formatted versions (e.g., "Agrigento" -> "(AG) Agrigento")
    normalized_choices = {choice.split(") ", 1)[1].lower(): choice for choice in available_choices if ") " in choice}

    matched_choices = []  # List to store successfully matched provinces
    unmatched_provinces = []  # List for unmatched provinces

    # ✅ Normalize the extracted province names from ChatGPT
    chatgpt_provinces_normalized = [normalize_name(province) for province in provinces]

    for province in chatgpt_provinces_normalized:
        if province in normalized_choices.values():  # If it is already formatted correctly
            matched_choices.append(province)
        elif province in normalized_choices:  # If it is a valid province, format it correctly
            matched_choices.append(normalized_choices[province])

    # Identify unmatched provinces (those not found in ChatGPT's response)
    unmatched_provinces = [
        normalized_choices[province] for province in normalized_choices.keys() if
        normalized_choices[province] not in matched_choices
    ]

    print(f"Matched Choices: {matched_choices}")
    print(f"Unmatched Provinces: {unmatched_provinces}")

    try:
        if matched_choices:
            # ✅ Update the Airtable record with the matched provinces
            table.update(record_id, {"Tipo di campo isilay": matched_choices})
            print(f"✅ Record {record_id} successfully updated with provinces: {matched_choices}\n")
        else:
            print(f"⚠️ No valid provinces found for record {record_id}. Skipping update.\n")
    except Exception as e:
        print(f"❌ Error updating record {record_id}: {e}\n")



available_choices = [
    "(AQ) L'Aquila", "(CH) Chieti", "(PE) Pescara", "(TE) Teramo",
    "(MT) Matera", "(PZ) Potenza",
    "(CZ) Catanzaro", "(CS) Cosenza", "(KR) Crotone", "(RC) Reggio Calabria", "(VV) Vibo Valentia",
    "(AV) Avellino", "(BN) Benevento", "(CE) Caserta", "(NA) Napoli", "(SA) Salerno",
    "(BO) Bologna", "(FE) Ferrara", "(FC) Forlì-Cesena", "(MO) Modena", "(PR) Parma", "(PC) Piacenza",
    "(RA) Ravenna", "(RE) Reggio Emilia", "(RN) Rimini",
    "(GO) Gorizia", "(PN) Pordenone", "(TS) Trieste", "(UD) Udine",
    "(FR) Frosinone", "(LT) Latina", "(RI) Rieti", "(RM) Roma", "(VT) Viterbo",
    "(GE) Genova", "(IM) Imperia", "(SP) La Spezia", "(SV) Savona",
    "(BG) Bergamo", "(BS) Brescia", "(CO) Como", "(CR) Cremona", "(LC) Lecco", "(LO) Lodi",
    "(MN) Mantova", "(MI) Milano", "(MB) Monza e Brianza", "(PV) Pavia", "(SO) Sondrio", "(VA) Varese",
    "(AN) Ancona", "(AP) Ascoli Piceno", "(FM) Fermo", "(MC) Macerata", "(PU) Pesaro e Urbino",
    "(CB) Campobasso", "(IS) Isernia",
    "(AL) Alessandria", "(AT) Asti", "(BI) Biella", "(CN) Cuneo", "(NO) Novara", "(TO) Torino",
    "(VB) Verbano-Cusio-Ossola", "(VC) Vercelli",
    "(BA) Bari", "(BT) Barletta-Andria-Trani", "(BR) Brindisi", "(FG) Foggia", "(LE) Lecce", "(TA) Taranto",
    "(CA) Cagliari", "(CI) Carbonia-Iglesias", "(VS) Medio Campidano", "(NU) Nuoro", "(OG) Ogliastra",
    "(OT) Olbia-Tempio", "(OR) Oristano", "(SS) Sassari",
    "(AG) Agrigento", "(CL) Caltanissetta", "(CT) Catania", "(EN) Enna", "(ME) Messina", "(PA) Palermo",
    "(RG) Ragusa", "(SR) Siracusa", "(TP) Trapani",
    "(AR) Arezzo", "(FI) Firenze", "(GR) Grosseto", "(LI) Livorno", "(LU) Lucca", "(MS) Massa-Carrara",
    "(PI) Pisa", "(PT) Pistoia", "(PO) Prato", "(SI) Siena",
    "(BZ) Bolzano", "(TN) Trento",
    "(PG) Perugia", "(TR) Terni",
    "(AO) Valle d'Aosta",
    "(BL) Belluno", "(PD) Padova", "(RO) Rovigo", "(TV) Treviso", "(VE) Venezia", "(VR) Verona", "(VI) Vicenza"
]



def clean_available_choices(choices):
    """
    Cleans the available_choices list by:
    - Removing duplicates.
    - Stripping extra spaces around names.
    - Sorting for better readability.
    """
    cleaned_choices = set()  # Use a set to remove duplicates
    for choice in choices:
        cleaned_choices.add(choice.strip())

    return sorted(cleaned_choices)  # Return sorted list for readability



def main():
    """
    Main execution function:
    - Fetches records from Airtable
    - Extracts relevant sections from PDF text
    - Calls ChatGPT for province detection
    - Updates Airtable with the extracted province information
    """
    AIRTABLE_API_KEY = AIRTABLE_KEY
    TABLE_NAME = 'Bandi online'
    VIEW_NAME = 'Open'
    START_ROW = 154
    END_ROW = 294

    api = Api(AIRTABLE_API_KEY)
    table = api.table(BASE_ID, TABLE_NAME)
    openai.api_key = OPENAI_KEY

    unmatched_provinces_record = {}

    records = fetch_records(table, VIEW_NAME, START_ROW, END_ROW)

    cleaned_available_choices = clean_available_choices(available_choices)

    for record in records:
        text = process_airtable_pdfs_and_return_text(record)

        if text is None:
            print(f"⚠️ No PDF attachment found for record {record['id']}. Skipping...\n")
            continue

        text = summarize_text(text)

        # ✅ Extract the specific section before calling ChatGPT
        specific_section_text = extract_specific_section(text)

        if text is None:
            print(f"⚠️ No PDF attachment found for record {record['id']}. Skipping...\n")
            continue

        # ✅ Extract the specific section before calling ChatGPT
        specific_section_text = extract_specific_section(text)

        # ✅ Call ChatGPT with the extracted section
        result = call_chatgpt(specific_section_text)

        provinces = extract_provinces_from_chatgpt_result(result)

        record_id = record["id"]

        update_airtable_record_with_provinces(
            table, record_id, provinces, cleaned_available_choices, unmatched_provinces_record
        )


# ✅ Ensures that the script runs only when executed directly
if __name__ == "__main__":
    main()




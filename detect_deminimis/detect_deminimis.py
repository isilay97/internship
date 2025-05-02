from pyairtable import Api

from access_airtable import fetch_records
from access_airtable import process_airtable_pdfs_and_return_text
import spacy
from local_variables import BASE_ID, AIRTABLE_KEY




def detect_de_minimis(text, nlp):
    """
    Detects if 'de minimis' is present in the text, accounting for possible negations.
    Returns 'De Minimis' if detected without negation; otherwise, returns None.

    Parameters:
        text (str): The text to analyze.
        nlp: The NLP model for processing the text.

    Returns:
        str or None: 'De Minimis' if detected without negation; None otherwise.
    """
    try:
        doc = nlp(text)
        for token in doc:
            if token.text.lower() in ["minimis", "deminimis"]:
                # Define the span around the found token to check for negations
                minimis_span = doc[max(0, token.i - 7):token.i + 1]
                negation_detected = any(
                    tok.dep == "neg" or tok.text.lower() in ["non", "senza", "mancato", "nonostante"]
                    for tok in minimis_span
                )
                # Set result based on negation detection
                if not negation_detected:
                    return "De Minimis"
                else:
                    return None

    except Exception as e:
        print(f"Error detecting 'De Minimis': {e}")

#Initialize Spacy NLP model

nlp = spacy.load("it_core_news_sm")

def save_deminimis_status(record_id, result, table):
    """
    Updates the 'deminimis' checkbox field in an Airtable record based on the provided value.

    Parameters:
        record_id (str): The ID of the record to update.
        value (str): The value to evaluate ('De Minimis' will check the box).
        table: The Airtable table object.

    Returns:
        dict: The updated record from Airtable.
    """
    try:
        # Determine if the checkbox should be checked
        is_deminimis = result.lower() == "de minimis"

        # Prepare the field update
        fields = {"Deminimis": True}

        # Update the Airtable record
        updated_record = table.update(record_id, fields)

        print(f"Record {record_id} updated successfully with deminimis: {is_deminimis}")
        return updated_record
    except Exception as e:
        print(f"Error updating record {record_id}: {e}")
        return None



def main():
    column_name = "Deminimis"
    TABLE_NAME = "Bandi online"
    view = "Open"
    start_row = 6
    end_row = 6
    api = Api(AIRTABLE_KEY)

    table = api.table(BASE_ID, TABLE_NAME)

    records = fetch_records(table, view,start_row,end_row)

    for record in records:
        text= process_airtable_pdfs_and_return_text(record)
        if text:
            result = detect_de_minimis(text,nlp)
            save_deminimis_status(record["id"],result,table)


main()

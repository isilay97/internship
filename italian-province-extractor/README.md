# Italian Province Extractor from Public Funding PDFs

## Overview
This project automates the extraction of province names from funding call documents.  
It processes PDF attachments in Airtable, applies summarization if needed, and uses OpenAI’s GPT-4o to identify referenced provinces.  
The result is written back into a multiple-select field in Airtable using standardized labels.

## Key Features
- Integrates with Airtable to fetch and update records
- Supports scanned and encrypted PDFs (via OCR fallback)
- Extracts key sections using rule-based parsing
- Summarizes lengthy text before LLM processing
- Uses OpenAI GPT-4o for accurate, rules-based location extraction
- Normalizes output to match predefined province format (e.g., `(TO) Torino`)

## Technologies
- Python  
- Airtable API (`pyairtable`)  
- OpenAI GPT-4o  
- pdfplumber  
- pytesseract (OCR)  
- tiktoken (token counting)  
- Regex + rule-based filters

## Notes
This project was used to process over 100 real funding documents and automatically identify target provinces.

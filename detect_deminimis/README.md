# De Minimis Clause Detector (Airtable Integration)

## Overview
This script automates the detection of “De Minimis” clauses in PDF documents attached to Airtable records.  
It uses Italian language NLP (spaCy) to scan the document text and determine whether the clause is present or negated.  
Results are directly written to a checkbox field in the Airtable table.

## Key Features
- Connects to Airtable via API
- Parses and reads PDF attachments
- Uses spaCy NLP (Italian model) for clause detection
- Automatically updates the "De Minimis" checkbox field in Airtable
- Detects negated forms of the clause (e.g., “non de minimis”)

## Technologies
- Python  
- pyAirtable  
- spaCy (`it_core_news_sm`)  
- PDF text extraction  
- Airtable API

## Purpose
This is a showcase project for technical demonstration only. Not intended for external execution or deployment.

> This project was part of an internal automation effort during my internship.

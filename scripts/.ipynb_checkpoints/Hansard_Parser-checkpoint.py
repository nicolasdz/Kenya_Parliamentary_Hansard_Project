# @title Hansard Parser
# Author: Joshua Been
# Date: August 5, 2025

# This script is designed to parse multiple PDF files of Parliamentary Hansard reports,
# extract speeches by individual speakers, and compile them into a single,
# clean, and analysis-ready CSV file.

# --- Core Libraries ---
import os
import re
import csv
import html # Used to handle the decoding of HTML entities (e.g., &#x2019; to ').
from datetime import datetime

# --- Dependency Check ---
# This block checks if the required 'PyMuPDF' library is installed.
# If not, it uses Python's package manager (pip) to install it.
# This makes the script more portable and easier for others to run.
try:
    import fitz  # PyMuPDF
except ImportError:
    # Use the 'subprocess' module for a more robust way to call pip from within the script.
    import subprocess
    import sys
    print("PyMuPDF not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyMuPDF"])
    import fitz
    print("Installation complete.")


# ==============================================================================
# --- CONFIGURATION SETTINGS ---
# This section contains all the user-configurable variables. Adjust these values
# to change the script's behavior without modifying the core functions below.
# ==============================================================================

# The folder where your Hansard PDFs are located.
DOWNLOAD_DIR = "parliament_hansards"
# The name of the final output CSV file.
OUTPUT_CSV_FILE = "hansard_output_final.csv"
# Excel has a character limit per cell (32,767). We set a safe limit below this.
# Long speeches will be split intelligently across multiple rows.
MAX_CELL_LENGTH = 30000

# --- Speaker Identification ---
# A list of regular expression patterns to identify lines where a speaker begins.
# This pattern looks for common honorifics and titles that precede a speaker's name.
SPEAKER_PATTERNS = [
    r'^(Hon\.|The Speaker|The Deputy Speaker|The Temporary Speaker|Hon\. Chairlady|The Temporary Speaker \(Hon\.\)|Hon\. Members)'
]

# --- Content Cleaning ---
# A list of exact, case-sensitive phrases to be completely removed from the text.
# These are typically parenthetical notes about events in the chamber.
EXACT_NOTES_TO_REMOVE = [
    "(Applause)", "(Laughter)", "(Loud consultations)",
    "(The Quorum Bell was rung)", "(The Division Bell was rung)",
    "(Voting in progress)", "(Serjeant-at-Arms closed the bars)"
]

# A list of more complex patterns to remove using regular expressions.
# This is for notes that may have slight variations in their wording.
REGEX_PATTERNS_TO_REMOVE = [
    r"\(.*?spoke off the record.*?\)",
    r"\(The Oath of Allegiance was administered to.*?\)"
]

# A list of exact, case-insensitive headings to ignore during parsing.
# These are procedural sections, not speeches, so they should be skipped.
HEADINGS_TO_IGNORE = [
    "PRAYERS", "COMMUNICATION FROM THE CHAIR", "PAPERS LAID", "NOTICE OF MOTION",
    "ORDINARY QUESTIONS", "REQUEST FOR STATEMENTS", "ADMINISTRATION OF OATH",
    "PETITION", "STATEMENTS", "PERSONAL STATEMENT", "MOTION", "MOTIONS", "BILL", "BILLS",
    "DIVISION", "ADJOURNMENT", "PAPER LAID", "PAPER", "PAPERS"
]

# ==============================================================================
# --- CORE FUNCTIONS ---
# ==============================================================================

def repair_and_clean_text(text):
    """
    Repairs common encoding errors and cleans text extracted from the PDF.
    This function is crucial for ensuring data quality and readability.
    """
    if not text:
        return ""
    
    # --- Step 1: Repair common encoding errors (mojibake) ---
    # Sometimes, text encoded in UTF-8 is mistakenly read as another format (e.g., latin-1).
    # This code attempts to reverse that error.
    try:
        # This is a common fix for encoding issues, e.g., text that displays 'â€TM' instead of an apostrophe.
        repaired_text = text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        # If the repair attempt fails, it means the text was likely correct to begin with.
        repaired_text = text

    # --- Step 2: Replace non-standard punctuation with standard ASCII equivalents ---
    # This standardizes different types of quotes, dashes, etc., for consistency.
    replacements = {
        'â€œ': '"', 'â€': '"',  # Double quotes
        'â€™': "'",           # Apostrophe/Single quote
        'â€”': '-',           # Em-dash
        'â€¦': '...',         # Ellipsis
        '&#x2019;': "'",      # HTML entity for apostrophe
        '&#x201c;': '"',      # HTML entity for left double quote
        '&#x201d;': '"',      # HTML entity for right double quote
    }
    for bad, good in replacements.items():
        repaired_text = repaired_text.replace(bad, good)

    # --- Step 3: Remove any remaining HTML tags and normalize whitespace ---
    no_html = re.sub(r'<.*?>', '', repaired_text)
    # Replace multiple spaces or tabs with a single space.
    normalized_space = re.sub(r'[ \t]+', ' ', no_html)
    return normalized_space.strip()


def extract_metadata(filename, doc):
    """
    Extracts metadata (date, volume, number) from the PDF.
    It prioritizes parsing the filename first, then falls back to the document's content.
    """
    metadata = {"date": None, "volume": None, "number": None}
    
    # --- Plan A: Parse Date from Filename (e.g., "Hansard - 25th July 2024.pdf") ---
    date_match_name = re.search(r'(\d{1,2})(?:st|nd|rd|th)[\s_]([A-Za-z]+)[\s_](\d{4})', filename, re.IGNORECASE)
    if date_match_name:
        try:
            date_str = f"{date_match_name.group(1)} {date_match_name.group(2)} {date_match_name.group(3)}"
            # Standardize the date format to YYYY-MM-DD for easy sorting and analysis.
            metadata["date"] = datetime.strptime(date_str, "%d %B %Y").strftime("%Y-%m-%d")
        except ValueError:
            # If parsing fails (e.g., "32nd July"), try Plan B.
            pass 

    # --- Plan B: Parse from Document Content ---
    # If the filename didn't contain a usable date, scan the first couple of pages of text.
    if not metadata["date"]:
        text_from_first_pages = ""
        for page_num in range(min(2, len(doc))): # Read first 2 pages, or fewer if doc is short.
            text_from_first_pages += doc[page_num].get_text()
        
        # Try to find common date patterns like "25th July, 2024" or "July 25, 2024".
        date_match1 = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})\b', text_from_first_pages)
        date_match2 = re.search(r'\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b', text_from_first_pages)

        date_str, date_format = None, None
        if date_match1:
            date_str = f"{date_match1.group(1)} {date_match1.group(2)} {date_match1.group(3)}"
            date_format = "%d %B %Y"
        elif date_match2:
            date_str = f"{date_match2.group(1)} {date_match2.group(2)} {date_match2.group(3)}"
            date_format = "%B %d %Y"
        
        if date_str and date_format:
            try:
                metadata["date"] = datetime.strptime(date_str, date_format).strftime("%Y-%m-%d")
            except ValueError:
                metadata["date"] = date_str # Keep the raw string if format is unexpected.

    # --- Extract Volume and Number ---
    # These are usually found together on the first page in a "VOL. X NO. Y" format.
    text_for_vol = doc[0].get_text() + (doc[1].get_text() if len(doc) > 1 else "")
    vol_no_match = re.search(r'VOL\.\s+([IVXLCDM\d]+)\s+NO\.\s+([\d]+)', text_for_vol, re.IGNORECASE)
    if vol_no_match:
        metadata["volume"] = vol_no_match.group(1).strip()
        metadata["number"] = vol_no_match.group(2).strip()

    return metadata

def process_pdf_file(filepath, config):
    """
    The main processing function. It opens a PDF, extracts and cleans the text,
    identifies speakers, assembles their speeches, and returns a list of data records.
    """
    filename = os.path.basename(filepath)
    print(f"--- Processing: {filename} ---")
    try:
        doc = fitz.open(filepath)
    except Exception as e:
        print(f"      Could not open file {filename}. Error: {e}")
        return []

    # Extract metadata at the beginning of the process.
    metadata = extract_metadata(filename, doc)
    print(f"      Extracted Metadata: {metadata}")

    # --- Step 1: Extract all text blocks from the PDF ---
    # Processing paragraph by paragraph is more robust than using one giant string.
    all_blocks = []
    for page in doc:
        # Extract the page as HTML to preserve paragraph structure.
        page_html = page.get_text("html")
        # Decode HTML entities (e.g., &#x2019; -> ') before further processing.
        decoded_html = html.unescape(page_html)
        # Find all paragraphs within the <p> tags.
        paragraphs = re.findall(r'<p.*?>(.*?)</p>', decoded_html, re.DOTALL)
        for p_html in paragraphs:
            # Clean each paragraph individually.
            p_text = repair_and_clean_text(p_html)
            if p_text:
                all_blocks.append({'text': p_text})
    doc.close()

    # --- Step 2: First Pass - Identify all speakers and their locations ---
    speakers_with_locations = []
    # Combine all speaker patterns into a single regex for efficiency.
    combined_speaker_pattern = '|'.join(config['speaker_patterns'])
    for i, block in enumerate(all_blocks):
        text = block['text']
        # Ignore blocks that are just procedural headings.
        if text.strip().upper() in config['headings_to_ignore']:
            continue
        
        # A speaker line is assumed to contain a colon.
        if ':' in text:
            potential_speaker = text.split(':', 1)[0].strip()
            # Check if the start of the line matches our speaker patterns.
            if re.search(combined_speaker_pattern, potential_speaker, re.IGNORECASE):
                speakers_with_locations.append({"name": potential_speaker, "block_index": i})

    # --- Step 3: Second Pass - Extract content between speakers ---
    extracted_data = []
    for i, current_speaker in enumerate(speakers_with_locations):
        speaker_name = current_speaker["name"]
        start_block_index = current_speaker["block_index"]
        
        # The speech ends where the next speaker begins, or at the end of the document.
        end_block_index = len(all_blocks)
        if i + 1 < len(speakers_with_locations):
            end_block_index = speakers_with_locations[i+1]["block_index"]

        # --- Assemble the full speech content ---
        content_accumulator = []
        # The first line of the speech is the text after the colon on the speaker's line.
        first_block_text = all_blocks[start_block_index]['text']
        if ':' in first_block_text:
            content_accumulator.append(first_block_text.split(':', 1)[1].strip())

        # Add all subsequent text blocks until the next speaker is found.
        for b_index in range(start_block_index + 1, end_block_index):
            block_text = all_blocks[b_index]['text']
            # Stop if a procedural heading is encountered mid-speech.
            if block_text.strip().upper() in config['headings_to_ignore']:
                break
            content_accumulator.append(block_text)

        # --- Final Cleaning and Formatting ---
        # Join all parts of the speech, preserving paragraph breaks with a special marker.
        full_content = " [NEWLINE] ".join(filter(None, content_accumulator))
        
        # Perform the final cleaning on the fully assembled speech.
        cleaned_lines = []
        for line in full_content.split(" [NEWLINE] "):
            temp_line = line
            # Remove exact notes like (Applause).
            for note in config['exact_notes_to_remove']: 
                temp_line = temp_line.replace(note, '')
            # Remove more complex patterns via regex.
            for pattern in config['regex_patterns_to_remove']: 
                temp_line = re.sub(pattern, '', temp_line, flags=re.IGNORECASE)
            
            # Consolidate extra spaces within the line.
            cleaned_line = re.sub(r'\s+', ' ', temp_line).strip()
            if cleaned_line:
                 cleaned_lines.append(cleaned_line)

        # Join the cleaned lines back together, creating a clean multi-line string.
        final_content = ' \n'.join(cleaned_lines)

        if not final_content:
            continue

        # --- Smart Splitter for Excel ---
        # If content is too long for one cell, split it into multiple rows.
        is_first_chunk = True
        remaining_content = final_content
        while remaining_content:
            chunk = ""
            if len(remaining_content) > MAX_CELL_LENGTH:
                # Find the last space before the limit to avoid breaking words.
                split_index = remaining_content.rfind(' ', 0, MAX_CELL_LENGTH)
                if split_index == -1: # If no space is found, a hard cut is necessary.
                    split_index = MAX_CELL_LENGTH
                chunk = remaining_content[:split_index]
                remaining_content = remaining_content[split_index:].lstrip()
            else:
                chunk = remaining_content
                remaining_content = ""

            # This formula creates a clickable link in Excel to the source PDF.
            source_link_formula = f'=HYPERLINK("{filename}", "Open PDF")'
            
            record = {
                "filename": filename,
                "speaker": speaker_name,
                "content": chunk,
                "source_link": source_link_formula,
                "is_continuation": not is_first_chunk
            }
            # The first chunk of a speech gets the full metadata.
            if is_first_chunk:
                record.update(metadata)
            else:
                # Subsequent chunks get empty metadata fields for clarity in the CSV.
                record.update({"date": "", "volume": "", "number": ""})

            extracted_data.append(record)
            is_first_chunk = False

    return extracted_data

# ==============================================================================
# --- SCRIPT EXECUTION BLOCK ---
# This is the part of the script that runs when you execute the file directly.
# ==============================================================================
if __name__ == "__main__":
    # Create the input directory if it doesn't exist.
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        print(f"Created directory '{DOWNLOAD_DIR}'. Please place your PDF files inside.")

    # Load the configuration settings into a dictionary to pass to the processor.
    config = {
        'speaker_patterns': SPEAKER_PATTERNS,
        'exact_notes_to_remove': EXACT_NOTES_TO_REMOVE,
        'regex_patterns_to_remove': REGEX_PATTERNS_TO_REMOVE,
        'headings_to_ignore': HEADINGS_TO_IGNORE
    }

    all_speaker_data = []
    # Sort the files to ensure a consistent processing order.
    try:
        files_in_dir = sorted(os.listdir(DOWNLOAD_DIR))
    except FileNotFoundError:
        files_in_dir = []
        print(f"Error: The directory '{DOWNLOAD_DIR}' was not found.")

    if not files_in_dir:
        print(f"\nNo files found in '{DOWNLOAD_DIR}'. Please add PDF files and run again.")
    else:
        # Loop through all files in the directory.
        for filename in files_in_dir:
            # Process only files that end with .pdf.
            if filename.lower().endswith('.pdf'):
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                # The data from each file is added to our master list.
                all_speaker_data.extend(process_pdf_file(filepath, config))

    # --- Write all collected data to a single CSV file ---
    if all_speaker_data:
        # Define the headers for the CSV file. This order determines the column order.
        fieldnames = ['filename', 'date', 'volume', 'number', 'speaker', 'content', 'source_link', 'is_continuation']
        
        with open(OUTPUT_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_speaker_data)
        
        print(f"\nSuccessfully created consolidated CSV file: '{OUTPUT_CSV_FILE}'")
    else:
        print("\nNo speaker data was extracted. Check that PDF files are in the correct directory.")

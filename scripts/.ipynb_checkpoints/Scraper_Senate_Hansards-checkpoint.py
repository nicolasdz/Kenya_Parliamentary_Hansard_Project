# @title Web Scraper for Senate Hansards
# Date: August 5, 2025

# This script automates the process of downloading Hansard PDF documents
# from the official Parliament of Kenya website for the Senate.
# It is designed to be robust, automatically discovering all available parliamentary
# sessions and pages to ensure a complete collection of documents.

# --- Core Libraries ---
import os                   # For interacting with the operating system (e.g., creating directories, checking for files).
import requests             # For making HTTP requests to fetch web pages.
from bs4 import BeautifulSoup # For parsing HTML content and extracting data.
from urllib.parse import unquote, urljoin, urlparse, parse_qs # For handling and parsing URLs.
import time                 # For adding delays to be respectful to the web server.

# ==============================================================================
# --- CONFIGURATION SETTINGS ---
# ==============================================================================

# The base URL of the website, used for constructing absolute URLs from relative ones.
BASE_URL = "https://www.parliament.go.ke"
# The starting page that lists the Senate Hansard documents.
START_URL = "https://www.parliament.go.ke/the-senate/Hansard"
# The name of the local directory where the downloaded Senate PDFs will be saved.
DOWNLOAD_DIR = "senate_hansards"

# ==============================================================================
# --- SCRIPT EXECUTION ---
# ==============================================================================

# --- Step 1: Setup the Download Directory ---
# Check if the target directory exists. If not, create it.
# This prevents errors when the script tries to save files.
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Step 2: Dynamically Discover Available Parliamentary Sessions ---
# Instead of hardcoding session years, the script first visits the main Hansard
# page to find all available sessions listed in the filter dropdown menu.
# This makes the script future-proof, as it will automatically find new sessions
# as they are added to the website.
session_values = []
try:
    print("Finding available parliamentary sessions for the Senate...")
    main_page_response = requests.get(START_URL)
    # Raise an exception if the request was unsuccessful (e.g., 404 Not Found).
    main_page_response.raise_for_status()
    soup = BeautifulSoup(main_page_response.text, 'html.parser')

    # Find the HTML <select> element (dropdown menu) by its 'name' attribute.
    session_dropdown = soup.find('select', {'name': 'field_parliament_value'})
    if session_dropdown:
        # Extract the 'value' from each <option> tag within the dropdown.
        # The first option is usually a placeholder like "- Any -", so it's skipped.
        for option in session_dropdown.find_all('option')[1:]:
            if option.has_attr('value'):
                session_values.append(option['value'])
    print(f"Found Senate sessions: {session_values}")
except requests.exceptions.RequestException as e:
    print(f"Could not fetch parliamentary sessions: {e}")

# --- Step 3: Iterate Through Each Session and Download PDFs ---
# The script will now loop through each session it discovered for the Senate.
for session in session_values:
    print(f"\n--- Starting Senate session: {session} ---")

    # --- Step 3a: Dynamically Determine the Number of Pages for the Session ---
    # For each session, the script checks for pagination to find out how many pages
    # of documents exist. This avoids needing to guess the number of pages.
    last_page = 0 # Default to 0 (meaning one page) if pagination isn't found.
    try:
        # Construct a URL for the first page of the current session.
        first_page_url = f"{START_URL}?title=%20&field_parliament_value={session}&page=0"
        response = requests.get(first_page_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # The most reliable way to find the last page is to look for the "last" button
        # in the pagination controls (e.g., First < 1 2 3 ... > Last).
        last_page_li = soup.find('li', class_='pager-last')
        if last_page_li and last_page_li.find('a'):
            href = last_page_li.find('a')['href']
            # The URL's query string (e.g., "?...&page=52") contains the page number.
            query_params = parse_qs(urlparse(href).query)
            if 'page' in query_params:
                last_page = int(query_params['page'][0])
        else:
            # Fallback strategy: If there is no "last" link (e.g., on sessions with few pages),
            # find all visible page number links and use the highest number as the last page.
            page_links = soup.select('ul.pager li.pager-item a')
            if page_links:
                pages = [int(parse_qs(urlparse(a['href']).query).get('page', ['0'])[0]) for a in page_links]
                last_page = max(pages) if pages else 0

        print(f"Found {last_page + 1} pages for this session.")

    except requests.exceptions.RequestException as e:
        print(f"Could not determine page count for session {session}: {e}")
        continue # Skip to the next session if page count cannot be determined.

    # --- Step 3b: Loop Through Each Page and Scrape PDF Links ---
    # The page numbers on this website are 0-indexed.
    for page_num in range(last_page + 1):
        page_url = f"{START_URL}?title=%20&field_parliament_value={session}&page={page_num}"
        print(f"Scraping page: {page_url}")

        try:
            response = requests.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # The links to the PDFs are inside a table, within <td> elements
            # that have a specific class name. This targets them precisely.
            for td in soup.find_all('td', class_='views-field-field-pdf'):
                link = td.find('a') # Find the anchor (<a>) tag within the cell.
                if link and 'href' in link.attrs:
                    pdf_url = link['href']

                    # Use urljoin to gracefully handle both absolute URLs (starting with http)
                    # and relative URLs (e.g., /sites/default/...).
                    pdf_url = urljoin(BASE_URL, pdf_url)

                    # The filename is part of the URL. 'unquote' handles special
                    # characters in the URL (e.g., %20 for a space).
                    filename = os.path.basename(unquote(pdf_url))
                    filepath = os.path.join(DOWNLOAD_DIR, filename)

                    # --- Step 3c: Download the PDF ---
                    # To save time and bandwidth, check if the file already exists.
                    if not os.path.exists(filepath):
                        print(f"  Downloading: {filename}")
                        # Fetch the PDF file content.
                        pdf_response = requests.get(pdf_url)
                        pdf_response.raise_for_status()

                        # Save the content to a local file. 'wb' mode is used for
                        # writing binary data like PDFs.
                        with open(filepath, 'wb') as f:
                            f.write(pdf_response.content)
                        
                        # A "politeness" delay to avoid sending too many requests
                        # to the server in a short period of time.
                        time.sleep(1)
                    else:
                        print(f"  Skipping (already exists): {filename}")

        except requests.exceptions.RequestException as e:
            # This ensures that if one page fails, the script can continue with the next.
            print(f"An error occurred while scraping page {page_num}: {e}")

print("\nScraping process completed.")

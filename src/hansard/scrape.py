"""Download Hansard PDFs from the Parliament of Kenya website.

Originally written by Josh Been as separate National Assembly and Senate
notebooks (August 2025). The two were identical apart from the listing URL,
so both chambers now share this module.

Sessions are discovered from the listing page's filter dropdown, so new
parliamentary sessions are picked up automatically.
"""

import os
import re
import time
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import BASE_URL
from .manifest import load_manifest, save_manifest

# The Hansard listings also contain order papers and similar documents; these
# are recorded in the manifest but not downloaded.
NON_HANSARD_FILENAME = re.compile(r'ORDER PAPER|ORDERS OF THE DAY|VOTES AND PROCEEDINGS', re.IGNORECASE)

REQUEST_TIMEOUT = 60  # Seconds.
POLITENESS_DELAY = 1  # Seconds to wait after each download.
USER_AGENT = "kenya-hansard-pipeline (+https://github.com/nicolasdz/Kenya_Parliamentary_Hansard_Project)"


def _get_soup(session, url):
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, 'html.parser')


def _page_from_href(li):
    """Return the 0-indexed page number linked from a pager <li>, or None."""
    if li and li.find('a'):
        query_params = parse_qs(urlparse(li.find('a')['href']).query)
        if 'page' in query_params:
            return int(query_params['page'][0])
    return None


def find_sessions(session, listing_url):
    """Return the parliamentary session values from the listing page's filter dropdown."""
    soup = _get_soup(session, listing_url)
    dropdown = soup.find('select', {'name': 'field_parliament_value'})
    if not dropdown:
        return []
    # The first option is a placeholder like "- Any -".
    return [option['value'] for option in dropdown.find_all('option')[1:] if option.has_attr('value')]


def find_last_page(soup):
    """Return the 0-indexed number of the last listing page, trying several pager formats."""
    # Method 1: the "Last" button, using the most common class name.
    last_page = _page_from_href(soup.find('li', class_='pager__item--last'))
    if last_page is not None:
        return last_page

    # Method 2: the "Last" button, using an alternative class name.
    last_page = _page_from_href(soup.find('li', class_='pager-last'))
    if last_page is not None:
        return last_page

    # Method 3: short sessions render no "Last" button, so use the highest visible
    # page number. Visible numbers are 1-indexed; the URL parameter is 0-indexed.
    pages = [0]
    for item in soup.select('ul.pager li, ul.pager__items li'):
        text = item.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text) - 1)
    return max(pages)


def find_pdf_links(soup):
    """Return the absolute URLs of every PDF in a listing page's table."""
    links = []
    for td in soup.find_all('td', class_='views-field-field-pdf'):
        link = td.find('a')
        if link and 'href' in link.attrs:
            links.append(urljoin(BASE_URL, link['href']))
    return links


def scrape_chamber(chamber, sessions=None, dry_run=False):
    """Download every Hansard PDF for a chamber that isn't already in its PDF folder.

    `sessions` limits scraping to specific session values; by default all are scraped.
    With `dry_run`, files are listed but not downloaded. Either way, every PDF link
    found is recorded in the manifest. Returns the number of new files.
    """
    os.makedirs(chamber.pdf_dir, exist_ok=True)
    http = requests.Session()
    http.headers['User-Agent'] = USER_AGENT

    print(f"Finding available parliamentary sessions for the {chamber.label}...")
    try:
        session_values = find_sessions(http, chamber.hansard_url)
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch parliamentary sessions: {e}")
        return 0
    print(f"Found sessions: {session_values}")
    if sessions:
        session_values = [s for s in session_values if s in sessions]

    manifest = load_manifest()
    new_files = 0
    failed = []
    seen = set()  # The site lists some files more than once.
    for session_value in session_values:
        print(f"\n--- Starting session: {session_value} ---")
        # Saved after each session so an interrupted run keeps what it found.
        if seen:
            save_manifest(manifest)
        page_url = f"{chamber.hansard_url}?title=%20&field_parliament_value={session_value}&page={{}}"

        try:
            last_page = find_last_page(_get_soup(http, page_url.format(0)))
        except requests.exceptions.RequestException as e:
            print(f"Could not determine page count for session {session_value}: {e}")
            continue
        print(f"Found {last_page + 1} pages for this session.")

        for page_num in range(last_page + 1):
            url = page_url.format(page_num)
            print(f"Scraping page: {url}")
            try:
                pdf_urls = find_pdf_links(_get_soup(http, url))
            except requests.exceptions.RequestException as e:
                # Log errors for individual pages but carry on with the rest.
                print(f"An error occurred while scraping page {page_num}: {e}")
                continue

            for pdf_url in pdf_urls:
                filename = os.path.basename(unquote(pdf_url))
                filepath = chamber.pdf_dir / filename
                # Keep the first URL seen for a filename (listings run newest first).
                manifest.setdefault((chamber.key, filename), {
                    "chamber": chamber.key, "filename": filename,
                    "source_url": pdf_url, "session": session_value,
                })
                if filepath.exists() or filename in seen:
                    print(f"  Skipping (already exists): {filename}")
                    continue
                seen.add(filename)
                if NON_HANSARD_FILENAME.search(filename):
                    print(f"  Skipping (not a Hansard): {filename}")
                    continue

                if dry_run:
                    print(f"  Would download: {filename}")
                    new_files += 1
                    continue
                print(f"  Downloading: {filename}")
                try:
                    pdf_response = http.get(pdf_url, timeout=REQUEST_TIMEOUT)
                    pdf_response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    # A broken link (the site has some 404s) shouldn't stop the rest of the page.
                    print(f"  Could not download {filename}: {e}")
                    failed.append(pdf_url)
                    continue
                filepath.write_bytes(pdf_response.content)
                new_files += 1
                time.sleep(POLITENESS_DELAY)

    save_manifest(manifest)
    verb = "would be downloaded" if dry_run else "downloaded"
    print(f"\nScraping completed: {new_files} new file(s) {verb}.")
    if failed:
        print(f"{len(failed)} file(s) could not be downloaded:")
        for pdf_url in failed:
            print(f"  {pdf_url}")
    return new_files

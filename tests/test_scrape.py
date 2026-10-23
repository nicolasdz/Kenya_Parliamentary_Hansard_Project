from bs4 import BeautifulSoup

from hansard.scrape import find_last_page, find_pdf_links


def soup(markup):
    return BeautifulSoup(markup, "html.parser")


def test_last_page_from_last_button():
    page = soup('<ul class="pager__items"><li class="pager__item--last"><a href="?x=1&page=7">Last</a></li></ul>')
    assert find_last_page(page) == 7


def test_last_page_from_alternative_class():
    page = soup('<ul class="pager"><li class="pager-last"><a href="?page=3">last</a></li></ul>')
    assert find_last_page(page) == 3


def test_last_page_from_visible_numbers():
    page = soup('<ul class="pager"><li>1</li><li>2</li><li>3</li></ul>')
    assert find_last_page(page) == 2


def test_single_page_session():
    assert find_last_page(soup("<div>No pager</div>")) == 0


def test_find_pdf_links_makes_urls_absolute():
    page = soup(
        '<table><tr><td class="views-field-field-pdf"><a href="/sites/default/files/a%20b.pdf">PDF</a></td></tr>'
        '<tr><td class="views-field-field-pdf"></td></tr></table>'
    )
    assert find_pdf_links(page) == ["https://www.parliament.go.ke/sites/default/files/a%20b.pdf"]

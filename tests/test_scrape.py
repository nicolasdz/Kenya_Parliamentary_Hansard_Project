import requests
from bs4 import BeautifulSoup

from hansard import scrape
from hansard.config import Chamber
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


class FakeResponse:
    def __init__(self, status=200, text="", content=b""):
        self.status_code, self.text, self.content = status, text, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Client Error")


LISTING = (
    '<select name="field_parliament_value"><option>- Any -</option><option value="2022">2022</option></select>'
    '<table><tr><td class="views-field-field-pdf"><a href="/files/missing.pdf">PDF</a></td></tr>'
    '<tr><td class="views-field-field-pdf"><a href="/files/present.pdf">PDF</a></td></tr></table>'
)


class FakeSession:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout):
        if url.endswith("missing.pdf"):
            return FakeResponse(status=404)
        if url.endswith(".pdf"):
            return FakeResponse(content=b"%PDF-1.4 test")
        return FakeResponse(text=LISTING)


def test_broken_link_does_not_skip_the_rest_of_the_page(tmp_path, monkeypatch):
    monkeypatch.setattr(scrape.requests, "Session", FakeSession)
    monkeypatch.setattr(scrape, "POLITENESS_DELAY", 0)
    monkeypatch.setattr(scrape, "load_manifest", lambda: {})
    saved = {}
    monkeypatch.setattr(scrape, "save_manifest", saved.update)
    chamber = Chamber("senate", "Senate", "https://www.parliament.go.ke/the-senate/Hansard",
                      tmp_path, tmp_path / "out.csv")

    assert scrape.scrape_chamber(chamber) == 1
    assert (tmp_path / "present.pdf").read_bytes() == b"%PDF-1.4 test"
    assert not (tmp_path / "missing.pdf").exists()
    assert {filename for _, filename in saved} == {"missing.pdf", "present.pdf"}

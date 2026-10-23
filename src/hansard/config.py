"""Project paths and per-chamber settings shared by the scraper and parser."""

import os
from dataclasses import dataclass
from pathlib import Path

# The project root is two levels above this package (src/hansard/ -> project root).
# Set HANSARD_ROOT to point the pipeline at a different data location.
PROJECT_ROOT = Path(os.environ.get("HANSARD_ROOT", Path(__file__).resolve().parents[2]))
INPUTS_DIR = PROJECT_ROOT / "inputs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
MEMBERS_FILE = INPUTS_DIR / "parliamentarians" / "googlesheet.tsv"

BASE_URL = "https://www.parliament.go.ke"


@dataclass(frozen=True)
class Chamber:
    key: str
    label: str
    hansard_url: str  # Listing page with the session filter and paginated PDF table.
    pdf_dir: Path
    output_csv: Path


CHAMBERS = {
    "national_assembly": Chamber(
        key="national_assembly",
        label="National Assembly",
        hansard_url=f"{BASE_URL}/the-national-assembly/house-business/hansard",
        pdf_dir=INPUTS_DIR / "national_assembly_hansards",
        output_csv=OUTPUTS_DIR / "national_assembly_parser_outputs.csv",
    ),
    "senate": Chamber(
        key="senate",
        label="Senate",
        hansard_url=f"{BASE_URL}/the-senate/Hansard",
        pdf_dir=INPUTS_DIR / "senate_hansards",
        output_csv=OUTPUTS_DIR / "senate_parser_outputs.csv",
    ),
}

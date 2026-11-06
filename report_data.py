"""Read the saved evaluation report without running tests or changing case data."""
from pathlib import Path

REPORT_PATH = Path(__file__).parent / "test_results.md"


def report_sections(text: str) -> dict[str, str]:
    sections = {}
    heading = "Introduction"
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            sections[heading] = "\n".join(lines).strip()
            heading, lines = line[3:], []
        else:
            lines.append(line)
    sections[heading] = "\n".join(lines).strip()
    return sections


def table_rows(section: str) -> list[list[str]]:
    rows = [line.strip().strip("|").split("|") for line in section.splitlines()
            if line.lstrip().startswith("|")]
    return [[cell.strip() for cell in row] for row in rows[2:]]

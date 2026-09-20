import json
from pathlib import Path


def matrix_to_markdown(table: list[list[str]]) -> str:
    if not table:
        return ""

    max_cols = max(len(row) for row in table)
    cleaned_rows = []

    for row in table:
        padded = row + [""] * (max_cols - len(row))
        # Sanitize pipes and linebreaks inside cells
        cells = [c.replace("\n", " ").replace("|", "\\|").strip() for c in padded]
        cleaned_rows.append(cells)

    header = "| " + " | ".join(cleaned_rows[0]) + " |"
    separator = "| " + " | ".join(["---"] * max_cols) + " |"
    body = ["| " + " | ".join(r) + " |" for r in cleaned_rows[1:]]

    return "\n".join([header, separator] + body)


def convert_file(input_file: str, output_file: str = "extracted_tables.md"):
    data = json.loads(Path(input_file).read_text(encoding="utf-8"))
    md_sections = []

    for item in data:
        page = item.get("page")
        tables = item.get("tables", [])

        if not tables:
            continue

        for idx, table in enumerate(tables, start=1):
            md_table = matrix_to_markdown(table)
            md_sections.append(f"### Sayfa {page} - Tablo {idx}\n\n{md_table}")

    output_content = "\n\n---\n\n".join(md_sections)
    Path(output_file).write_text(output_content, encoding="utf-8")
    print(f"Markdown tables saved to {output_file}")


if __name__ == "__main__":
    convert_file("01_pages.json", "01_pages.md")
    convert_file("02_tables.json", "02_tables.md")
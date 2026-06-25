from __future__ import annotations

from html.parser import HTMLParser

import pandas as pd


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            self._current_row.append(" ".join("".join(self._cell_parts).split()))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._current_row:
                self._current_table.append(self._current_row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            if self._current_table:
                self.tables.append(self._current_table)
            self._in_table = False


def parse_html_tables(text: str) -> list[pd.DataFrame]:
    parser = _TableParser()
    parser.feed(text.replace("<!--", "").replace("-->", ""))
    frames: list[pd.DataFrame] = []
    for table in parser.tables:
        if not table:
            continue
        header = table[0]
        rows = table[1:]
        if not rows:
            continue
        width = len(header)
        normalized_rows = [row[:width] + [""] * max(0, width - len(row)) for row in rows]
        frames.append(pd.DataFrame(normalized_rows, columns=header))
    return frames

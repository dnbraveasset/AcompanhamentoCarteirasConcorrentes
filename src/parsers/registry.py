"""Fábrica de parsers: mapeia extensão de arquivo para o parser adequado."""
from __future__ import annotations

from typing import Optional

from src.parsers.base_parser import BaseParser
from src.parsers.csv_parser import CsvParser
from src.parsers.excel_parser import ExcelParser
from src.parsers.pdf_parser import PdfParser
from src.parsers.txt_parser import TxtParser
from src.parsers.xml_parser import XmlParser
from src.parsers.zip_parser import ZipParser

_MAPA = {
    ".xml": XmlParser,
    ".pdf": PdfParser,
    ".xlsx": ExcelParser,
    ".xls": ExcelParser,
    ".csv": CsvParser,
    ".txt": TxtParser,
    ".zip": ZipParser,
}


def parser_para_extensao(ext: str) -> Optional[BaseParser]:
    cls = _MAPA.get(ext.lower())
    return cls() if cls else None

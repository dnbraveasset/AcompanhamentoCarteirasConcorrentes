"""
Parser de PDF.

Estratégia MVP: extrair texto e tabelas com pdfplumber e recuperar CNPJs por
regex, associando valores/percentuais quando aparecem na mesma linha. PDFs de
CDA não têm layout único, então priorizamos resiliência sobre precisão total.
Para tabelas complexas, camelot/tabula podem ser plugados depois (ver README).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from src.parsers.base_parser import BaseParser, Holding, ResultadoParse
from src.utils.cnpj import CNPJ_REGEX, normalizar_cnpj
from src.utils.file_utils import parse_decimal_br

# valores monetários / percentuais na mesma linha do CNPJ
_VALOR_RE = re.compile(r"[-+]?\d{1,3}(?:\.\d{3})*,\d{2}")
_PCT_RE = re.compile(r"(\d{1,3},\d{1,4})\s*%")


class PdfParser(BaseParser):
    formato = "pdf"

    def parse(self, caminho: Path) -> ResultadoParse:
        resultado = ResultadoParse(formato="pdf")
        try:
            import pdfplumber
        except ImportError:
            resultado.aviso = "pdfplumber não instalado; instale para ler PDFs."
            return resultado

        linhas: List[str] = []
        try:
            with pdfplumber.open(caminho) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text() or ""
                    linhas.extend(txt.splitlines())
        except Exception as e:  # não deixa quebrar a importação
            resultado.aviso = f"Falha ao ler PDF: {e}"
            return resultado

        holdings: List[Holding] = []
        vistos = set()
        for linha in linhas:
            for bruto in CNPJ_REGEX.findall(linha):
                cnpj = normalizar_cnpj(bruto, validar=True)
                if not cnpj or cnpj in vistos:
                    continue
                vistos.add(cnpj)
                valor = self._maior_valor(linha)
                pct = self._percentual(linha)
                nome = self._nome_aproximado(linha, bruto)
                holdings.append(
                    Holding(
                        cnpj_investido=cnpj,
                        nome_ativo=nome,
                        tipo_ativo="PDF",
                        valor_financeiro=valor,
                        percentual=pct,
                    )
                )

        resultado.holdings = holdings
        if not holdings:
            resultado.aviso = "Nenhum CNPJ localizado no PDF."
        return resultado

    @staticmethod
    def _maior_valor(linha: str) -> Optional[float]:
        valores = [parse_decimal_br(v) for v in _VALOR_RE.findall(linha)]
        valores = [v for v in valores if v is not None]
        return max(valores) if valores else None

    @staticmethod
    def _percentual(linha: str) -> Optional[float]:
        m = _PCT_RE.search(linha)
        return parse_decimal_br(m.group(1)) if m else None

    @staticmethod
    def _nome_aproximado(linha: str, cnpj_bruto: str) -> Optional[str]:
        # texto antes do CNPJ, sem números soltos, como nome aproximado
        antes = linha.split(cnpj_bruto)[0].strip(" \t-|")
        antes = re.sub(r"[\d.,/%-]+$", "", antes).strip()
        return antes or None

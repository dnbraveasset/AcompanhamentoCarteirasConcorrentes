"""
Parser de CSV.

Detecta separador (`;` ou `,`) e encoding, reaproveitando a mesma heurística
de colunas do parser de Excel. Fallback por regex se não achar coluna de CNPJ.
"""
from __future__ import annotations

import csv as _csv
from pathlib import Path
from typing import List, Optional

from src.parsers.base_parser import BaseParser, Holding, ResultadoParse
from src.parsers.excel_parser import (
    _achar_coluna, _COLS_CNPJ, _COLS_NOME, _COLS_VALOR, _COLS_PCT,
)
from src.utils.cnpj import normalizar_cnpj
from src.utils.file_utils import parse_decimal_br


def _detectar_sep(amostra: str) -> str:
    try:
        dialect = _csv.Sniffer().sniff(amostra, delimiters=";,\t")
        return dialect.delimiter
    except Exception:
        return ";" if amostra.count(";") >= amostra.count(",") else ","


class CsvParser(BaseParser):
    formato = "csv"

    def parse(self, caminho: Path) -> ResultadoParse:
        import pandas as pd

        resultado = ResultadoParse(formato="csv")
        # tenta encodings comuns no Brasil
        conteudo = None
        for enc in ("utf-8-sig", "windows-1252", "latin-1"):
            try:
                conteudo = Path(caminho).read_text(encoding=enc)
                encoding_ok = enc
                break
            except UnicodeDecodeError:
                continue
        if conteudo is None:
            resultado.aviso = "Não foi possível decodificar o CSV."
            return resultado

        sep = _detectar_sep(conteudo[:4096])
        try:
            df = pd.read_csv(caminho, sep=sep, dtype=str, encoding=encoding_ok)
        except Exception as e:
            resultado.aviso = f"Falha ao ler CSV: {e}"
            resultado.holdings = self.fallback_cnpjs(conteudo, tipo_ativo="CSV")
            return resultado

        holdings: List[Holding] = []
        col_cnpj = _achar_coluna(df.columns, _COLS_CNPJ)
        if col_cnpj is not None:
            col_nome = _achar_coluna(df.columns, _COLS_NOME)
            col_valor = _achar_coluna(df.columns, _COLS_VALOR)
            col_pct = _achar_coluna(df.columns, _COLS_PCT)
            for _, row in df.iterrows():
                cnpj = normalizar_cnpj(row.get(col_cnpj), validar=True)
                if not cnpj:
                    continue
                holdings.append(
                    Holding(
                        cnpj_investido=cnpj,
                        nome_ativo=(str(row.get(col_nome)).strip() if col_nome else None) or None,
                        tipo_ativo="CSV",
                        valor_financeiro=parse_decimal_br(row.get(col_valor)) if col_valor else None,
                        percentual=parse_decimal_br(row.get(col_pct)) if col_pct else None,
                    )
                )
        else:
            holdings = self.fallback_cnpjs(conteudo, tipo_ativo="CSV")

        resultado.holdings = holdings
        if not holdings:
            resultado.aviso = "Nenhum CNPJ localizado no CSV."
        return resultado

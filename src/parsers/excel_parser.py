"""
Parser de XLSX/XLS.

Lê todas as abas com pandas e tenta identificar heuristicamente as colunas de
CNPJ, nome, valor e percentual. Se não identificar colunas, cai no fallback:
varre todas as células como texto e extrai CNPJs por regex.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from src.parsers.base_parser import BaseParser, Holding, ResultadoParse
from src.utils.cnpj import normalizar_cnpj
from src.utils.file_utils import parse_decimal_br

_COLS_CNPJ = ("cnpj",)
_COLS_NOME = ("nome", "ativo", "fundo", "emissor", "descri", "papel")
_COLS_VALOR = ("valor", "financeiro", "mercado", "merc", "posicao", "posição", "vl_merc")
_COLS_PCT = ("percentual", "%", "pct", "perc", "part")


def _achar_coluna(colunas, chaves) -> Optional[str]:
    for c in colunas:
        cl = str(c).strip().lower()
        if any(k in cl for k in chaves):
            return c
    return None


class ExcelParser(BaseParser):
    formato = "xlsx"

    def parse(self, caminho: Path) -> ResultadoParse:
        import pandas as pd

        resultado = ResultadoParse(formato="xlsx")
        holdings: List[Holding] = []
        try:
            abas = pd.read_excel(caminho, sheet_name=None, dtype=str)
        except Exception as e:
            resultado.aviso = f"Falha ao ler Excel: {e}"
            return resultado

        for _, df in abas.items():
            if df is None or df.empty:
                continue
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
                            tipo_ativo="XLSX",
                            valor_financeiro=parse_decimal_br(row.get(col_valor)) if col_valor else None,
                            percentual=parse_decimal_br(row.get(col_pct)) if col_pct else None,
                        )
                    )
            else:
                # fallback: concatena tudo como texto
                texto = "\n".join(df.astype(str).fillna("").apply(" ".join, axis=1))
                holdings.extend(self.fallback_cnpjs(texto, tipo_ativo="XLSX"))

        # dedup por CNPJ
        vistos, unicos = set(), []
        for h in holdings:
            chave = (h.cnpj_investido, h.nome_ativo)
            if chave not in vistos:
                vistos.add(chave)
                unicos.append(h)
        resultado.holdings = unicos
        if not unicos:
            resultado.aviso = "Nenhum CNPJ localizado no Excel."
        return resultado

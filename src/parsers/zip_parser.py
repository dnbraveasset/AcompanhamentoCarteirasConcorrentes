"""
Parser de ZIP.

Extrai os arquivos internos num diretório temporário e delega cada um ao parser
apropriado (via a fábrica em ``registry``). Consolida os holdings de todos os
arquivos internos. Usa o primeiro header estruturado encontrado.
"""
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from src.parsers.base_parser import BaseParser, ResultadoParse


class ZipParser(BaseParser):
    formato = "zip"

    def parse(self, caminho: Path) -> ResultadoParse:
        # import tardio para evitar ciclo (registry importa este módulo)
        from src.parsers.registry import parser_para_extensao

        resultado = ResultadoParse(formato="zip")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                with zipfile.ZipFile(caminho) as z:
                    z.extractall(tmp_dir)

                for interno in sorted(tmp_dir.rglob("*")):
                    if interno.is_dir():
                        continue
                    parser = parser_para_extensao(interno.suffix.lower())
                    if parser is None:
                        continue
                    parcial = parser.parse(interno)
                    # herda metadados do primeiro documento estruturado
                    if resultado.fundo_cnpj is None and parcial.fundo_cnpj:
                        resultado.fundo_cnpj = parcial.fundo_cnpj
                        resultado.competencia = parcial.competencia
                        resultado.vl_pl = parcial.vl_pl
                        resultado.cod_doc = parcial.cod_doc
                        resultado.versao = parcial.versao
                        resultado.dt_gerac_arq = parcial.dt_gerac_arq
                    resultado.holdings.extend(parcial.holdings)
        except zipfile.BadZipFile:
            resultado.aviso = "Arquivo ZIP inválido/corrompido."
            return resultado

        if not resultado.holdings:
            resultado.aviso = "Nenhum CNPJ localizado nos arquivos do ZIP."
        return resultado

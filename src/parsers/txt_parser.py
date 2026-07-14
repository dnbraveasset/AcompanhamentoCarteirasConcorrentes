"""Parser de TXT: leitura direta e extração de CNPJs por regex."""
from __future__ import annotations

from pathlib import Path

from src.parsers.base_parser import BaseParser, ResultadoParse


class TxtParser(BaseParser):
    formato = "txt"

    def parse(self, caminho: Path) -> ResultadoParse:
        resultado = ResultadoParse(formato="txt")
        conteudo = None
        for enc in ("utf-8", "windows-1252", "latin-1"):
            try:
                conteudo = Path(caminho).read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        if conteudo is None:
            resultado.aviso = "Não foi possível decodificar o TXT."
            return resultado

        resultado.holdings = self.fallback_cnpjs(conteudo, tipo_ativo="TXT")
        if not resultado.holdings:
            resultado.aviso = "Nenhum CNPJ localizado no TXT."
        return resultado

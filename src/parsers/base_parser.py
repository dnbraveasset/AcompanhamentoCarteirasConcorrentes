"""
Contrato comum a todos os parsers.

Todo parser recebe um caminho de arquivo e devolve um ``ResultadoParse`` com:
- header: metadados do documento (fundo analisado, competência, PL...);
- holdings: lista de posições/ativos da carteira.

Quando o parser não consegue estruturar os dados, deve ao menos devolver os
CNPJs achados por regex, de forma que NADA quebre a execução.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Holding:
    cnpj_investido: Optional[str] = None
    nome_ativo: Optional[str] = None
    tipo_ativo: Optional[str] = None
    valor_financeiro: Optional[float] = None
    percentual: Optional[float] = None
    quantidade: Optional[float] = None
    empresa_ligada: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultadoParse:
    fundo_cnpj: Optional[str] = None
    competencia: Optional[str] = None          # 'aaaa-mm'
    cod_doc: Optional[str] = None
    versao: Optional[str] = None
    dt_gerac_arq: Optional[str] = None
    vl_pl: Optional[float] = None
    holdings: List[Holding] = field(default_factory=list)
    formato: Optional[str] = None
    aviso: Optional[str] = None                 # mensagens não-fatais


class BaseParser:
    """Classe base. Subclasses implementam ``parse``."""

    formato: str = "desconhecido"

    def parse(self, caminho: Path) -> ResultadoParse:  # pragma: no cover - interface
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Fallback comum: extrair CNPJs por regex a partir de texto bruto.
    # ------------------------------------------------------------------
    @staticmethod
    def fallback_cnpjs(texto: str, tipo_ativo: str = "TEXTO") -> List[Holding]:
        from src.utils.cnpj import extrair_cnpjs
        return [
            Holding(cnpj_investido=c, tipo_ativo=tipo_ativo)
            for c in extrair_cnpjs(texto, validar=True)
        ]

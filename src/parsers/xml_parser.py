"""
Parser do XML de Composição da Carteira (CDA) — layout ``urn:cda`` da CVM.

Estrutura real observada (arquivo de exemplo do Fundos.NET):

    DOC_ARQ
      CAB_INFORM            -> COD_DOC, VERSAO, DT_COMPT (MM/AAAA), DT_GERAC_ARQ
      LISTA_INFORM
        INFORM
          CNPJ_FDO          -> CNPJ do fundo ANALISADO
          VL_PL             -> patrimônio líquido (decimal BR)
          LISTA_ATIV
            COTAS           -> cotas de fundos investidos (chave p/ FIC FIDC)
              CNPJ_FDO      -> CNPJ do fundo INVESTIDO
              APLIC
                EMPR_LIGADA
                POS_FIM
                  QTDE_POS_FIM   -> quantidade
                  MERC_POS_FIM   -> valor de mercado (valor financeiro)
            DEMAIS_N_CODIF  -> outros ativos (com DESC, EMIS/NM_EMIS)
            TITPUBLICO / TITPRIVADO / SWAP / ... (mesma lógica de varredura)

Observações que viram regra:
- O NOME do fundo investido NÃO vem no bloco COTAS (só o CNPJ). Fica nulo aqui
  e é enriquecido depois via cadastro CVM.
- O PERCENTUAL não existe no arquivo: é calculado (MERC_POS_FIM / VL_PL * 100).
- Números usam vírgula decimal; encoding costuma ser windows-1252.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET

from src.parsers.base_parser import BaseParser, Holding, ResultadoParse
from src.utils.cnpj import normalizar_cnpj
from src.utils.file_utils import normalizar_competencia, parse_decimal_br


# Blocos de LISTA_ATIV que representam posições da carteira.
BLOCOS_ATIVO = {
    "COTAS", "TITPUBLICO", "TITPRIVADO", "SWAP", "DERIV", "OPCOES",
    "DEPOSITO", "DEMAIS_N_CODIF", "INVEST_EXTERIOR", "DISPONIBILIDADES",
    "VLR_MERCADO", "CANCELADO",
}


def _sem_namespace(elem: ET.Element) -> None:
    """Remove o namespace das tags recursivamente (simplifica as buscas)."""
    for e in elem.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]


def _txt(elem: Optional[ET.Element], caminho: str) -> Optional[str]:
    if elem is None:
        return None
    achado = elem.find(caminho)
    if achado is None or achado.text is None:
        return None
    valor = achado.text.strip()
    return valor or None


def _primeiro_texto(elem: ET.Element, tags: List[str]) -> Optional[str]:
    """Retorna o primeiro texto não-vazio encontrado em qualquer profundidade."""
    for tag in tags:
        achado = elem.find(f".//{tag}")
        if achado is not None and achado.text and achado.text.strip():
            return achado.text.strip()
    return None


class XmlParser(BaseParser):
    formato = "xml"

    def parse(self, caminho: Path) -> ResultadoParse:
        dados = Path(caminho).read_bytes()

        # Detecta encoding declarado; ET lida com o declarado se receber bytes.
        try:
            raiz = ET.fromstring(dados)
        except ET.ParseError:
            # tenta decodificar manualmente como windows-1252 e re-parsear
            texto = dados.decode("windows-1252", errors="replace")
            texto = re.sub(r"encoding=['\"][^'\"]+['\"]", "", texto, count=1)
            raiz = ET.fromstring(texto)

        _sem_namespace(raiz)

        resultado = ResultadoParse(formato="xml")

        # -------- Cabeçalho
        cab = raiz.find(".//CAB_INFORM")
        if cab is not None:
            resultado.cod_doc = _txt(cab, "COD_DOC")
            resultado.versao = _txt(cab, "VERSAO")
            resultado.competencia = normalizar_competencia(_txt(cab, "DT_COMPT"))
            resultado.dt_gerac_arq = _txt(cab, "DT_GERAC_ARQ")

        # -------- INFORM (pode haver mais de um; pegamos o primeiro fundo)
        inform = raiz.find(".//INFORM")
        if inform is None:
            # sem estrutura conhecida: fallback por regex no texto todo
            resultado.aviso = "XML sem bloco INFORM; usando fallback por regex."
            resultado.holdings = self.fallback_cnpjs(
                dados.decode("windows-1252", errors="replace"), tipo_ativo="XML"
            )
            return resultado

        resultado.fundo_cnpj = normalizar_cnpj(_txt(inform, "CNPJ_FDO"), validar=False)
        resultado.vl_pl = parse_decimal_br(_txt(inform, "VL_PL"))

        lista_ativ = inform.find("LISTA_ATIV")
        if lista_ativ is None:
            resultado.aviso = "INFORM sem LISTA_ATIV."
            return resultado

        holdings: List[Holding] = []
        for bloco in list(lista_ativ):
            tipo = bloco.tag
            if tipo not in BLOCOS_ATIVO:
                # ainda tentamos, mas marcamos o tipo bruto
                pass
            holding = self._extrair_holding(bloco, tipo, resultado.vl_pl)
            if holding is not None:
                holdings.append(holding)

        resultado.holdings = holdings
        return resultado

    # ------------------------------------------------------------------
    def _extrair_holding(
        self, bloco: ET.Element, tipo: str, vl_pl: Optional[float]
    ) -> Optional[Holding]:
        # CNPJ investido: preferir CNPJ_FDO; senão emissor PJ.
        cnpj_raw = _primeiro_texto(bloco, ["CNPJ_FDO"])
        if not cnpj_raw:
            tp_emis = _primeiro_texto(bloco, ["TP_PF_PJ_EMIS"])
            nr_emis = _primeiro_texto(bloco, ["NR_PF_PJ_EMIS"])
            # J = pessoa jurídica -> tratamos como CNPJ
            if nr_emis and (tp_emis in (None, "", "J")):
                cnpj_raw = nr_emis
        cnpj = normalizar_cnpj(cnpj_raw, validar=False) if cnpj_raw else None

        nome = _primeiro_texto(bloco, ["NM_EMIS", "DESC", "NM_ATIVO"])
        qtde = parse_decimal_br(_primeiro_texto(bloco, ["QTDE_POS_FIM"]))
        valor = parse_decimal_br(_primeiro_texto(bloco, ["MERC_POS_FIM", "VL_MERC_POS_FIM"]))
        empr = _primeiro_texto(bloco, ["EMPR_LIGADA"])

        percentual = None
        if valor is not None and vl_pl:
            percentual = round(valor / vl_pl * 100, 4)

        # Se não há CNPJ, nome nem valor, ignora (bloco vazio/irrelevante).
        if not cnpj and not nome and valor is None:
            return None

        extra = {}
        cod_tp = _primeiro_texto(bloco, ["COD_TP_ATIV", "COD_TP_APLIC"])
        if cod_tp:
            extra["cod_tp"] = cod_tp

        return Holding(
            cnpj_investido=cnpj,
            nome_ativo=nome,
            tipo_ativo=tipo,
            valor_financeiro=valor,
            percentual=percentual,
            quantidade=qtde,
            empresa_ligada=empr,
            extra=extra,
        )

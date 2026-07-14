"""
Serviço da Base de Fundos (planilha Excel mensal).

Processa o arquivo Excel com duas abas:
  - COMPARACAO_FUNDOS: resumo pronto (PL, subordinação, rentabilidade, etc.);
  - flokiCVM_tbCVM_FIDCS: base bruta (de onde vêm % caixa, condomínio, cedentes).

Para cada fundo, guarda no banco (tabela base_fundos) apenas o snapshot da
DATA MAIS RECENTE — não o histórico inteiro, para manter o banco enxuto.
"""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd

from src.database import conectar, sessao
from src.utils.cnpj import normalizar_cnpj, formatar_cnpj

ABA_RESUMO = "COMPARACAO_FUNDOS"
ABA_BRUTA = "flokiCVM_tbCVM_FIDCS"


def _to_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _garantir_tabela(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS base_fundos (
            cnpj                TEXT PRIMARY KEY,
            nome                TEXT,
            data_base           TEXT,
            pl                  REAL,
            pct_caixa           REAL,
            condominio          TEXT,
            administrador       TEXT,
            subord_sen          REAL,
            subord_mez          REAL,
            rentsub_12          REAL,
            pct_meses_negativos REAL,
            cedentes_sub_json   TEXT,
            rating_final        TEXT,
            atualizado_em       TEXT DEFAULT (datetime('now'))
        )
    """)


def garantir_tabela_base_fundos():
    with sessao() as con:
        _garantir_tabela(con)


def _cedentes_da_linha(linha: pd.Series) -> list:
    """Extrai a lista de cedentes (CNPJ + participação) de uma linha da base
    bruta, colunas CPF_CNPJ_CEDENTE_1..9 e PARTICPACAO_CEDENTE_1..9."""
    ced = []
    for i in range(1, 14):  # a base tem até 13, mas normalmente 9 preenchidos
        col_cnpj = f"CPF_CNPJ_CEDENTE_{i}"
        # o arquivo tem grafias diferentes: PARTICPACAO e PARTICIPACAO
        col_part = None
        for cand in (f"PARTICPACAO_CEDENTE_{i}", f"PARTICIPACAO_CEDENTE_{i}"):
            if cand in linha.index:
                col_part = cand
                break
        if col_cnpj not in linha.index:
            continue
        val = linha.get(col_cnpj)
        if val is None or str(val).strip() in ("", "0", "0.0", "nan"):
            continue
        # o Excel às vezes traz o CNPJ como número (termina em .0)
        cnpj_ced = str(val).strip()
        if cnpj_ced.endswith(".0"):
            cnpj_ced = cnpj_ced[:-2]
        cnpj_fmt = formatar_cnpj(cnpj_ced) or cnpj_ced
        part = _to_float(linha.get(col_part)) if col_part else None
        ced.append({"cnpj": cnpj_fmt, "participacao": part})
    # ordena por participação desc e pega os 10 maiores
    ced.sort(key=lambda x: (x["participacao"] or 0), reverse=True)
    return ced[:10]


def importar_base_excel(conteudo: bytes) -> dict:
    """Lê o Excel (bytes), pega a data mais recente da aba de resumo, cruza com
    a base bruta por CNPJ+data, e grava o snapshot em base_fundos (substitui
    tudo que havia — é sempre a foto mais recente)."""
    import io

    xls = pd.ExcelFile(io.BytesIO(conteudo))
    if ABA_RESUMO not in xls.sheet_names:
        return {"status": "erro",
                "mensagem": f"Aba '{ABA_RESUMO}' não encontrada no arquivo."}

    resumo = pd.read_excel(xls, sheet_name=ABA_RESUMO)
    resumo.columns = [str(c).strip() for c in resumo.columns]
    if "DATA" not in resumo.columns or "CNPJ_FUNDO" not in resumo.columns:
        return {"status": "erro",
                "mensagem": "Colunas DATA/CNPJ_FUNDO não encontradas no resumo."}

    resumo["DATA"] = pd.to_datetime(resumo["DATA"], errors="coerce")
    data_recente = resumo["DATA"].max()
    if pd.isna(data_recente):
        return {"status": "erro", "mensagem": "Nenhuma data válida no resumo."}

    resumo_rec = resumo[resumo["DATA"] == data_recente].copy()

    # base bruta: filtra a mesma data, indexa por CNPJ para cruzar caixa/condom/cedentes
    bruta_por_cnpj = {}
    if ABA_BRUTA in xls.sheet_names:
        bruta = pd.read_excel(xls, sheet_name=ABA_BRUTA)
        bruta.columns = [str(c).strip() for c in bruta.columns]
        if "DATA" in bruta.columns:
            bruta["DATA"] = pd.to_datetime(bruta["DATA"], errors="coerce")
            bruta_rec = bruta[bruta["DATA"] == data_recente]
        else:
            bruta_rec = bruta
        for _, lin in bruta_rec.iterrows():
            cnpj_norm = normalizar_cnpj(str(lin.get("CNPJ_FUNDO", "")), validar=False)
            if cnpj_norm:
                bruta_por_cnpj[cnpj_norm] = lin

    registros = []
    for _, r in resumo_rec.iterrows():
        cnpj_norm = normalizar_cnpj(str(r.get("CNPJ_FUNDO", "")), validar=False)
        if not cnpj_norm:
            continue
        pl = _to_float(r.get("PL"))
        lin_bruta = bruta_por_cnpj.get(cnpj_norm)

        pct_caixa = None
        condominio = None
        administrador = None
        cedentes = []
        if lin_bruta is not None:
            caixa = _to_float(lin_bruta.get("CAIXA"))
            if caixa is not None and pl:
                pct_caixa = caixa / pl if pl else None
            cond = lin_bruta.get("CONDOM")
            condominio = str(cond) if cond not in (None, 0, "0", "0.0") else None
            adm = lin_bruta.get("ADMIN")
            administrador = str(adm) if adm not in (None, 0, "0", "0.0") else None
            cedentes = _cedentes_da_linha(lin_bruta)

        registros.append({
            "cnpj": cnpj_norm,
            "nome": r.get("NOME"),
            "data_base": data_recente.strftime("%Y-%m-%d"),
            "pl": pl,
            "pct_caixa": pct_caixa,
            "condominio": condominio,
            "administrador": administrador,
            "subord_sen": _to_float(r.get("SUBORD_SEN")),
            "subord_mez": _to_float(r.get("SUBORD_MEZ")),
            "rentsub_12": _to_float(r.get("RENTSUB_12")),
            "pct_meses_negativos": _to_float(r.get("%_MESES_NEGATIVOS")),
            "cedentes_sub_json": json.dumps(cedentes, ensure_ascii=False),
            "rating_final": (str(r.get("RATING_FINAL"))
                             if r.get("RATING_FINAL") not in (None, "") else None),
        })

    with sessao() as con:
        _garantir_tabela(con)
        con.execute("DELETE FROM base_fundos")  # sempre substitui pela foto nova
        con.executemany("""
            INSERT INTO base_fundos
                (cnpj, nome, data_base, pl, pct_caixa, condominio, administrador,
                 subord_sen, subord_mez, rentsub_12, pct_meses_negativos,
                 cedentes_sub_json, rating_final, atualizado_em)
            VALUES
                (:cnpj, :nome, :data_base, :pl, :pct_caixa, :condominio, :administrador,
                 :subord_sen, :subord_mez, :rentsub_12, :pct_meses_negativos,
                 :cedentes_sub_json, :rating_final, datetime('now'))
        """, registros)

    return {"status": "ok", "fundos": len(registros),
            "data_base": data_recente.strftime("%Y-%m-%d")}


def base_disponivel() -> bool:
    """True se há dados de base importados."""
    try:
        with conectar() as con:
            n = con.execute("SELECT COUNT(*) FROM base_fundos").fetchone()[0]
            return n > 0
    except Exception:
        return False


def data_base_atual() -> Optional[str]:
    try:
        with conectar() as con:
            r = con.execute("SELECT MAX(data_base) FROM base_fundos").fetchone()
            return r[0] if r else None
    except Exception:
        return None


def detalhe_fundo(cnpj: str) -> Optional[dict]:
    """Retorna o dict de resumo de um fundo pela base, ou None."""
    cnpj = normalizar_cnpj(cnpj, validar=False)
    if not cnpj:
        return None
    try:
        with conectar() as con:
            row = con.execute("SELECT * FROM base_fundos WHERE cnpj = ?",
                              (cnpj,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    d = dict(row)
    try:
        d["cedentes_sub"] = json.loads(d.get("cedentes_sub_json") or "[]")
    except Exception:
        d["cedentes_sub"] = []
    return d


def listar_base_fundos() -> pd.DataFrame:
    """Todos os fundos da base, para a página Resumo Fundos."""
    try:
        with conectar() as con:
            return pd.read_sql_query(
                "SELECT * FROM base_fundos ORDER BY pl DESC", con)
    except Exception:
        return pd.DataFrame()

"""
Integração com dados públicos da CVM — enriquecimento de nomes (Fase 2).

Objetivo: os CDAs trazem apenas o CNPJ dos fundos investidos (cotas), sem o
nome. Este módulo cruza cada CNPJ com o cadastro público da CVM e preenche o
nome (e, quando disponível, administrador/gestor/classe/tipo).

Usa DUAS bases, porque FIDC é fundo estruturado e nem sempre aparece na base
antiga:
  1. cad_fi.csv                  -> conjunto completo (colunas DENOM_SOCIAL, ...)
  2. registro_fundo.csv (no zip  -> base da Resolução CVM 175, cobre FIDC/FIP/FII
     registro_fundo_classe.zip)     (colunas Denominacao_Social, Tipo_Fundo, ...)

A base 2 tem prioridade para o NOME (mais atual e com estruturados). Se a rede
não estiver disponível, o MVP continua funcionando com os dados dos próprios
CDAs — este passo é opcional e idempotente (pode rodar quantas vezes quiser).
"""
from __future__ import annotations

import io
import zipfile
from typing import Optional

from config import settings
from src.database import sessao, registrar_log
from src.utils.cnpj import normalizar_cnpj
from src.utils.logger import obter_logger

log = obter_logger()

_ENCODINGS = ("latin-1", "utf-8", "cp1252")


def _ler_csv(conteudo: bytes):
    import pandas as pd
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(io.BytesIO(conteudo), sep=";", dtype=str,
                               encoding=enc, on_bad_lines="skip")
        except Exception:
            continue
    return None


def _baixar_cad_fi():
    """cad_fi.csv (conjunto completo). Retorna DataFrame ou None."""
    try:
        import requests
    except ImportError:
        log.warning("requests necessário para integração CVM.")
        return None
    try:
        resp = requests.get(settings.CVM_CADASTRO_URL, timeout=120)
        resp.raise_for_status()
    except Exception as e:
        log.warning("Falha ao baixar cad_fi.csv: %s", e)
        return None
    return _ler_csv(resp.content)


def _baixar_registro_fundo():
    """registro_fundo.csv de dentro do registro_fundo_classe.zip (RCVM175)."""
    try:
        import requests
    except ImportError:
        return None
    try:
        resp = requests.get(settings.CVM_REGISTRO_FUNDO_URL, timeout=120)
        resp.raise_for_status()
    except Exception as e:
        log.warning("Falha ao baixar registro_fundo_classe.zip: %s", e)
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
    except Exception as e:
        log.warning("Zip da CVM inválido: %s", e)
        return None
    # procura o membro registro_fundo.csv (nome pode variar de caixa)
    alvo = next(
        (n for n in zf.namelist()
         if "registro_fundo" in n.lower() and n.lower().endswith(".csv")),
        None,
    )
    if alvo is None:
        log.warning("registro_fundo.csv não encontrado no zip da CVM.")
        return None
    with zf.open(alvo) as fh:
        return _ler_csv(fh.read())


def _achar_col(df, *chaves):
    """Primeira coluna cujo nome (upper) contém TODAS as chaves informadas."""
    for c in df.columns:
        cu = c.upper()
        if all(k in cu for k in chaves):
            return c
    return None


def _mapa_cnpj(df) -> dict:
    """Constrói {cnpj_limpo: {nome, admin, gestor, classe, tipo, situacao}}."""
    if df is None or df.empty:
        return {}
    df.columns = [c.strip() for c in df.columns]

    # CNPJ do fundo: prioriza coluna com CNPJ + FUNDO; senão qualquer CNPJ.
    col_cnpj = _achar_col(df, "CNPJ", "FUNDO") or _achar_col(df, "CNPJ")
    if col_cnpj is None:
        return {}
    # nome social: casa DENOM_SOCIAL e DENOMINACAO_SOCIAL
    col_nome = _achar_col(df, "DENOM")
    col_admin = _achar_col(df, "ADMIN")
    col_gestor = _achar_col(df, "GESTOR")
    col_classe = _achar_col(df, "CLASSE") or _achar_col(df, "TP", "FUNDO") \
        or _achar_col(df, "TIPO", "FUNDO")
    col_sit = _achar_col(df, "SIT")

    def _val(row, col):
        if not col:
            return None
        v = row.get(col)
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s.lower() != "nan" else None

    mapa: dict = {}
    for _, row in df.iterrows():
        cnpj = normalizar_cnpj(row.get(col_cnpj), validar=False)
        if not cnpj:
            continue
        mapa[cnpj] = {
            "nome": _val(row, col_nome),
            "admin": _val(row, col_admin),
            "gestor": _val(row, col_gestor),
            "classe": _val(row, col_classe),
            "situacao": _val(row, col_sit),
        }
    return mapa


def enriquecer_cvm() -> dict:
    # base nova (FIDC/estruturados) tem prioridade para o nome
    df_reg = _baixar_registro_fundo()
    df_cad = _baixar_cad_fi()

    mapa_reg = _mapa_cnpj(df_reg)
    mapa_cad = _mapa_cnpj(df_cad)

    if not mapa_reg and not mapa_cad:
        log.warning("Nenhuma base da CVM pôde ser carregada.")
        return {"status": "indisponivel", "atualizados": 0,
                "fontes": {"registro_fundo": 0, "cad_fi": 0}}

    def _lookup(cnpj, campo):
        # registro_fundo primeiro, cad_fi como fallback
        for mapa in (mapa_reg, mapa_cad):
            info = mapa.get(cnpj)
            if info and info.get(campo):
                return info[campo]
        return None

    atualizados_fundos = 0
    atualizados_ativos = 0
    with sessao() as con:
        # 1) fundos monitorados (o próprio concorrente)
        for row in con.execute("SELECT cnpj FROM fundos").fetchall():
            cnpj = row["cnpj"]
            nome = _lookup(cnpj, "nome")
            admin = _lookup(cnpj, "admin")
            gestor = _lookup(cnpj, "gestor")
            classe = _lookup(cnpj, "classe")
            situacao = _lookup(cnpj, "situacao")
            if any([nome, admin, gestor, classe]):
                con.execute(
                    """UPDATE fundos SET
                         nome=COALESCE(nome, ?),
                         administrador=COALESCE(administrador, ?),
                         gestor=COALESCE(gestor, ?),
                         classe=COALESCE(classe, ?),
                         observacoes=COALESCE(observacoes, ?),
                         atualizado_em=datetime('now')
                       WHERE cnpj=?""",
                    (nome, admin, gestor, classe,
                     f"situacao CVM: {situacao}" if situacao else None, cnpj),
                )
                atualizados_fundos += 1

        # 2) ativos investidos (as cotas/FIDC que faltavam nome)
        for row in con.execute(
            "SELECT cnpj FROM ativos_investidos WHERE nome IS NULL OR nome=''"
        ).fetchall():
            cnpj = row["cnpj"]
            nome = _lookup(cnpj, "nome")
            if nome:
                con.execute(
                    "UPDATE ativos_investidos SET nome=?, fonte_nome='cvm', "
                    "atualizado_em=datetime('now') WHERE cnpj=?",
                    (nome, cnpj),
                )
                atualizados_ativos += 1

        registrar_log(
            con, "INFO", "enriquecer-cvm",
            f"fundos={atualizados_fundos} ativos={atualizados_ativos} "
            f"(registro_fundo={len(mapa_reg)} cad_fi={len(mapa_cad)})",
        )

    total = atualizados_fundos + atualizados_ativos
    log.info(
        "Enriquecimento CVM: %d atualizados (fundos=%d, ativos=%d). "
        "Bases: registro_fundo=%d, cad_fi=%d.",
        total, atualizados_fundos, atualizados_ativos,
        len(mapa_reg), len(mapa_cad),
    )
    return {
        "status": "ok",
        "atualizados": total,
        "fundos": atualizados_fundos,
        "ativos": atualizados_ativos,
        "fontes": {"registro_fundo": len(mapa_reg), "cad_fi": len(mapa_cad)},
    }

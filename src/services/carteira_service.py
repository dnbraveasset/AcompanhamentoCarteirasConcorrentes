"""
Serviço de consulta das carteiras — camada entre o banco e o dashboard.

Todas as funções retornam DataFrames pandas prontos para exibir/exportar.
O CNPJ investido é a chave usada em comparações e consolidações.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd

from config import settings
from src.database import conectar


# ---------------------------------------------------------------------------
# Consultas básicas
# ---------------------------------------------------------------------------
def listar_gestoras() -> pd.DataFrame:
    with conectar() as con:
        return pd.read_sql_query(
            "SELECT id, nome, cnpj FROM gestoras ORDER BY nome", con
        )


def listar_fundos(gestora_nome: Optional[str] = None) -> pd.DataFrame:
    sql = """
        SELECT f.id, f.cnpj, f.nome, f.administrador, f.gestor, f.classe,
               f.ativo, g.nome AS gestora
        FROM fundos f
        LEFT JOIN gestoras g ON g.id = f.gestora_id
    """
    params: list = []
    if gestora_nome:
        sql += " WHERE g.nome = ?"
        params.append(gestora_nome)
    sql += " ORDER BY f.nome"
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=params)


def competencias_disponiveis(fundo_cnpj: Optional[str] = None) -> List[str]:
    sql = "SELECT DISTINCT competencia FROM documentos_cda WHERE competencia IS NOT NULL"
    params: list = []
    if fundo_cnpj:
        sql += " AND fundo_cnpj = ?"
        params.append(fundo_cnpj)
    sql += " ORDER BY competencia DESC"
    with conectar() as con:
        rows = con.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def carteira(fundo_cnpj: str, competencia: str) -> pd.DataFrame:
    """Carteira de um fundo em um mês, enriquecida com nome do ativo (se houver)
    e com as anotações manuais do usuário (classe e observação por CNPJ)."""
    sql = """
        SELECT c.cnpj_investido,
               COALESCE(c.nome_ativo, a.nome) AS nome_ativo,
               c.tipo_ativo,
               c.valor_financeiro,
               c.percentual,
               c.quantidade,
               c.empresa_ligada,
               COALESCE(an.classe_manual, '') AS classe_manual,
               COALESCE(an.observacao, '')    AS observacao
        FROM carteiras_cda c
        LEFT JOIN ativos_investidos a  ON a.cnpj  = c.cnpj_investido
        LEFT JOIN anotacoes_ativos an  ON an.cnpj = c.cnpj_investido
        WHERE c.fundo_cnpj = ? AND c.competencia = ?
        ORDER BY c.valor_financeiro DESC
    """
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=[fundo_cnpj, competencia])


# ---------------------------------------------------------------------------
# Anotações manuais por CNPJ investido (classe e observação)
# ---------------------------------------------------------------------------
def obter_anotacoes(cnpjs: Optional[List[str]] = None) -> pd.DataFrame:
    """Retorna as anotações salvas. Se ``cnpjs`` for dado, filtra por eles."""
    sql = "SELECT cnpj, classe_manual, observacao FROM anotacoes_ativos"
    params: list = []
    if cnpjs:
        placeholders = ",".join("?" * len(cnpjs))
        sql += f" WHERE cnpj IN ({placeholders})"
        params = list(cnpjs)
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=params)


def salvar_anotacao(cnpj: str, classe_manual: Optional[str],
                    observacao: Optional[str]) -> None:
    """Grava/atualiza a anotação de um CNPJ (upsert). Vale para todos os
    fundos/meses. Se ambos os campos ficarem vazios, remove a linha."""
    if not cnpj:
        return
    classe_manual = (classe_manual or "").strip() or None
    observacao = (observacao or "").strip() or None
    with conectar() as con:
        if classe_manual is None and observacao is None:
            con.execute("DELETE FROM anotacoes_ativos WHERE cnpj = ?", (cnpj,))
        else:
            con.execute(
                """INSERT INTO anotacoes_ativos (cnpj, classe_manual, observacao, atualizado_em)
                   VALUES (?,?,?, datetime('now'))
                   ON CONFLICT(cnpj) DO UPDATE SET
                       classe_manual = excluded.classe_manual,
                       observacao    = excluded.observacao,
                       atualizado_em = datetime('now')""",
                (cnpj, classe_manual, observacao),
            )
        con.commit()


# ---------------------------------------------------------------------------
# Visão da gestora
# ---------------------------------------------------------------------------
def resumo_gestora(gestora_nome: str) -> dict:
    with conectar() as con:
        fundos = con.execute(
            """SELECT f.cnpj FROM fundos f
               LEFT JOIN gestoras g ON g.id=f.gestora_id WHERE g.nome=?""",
            (gestora_nome,),
        ).fetchall()
        cnpjs = [f[0] for f in fundos]
        n_fundos = len(cnpjs)

        n_com_cda = 0
        meses = set()
        pl_total = 0.0
        if cnpjs:
            placeholders = ",".join("?" * len(cnpjs))
            docs = con.execute(
                f"""SELECT fundo_cnpj, competencia, vl_pl FROM documentos_cda
                    WHERE fundo_cnpj IN ({placeholders})""",
                cnpjs,
            ).fetchall()
            n_com_cda = len({d["fundo_cnpj"] for d in docs})
            meses = {d["competencia"] for d in docs if d["competencia"]}
            # PL total = último PL de cada fundo
            ult = con.execute(
                f"""SELECT fundo_cnpj, vl_pl FROM documentos_cda d
                    WHERE fundo_cnpj IN ({placeholders})
                      AND competencia = (SELECT MAX(competencia) FROM documentos_cda
                                         WHERE fundo_cnpj = d.fundo_cnpj)""",
                cnpjs,
            ).fetchall()
            pl_total = sum(r["vl_pl"] or 0 for r in ult)

        # CNPJs distintos investidos pelos fundos desta gestora (todos os meses)
        n_cnpjs_investidos = 0
        if cnpjs:
            placeholders = ",".join("?" * len(cnpjs))
            r = con.execute(
                f"""SELECT COUNT(DISTINCT cnpj_investido) FROM carteiras_cda
                    WHERE fundo_cnpj IN ({placeholders})
                      AND cnpj_investido IS NOT NULL""",
                cnpjs,
            ).fetchone()
            n_cnpjs_investidos = r[0] or 0

    return {
        "n_fundos": n_fundos,
        "n_com_cda": n_com_cda,
        "meses": sorted(meses, reverse=True),
        "pl_total": pl_total,
        "n_cnpjs_investidos": n_cnpjs_investidos,
    }


def fundos_com_cda(gestora_nome: Optional[str] = None) -> pd.DataFrame:
    """Apenas os fundos que já têm pelo menos um CDA importado.

    É a lista que interessa na análise de concorrentes: os fundos para os
    quais você efetivamente subiu a Composição da Carteira.
    """
    sql = """
        SELECT f.cnpj,
               f.nome,
               g.nome AS gestora,
               COUNT(DISTINCT d.competencia) AS meses,
               MAX(d.competencia)            AS ultima_competencia
        FROM fundos f
        JOIN documentos_cda d ON d.fundo_cnpj = f.cnpj
        LEFT JOIN gestoras g   ON g.id = f.gestora_id
    """
    params: list = []
    if gestora_nome:
        sql += " WHERE g.nome = ?"
        params.append(gestora_nome)
    sql += " GROUP BY f.cnpj, f.nome, g.nome ORDER BY f.nome"
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=params)


def resumo_fundo(fundo_cnpj: str, competencia: Optional[str] = None) -> dict:
    """Big numbers de um fundo concorrente numa competência.

    Se ``competencia`` for None, usa o mês mais recente disponível.
    Retorna PL, nº de posições, nº de CNPJs investidos e a maior posição
    (nome/cnpj/percentual) — a concentração de topo do concorrente.
    """
    with conectar() as con:
        if competencia is None:
            row = con.execute(
                "SELECT MAX(competencia) FROM documentos_cda WHERE fundo_cnpj = ?",
                (fundo_cnpj,),
            ).fetchone()
            competencia = row[0] if row else None

        vazio = {
            "competencia": competencia, "pl": None, "n_posicoes": 0,
            "n_cnpjs": 0, "top_nome": None, "top_cnpj": None, "top_pct": None,
        }
        if competencia is None:
            return vazio

        doc = con.execute(
            "SELECT vl_pl FROM documentos_cda WHERE fundo_cnpj = ? AND competencia = ?",
            (fundo_cnpj, competencia),
        ).fetchone()
        pl = doc["vl_pl"] if doc else None

    df = carteira(fundo_cnpj, competencia)
    if df.empty:
        vazio["pl"] = pl
        return vazio

    com_cnpj = df.dropna(subset=["cnpj_investido"])
    top = df.sort_values("valor_financeiro", ascending=False).iloc[0]
    top_nome = top.get("nome_ativo")
    top_cnpj = top.get("cnpj_investido")
    return {
        "competencia": competencia,
        "pl": pl,
        "n_posicoes": int(len(df)),
        "n_cnpjs": int(com_cnpj["cnpj_investido"].nunique()),
        "top_nome": top_nome if pd.notna(top_nome) else None,
        "top_cnpj": top_cnpj if pd.notna(top_cnpj) else None,
        "top_pct": float(top["percentual"]) if pd.notna(top.get("percentual")) else None,
    }


def evolucao_pl(gestora_nome: str) -> pd.DataFrame:
    sql = """
        SELECT d.competencia, SUM(d.vl_pl) AS pl_total
        FROM documentos_cda d
        JOIN fundos f ON f.cnpj = d.fundo_cnpj
        JOIN gestoras g ON g.id = f.gestora_id
        WHERE g.nome = ? AND d.competencia IS NOT NULL
        GROUP BY d.competencia
        ORDER BY d.competencia
    """
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=[gestora_nome])


# ---------------------------------------------------------------------------
# Comparação mês a mês (por CNPJ investido)
# ---------------------------------------------------------------------------
def comparar_meses(fundo_cnpj: str, comp_atual: str, comp_anterior: str) -> dict:
    atual = carteira(fundo_cnpj, comp_atual)
    anterior = carteira(fundo_cnpj, comp_anterior)

    def _dedup_por_cnpj(df):
        """Agrega possíveis linhas duplicadas do mesmo CNPJ investido no mesmo
        mês (pode acontecer em CDAs reais, principalmente linhas extraídas com
        confiança baixa/média). Sem isso, a comparação quebra ao montar o
        índice por CNPJ."""
        if df.empty or "cnpj_investido" not in df.columns:
            return df
        com_cnpj = df.dropna(subset=["cnpj_investido"])
        if com_cnpj["cnpj_investido"].duplicated().any():
            com_cnpj = com_cnpj.groupby("cnpj_investido", as_index=False).agg({
                "nome_ativo": "first",
                "tipo_ativo": "first",
                "valor_financeiro": "sum",
                "percentual": "sum",
                "quantidade": "sum",
                "empresa_ligada": "first",
            })
        return com_cnpj

    atual = _dedup_por_cnpj(atual)
    anterior = _dedup_por_cnpj(anterior)

    set_atual = set(atual["cnpj_investido"].dropna())
    set_ant = set(anterior["cnpj_investido"].dropna())

    entraram_cnpjs = sorted(set_atual - set_ant)
    sairam_cnpjs = sorted(set_ant - set_atual)
    permaneceram = sorted(set_atual & set_ant)

    # nome do ativo para exibição (entraram -> nome no mês atual;
    # sairam -> nome no mês anterior, já que não está mais na carteira atual)
    nome_atual = atual.set_index("cnpj_investido")["nome_ativo"] \
        if "nome_ativo" in atual.columns else pd.Series(dtype=object)
    nome_ant = anterior.set_index("cnpj_investido")["nome_ativo"] \
        if "nome_ativo" in anterior.columns else pd.Series(dtype=object)

    def _nome(cnpj, serie):
        try:
            v = serie.loc[cnpj]
            if isinstance(v, pd.Series):  # duplicado por linha de posição
                v = v.dropna().iloc[0] if not v.dropna().empty else None
            return v if pd.notna(v) else None
        except KeyError:
            return None

    entraram = [{"cnpj": c, "nome": _nome(c, nome_atual)} for c in entraram_cnpjs]
    sairam = [{"cnpj": c, "nome": _nome(c, nome_ant)} for c in sairam_cnpjs]

    # variação de exposição (percentual) para os que permaneceram
    variacoes = []
    a_idx = atual.set_index("cnpj_investido")
    p_idx = anterior.set_index("cnpj_investido")
    for cnpj in permaneceram:
        pct_a = a_idx.loc[cnpj, "percentual"] if cnpj in a_idx.index else None
        pct_p = p_idx.loc[cnpj, "percentual"] if cnpj in p_idx.index else None
        val_a = a_idx.loc[cnpj, "valor_financeiro"] if cnpj in a_idx.index else None
        val_p = p_idx.loc[cnpj, "valor_financeiro"] if cnpj in p_idx.index else None
        pct_a = float(pct_a) if pct_a is not None and pd.notna(pct_a) else None
        pct_p = float(pct_p) if pct_p is not None and pd.notna(pct_p) else None
        variacoes.append({
            "cnpj_investido": cnpj,
            "pct_anterior": pct_p,
            "pct_atual": pct_a,
            "delta_pct": (pct_a - pct_p) if (pct_a is not None and pct_p is not None) else None,
            "valor_anterior": float(val_p) if val_p is not None and pd.notna(val_p) else None,
            "valor_atual": float(val_a) if val_a is not None and pd.notna(val_a) else None,
        })

    return {
        "entraram": entraram,
        "sairam": sairam,
        "permaneceram": permaneceram,
        "variacoes": pd.DataFrame(variacoes),
        "atual": atual,
        "anterior": anterior,
    }


# ---------------------------------------------------------------------------
# Exposição consolidada
# ---------------------------------------------------------------------------
def exposicao_consolidada(gestora_nome: Optional[str] = None,
                          competencia: Optional[str] = None) -> pd.DataFrame:
    """Consolida por CNPJ investido: em quantos fundos e gestoras aparece,
    e valor total."""
    sql = """
        SELECT c.cnpj_investido,
               COALESCE(a.nome, MAX(c.nome_ativo)) AS nome_ativo,
               COUNT(DISTINCT c.fundo_cnpj) AS qtd_fundos,
               COUNT(DISTINCT g.nome) AS qtd_gestoras,
               GROUP_CONCAT(DISTINCT g.nome) AS gestoras,
               GROUP_CONCAT(DISTINCT c.fundo_cnpj) AS fundos,
               SUM(c.valor_financeiro) AS valor_total
        FROM carteiras_cda c
        LEFT JOIN ativos_investidos a ON a.cnpj = c.cnpj_investido
        JOIN fundos f ON f.cnpj = c.fundo_cnpj
        LEFT JOIN gestoras g ON g.id = f.gestora_id
        WHERE c.cnpj_investido IS NOT NULL
    """
    params: list = []
    if gestora_nome:
        sql += " AND g.nome = ?"
        params.append(gestora_nome)
    if competencia:
        sql += " AND c.competencia = ?"
        params.append(competencia)
    sql += " GROUP BY c.cnpj_investido ORDER BY qtd_gestoras DESC, qtd_fundos DESC, valor_total DESC"
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=params)


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------
def alertas(gestora_nome: Optional[str] = None,
            limite_concentracao: float = settings.LIMITE_CONCENTRACAO_PADRAO) -> dict:
    alertas_out = {
        "fundos_sem_cda": pd.DataFrame(),
        "importacoes_erro": pd.DataFrame(),
        "concentracao": pd.DataFrame(),
    }
    with conectar() as con:
        # fundos cadastrados sem nenhum CDA importado
        sql_sem = """
            SELECT f.cnpj, f.nome, g.nome AS gestora
            FROM fundos f
            LEFT JOIN gestoras g ON g.id = f.gestora_id
            WHERE f.cnpj NOT IN (SELECT DISTINCT fundo_cnpj FROM documentos_cda)
        """
        params = []
        if gestora_nome:
            sql_sem += " AND g.nome = ?"
            params.append(gestora_nome)
        alertas_out["fundos_sem_cda"] = pd.read_sql_query(sql_sem, con, params=params)

        # importações com erro/parcial
        alertas_out["importacoes_erro"] = pd.read_sql_query(
            "SELECT arquivo_nome, status, mensagem, iniciado_em FROM importacoes "
            "WHERE status IN ('ERRO','PARCIAL','DUPLICADO') ORDER BY iniciado_em DESC",
            con,
        )

        # concentração acima do limite (último mês por fundo)
        sql_conc = """
            SELECT c.fundo_cnpj, c.competencia, c.cnpj_investido,
                   COALESCE(c.nome_ativo, a.nome) AS nome_ativo, c.percentual
            FROM carteiras_cda c
            LEFT JOIN ativos_investidos a ON a.cnpj = c.cnpj_investido
            WHERE c.percentual IS NOT NULL AND c.percentual >= ?
            ORDER BY c.percentual DESC
        """
        alertas_out["concentracao"] = pd.read_sql_query(
            sql_conc, con, params=[limite_concentracao]
        )

    return alertas_out


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------
def exportar_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def exportar_excel(df: pd.DataFrame, nome_aba: str = "dados") -> bytes:
    import io
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=nome_aba[:31] or "dados")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Rankings (visão consolidada dos concorrentes monitorados)
# ---------------------------------------------------------------------------
def ranking_fundos_por_pl(gestora_nome: Optional[str] = None) -> pd.DataFrame:
    """Maiores fundos por PL (último mês de cada fundo)."""
    sql = """
        SELECT f.nome, f.cnpj, g.nome AS gestora,
               (SELECT d.vl_pl FROM documentos_cda d
                WHERE d.fundo_cnpj = f.cnpj
                ORDER BY d.competencia DESC LIMIT 1) AS pl,
               (SELECT MAX(d.competencia) FROM documentos_cda d
                WHERE d.fundo_cnpj = f.cnpj) AS ultima_competencia
        FROM fundos f
        LEFT JOIN gestoras g ON g.id = f.gestora_id
        WHERE f.cnpj IN (SELECT DISTINCT fundo_cnpj FROM documentos_cda)
    """
    params: list = []
    if gestora_nome:
        sql += " AND g.nome = ?"
        params.append(gestora_nome)
    sql += " ORDER BY (pl IS NULL), pl DESC"
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=params)


def ranking_gestoras_por_pl() -> pd.DataFrame:
    """Gestoras concorrentes por PL somado dos fundos monitorados (último mês)."""
    sql = """
        SELECT g.nome AS gestora,
               COUNT(DISTINCT f.cnpj) AS n_fundos,
               COALESCE(SUM(
                   (SELECT d.vl_pl FROM documentos_cda d
                    WHERE d.fundo_cnpj = f.cnpj
                    ORDER BY d.competencia DESC LIMIT 1)), 0) AS pl_total
        FROM gestoras g
        JOIN fundos f ON f.gestora_id = g.id
        WHERE f.cnpj IN (SELECT DISTINCT fundo_cnpj FROM documentos_cda)
        GROUP BY g.nome
        ORDER BY pl_total DESC
    """
    with conectar() as con:
        return pd.read_sql_query(sql, con)


def ranking_maiores_concentracoes(gestora_nome: Optional[str] = None) -> pd.DataFrame:
    """Maiores posições individuais (% do PL) entre os fundos monitorados,
    considerando a última competência de cada fundo."""
    sql = """
        SELECT f.nome AS fundo, c.fundo_cnpj,
               COALESCE(c.nome_ativo, a.nome) AS ativo,
               c.cnpj_investido, c.percentual, c.valor_financeiro, c.competencia
        FROM carteiras_cda c
        JOIN fundos f ON f.cnpj = c.fundo_cnpj
        LEFT JOIN gestoras g ON g.id = f.gestora_id
        LEFT JOIN ativos_investidos a ON a.cnpj = c.cnpj_investido
        WHERE c.percentual IS NOT NULL
          AND c.competencia = (SELECT MAX(d.competencia) FROM documentos_cda d
                               WHERE d.fundo_cnpj = c.fundo_cnpj)
    """
    params: list = []
    if gestora_nome:
        sql += " AND g.nome = ?"
        params.append(gestora_nome)
    sql += " ORDER BY c.percentual DESC LIMIT 50"
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=params)


def ranking_cnpjs_recorrentes(gestora_nome: Optional[str] = None) -> pd.DataFrame:
    """CNPJs investidos que mais aparecem entre os fundos monitorados."""
    return exposicao_consolidada(gestora_nome=gestora_nome)


# ---------------------------------------------------------------------------
# Upload de CDA pelo dashboard (salva na estrutura padrão e importa)
# ---------------------------------------------------------------------------
def cadastrar_fundos_faltantes() -> dict:
    """Cadastra na tabela 'fundos' todo fundo que tem documento importado
    (documentos_cda) mas ainda não existe em 'fundos'. Reparo para CDAs
    enviados antes do cadastro automático no upload.

    A gestora é recuperada automaticamente a partir do caminho de origem do
    arquivo (data/import/<gestora>/<cnpj>/<competência>/...), registrado na
    tabela 'importacoes'. Se não for possível descobrir, o fundo é cadastrado
    sem gestora (e pode ser associado depois reenviando o CDA).
    """
    from pathlib import Path as _Path
    from src.database import sessao
    from src.utils.cnpj import normalizar_cnpj

    def _gestora_do_caminho(caminho: str, cnpj: str):
        """Extrai o nome da gestora de .../import/<gestora>/<cnpj>/...

        Aceita separadores de qualquer SO (/ ou barra invertida), pois o
        caminho pode ter sido gravado no Windows e lido em outro ambiente.
        """
        if not caminho:
            return None
        partes = [p for p in caminho.replace("\\", "/").split("/") if p]
        for i, seg in enumerate(partes):
            if normalizar_cnpj(seg, validar=False) == cnpj and i >= 1:
                cand = partes[i - 1]
                if normalizar_cnpj(cand, validar=False):  # se for outro CNPJ, ignora
                    return None
                if cand.strip().lower() == "import":       # CNPJ direto sob import/
                    return None
                return cand.replace("_", " ").strip() or None
        return None

    criados = []
    corrigidos = []
    with sessao() as con:
        # 1) fundos que existem em documentos mas NÃO em 'fundos' -> cadastra
        orfaos = con.execute("""
            SELECT DISTINCT fundo_cnpj
            FROM documentos_cda
            WHERE fundo_cnpj IS NOT NULL
              AND fundo_cnpj NOT IN (SELECT cnpj FROM fundos)
        """).fetchall()

        def _acha_gestora(cnpj):
            imps = con.execute(
                "SELECT caminho_origem FROM importacoes WHERE caminho_origem IS NOT NULL"
            ).fetchall()
            for imp in imps:
                g = _gestora_do_caminho(imp["caminho_origem"], cnpj)
                if g:
                    return g
            return None

        def _id_gestora(nome):
            if not nome:
                return None
            gr = con.execute("SELECT id FROM gestoras WHERE nome=?", (nome,)).fetchone()
            return gr["id"] if gr else con.execute(
                "INSERT INTO gestoras (nome) VALUES (?)", (nome,)).lastrowid

        for row in orfaos:
            cnpj = row["fundo_cnpj"]
            gestora_nome = _acha_gestora(cnpj)
            con.execute("INSERT INTO fundos (cnpj, gestora_id) VALUES (?, ?)",
                        (cnpj, _id_gestora(gestora_nome)))
            criados.append({"cnpj": cnpj, "gestora": gestora_nome})

        # 2) fundos que JÁ existem mas estão SEM gestora -> tenta associar
        sem_gestora = con.execute("""
            SELECT cnpj FROM fundos
            WHERE gestora_id IS NULL
              AND cnpj IN (SELECT DISTINCT fundo_cnpj FROM documentos_cda)
        """).fetchall()
        for row in sem_gestora:
            cnpj = row["cnpj"]
            gestora_nome = _acha_gestora(cnpj)
            if gestora_nome:
                con.execute("UPDATE fundos SET gestora_id=? WHERE cnpj=?",
                            (_id_gestora(gestora_nome), cnpj))
                corrigidos.append({"cnpj": cnpj, "gestora": gestora_nome})

    return {"criados": len(criados), "fundos": criados,
            "corrigidos": len(corrigidos), "fundos_corrigidos": corrigidos}


def importar_arquivo_enviado(nome_arquivo: str, conteudo: bytes,
                             gestora: str, fundo_cnpj: str,
                             competencia: str) -> dict:
    """Salva um arquivo enviado pelo dashboard em
    data/import/<gestora>/<cnpj>/<aaaa-mm>/ e roda a importação normal.

    Reaproveita todo o pipeline testado (hash, dedup, parsing, auditoria).
    """
    import re
    from pathlib import Path
    from src.utils.cnpj import normalizar_cnpj
    from src.database import sessao
    from src.importers.cda_importer import importar_um

    ext = Path(nome_arquivo).suffix.lower()
    if ext not in settings.EXTENSOES_ACEITAS:
        return {"status": "ERRO", "arquivo": nome_arquivo,
                "mensagem": f"Extensão não aceita: {ext}"}

    cnpj_limpo = normalizar_cnpj(fundo_cnpj, validar=False)
    if not cnpj_limpo:
        return {"status": "ERRO", "arquivo": nome_arquivo,
                "mensagem": "CNPJ do fundo inválido."}

    if not re.match(r"^\d{4}-\d{2}$", competencia or ""):
        return {"status": "ERRO", "arquivo": nome_arquivo,
                "mensagem": "Competência deve estar no formato AAAA-MM."}

    # nome de pasta da gestora seguro (sem caracteres problemáticos)
    gestora_dir = re.sub(r"[^\w\- ]", "_", (gestora or "SemGestora").strip()) or "SemGestora"
    destino_dir = settings.IMPORT_DIR / gestora_dir / cnpj_limpo / competencia
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / Path(nome_arquivo).name
    destino.write_bytes(conteudo)

    with sessao() as con:
        # ---- cadastra gestora e fundo automaticamente se ainda não existirem
        # (sem isso, o fundo importado não apareceria nas outras páginas, que
        # listam a partir da tabela 'fundos').
        gestora_nome = (gestora or "").strip()
        gestora_id = None
        if gestora_nome:
            row = con.execute("SELECT id FROM gestoras WHERE nome = ?",
                              (gestora_nome,)).fetchone()
            if row:
                gestora_id = row["id"]
            else:
                cur = con.execute("INSERT INTO gestoras (nome) VALUES (?)",
                                  (gestora_nome,))
                gestora_id = cur.lastrowid

        fundo = con.execute("SELECT id FROM fundos WHERE cnpj = ?",
                            (cnpj_limpo,)).fetchone()
        if fundo is None:
            con.execute(
                "INSERT INTO fundos (cnpj, gestora_id) VALUES (?, ?)",
                (cnpj_limpo, gestora_id))
        elif gestora_id is not None:
            # se o fundo já existia mas sem gestora, associa a informada agora
            con.execute(
                "UPDATE fundos SET gestora_id = COALESCE(gestora_id, ?) WHERE cnpj = ?",
                (gestora_id, cnpj_limpo))

        resultado = importar_um(con, destino)
    return resultado


# ---------------------------------------------------------------------------
# Exclusão de dados (fundo completo, um mês específico, ou gestora inteira)
# ---------------------------------------------------------------------------
def _excluir_fundo_na_sessao(con, cnpj: str) -> dict:
    """Apaga TODAS as competências de um fundo (usa a mesma conexão/transação
    de quem chamar, para permitir uso em excluir_gestora)."""
    n_carteira = con.execute(
        "DELETE FROM carteiras_cda WHERE fundo_cnpj = ?", (cnpj,)).rowcount
    n_docs = con.execute(
        "DELETE FROM documentos_cda WHERE fundo_cnpj = ?", (cnpj,)).rowcount
    n_pl = con.execute(
        "DELETE FROM pl_historico WHERE fundo_cnpj = ?", (cnpj,)).rowcount
    n_rent = con.execute(
        "DELETE FROM rentabilidade_historica WHERE fundo_cnpj = ?", (cnpj,)).rowcount
    n_fundo = con.execute(
        "DELETE FROM fundos WHERE cnpj = ?", (cnpj,)).rowcount
    return {"carteira": n_carteira, "documentos": n_docs, "pl_historico": n_pl,
            "rentabilidade": n_rent, "fundo": n_fundo}


def excluir_fundo(cnpj: str) -> dict:
    """Apaga um fundo por completo: todas as competências, carteira, PL
    histórico e o cadastro do fundo. Não apaga a gestora (pode ter outros
    fundos)."""
    from src.database import sessao
    from src.utils.cnpj import normalizar_cnpj
    cnpj = normalizar_cnpj(cnpj, validar=False)
    if not cnpj:
        return {"status": "erro", "mensagem": "CNPJ inválido."}
    with sessao() as con:
        r = _excluir_fundo_na_sessao(con, cnpj)
    r["status"] = "ok"
    return r


def excluir_mes_fundo(cnpj: str, competencia: str) -> dict:
    """Apaga apenas uma competência (mês) específica de um fundo. O fundo
    continua cadastrado se tiver outras competências."""
    from src.database import sessao
    from src.utils.cnpj import normalizar_cnpj
    cnpj = normalizar_cnpj(cnpj, validar=False)
    if not cnpj:
        return {"status": "erro", "mensagem": "CNPJ inválido."}
    with sessao() as con:
        n_carteira = con.execute(
            "DELETE FROM carteiras_cda WHERE fundo_cnpj=? AND competencia=?",
            (cnpj, competencia)).rowcount
        n_docs = con.execute(
            "DELETE FROM documentos_cda WHERE fundo_cnpj=? AND competencia=?",
            (cnpj, competencia)).rowcount
        n_pl = con.execute(
            "DELETE FROM pl_historico WHERE fundo_cnpj=? AND competencia=?",
            (cnpj, competencia)).rowcount
        n_rent = con.execute(
            "DELETE FROM rentabilidade_historica WHERE fundo_cnpj=? AND competencia=?",
            (cnpj, competencia)).rowcount
    return {"status": "ok", "carteira": n_carteira, "documentos": n_docs,
            "pl_historico": n_pl, "rentabilidade": n_rent}


def excluir_gestora(gestora_nome: str) -> dict:
    """Apaga uma gestora inteira: todos os fundos dela (com toda a carteira e
    histórico de cada um) e a própria gestora."""
    from src.database import sessao
    with sessao() as con:
        g = con.execute("SELECT id FROM gestoras WHERE nome=?",
                        (gestora_nome,)).fetchone()
        if g is None:
            return {"status": "erro", "mensagem": "Gestora não encontrada."}
        fundos = con.execute("SELECT cnpj FROM fundos WHERE gestora_id=?",
                             (g["id"],)).fetchall()
        totais = {"carteira": 0, "documentos": 0, "pl_historico": 0,
                  "rentabilidade": 0, "fundo": 0}
        for row in fundos:
            r = _excluir_fundo_na_sessao(con, row["cnpj"])
            for k in totais:
                totais[k] += r[k]
        con.execute("DELETE FROM gestoras WHERE id=?", (g["id"],))
    totais["status"] = "ok"
    totais["n_fundos"] = len(fundos)
    return totais


# ---------------------------------------------------------------------------
# Leitura prévia do arquivo (antes de importar) — evita digitação manual
# ---------------------------------------------------------------------------
def gestora_do_fundo(cnpj: str) -> Optional[str]:
    """Nome da gestora já cadastrada para este CNPJ de fundo, se existir."""
    from src.database import conectar
    from src.utils.cnpj import normalizar_cnpj
    cnpj = normalizar_cnpj(cnpj, validar=False)
    if not cnpj:
        return None
    with conectar() as con:
        row = con.execute(
            """SELECT g.nome FROM fundos f JOIN gestoras g ON g.id = f.gestora_id
               WHERE f.cnpj = ?""", (cnpj,)).fetchone()
        return row["nome"] if row else None


def detectar_dados_do_arquivo(nome_arquivo: str, conteudo: bytes) -> dict:
    """Lê o CNPJ do fundo e a competência de DENTRO do arquivo, sem importar
    nada (não grava no banco). Usado para pré-preencher o formulário de
    upload e evitar erro de digitação manual.

    Retorna {} se não conseguir extrair (formato não suportado, arquivo
    corrompido etc.) — nesse caso o usuário preenche manualmente, como antes.
    """
    import tempfile
    from pathlib import Path as _Path
    from src.parsers.registry import parser_para_extensao

    ext = _Path(nome_arquivo).suffix.lower()
    parser = parser_para_extensao(ext)
    if parser is None:
        return {}

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as fh:
            fh.write(conteudo)
            tmp = _Path(fh.name)
        resultado = parser.parse(tmp)
        dados = {
            "fundo_cnpj": getattr(resultado, "fundo_cnpj", None),
            "competencia": getattr(resultado, "competencia", None),
        }
        cnpj_detectado = dados.get("fundo_cnpj")
        if cnpj_detectado:
            dados["gestora_sugerida"] = gestora_do_fundo(cnpj_detectado)
        return dados
    except Exception:
        # leitura prévia é só uma conveniência — qualquer falha aqui não deve
        # impedir o usuário de preencher manualmente e tentar importar.
        return {}
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

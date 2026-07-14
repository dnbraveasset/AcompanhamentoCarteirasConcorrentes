"""
Importa o cadastro manual de gestoras e fundos a partir de um CSV.

Colunas esperadas (cabeçalho):
    gestora_nome; gestora_cnpj; fundo_nome; fundo_cnpj;
    administrador; gestor; classe; ativo; observacoes

Regras:
- CNPJ do fundo é a chave (UNIQUE) -> upsert por CNPJ;
- gestora identificada por nome (UNIQUE);
- campos ausentes viram NULL, nunca quebram a execução.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings
from src.database import registrar_log, sessao
from src.utils.cnpj import normalizar_cnpj
from src.utils.logger import obter_logger

log = obter_logger()


def _limpar(valor) -> Optional[str]:
    if valor is None:
        return None
    s = str(valor).strip()
    if s.lower() in ("", "nan", "none"):
        return None
    return s


def _upsert_gestora(con, nome: str, cnpj: Optional[str]) -> Optional[int]:
    if not nome:
        return None
    row = con.execute("SELECT id FROM gestoras WHERE nome = ?", (nome,)).fetchone()
    if row:
        if cnpj:
            con.execute("UPDATE gestoras SET cnpj = COALESCE(cnpj, ?) WHERE id = ?", (cnpj, row["id"]))
        return row["id"]
    cur = con.execute("INSERT INTO gestoras (nome, cnpj) VALUES (?,?)", (nome, cnpj))
    return cur.lastrowid


def _upsert_fundo(con, dados: dict, gestora_id: Optional[int]) -> None:
    cnpj = dados["fundo_cnpj"]
    row = con.execute("SELECT id FROM fundos WHERE cnpj = ?", (cnpj,)).fetchone()
    if row:
        con.execute(
            """UPDATE fundos SET
                 nome=COALESCE(?, nome),
                 gestora_id=COALESCE(?, gestora_id),
                 administrador=COALESCE(?, administrador),
                 gestor=COALESCE(?, gestor),
                 classe=COALESCE(?, classe),
                 ativo=COALESCE(?, ativo),
                 observacoes=COALESCE(?, observacoes),
                 atualizado_em=datetime('now')
               WHERE cnpj=?""",
            (dados["fundo_nome"], gestora_id, dados["administrador"], dados["gestor"],
             dados["classe"], dados["ativo"], dados["observacoes"], cnpj),
        )
    else:
        con.execute(
            """INSERT INTO fundos
                 (cnpj, nome, gestora_id, administrador, gestor, classe, ativo, observacoes)
               VALUES (?,?,?,?,?,?,?,?)""",
            (cnpj, dados["fundo_nome"], gestora_id, dados["administrador"],
             dados["gestor"], dados["classe"], dados["ativo"], dados["observacoes"]),
        )


def importar_cadastro(csv_path: Optional[Path] = None) -> dict:
    csv_path = Path(csv_path or settings.CADASTRO_CSV)
    if not csv_path.exists():
        raise FileNotFoundError(f"Cadastro não encontrado: {csv_path}")

    df = pd.read_csv(csv_path, sep=None, engine="python", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]

    inseridos = atualizados = ignorados = 0
    with sessao() as con:
        for _, row in df.iterrows():
            fundo_cnpj = normalizar_cnpj(_limpar(row.get("fundo_cnpj")), validar=False)
            if not fundo_cnpj:
                ignorados += 1
                log.warning("Linha ignorada (CNPJ do fundo ausente/invalido): %s", dict(row))
                continue

            gestora_nome = _limpar(row.get("gestora_nome"))
            gestora_cnpj = normalizar_cnpj(_limpar(row.get("gestora_cnpj")), validar=False)
            existia = con.execute("SELECT 1 FROM fundos WHERE cnpj=?", (fundo_cnpj,)).fetchone()

            gestora_id = _upsert_gestora(con, gestora_nome, gestora_cnpj) if gestora_nome else None
            _upsert_fundo(
                con,
                {
                    "fundo_cnpj": fundo_cnpj,
                    "fundo_nome": _limpar(row.get("fundo_nome")),
                    "administrador": _limpar(row.get("administrador")),
                    "gestor": _limpar(row.get("gestor")),
                    "classe": _limpar(row.get("classe")),
                    "ativo": _limpar(row.get("ativo")),
                    "observacoes": _limpar(row.get("observacoes")),
                },
                gestora_id,
            )
            if existia:
                atualizados += 1
            else:
                inseridos += 1

        registrar_log(con, "INFO", "import-cadastro",
                      f"inseridos={inseridos} atualizados={atualizados} ignorados={ignorados}")

    resumo = {"inseridos": inseridos, "atualizados": atualizados, "ignorados": ignorados}
    log.info("Cadastro importado: %s", resumo)
    return resumo

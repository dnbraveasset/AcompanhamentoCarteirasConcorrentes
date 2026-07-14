"""
Camada de acesso ao SQLite.

Fornece conexão com row_factory (acesso por nome de coluna), inicialização do
schema, e helpers de log/registro. Projetado para migrar depois para
PostgreSQL sem grandes mudanças na API (execute/fetch).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

from config import settings
from src.models.schema import DDL


def conectar(db_path: Optional[Path] = None) -> sqlite3.Connection:
    caminho = Path(db_path or settings.DB_PATH)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con


@contextmanager
def sessao(db_path: Optional[Path] = None):
    con = conectar(db_path)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Cria todas as tabelas (idempotente)."""
    with sessao(db_path) as con:
        con.executescript(DDL)


def garantir_tabela_anotacoes(db_path: Optional[Path] = None) -> None:
    """Cria a tabela de anotações manuais se ela ainda não existir.

    Chamada pelo dashboard para funcionar mesmo em bancos criados antes desta
    funcionalidade, sem precisar recriar o banco.
    """
    with sessao(db_path) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS anotacoes_ativos (
                   cnpj          TEXT PRIMARY KEY,
                   classe_manual TEXT,
                   observacao    TEXT,
                   atualizado_em TEXT DEFAULT (datetime('now'))
               )"""
        )


# ---------------------------------------------------------------------------
# Helpers genéricos
# ---------------------------------------------------------------------------
def executar(con: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    return con.execute(sql, tuple(params))


def registrar_log(con: sqlite3.Connection, nivel: str, contexto: str, mensagem: str) -> None:
    con.execute(
        "INSERT INTO logs_execucao (nivel, contexto, mensagem) VALUES (?,?,?)",
        (nivel, contexto, mensagem),
    )


def hash_ja_importado(con: sqlite3.Connection, arquivo_hash: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM documentos_cda WHERE arquivo_hash = ? LIMIT 1",
        (arquivo_hash,),
    ).fetchone()
    return row is not None


def upsert_ativo_investido(
    con: sqlite3.Connection,
    cnpj: Optional[str],
    nome: Optional[str],
    tipo: Optional[str],
    fonte: str = "cda",
) -> None:
    if not cnpj:
        return
    existente = con.execute(
        "SELECT id, nome FROM ativos_investidos WHERE cnpj = ?", (cnpj,)
    ).fetchone()
    if existente is None:
        con.execute(
            "INSERT INTO ativos_investidos (cnpj, nome, tipo, fonte_nome) VALUES (?,?,?,?)",
            (cnpj, nome, tipo, fonte),
        )
    else:
        # só sobrescreve nome se ainda estiver vazio e agora temos um
        if not existente["nome"] and nome:
            con.execute(
                "UPDATE ativos_investidos SET nome=?, atualizado_em=datetime('now') WHERE cnpj=?",
                (nome, cnpj),
            )

"""
Importador de arquivos CDA.

Fluxo por arquivo encontrado em data/import/<gestora>/<fundo_cnpj>/<aaaa-mm>/:
  1. interpreta gestora/fundo/competência pelo caminho;
  2. calcula hash SHA256;
  3. checa duplicidade (mesmo hash já importado -> pula);
  4. copia original para data/raw/ (auditoria);
  5. seleciona o parser pela extensão e faz o parse;
  6. concilia CNPJ do fundo/competência (documento x pasta) e avisa divergência;
  7. grava documento + linhas de carteira; atualiza ativos, PL e importações;
  8. registra status (OK/PARCIAL/ERRO) e continua mesmo em caso de falha.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from config import settings
from src.database import (
    hash_ja_importado, registrar_log, sessao, upsert_ativo_investido,
)
from src.parsers.registry import parser_para_extensao
from src.utils.cnpj import normalizar_cnpj
from src.utils.file_utils import (
    copiar_para_raw, interpretar_caminho, sha256_arquivo,
)
from src.utils.logger import obter_logger

log = obter_logger()


def _arquivos_para_importar(import_dir: Path) -> List[Path]:
    arquivos = []
    for p in sorted(import_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in settings.EXTENSOES_ACEITAS:
            arquivos.append(p)
    return arquivos


def _fundo_id_por_cnpj(con, cnpj: Optional[str]) -> Optional[int]:
    if not cnpj:
        return None
    row = con.execute("SELECT id FROM fundos WHERE cnpj = ?", (cnpj,)).fetchone()
    return row["id"] if row else None


def importar_um(con, arquivo: Path) -> dict:
    ctx = interpretar_caminho(arquivo, settings.IMPORT_DIR)
    hash_arq = sha256_arquivo(arquivo)
    ext = arquivo.suffix.lower()

    # registro em importacoes (auditoria de tentativa)
    cur = con.execute(
        "INSERT INTO importacoes (arquivo_nome, arquivo_hash, caminho_origem, status) "
        "VALUES (?,?,?,?)",
        (arquivo.name, hash_arq, str(arquivo), "INICIADO"),
    )
    imp_id = cur.lastrowid

    if hash_ja_importado(con, hash_arq):
        con.execute(
            "UPDATE importacoes SET status=?, mensagem=?, finalizado_em=datetime('now') WHERE id=?",
            ("DUPLICADO", "Arquivo com mesmo hash já importado.", imp_id),
        )
        registrar_log(con, "INFO", "import-cdas", f"DUPLICADO: {arquivo.name}")
        return {"arquivo": arquivo.name, "status": "DUPLICADO", "cnpjs": 0}

    caminho_raw = copiar_para_raw(arquivo, settings.RAW_DIR, hash_arq)

    parser = parser_para_extensao(ext)
    if parser is None:
        con.execute(
            "UPDATE importacoes SET status=?, mensagem=?, finalizado_em=datetime('now') WHERE id=?",
            ("ERRO", f"Extensão não suportada: {ext}", imp_id),
        )
        return {"arquivo": arquivo.name, "status": "ERRO", "cnpjs": 0}

    status = "OK"
    mensagem_partes: List[str] = []
    try:
        resultado = parser.parse(arquivo)
    except Exception as e:  # nunca deixa quebrar o lote
        con.execute(
            "UPDATE importacoes SET status=?, mensagem=?, finalizado_em=datetime('now') WHERE id=?",
            ("ERRO", f"Falha no parser: {e}", imp_id),
        )
        registrar_log(con, "ERROR", "import-cdas", f"ERRO em {arquivo.name}: {e}")
        return {"arquivo": arquivo.name, "status": "ERRO", "cnpjs": 0}

    if resultado.aviso:
        mensagem_partes.append(resultado.aviso)
        status = "PARCIAL"

    # Concilia CNPJ do fundo: prioriza o do documento; concilia com a pasta.
    fundo_cnpj = resultado.fundo_cnpj or ctx.fundo_cnpj
    if resultado.fundo_cnpj and ctx.fundo_cnpj and resultado.fundo_cnpj != ctx.fundo_cnpj:
        mensagem_partes.append(
            f"Divergência CNPJ pasta({ctx.fundo_cnpj}) x documento({resultado.fundo_cnpj})."
        )
        status = "PARCIAL"

    competencia = resultado.competencia or ctx.competencia
    if resultado.competencia and ctx.competencia and resultado.competencia != ctx.competencia:
        mensagem_partes.append(
            f"Divergência competência pasta({ctx.competencia}) x documento({resultado.competencia})."
        )
        status = "PARCIAL"

    cnpjs_validos = [h for h in resultado.holdings if h.cnpj_investido]
    qtd_cnpjs = len({h.cnpj_investido for h in cnpjs_validos})

    # grava documento
    fundo_id = _fundo_id_por_cnpj(con, fundo_cnpj)
    cur_doc = con.execute(
        """INSERT INTO documentos_cda
             (fundo_id, fundo_cnpj, competencia, competencia_pasta, cod_doc, versao,
              dt_gerac_arq, vl_pl, arquivo_nome, arquivo_hash, caminho_raw, formato,
              status, mensagem, qtd_cnpjs)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (fundo_id, fundo_cnpj, competencia, ctx.competencia, resultado.cod_doc,
         resultado.versao, resultado.dt_gerac_arq, resultado.vl_pl, arquivo.name,
         hash_arq, str(caminho_raw), resultado.formato, status,
         " | ".join(mensagem_partes) or None, qtd_cnpjs),
    )
    doc_id = cur_doc.lastrowid

    # grava linhas de carteira
    for h in resultado.holdings:
        try:
            con.execute(
                """INSERT OR IGNORE INTO carteiras_cda
                     (documento_id, fundo_cnpj, competencia, cnpj_investido, nome_ativo,
                      tipo_ativo, valor_financeiro, percentual, quantidade, empresa_ligada, extra_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (doc_id, fundo_cnpj, competencia, h.cnpj_investido, h.nome_ativo,
                 h.tipo_ativo, h.valor_financeiro, h.percentual, h.quantidade,
                 h.empresa_ligada, json.dumps(h.extra, ensure_ascii=False) if h.extra else None),
            )
            upsert_ativo_investido(con, h.cnpj_investido, h.nome_ativo, h.tipo_ativo, fonte="cda")
        except Exception as e:
            registrar_log(con, "WARNING", "import-cdas", f"linha ignorada em {arquivo.name}: {e}")

    # PL do documento -> histórico
    if fundo_cnpj and competencia and resultado.vl_pl is not None:
        con.execute(
            "INSERT OR IGNORE INTO pl_historico (fundo_cnpj, competencia, vl_pl, fonte) VALUES (?,?,?,?)",
            (fundo_cnpj, competencia, resultado.vl_pl, "cda"),
        )

    con.execute(
        "UPDATE importacoes SET status=?, mensagem=?, cnpjs_encontrados=?, finalizado_em=datetime('now') WHERE id=?",
        (status, " | ".join(mensagem_partes) or None, qtd_cnpjs, imp_id),
    )
    registrar_log(con, "INFO", "import-cdas",
                  f"{status}: {arquivo.name} fundo={fundo_cnpj} comp={competencia} cnpjs={qtd_cnpjs}")

    return {"arquivo": arquivo.name, "status": status, "cnpjs": qtd_cnpjs,
            "fundo_cnpj": fundo_cnpj, "competencia": competencia}


def importar_cdas(import_dir: Optional[Path] = None) -> List[dict]:
    import_dir = Path(import_dir or settings.IMPORT_DIR)
    arquivos = _arquivos_para_importar(import_dir)
    if not arquivos:
        log.warning("Nenhum arquivo encontrado em %s", import_dir)
        return []

    resumos = []
    with sessao() as con:
        for arq in arquivos:
            resumos.append(importar_um(con, arq))

    ok = sum(1 for r in resumos if r["status"] == "OK")
    parcial = sum(1 for r in resumos if r["status"] == "PARCIAL")
    dup = sum(1 for r in resumos if r["status"] == "DUPLICADO")
    erro = sum(1 for r in resumos if r["status"] == "ERRO")
    log.info("Importação concluída: OK=%d PARCIAL=%d DUPLICADO=%d ERRO=%d",
             ok, parcial, dup, erro)
    return resumos

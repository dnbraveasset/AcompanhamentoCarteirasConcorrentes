"""
Utilitários de arquivo: hash SHA256, cópia para auditoria, leitura de bytes,
interpretação do caminho de importação e conversão de decimais brasileiros.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.utils.cnpj import apenas_digitos, normalizar_cnpj


# ---------------------------------------------------------------------------
# Hash / cópia
# ---------------------------------------------------------------------------
def sha256_arquivo(caminho: Path, chunk: int = 1 << 16) -> str:
    """Calcula o SHA256 de um arquivo (streaming, seguro para arquivos grandes)."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(chunk), b""):
            h.update(bloco)
    return h.hexdigest()


def copiar_para_raw(origem: Path, raw_dir: Path, hash_arquivo: str) -> Path:
    """Copia o original para data/raw/ preservando-o para auditoria.

    Usa o prefixo do hash no nome para evitar colisão e manter rastreabilidade.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    destino = raw_dir / f"{hash_arquivo[:12]}__{origem.name}"
    if not destino.exists():
        shutil.copy2(origem, destino)
    return destino


# ---------------------------------------------------------------------------
# Interpretação do caminho de importação
# data/import/<gestora>/<fundo_cnpj>/<aaaa-mm>/arquivo.ext
# ---------------------------------------------------------------------------
@dataclass
class ContextoImportacao:
    gestora_nome: Optional[str]
    fundo_cnpj: Optional[str]      # do caminho (pode divergir do interno)
    competencia: Optional[str]     # 'aaaa-mm' do caminho (pode divergir do interno)
    caminho: Path


_COMPETENCIA_RE = re.compile(r"^(\d{4})-(\d{2})$")


def interpretar_caminho(arquivo: Path, import_dir: Path) -> ContextoImportacao:
    """Extrai gestora, CNPJ do fundo e competência a partir da estrutura de pastas.

    É tolerante: se a estrutura não bater exatamente, retorna o que conseguir e
    deixa o restante como None (o parser ainda pode recuperar pelo conteúdo).
    """
    try:
        rel = arquivo.relative_to(import_dir)
    except ValueError:
        rel = arquivo
    partes = rel.parts

    gestora = partes[0] if len(partes) >= 1 else None
    fundo_cnpj = None
    competencia = None

    if len(partes) >= 2:
        fundo_cnpj = normalizar_cnpj(partes[1], validar=False) or apenas_digitos(partes[1]) or None

    if len(partes) >= 3 and _COMPETENCIA_RE.match(partes[2]):
        competencia = partes[2]

    return ContextoImportacao(
        gestora_nome=gestora,
        fundo_cnpj=fundo_cnpj,
        competencia=competencia,
        caminho=arquivo,
    )


# ---------------------------------------------------------------------------
# Decimais brasileiros: "78239632,82" -> 78239632.82
# ---------------------------------------------------------------------------
def parse_decimal_br(valor) -> Optional[float]:
    """Converte string com vírgula decimal (padrão BR) para float.

    Trata milhar com ponto ("1.234.567,89") e valores já em ponto.
    Retorna None para vazio/nulo/inválido — nunca levanta exceção.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    if not s:
        return None
    # Se tem vírgula, assume-se BR: ponto = milhar, vírgula = decimal
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Competência: "05/2026" (DT_COMPT da CVM) -> "2026-05"
# ---------------------------------------------------------------------------
def normalizar_competencia(valor: Optional[str]) -> Optional[str]:
    """Normaliza competência para 'aaaa-mm'. Aceita 'MM/AAAA', 'AAAA-MM', 'AAAAMM'."""
    if not valor:
        return None
    s = str(valor).strip()
    m = re.match(r"^(\d{2})/(\d{4})$", s)          # 05/2026
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    m = re.match(r"^(\d{4})-(\d{2})$", s)          # 2026-05
    if m:
        return s
    m = re.match(r"^(\d{4})(\d{2})$", s)           # 202605
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None

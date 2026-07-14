"""
Configurações centrais do projeto FIDC-CDA MVP.

Todos os caminhos são relativos à raiz do projeto, de forma que o sistema
rode localmente sem configuração adicional. Basta clonar/descompactar e usar.
"""
from __future__ import annotations

from pathlib import Path

# Raiz do projeto (config/ -> raiz)
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Diretórios
# ---------------------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
IMPORT_DIR = DATA_DIR / "import"       # onde VOCÊ coloca os CDAs baixados manualmente
RAW_DIR = DATA_DIR / "raw"             # cópia imutável dos originais (auditoria)
PROCESSED_DIR = DATA_DIR / "processed"  # exportações / arquivos derivados
DATABASE_DIR = BASE_DIR / "database"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"

# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
DB_PATH = DATABASE_DIR / "fidc_cda.sqlite"

# ---------------------------------------------------------------------------
# Cadastro manual
# ---------------------------------------------------------------------------
CADASTRO_CSV = CONFIG_DIR / "fundos_monitorados.csv"

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------
LOG_FILE = LOGS_DIR / "execucao.log"
LOG_LEVEL = "INFO"

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
# Extensões aceitas pelo importador
EXTENSOES_ACEITAS = {".pdf", ".xlsx", ".xls", ".csv", ".xml", ".txt", ".zip"}

# Encoding padrão dos arquivos da CVM/Fundos.NET
ENCODING_CVM = "windows-1252"

# ---------------------------------------------------------------------------
# Regras de negócio (limites usados no dashboard/alertas)
# ---------------------------------------------------------------------------
LIMITE_CONCENTRACAO_PADRAO = 20.0  # % da carteira em um único CNPJ investido
VARIACAO_RELEVANTE_PADRAO = 5.0    # variação de exposição (p.p.) considerada relevante

# ---------------------------------------------------------------------------
# CVM - Dados Abertos (opcional, usado apenas pelo módulo de enriquecimento)
# ---------------------------------------------------------------------------
CVM_CADASTRO_URL = (
    "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
)
# Base nova (Resolução CVM 175) — cobre fundos estruturados como FIDC.
# Zip com registro_fundo.csv / registro_classe.csv / registro_subclasse.csv.
CVM_REGISTRO_FUNDO_URL = (
    "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
)
CVM_INF_DIARIO_BASE = (
    "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/"
)


def garantir_diretorios() -> None:
    """Cria todos os diretórios necessários caso não existam."""
    for d in (
        DATA_DIR, IMPORT_DIR, RAW_DIR, PROCESSED_DIR,
        DATABASE_DIR, LOGS_DIR, CONFIG_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)

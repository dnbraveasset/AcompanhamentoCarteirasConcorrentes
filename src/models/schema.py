"""
Modelo de dados (DDL) em SQLite.

Princípios:
- CNPJ sempre TEXT (preserva zeros à esquerda);
- valores monetários em REAL (float) — para MVP é suficiente;
- restrições UNIQUE para evitar duplicidade;
- chaves estrangeiras habilitadas via PRAGMA em database.py.
"""

DDL = r"""
-- ------------------------------------------------------------------ gestoras
CREATE TABLE IF NOT EXISTS gestoras (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nome         TEXT NOT NULL,
    cnpj         TEXT UNIQUE,                 -- pode ser nulo
    criado_em    TEXT DEFAULT (datetime('now')),
    UNIQUE (nome)
);

-- -------------------------------------------------------------------- fundos
CREATE TABLE IF NOT EXISTS fundos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj           TEXT NOT NULL UNIQUE,      -- CHAVE PRINCIPAL do fundo
    nome           TEXT,
    gestora_id     INTEGER,
    administrador  TEXT,
    gestor         TEXT,
    classe         TEXT,
    ativo          TEXT,                      -- S/N ou descrição livre
    observacoes    TEXT,
    criado_em      TEXT DEFAULT (datetime('now')),
    atualizado_em  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (gestora_id) REFERENCES gestoras(id)
);

-- ----------------------------------------------------------- documentos_cda
-- Um registro por arquivo CDA importado (auditoria + metadados do documento).
CREATE TABLE IF NOT EXISTS documentos_cda (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fundo_id       INTEGER,
    fundo_cnpj     TEXT NOT NULL,
    competencia    TEXT,                      -- 'aaaa-mm' (DT_COMPT do documento)
    competencia_pasta TEXT,                   -- 'aaaa-mm' inferido da pasta
    cod_doc        TEXT,
    versao         TEXT,
    dt_gerac_arq   TEXT,
    vl_pl          REAL,                      -- patrimônio líquido informado no CDA
    arquivo_nome   TEXT NOT NULL,
    arquivo_hash   TEXT NOT NULL UNIQUE,      -- evita reimportar o mesmo arquivo
    caminho_raw    TEXT,
    formato        TEXT,                      -- xml, pdf, xlsx, csv, txt, zip
    status         TEXT,                      -- OK, ERRO, PARCIAL, DUPLICADO
    mensagem       TEXT,
    qtd_cnpjs      INTEGER DEFAULT 0,
    importado_em   TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (fundo_id) REFERENCES fundos(id)
);

-- ------------------------------------------------------------- carteiras_cda
-- Uma linha por ativo/posição encontrada na carteira do documento.
CREATE TABLE IF NOT EXISTS carteiras_cda (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id      INTEGER NOT NULL,
    fundo_cnpj        TEXT NOT NULL,
    competencia       TEXT,
    cnpj_investido    TEXT,                   -- pode ser nulo (ativo sem CNPJ)
    nome_ativo        TEXT,
    tipo_ativo        TEXT,                   -- COTAS, TITPUBLICO, DEMAIS_N_CODIF...
    valor_financeiro  REAL,                   -- MERC_POS_FIM
    percentual        REAL,                   -- calculado: valor / vl_pl * 100
    quantidade        REAL,                   -- QTDE_POS_FIM
    empresa_ligada    TEXT,                   -- S/N
    extra_json        TEXT,                   -- campos brutos adicionais
    FOREIGN KEY (documento_id) REFERENCES documentos_cda(id),
    -- evita duplicar a mesma posição dentro do mesmo documento
    UNIQUE (documento_id, cnpj_investido, tipo_ativo, nome_ativo)
);

-- --------------------------------------------------------- ativos_investidos
-- Dimensão de CNPJs/ativos distintos investidos (para enriquecer com CVM).
CREATE TABLE IF NOT EXISTS ativos_investidos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj          TEXT UNIQUE,
    nome          TEXT,
    tipo          TEXT,
    fonte_nome    TEXT,                       -- 'cda', 'cvm', 'manual'
    primeira_vez  TEXT DEFAULT (datetime('now')),
    atualizado_em TEXT DEFAULT (datetime('now'))
);

-- --------------------------------------------------------------- pl_historico
CREATE TABLE IF NOT EXISTS pl_historico (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fundo_cnpj    TEXT NOT NULL,
    competencia   TEXT NOT NULL,              -- 'aaaa-mm' ou 'aaaa-mm-dd'
    vl_pl         REAL,
    fonte         TEXT,                       -- 'cda', 'cvm'
    UNIQUE (fundo_cnpj, competencia, fonte)
);

-- ---------------------------------------------------- rentabilidade_historica
CREATE TABLE IF NOT EXISTS rentabilidade_historica (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fundo_cnpj    TEXT NOT NULL,
    competencia   TEXT NOT NULL,
    rentabilidade REAL,
    fonte         TEXT,
    UNIQUE (fundo_cnpj, competencia, fonte)
);

-- ----------------------------------------------------------------- importacoes
CREATE TABLE IF NOT EXISTS importacoes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo_nome      TEXT,
    arquivo_hash      TEXT,
    caminho_origem    TEXT,
    status            TEXT,                   -- OK, ERRO, DUPLICADO
    mensagem          TEXT,
    cnpjs_encontrados INTEGER DEFAULT 0,
    iniciado_em       TEXT DEFAULT (datetime('now')),
    finalizado_em     TEXT
);

-- --------------------------------------------------------------- logs_execucao
CREATE TABLE IF NOT EXISTS logs_execucao (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nivel      TEXT,
    contexto   TEXT,
    mensagem   TEXT,
    criado_em  TEXT DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------- anotacoes_ativos
-- Anotações MANUAIS do usuário por CNPJ investido (classe e observação).
-- Chaveada por CNPJ: vale para todos os fundos/meses e NÃO é tocada ao
-- reimportar CDAs.
CREATE TABLE IF NOT EXISTS anotacoes_ativos (
    cnpj          TEXT PRIMARY KEY,
    classe_manual TEXT,
    observacao    TEXT,
    atualizado_em TEXT DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------- base_fundos
-- Resumo de fundos vindo da base Excel (planilha COMPARACAO_FUNDOS + dados da
-- base bruta). Guarda apenas o snapshot da data mais recente por CNPJ.
CREATE TABLE IF NOT EXISTS base_fundos (
    cnpj                TEXT PRIMARY KEY,
    nome                TEXT,
    data_base           TEXT,      -- competência do dado (AAAA-MM-DD)
    pl                  REAL,
    pct_caixa           REAL,      -- CAIXA / PL (da base bruta)
    condominio          TEXT,      -- ABERTO / FECHADO (da base bruta)
    administrador       TEXT,
    subord_sen          REAL,
    subord_mez          REAL,
    rentsub_12          REAL,
    pct_meses_negativos REAL,
    cedentes_sub_json   TEXT,      -- lista JSON dos 10 maiores cedentes
    rating_final        TEXT,
    atualizado_em       TEXT DEFAULT (datetime('now'))
);

-- --------------------------------------------------------------------- índices
CREATE INDEX IF NOT EXISTS idx_carteira_fundo   ON carteiras_cda (fundo_cnpj, competencia);
CREATE INDEX IF NOT EXISTS idx_carteira_invest  ON carteiras_cda (cnpj_investido);
CREATE INDEX IF NOT EXISTS idx_doc_fundo         ON documentos_cda (fundo_cnpj, competencia);
"""

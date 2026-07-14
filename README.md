# FIDC-CDA MVP — Análise semi-automática de carteiras de FIC FIDC

Sistema local em Python para importar, ler, tratar, armazenar e visualizar os
documentos de **Composição da Carteira (CDA)** de FIC FIDCs baixados manualmente
do Fundos.NET (B3/CVM).

Nesta fase (MVP semi-automático) **você baixa os CDAs manualmente** e o sistema
faz o resto: importa, faz o parsing, extrai os CNPJs investidos, normaliza,
grava em SQLite e exibe num dashboard Streamlit. O scraping automático do
Fundos.NET fica para uma fase futura (ver Roadmap).

> O parser de XML foi calibrado com um CDA real (layout `urn:cda`, `COD_DOC=3`).
> Ele extrai CNPJ investido, valor de mercado (`MERC_POS_FIM`), quantidade
> (`QTDE_POS_FIM`), tipo de bloco (`COTAS`, `DEMAIS_N_CODIF`, ...) e **calcula o
> percentual** (valor / PL), já que o percentual não vem no arquivo.

---

## 1. Instalação

Requer Python 3.10+.

```bash
cd fidc_cda_mvp
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Comandos

```bash
python main.py init-db            # cria o banco SQLite e as tabelas
python main.py import-cadastro    # lê config/fundos_monitorados.csv
python main.py import-cdas        # importa os CDAs de data/import/
python main.py status             # resumo do que está no banco
python main.py enriquecer-cvm     # (opcional) baixa dados públicos da CVM

streamlit run dashboard/app.py    # abre o dashboard
```

## 3. Onde colocar os arquivos

Estrutura esperada da pasta de importação:

```
data/import/<NomeGestora>/<CNPJ_do_fundo>/<aaaa-mm>/arquivo_cda.<ext>
```

Exemplo (já incluído para teste):

```
data/import/GestoraExemplo/57811727000176/2026-05/cda_maio.xml
```

Formatos aceitos: **PDF, XLSX/XLS, CSV, XML, TXT, ZIP**.
O sistema lê gestora, CNPJ do fundo e competência a partir do caminho, e
**também** confere o CNPJ/competência que vêm dentro do documento — se houver
divergência, ele importa mesmo assim e marca o status como `PARCIAL` com aviso.

## 4. Cadastro manual

Edite `config/fundos_monitorados.csv` (separador `;`). Colunas:

```
gestora_nome; gestora_cnpj; fundo_nome; fundo_cnpj;
administrador; gestor; classe; ativo; observacoes
```

O CNPJ do fundo é a chave: rodar `import-cadastro` de novo faz *upsert*
(insere novos, atualiza existentes sem apagar dados).

> **Foco em concorrentes.** Cadastre aqui apenas as **gestoras concorrentes**
> e os **fundos delas** para os quais você vai subir o CDA. Os fundos/emissores
> que aparecem *dentro* da carteira (o que o concorrente investe) NÃO precisam
> ser cadastrados — eles são descobertos automaticamente na leitura do CDA e
> aparecem como posições. A página 1 do dashboard mostra, por gestora, só os
> fundos que já têm CDA importado e a composição de cada um.

## 4.1. Anotações manuais (Classe e Observação)

Na página **"Carteira por fundo"** do dashboard, a tabela tem duas colunas
editáveis por você:

- **Classe** — você preenche como quiser (ex.: Sênior, Mezanino, Subordinada,
  Multimercado…);
- **Observação** — anotação livre sobre o ativo.

Edite direto na tabela e clique em **💾 Salvar anotações**. Elas são gravadas
**por CNPJ investido** (tabela `anotacoes_ativos`), então:

- valem para **todos os fundos e meses** em que aquele CNPJ aparecer;
- **não são apagadas** quando você reimporta o CDA (ficam numa tabela separada);
- entram nas exportações CSV/Excel.

Para bancos criados antes desta versão, a tabela de anotações é criada
automaticamente ao abrir o dashboard — não precisa recriar o banco.

## 5. Estrutura do projeto

```
fidc_cda_mvp/
├── main.py                     # CLI
├── requirements.txt
├── config/
│   ├── settings.py             # caminhos, constantes, limites
│   └── fundos_monitorados.csv  # cadastro manual (exemplo incluído)
├── data/
│   ├── import/                 # VOCÊ coloca os CDAs aqui
│   ├── raw/                    # cópia imutável dos originais (auditoria)
│   └── processed/              # exportações
├── database/                   # arquivo SQLite (criado no init-db)
├── logs/                       # logs de execução
├── src/
│   ├── database.py             # conexão + init + helpers
│   ├── models/schema.py        # DDL das tabelas
│   ├── utils/
│   │   ├── cnpj.py             # normalização/validação de CNPJ (chave!)
│   │   ├── file_utils.py       # hash, caminho, decimal BR, competência
│   │   └── logger.py
│   ├── parsers/                # um parser por formato + registry
│   │   ├── base_parser.py
│   │   ├── xml_parser.py       # <- calibrado no CDA real
│   │   ├── pdf_parser.py  excel_parser.py  csv_parser.py
│   │   ├── txt_parser.py  zip_parser.py    registry.py
│   ├── importers/
│   │   ├── cadastro_importer.py
│   │   └── cda_importer.py
│   └── services/
│       ├── carteira_service.py # consultas do dashboard + exportações
│       └── cvm_service.py      # integração CVM (opcional)
└── dashboard/app.py            # Streamlit (5 páginas)
```

## 6. Modelo de dados (SQLite)

`gestoras`, `fundos`, `documentos_cda`, `carteiras_cda`, `ativos_investidos`,
`pl_historico`, `rentabilidade_historica`, `importacoes`, `logs_execucao`,
`anotacoes_ativos` (classe/observação manuais por CNPJ).

Regras anti-duplicidade:
- `fundos.cnpj` e `gestoras.nome` são UNIQUE;
- `documentos_cda.arquivo_hash` é UNIQUE (mesmo arquivo não reentra);
- `carteiras_cda` tem UNIQUE por (documento, cnpj_investido, tipo, nome).

## 7. Auditoria

- SHA256 de cada arquivo; cópia do original em `data/raw/`;
- status de cada importação em `importacoes` (OK/PARCIAL/DUPLICADO/ERRO);
- logs em `logs/execucao.log` e na tabela `logs_execucao`;
- contagem de CNPJs por documento em `documentos_cda.qtd_cnpjs`.

## 8. Integração CVM — preenche os NOMES dos fundos investidos

O CDA traz só o **CNPJ** dos fundos investidos (cotas), não o nome. Para
preencher os nomes, rode:

```
python main.py enriquecer-cvm
```

Esse comando baixa **duas bases públicas da CVM** e cruza por CNPJ:

1. `registro_fundo.csv` (dentro de `registro_fundo_classe.zip`) — base da
   Resolução CVM 175, que cobre fundos **estruturados como FIDC**;
2. `cad_fi.csv` (conjunto completo) — usada como complemento.

Preenche nome/administrador/gestor/classe dos fundos monitorados e, principal
para a análise de concorrentes, **os nomes dos FIDCs investidos**. É seguro
rodar quantas vezes quiser (idempotente) e depende de internet. Sem rede, o MVP
continua funcionando com o que foi extraído dos CDAs — só fica sem os nomes.

> Depois de rodar o `enriquecer-cvm`, atualize a página do dashboard (F5) que os
> nomes aparecem na coluna `nome_ativo`.

## 9. Roadmap

- **Fase 1 (este MVP):** cadastro manual, download manual, importação local,
  parser, SQLite, dashboard.
- **Fase 2:** integração CVM (PL histórico, rentabilidade, cadastro oficial).
- **Fase 3:** automação do Fundos.NET (download incremental, faltantes).
- **Fase 4:** analytics (exposição cruzada, concentração, alertas automáticos).
- **Fase 5:** produção (PostgreSQL, agendamento, autenticação, testes).

---

## ✅ Checklist para testar o MVP

1. `pip install -r requirements.txt`
2. Editar `config/fundos_monitorados.csv` com suas gestoras e fundos.
3. Baixar alguns CDAs no Fundos.NET.
4. Colocar cada arquivo em `data/import/<Gestora>/<CNPJ_fundo>/<aaaa-mm>/`.
5. `python main.py init-db`
6. `python main.py import-cadastro`
7. `python main.py import-cdas`
8. `python main.py status` (confirme documentos e CNPJs)
9. `streamlit run dashboard/app.py`
10. Validar na página "Carteira por fundo" se os CNPJs investidos aparecem.

> Dica: o projeto já vem com um XML de exemplo em
> `data/import/GestoraExemplo/57811727000176/2026-05/`. Basta rodar os passos
> 5 a 9 para ver o pipeline funcionando de imediato.

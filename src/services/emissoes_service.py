#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robô CVM - Ofertas públicas de Cotas de FIDC.

Baixa o conjunto de dados abertos oficial da CVM (atualizado diariamente),
filtra as ofertas de Cotas de FIDC e devolve o Emissor e a(s) data(s).

Fonte: https://dados.cvm.gov.br/dataset/oferta-distrib
Não depende da tela (SPA) https://web.cvm.gov.br/sre-publico-cvm/ -> muito mais estável.
"""

import io
import sys
import unicodedata
import zipfile
from datetime import datetime

import pandas as pd
import requests

ZIP_URL = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"

# Termos que identificam um FIDC. Comparação é feita sem acento e em minúsculas.
TERMOS_FIDC = [
    "fidc",
    "direitos creditorios",          # "Direitos Creditórios"
    "investimento em direitos",      # variações do nome por extenso
]

# ----- Filtro de período -----
DIAS = 30  # traz apenas ofertas dos últimos N dias

# Qual data usar como referência para o filtro de período.
# A CVM traz mais de uma data por oferta; escolhemos a primeira coluna de data
# cujo nome contenha um destes termos (na ordem abaixo). Ajuste se quiser outra.
PREFERENCIA_DATA = ["inicio", "concess", "registro", "requerimento", "protocolo", "comunicado"]


def _sem_acento(texto: str) -> str:
    """Normaliza para minúsculas e sem acento, para casar 'Creditórios' == 'creditorios'."""
    if not isinstance(texto, str):
        texto = "" if texto is None else str(texto)
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _csvs_de_zip_bytes(conteudo: bytes) -> dict:
    """Lê um zip (em bytes) e devolve {nome_arquivo: DataFrame} de cada CSV interno."""
    dfs = {}
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        for nome in z.namelist():
            if not nome.lower().endswith(".csv"):
                continue
            with z.open(nome) as f:
                # CSVs da CVM são ISO-8859-1 (latin-1) e separados por ';'
                df = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str, low_memory=False)
            dfs[nome] = df
            print(f"    -> {nome}: {len(df)} linhas, {len(df.columns)} colunas", file=sys.stderr)
    return dfs


def baixar_csvs(url: str = ZIP_URL) -> dict:
    """Baixa o .zip da CVM e devolve {nome_arquivo: DataFrame} de cada CSV interno."""
    print(f"[+] Baixando {url} ...", file=sys.stderr)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return _csvs_de_zip_bytes(resp.content)


def _to_dt(serie: pd.Series) -> pd.Series:
    """Converte para datetime. Tenta ISO (AAAA-MM-DD) e, no que falhar, dd/mm/aaaa."""
    d = pd.to_datetime(serie, errors="coerce", format="%Y-%m-%d")
    faltando = d.isna() & serie.notna()
    if faltando.any():
        d.loc[faltando] = pd.to_datetime(serie[faltando], errors="coerce", dayfirst=True)
    return d


def _escolhe_col_data(cols_data, arquivo):
    """Escolhe a coluna de data de referência conforme PREFERENCIA_DATA."""
    norm = {c: _sem_acento(c) for c in cols_data}
    for chave in PREFERENCIA_DATA:
        for original, n in norm.items():
            if chave in n:
                print(f"    [{arquivo}] data de referência: '{original}'", file=sys.stderr)
                return original
    if cols_data:
        print(f"    [{arquivo}] data de referência (fallback): '{cols_data[0]}'", file=sys.stderr)
        return cols_data[0]
    return None


def _detecta_coluna(colunas, *palavras_chave):
    """Retorna a primeira coluna cujo nome (sem acento/minúsculo) contém alguma palavra-chave."""
    norm = {c: _sem_acento(c) for c in colunas}
    for chave in palavras_chave:
        for original, n in norm.items():
            if chave in n:
                return original
    return None


def filtra_fidc(df: pd.DataFrame, arquivo: str) -> pd.DataFrame:
    """Filtra linhas de FIDC e normaliza a saída para [arquivo, emissor, tipo, data_*]."""
    colunas = list(df.columns)

    col_emissor = _detecta_coluna(colunas, "nome_emissor", "emissor", "denom")
    # colunas candidatas a conter "FIDC" / "Direitos Creditórios"
    col_tipo_fundo = _detecta_coluna(colunas, "tipo_fundo")
    col_valor_mob = _detecta_coluna(colunas, "valor_mobiliario", "tipo_ativo", "ativo", "titulo")
    cols_data = [c for c in colunas if "data" in _sem_acento(c)]

    # Monta uma máscara: a linha é FIDC se QUALQUER coluna candidata contiver um termo FIDC.
    colunas_busca = [c for c in (col_tipo_fundo, col_valor_mob) if c]
    if not colunas_busca:
        # fallback: procura em todas as colunas de texto
        colunas_busca = colunas

    mask = pd.Series(False, index=df.index)
    for c in colunas_busca:
        valores = df[c].map(_sem_acento)
        for termo in TERMOS_FIDC:
            mask |= valores.str.contains(termo, na=False)

    sel = df[mask].copy()
    if sel.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=sel.index)
    out["arquivo"] = arquivo
    out["emissor"] = sel[col_emissor] if col_emissor else "(coluna de emissor não encontrada)"
    if col_tipo_fundo:
        out["tipo_fundo"] = sel[col_tipo_fundo]
    if col_valor_mob:
        out["valor_mobiliario"] = sel[col_valor_mob]
    for c in cols_data:
        out[c] = sel[c]

    # data de referência (datetime) usada para o filtro de período
    col_ref = _escolhe_col_data(cols_data, arquivo)
    out["data_referencia"] = _to_dt(sel[col_ref]) if col_ref else pd.NaT

    return out.reset_index(drop=True)


# ============================================================================
#  Enriquecimento para a dashboard: detecção semântica + filtro completo
# ============================================================================

# Mapa: conceito -> termos de busca no nome da coluna (sem acento, minúsculo).
# A dashboard usa o que existir; campos ausentes simplesmente não aparecem.
CAMPOS_SEMANTICOS = {
    "emissor":          ["nome_emissor", "emissor", "denominacao", "denom"],
    "valor":            ["valor_total_oferta", "valor_oferta", "vl_total_oferta",
                         "valor_total", "vl_oferta", "montante"],
    "coordenador":      ["coordenador_lider", "coordenador", "lider_distribuicao"],
    "situacao":         ["situacao", "status"],
    "tipo_oferta":      ["tipo_oferta"],
    "tipo_fundo":       ["tipo_fundo"],
    "valor_mobiliario": ["valor_mobiliario", "tipo_ativo"],
    "modalidade":       ["modalidade_oferta", "modalidade_registro", "modalidade",
                         "rito"],
    "publico":          ["publico_alvo", "investidor", "publico"],
    "processo":         ["numero_processo", "nr_processo", "numero_registro",
                         "nr_registro"],
    "cnpj":             ["cnpj"],
    "emissao":          ["emissao", "numero_emissao", "num_emissao"],
    "administrador":    ["administrador", "administracao", "admin"],
    "gestor":           ["gestor", "gestora", "gestao"],
}


def detecta_campos(colunas) -> dict:
    """Mapeia conceito -> nome real da coluna (ou None) pelo nome da coluna."""
    norm = {c: _sem_acento(c) for c in colunas}
    campos = {}
    for conceito, termos in CAMPOS_SEMANTICOS.items():
        achou = None
        for termo in termos:
            for original, n in norm.items():
                # 'valor' não pode casar com 'valor_mobiliario'
                if conceito == "valor" and "mobiliario" in n:
                    continue
                if termo in n:
                    achou = original
                    break
            if achou:
                break
        campos[conceito] = achou
    return campos


def to_num(serie: pd.Series) -> pd.Series:
    """Converte texto monetário da CVM em número (trata vírgula decimal BR)."""
    def conv(x):
        if x is None:
            return None
        x = str(x).strip()
        if x == "" or x.lower() == "nan":
            return None
        if "," in x:  # formato brasileiro: 1.234.567,89
            x = x.replace(".", "").replace(",", ".")
        return x
    return pd.to_numeric(serie.map(conv), errors="coerce")


def formata_brl(valor) -> str:
    """Formata número como 'R$ 1.234.567' (sem centavos, separador BR)."""
    if valor is None or pd.isna(valor):
        return "—"
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


def formata_cnpj(valor) -> str:
    """Formata CNPJ como 00.000.000/0000-00 quando tiver 14 dígitos; senão devolve como veio."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    digitos = "".join(ch for ch in str(valor) if ch.isdigit())
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return str(valor).strip()


def resumo_numerico(df: pd.DataFrame) -> pd.DataFrame:
    """Para cada coluna, mede quantos valores são numéricos, quantos != 0 e a magnitude típica.

    Serve para descobrir, empiricamente, qual coluna realmente carrega o
    montante das ofertas (em vez de confiar só no nome da coluna).
    """
    linhas = []
    for c in df.columns:
        if c.startswith("_") or c == "data_referencia":
            continue
        num = to_num(df[c])
        n_ok = int(num.notna().sum())
        if n_ok == 0:
            continue
        nz = num[(num.notna()) & (num != 0)]
        n_nz = int(len(nz))
        exemplo = next((str(v) for v in df[c] if isinstance(v, str) and v.strip()), "")
        linhas.append({"coluna": c, "n_numerico": n_ok, "n_nao_zero": n_nz,
                       "mediana_nao_zero": float(nz.median()) if n_nz else 0.0,
                       "maximo": float(num.max(skipna=True)), "exemplo": exemplo})
    res = pd.DataFrame(linhas)
    if not res.empty:
        # ordena pelas que têm magnitude de "dinheiro" primeiro
        res = res.sort_values(["mediana_nao_zero", "maximo"], ascending=False).reset_index(drop=True)
    return res


# valor de oferta é grande; isto separa montante (milhões) de contagem (1, 2, 3...)
MAGNITUDE_MIN_VALOR = 10_000


def candidatas_valor(df: pd.DataFrame) -> list:
    """Colunas plausíveis como 'valor da oferta': têm dados != 0 e magnitude alta primeiro."""
    res = resumo_numerico(df)
    if res.empty:
        return []
    grandes = res[(res["n_nao_zero"] > 0) & (res["mediana_nao_zero"] >= MAGNITUDE_MIN_VALOR)]
    pequenas = res[(res["n_nao_zero"] > 0) & (res["mediana_nao_zero"] < MAGNITUDE_MIN_VALOR)]
    # grandes (prováveis valores) primeiro; pequenas ainda ficam disponíveis para escolha manual
    return list(grandes["coluna"]) + list(pequenas["coluna"])


def escolhe_valor_auto(df: pd.DataFrame, campos: dict = None):
    """Melhor palpite: coluna de magnitude alta (>= R$ 10 mil de mediana), nunca uma contagem."""
    res = resumo_numerico(df)
    grandes = res[(res["n_nao_zero"] > 0) & (res["mediana_nao_zero"] >= MAGNITUDE_MIN_VALOR)].copy()
    if grandes.empty:
        return None  # não há coluna com cara de montante no dado aberto

    def parece_dinheiro(c):
        n = _sem_acento(c)
        bom = any(t in n for t in ["valor", "montante", "total"])
        return bom and "mobiliario" not in n

    pref = grandes[grandes["coluna"].map(parece_dinheiro)]
    alvo = pref if not pref.empty else grandes
    return alvo.iloc[0]["coluna"]


def filtra_fidc_completo(df: pd.DataFrame, arquivo: str) -> pd.DataFrame:
    """Igual ao filtro FIDC, mas preserva TODAS as colunas originais.

    Acrescenta 'arquivo' e 'data_referencia' (datetime) para a dashboard.
    """
    colunas = list(df.columns)
    col_tipo_fundo = _detecta_coluna(colunas, "tipo_fundo")
    col_valor_mob = _detecta_coluna(colunas, "valor_mobiliario", "tipo_ativo", "ativo", "titulo")

    colunas_busca = [c for c in (col_tipo_fundo, col_valor_mob) if c] or colunas
    mask = pd.Series(False, index=df.index)
    for c in colunas_busca:
        valores = df[c].map(_sem_acento)
        for termo in TERMOS_FIDC:
            mask |= valores.str.contains(termo, na=False)

    sel = df[mask].copy()
    if sel.empty:
        return pd.DataFrame()

    sel.insert(0, "arquivo", arquivo)
    cols_data = [c for c in df.columns if "data" in _sem_acento(c)]
    col_ref = _escolhe_col_data(cols_data, arquivo)
    sel["data_referencia"] = _to_dt(sel[col_ref]) if col_ref else pd.NaT
    return sel.reset_index(drop=True)


def carrega_fidc_completo(url: str = ZIP_URL) -> pd.DataFrame:
    """Baixa o zip, filtra FIDC em todos os CSVs e une tudo (todas as colunas)."""
    return _monta_fidc(baixar_csvs(url))


def carrega_fidc_de_bytes(conteudo: bytes) -> pd.DataFrame:
    """Mesmo que carrega_fidc_completo, mas a partir de um zip já em memória (upload)."""
    return _monta_fidc(_csvs_de_zip_bytes(conteudo))


def _monta_fidc(dfs: dict) -> pd.DataFrame:
    partes = [filtra_fidc_completo(df, nome) for nome, df in dfs.items()]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame()
    # une os dois arquivos mesmo com colunas diferentes (colunas ausentes viram NaN)
    return pd.concat(partes, ignore_index=True).drop_duplicates()


# ============================================================================
#  Estado / novidades (para alertas e "novo desde a última visita")
# ============================================================================
import json
import os

ESTADO_PADRAO = "fidc_estado.json"


def chave_oferta(row, campos: dict) -> str:
    """Identificador estável de uma oferta (para detectar novidades)."""
    proc = campos.get("processo")
    if proc and pd.notna(row.get(proc)) and str(row.get(proc)).strip():
        return _sem_acento(str(row[proc]))
    emissor = campos.get("emissor")
    emi = _sem_acento(str(row.get(emissor, ""))) if emissor else ""
    data = row.get("data_referencia")
    data_txt = data.strftime("%Y-%m-%d") if pd.notna(data) else "s-data"
    return f"{emi}|{data_txt}"


def carrega_estado(caminho: str = ESTADO_PADRAO) -> set:
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                return set(json.load(f).get("vistas", []))
        except Exception:
            return set()
    return set()


def salva_estado(chaves: set, caminho: str = ESTADO_PADRAO) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"vistas": sorted(chaves),
                   "atualizado_em": datetime.now().isoformat(timespec="seconds")},
                  f, ensure_ascii=False, indent=2)


def enviar_webhook(url: str, texto: str) -> None:
    """Posta uma mensagem simples (Slack/Teams/Discord aceitam {'text': ...})."""
    try:
        requests.post(url, json={"text": texto}, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"[!] Falha ao enviar webhook: {e}", file=sys.stderr)


def monitorar(dias: int = 30, estado: str = ESTADO_PADRAO, webhook: str = None) -> pd.DataFrame:
    """Modo robô: baixa, detecta ofertas novas (não vistas) e (opcional) avisa via webhook."""
    base = carrega_fidc_completo()
    if base.empty:
        print("Nenhuma oferta de FIDC na base.", file=sys.stderr)
        return base

    campos = detecta_campos(base.columns)
    limite = pd.Timestamp.now().normalize() - pd.Timedelta(days=dias)
    janela = base[base["data_referencia"] >= limite].copy()
    janela["_chave"] = janela.apply(lambda r: chave_oferta(r, campos), axis=1)

    vistas = carrega_estado(estado)
    novas = janela[~janela["_chave"].isin(vistas)]

    if novas.empty:
        print(f"[=] Sem ofertas novas de FIDC nos últimos {dias} dias.", file=sys.stderr)
    else:
        print(f"[+] {len(novas)} oferta(s) nova(s) de FIDC:", file=sys.stderr)
        emi = campos.get("emissor")
        linhas = []
        for _, r in novas.iterrows():
            data = r["data_referencia"]
            data_txt = data.strftime("%d/%m/%Y") if pd.notna(data) else "s/data"
            nome = r.get(emi, "?") if emi else "?"
            valor = formata_brl(to_num(pd.Series([r.get(campos["valor"])]))[0]) if campos.get("valor") else ""
            linha = f"• {data_txt} — {nome} {('(' + valor + ')') if valor and valor != '—' else ''}".strip()
            print("   " + linha, file=sys.stderr)
            linhas.append(linha)
        if webhook:
            enviar_webhook(webhook, f"*Novas ofertas de FIDC ({len(novas)})*\n" + "\n".join(linhas))

    # atualiza estado com tudo que está na janela atual
    salva_estado(vistas | set(janela["_chave"]), estado)
    return novas


def main():
    dfs = baixar_csvs()
    partes = [filtra_fidc(df, nome) for nome, df in dfs.items()]
    partes = [p for p in partes if not p.empty]

    if not partes:
        print("Nenhuma oferta de FIDC encontrada.", file=sys.stderr)
        return

    resultado = pd.concat(partes, ignore_index=True)

    # Remove duplicatas (mesma oferta pode aparecer em mais de um recorte)
    resultado = resultado.drop_duplicates()

    # ----- Filtro: apenas os últimos DIAS dias -----
    limite = pd.Timestamp.now().normalize() - pd.Timedelta(days=DIAS)
    antes = len(resultado)
    resultado = resultado[resultado["data_referencia"] >= limite]
    resultado = resultado.sort_values("data_referencia", ascending=False).reset_index(drop=True)
    print(f"[+] Filtro últimos {DIAS} dias (a partir de {limite:%d/%m/%Y}): "
          f"{len(resultado)} de {antes} ofertas.", file=sys.stderr)

    if resultado.empty:
        print("Nenhuma oferta de FIDC nos últimos "
              f"{DIAS} dias.", file=sys.stderr)
        return

    # Salva e mostra
    saida = f"ofertas_fidc_{datetime.now():%Y%m%d}.csv"
    resultado.to_csv(saida, index=False, encoding="utf-8-sig")
    print(f"\n[+] {len(resultado)} ofertas de FIDC encontradas. Salvo em: {saida}\n", file=sys.stderr)

    # Exibe Emissor + data de referência no console
    for _, r in resultado.iterrows():
        data = r["data_referencia"]
        data_txt = data.strftime("%d/%m/%Y") if pd.notna(data) else "(sem data)"
        print(f"{data_txt}  |  {r['emissor']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Robô CVM - ofertas de FIDC")
    parser.add_argument("--monitorar", action="store_true",
                        help="modo robô: detecta apenas ofertas NOVAS e atualiza o estado")
    parser.add_argument("--dias", type=int, default=DIAS, help="janela em dias (padrão 30)")
    parser.add_argument("--webhook", default=None,
                        help="URL de webhook (Slack/Teams/Discord) para alerta de novidades")
    args = parser.parse_args()

    if args.monitorar:
        monitorar(dias=args.dias, webhook=args.webhook)
    else:
        main()

"""
Página "Emissões (CVM)" do app unificado Brave Asset.

Adaptado do dashboard standalone de Monitor de Ofertas de FIDC. Diferenças em
relação ao original:
  - é uma função render() chamada pelo app principal (não um app standalone);
  - não define set_page_config, CSS global nem tela de senha (o app unificado
    já cuida disso);
  - os filtros saem da barra lateral (ocupada pela navegação) para uma coluna
    interna à esquerda da própria página;
  - a paleta dos gráficos usa o tema escuro do app unificado.

A engine de dados vive em src/services/emissoes_service.py (cópia do
robo_fidc.py original), sem alterações.
"""
from __future__ import annotations

import io
import os

import pandas as pd
import streamlit as st

try:
    import plotly.express as px
    TEM_PLOTLY = True
except ImportError:
    TEM_PLOTLY = False

from src.services.emissoes_service import (
    ZIP_URL,
    carrega_fidc_completo,
    carrega_fidc_de_bytes,
    detecta_campos,
    formata_brl,
    formata_cnpj,
    to_num,
    resumo_numerico,
)

# caminho do estado de monitoramento (mesma pasta de assets)
_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
ESTADO = os.path.join(_ASSETS, "fidc_estado.json")


@st.cache_data(ttl=3600, show_spinner=False)
def _carregar_url():
    return carrega_fidc_completo(ZIP_URL)


@st.cache_data(show_spinner=False)
def _carregar_bytes(conteudo: bytes):
    return carrega_fidc_de_bytes(conteudo)


def render(cores: dict):
    """Desenha a página de Emissões. `cores` traz a paleta do tema do app
    unificado (COBRE, MARINHO, FUNDO, TEXTO, TEXTO_FRACO, BORDA)."""
    COBRE = cores["COBRE"]
    MARINHO = cores["MARINHO"]
    FUNDO = cores["FUNDO"]
    TEXTO = cores["TEXTO"]
    TEXTO_FRACO = cores["TEXTO_FRACO"]
    BORDA = cores["BORDA"]

    st.header("Emissões de FIDC (CVM)")
    st.caption("Ofertas públicas de cotas de FIDC — base de dados abertos da CVM "
               "(oferta_distribuicao.zip), atualizada diariamente. Cobre ofertas "
               "registradas/dispensadas e em rito automático (RCVM 160).")

    # ---- fonte de dados: upload opcional dentro da página -----------------
    with st.expander("Fonte de dados / opções", expanded=False):
        upload = st.file_uploader(
            "Usar zip baixado manualmente (opcional)", type=["zip"],
            help="Se a rede bloquear o site da CVM, baixe o oferta_distribuicao.zip "
                 "e solte aqui.", key="emissoes_upload")
        if st.button("🔄 Recarregar dados da CVM", key="emissoes_reload"):
            st.cache_data.clear()
            st.rerun()

    try:
        with st.spinner("Carregando dados da CVM…"):
            bruto = _carregar_bytes(upload.getvalue()) if upload else _carregar_url()
    except Exception as e:  # noqa: BLE001
        st.error(f"Não consegui baixar da CVM ({e}). "
                 "Baixe o zip em dados.cvm.gov.br e use o uploader acima.")
        return

    if bruto.empty:
        st.warning("Nenhuma oferta de FIDC encontrada na base.")
        return

    base = bruto.copy()
    campos = detecta_campos(base.columns)
    c_emissor = campos.get("emissor")
    agora = pd.Timestamp.now().normalize()

    COL_VALOR = "Valor_Total_Registrado"
    tem_valor = False
    if COL_VALOR in base.columns:
        base["_valor_num"] = to_num(base[COL_VALOR])
        tem_valor = base["_valor_num"].notna().any() and (base["_valor_num"].fillna(0) != 0).any()

    data_max = base["data_referencia"].max()
    st.caption(f"◆ {len(base)} ofertas de FIDC na base · "
               f"referência mais recente: "
               f"{data_max.strftime('%d/%m/%Y') if pd.notna(data_max) else '—'}")

    data_recente = base["data_referencia"].max()

    # ---- layout: filtros à esquerda | conteúdo à direita ------------------
    col_filtros, col_conteudo = st.columns([1, 4], gap="large")

    with col_filtros:
        st.markdown("##### Filtros")
        dias = st.slider("Período (últimos N dias)", 7, 365, 30, step=1,
                         key="emissoes_dias")
        busca = st.text_input("Buscar emissor", key="emissoes_busca").strip()

        sel_modalidade = None
        if campos.get("modalidade"):
            op = sorted(x for x in base[campos["modalidade"]].dropna().unique())
            if op:
                sel_modalidade = st.multiselect("Rito / modalidade", op,
                                                key="emissoes_modalidade")

        sel_tipofundo = None
        if campos.get("tipo_fundo"):
            op = sorted(x for x in base[campos["tipo_fundo"]].dropna().unique())
            if len(op) > 1:
                sel_tipofundo = st.multiselect("Tipo de fundo", op,
                                               key="emissoes_tipofundo")

        valor_min = 0
        if tem_valor:
            teto = int(base["_valor_num"].max())
            valor_min = st.slider("Valor mínimo da oferta (R$)", 0, teto, 0,
                                  step=max(1, teto // 100), key="emissoes_valormin")

    def filtros_nao_periodo(d):
        if busca and c_emissor:
            d = d[d[c_emissor].str.contains(busca, case=False, na=False)]
        if sel_modalidade:
            d = d[d[campos["modalidade"]].isin(sel_modalidade)]
        if sel_tipofundo:
            d = d[d[campos["tipo_fundo"]].isin(sel_tipofundo)]
        if valor_min:
            d = d[d["_valor_num"].fillna(0) >= valor_min]
        return d

    limite = agora - pd.Timedelta(days=dias)
    df = filtros_nao_periodo(base[base["data_referencia"] >= limite]).sort_values(
        "data_referencia", ascending=False).reset_index(drop=True)
    ant = filtros_nao_periodo(
        base[(base["data_referencia"] >= limite - pd.Timedelta(days=dias)) &
             (base["data_referencia"] < limite)])

    with col_conteudo:
        # ---- novidades (data mais recente) --------------------------------
        novas = base[base["data_referencia"] == data_recente].copy() \
            if pd.notna(data_recente) else base.iloc[0:0]
        if not novas.empty:
            linhas_novas = ""
            ordem = c_emissor if c_emissor else "data_referencia"
            for _, r in novas.sort_values(ordem).iterrows():
                nome = r.get(c_emissor, "?") if c_emissor else "?"
                val = (f" &nbsp;·&nbsp; {formata_brl(r['_valor_num'])}"
                       if tem_valor and pd.notna(r.get("_valor_num")) else "")
                linhas_novas += (f'<div style="padding:6px 0;border-bottom:1px solid '
                                 f'{BORDA};color:{TEXTO};">{nome}{val}</div>')
            data_txt = data_recente.strftime("%d/%m/%Y")
            st.markdown(
                f'<div style="border:1px solid {BORDA};border-left:3px solid {COBRE};'
                f'border-radius:6px;padding:16px 18px;margin-bottom:10px;'
                f'background:{MARINHO};">'
                f'<p style="font-family:Spectral,serif;font-size:1.1rem;margin:0 0 8px 0;'
                f'color:{TEXTO};">{len(novas)} oferta(s) novas em {data_txt}</p>'
                f'{linhas_novas}</div>', unsafe_allow_html=True)

        # ---- KPIs ---------------------------------------------------------
        n_novas = int((df["data_referencia"] == data_recente).sum()) if pd.notna(data_recente) else 0
        k = st.columns(4)
        k[0].metric("Ofertas no período", len(df), delta=f"{len(df) - len(ant):+d} vs. anterior")
        if c_emissor:
            k[1].metric("Emissores distintos", df[c_emissor].nunique())
        if tem_valor:
            vol, vol_ant = df["_valor_num"].sum(), ant["_valor_num"].sum()
            k[2].metric("Volume total", formata_brl(vol), delta=formata_brl(vol - vol_ant))
            k[3].metric("Ticket médio", formata_brl(df["_valor_num"].mean()))
        else:
            k[2].metric("Novas (data mais recente)", n_novas)

        if df.empty:
            st.info(f"Nenhuma oferta de FIDC nos últimos {dias} dias com esses filtros.")
            return

        st.divider()
        _abas(df, base, campos, c_emissor, tem_valor, dias, data_recente, cores)


def _abas(df, base, campos, c_emissor, tem_valor, dias, data_recente, cores):
    COBRE = cores["COBRE"]
    MARINHO = cores["MARINHO"]
    TEXTO = cores["TEXTO"]
    TEXTO_FRACO = cores["TEXTO_FRACO"]
    BORDA = cores["BORDA"]

    aba_of, aba_an, aba_diag = st.tabs(["Ofertas", "Análises", "Diagnóstico"])

    # ======================================================= aba OFERTAS
    with aba_of:
        vis = pd.DataFrame()
        vis["Novo"] = (df["data_referencia"] == data_recente).map({True: "🆕", False: ""})
        vis["Data"] = df["data_referencia"]
        if c_emissor:
            vis["Emissor"] = df[c_emissor]
        if campos.get("cnpj"):
            vis["CNPJ"] = df[campos["cnpj"]].map(formata_cnpj)
        if campos.get("emissao"):
            vis["Emissão"] = df[campos["emissao"]]
        if tem_valor:
            vis["Valor (R$)"] = df["_valor_num"].apply(
                lambda x: formata_brl(x) if pd.notna(x) else "—")
        for chave, titulo in [("coordenador", "Coordenador líder"),
                              ("administrador", "Administrador"), ("gestor", "Gestor"),
                              ("valor_mobiliario", "Valor mobiliário"),
                              ("modalidade", "Rito/modalidade"),
                              ("situacao", "Situação"), ("tipo_oferta", "Tipo de oferta"),
                              ("publico", "Público-alvo")]:
            if campos.get(chave):
                vis[titulo] = df[campos[chave]]
        vis["Arquivo"] = df["arquivo"]

        cfg = {"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
               "Novo": st.column_config.TextColumn("", width="small",
                                                   help="Oferta da data mais recente da base")}
        if "Emissão" in vis.columns:
            cfg["Emissão"] = st.column_config.TextColumn("Emissão", width="small")

        st.caption("Clique numa linha para ver os campos da oferta — ou busque no seletor abaixo.")
        ev_of = st.dataframe(vis, use_container_width=True, hide_index=True, column_config=cfg,
                             on_select="rerun", selection_mode="single-row", key="emissoes_ofertas_sel")

        sel_of = ev_of.selection.rows if ev_of and ev_of.selection else []
        idx_detalhe = None
        if c_emissor:
            rot = ["—"] + [
                f"{r['data_referencia'].strftime('%d/%m/%Y') if pd.notna(r['data_referencia']) else 's/data'}"
                f" — {r[c_emissor]}" for _, r in df.iterrows()]
            idx_padrao = sel_of[0] + 1 if sel_of else 0
            escolha = st.selectbox("Buscar / selecionar oferta", range(len(rot)),
                                   index=idx_padrao, format_func=lambda x: rot[x],
                                   key="emissoes_busca_oferta")
            if escolha > 0:
                idx_detalhe = escolha - 1
            elif sel_of:
                idx_detalhe = sel_of[0]

        if idx_detalhe is not None:
            nome_sel = df.iloc[idx_detalhe][c_emissor] if c_emissor else f"Oferta {idx_detalhe}"
            st.markdown(f"#### Detalhes — {nome_sel}")
            linha = df.iloc[idx_detalhe].drop(labels=[c for c in ["_valor_num"] if c in df.columns])
            det = linha.dropna().astype(str)
            det = det[det.str.strip() != ""]
            st.table(det.rename("valor").to_frame())

        exp = df.drop(columns=[c for c in ["_valor_num"] if c in df.columns])
        cols_baixar = st.columns(2)
        cols_baixar[0].download_button("⬇️ CSV", exp.to_csv(index=False).encode("utf-8-sig"),
                                       "ofertas_fidc.csv", "text/csv", use_container_width=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            vis.to_excel(w, index=False, sheet_name="Ofertas FIDC")
        cols_baixar[1].download_button("⬇️ Excel", buf.getvalue(), "ofertas_fidc.xlsx",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       use_container_width=True)

    # ======================================================= aba ANÁLISES
    with aba_an:
        if not TEM_PLOTLY:
            st.warning("Instale o Plotly para os gráficos: pip install plotly")
        else:
            PALETA = [COBRE, "#7CC3CC", "#D9A07C", "#586068", "#E8C4AC", "#9AA0A6"]
            FONTE = "Inter, Segoe UI, Arial, sans-serif"

            def estilo(fig):
                fig.update_layout(
                    font=dict(family=FONTE, color=TEXTO, size=13),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=10, b=10, l=10, r=10),
                    colorway=PALETA,
                    legend=dict(bgcolor="rgba(0,0,0,0)"),
                )
                fig.update_xaxes(gridcolor=BORDA, zerolinecolor=BORDA, color=TEXTO_FRACO)
                fig.update_yaxes(gridcolor=BORDA, zerolinecolor=BORDA, color=TEXTO_FRACO)
                return fig

            _MES_PT = {1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
                       7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez"}
            if dias <= 92:
                freq, titulo_x = "W-MON", "semana (início)"
                rotular = lambda d: d.strftime("%d/%m/%y")
            else:
                freq, titulo_x = "MS", "mês"
                rotular = lambda d: f"{_MES_PT[d.month]}/{d.year}"

            def agrega(col=None):
                g = df.dropna(subset=["data_referencia"]).groupby(
                    pd.Grouper(key="data_referencia", freq=freq))
                out = (g.size().reset_index(name="qtd") if col is None
                       else g[col].sum().reset_index().rename(columns={col: "qtd"}))
                out = out.sort_values("data_referencia")
                out["período"] = out["data_referencia"].map(rotular)
                return out

            def barra(out, ylab):
                fig = px.bar(out, x="período", y="qtd", labels={"qtd": ylab},
                            color_discrete_sequence=[COBRE])
                fig.update_xaxes(type="category", title=titulo_x)
                fig.update_layout(bargap=0.25)
                return estilo(fig)

            def barra_emissores(dados, xcol, xlab):
                fig = px.bar(dados, x=xcol, y=c_emissor, orientation="h",
                             labels={xcol: xlab, c_emissor: ""},
                             color_discrete_sequence=[COBRE])
                fig.update_layout(yaxis={"categoryorder": "total ascending"},
                                  height=max(320, len(dados) * 26))
                return estilo(fig)

            @st.dialog("Emissores da faixa", width="large")
            def abrir_faixa(faixa):
                nome, lo, hi = faixa
                sub = df[(df["_valor_num"] >= lo) & (df["_valor_num"] < hi)]
                st.markdown(f"**Faixa {nome}** · {len(sub)} emissão(ões)")
                if c_emissor and len(sub):
                    r = (sub.groupby(c_emissor)["_valor_num"].sum()
                            .sort_values(ascending=False).reset_index())
                    r.columns = [c_emissor, "valor"]
                    with st.container(height=460):
                        st.plotly_chart(barra_emissores(r, "valor", "volume (R$)"),
                                        use_container_width=True)
                else:
                    st.info("Sem emissores nesta faixa.")

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Ofertas por período")
                st.plotly_chart(barra(agrega(), "ofertas"), use_container_width=True)
                if tem_valor:
                    st.subheader("Volume por período (R$)")
                    st.plotly_chart(barra(agrega("_valor_num"), "volume (R$)"),
                                    use_container_width=True)
            with c2:
                if c_emissor:
                    st.subheader("Top emissores")
                    if tem_valor:
                        vmin = st.number_input(
                            "Volume mínimo do emissor (R$)", min_value=0, value=0,
                            step=10_000_000, format="%d", key="emissoes_vmin_emissor")
                        rank = (df.groupby(c_emissor)["_valor_num"].sum()
                                  .sort_values(ascending=False).reset_index())
                        rank.columns = [c_emissor, "valor"]
                        rank = rank[rank["valor"] >= vmin]
                        grafico = barra_emissores(rank, "valor", "volume (R$)")
                    else:
                        nmin = st.number_input(
                            "Mínimo de ofertas do emissor", min_value=0, value=0,
                            step=1, key="emissoes_nmin_emissor")
                        rank = df[c_emissor].value_counts().reset_index()
                        rank.columns = [c_emissor, "ofertas"]
                        rank = rank[rank["ofertas"] >= nmin]
                        grafico = barra_emissores(rank, "ofertas", "ofertas")
                    st.caption(f"{len(rank)} emissores — role para ver todos.")
                    with st.container(height=460):
                        st.plotly_chart(grafico, use_container_width=True)

                if tem_valor:
                    st.subheader("Emissões por faixa de tamanho")
                    FAIXAS = [("0–100 mi", 0, 100e6), ("100–300 mi", 100e6, 300e6),
                              ("300–500 mi", 300e6, 500e6), ("500 mi–1 bi", 500e6, 1e9),
                              ("+1 bi", 1e9, float("inf"))]
                    v = df["_valor_num"].fillna(-1)
                    tab_faixa = pd.DataFrame(
                        [{"Faixa": nome, "Nº de emissões": int(((v >= lo) & (v < hi)).sum())}
                         for nome, lo, hi in FAIXAS])
                    ev = st.dataframe(tab_faixa, hide_index=True, use_container_width=True,
                                      on_select="rerun", selection_mode="single-row",
                                      key="emissoes_faixa_sel")
                    st.caption("Clique numa faixa para ver os emissores dela.")
                    linhas_sel = ev.selection.rows if ev and ev.selection else []
                    if linhas_sel:
                        abrir_faixa(FAIXAS[linhas_sel[0]])

            cd1, cd2 = st.columns(2)
            if campos.get("modalidade"):
                with cd1:
                    st.subheader("Por rito/modalidade")
                    vc = df[campos["modalidade"]].value_counts().reset_index()
                    vc.columns = ["modalidade", "ofertas"]
                    fig = px.pie(vc, names="modalidade", values="ofertas", hole=0.55,
                                color_discrete_sequence=PALETA)
                    fig.update_traces(textfont=dict(family=FONTE))
                    st.plotly_chart(estilo(fig), use_container_width=True)
            if campos.get("situacao"):
                with cd2:
                    st.subheader("Por situação")
                    vc = df[campos["situacao"]].value_counts().reset_index()
                    vc.columns = ["situacao", "ofertas"]
                    fig = px.bar(vc, x="situacao", y="ofertas", labels={"situacao": ""},
                                color_discrete_sequence=[COBRE])
                    st.plotly_chart(estilo(fig), use_container_width=True)

    # ======================================================= aba DIAGNÓSTICO
    with aba_diag:
        st.subheader("Colunas que contêm valores numéricos")
        st.caption("Use isto para achar a coluna de valor certa: prefira a que tem mais "
                   "'n_nao_zero' e um 'maximo' coerente com tamanho de oferta.")
        rn = resumo_numerico(base)
        if rn.empty:
            st.write("Nenhuma coluna numérica encontrada.")
        else:
            st.dataframe(rn, use_container_width=True, hide_index=True)

        st.subheader("Mapeamento de campos detectado")
        st.table(pd.DataFrame([(k_, v if v else "— não encontrado —") for k_, v in campos.items()],
                              columns=["Conceito", "Coluna no arquivo da CVM"]))
        st.subheader("Todas as colunas disponíveis no arquivo")
        st.write(sorted(c for c in base.columns if not c.startswith("_")))

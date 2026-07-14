"""
Dashboard Streamlit — FIDC-CDA MVP.

Rode com:  streamlit run dashboard/app.py

Páginas:
  1. Visão geral da gestora
  2. Carteira por fundo
  3. Comparação mês a mês
  4. Exposição consolidada
  5. Alertas
"""
from __future__ import annotations

import sys
from pathlib import Path

# permite importar o pacote 'src' quando rodado via streamlit
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import base64  # noqa: E402
import html  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from PIL import Image  # noqa: E402

from config import settings  # noqa: E402
from src.services import carteira_service as svc  # noqa: E402
from src.utils.cnpj import formatar_cnpj  # noqa: E402

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_SHIELD = ASSETS_DIR / "logo_shield.png"
LOGO_HORIZONTAL = ASSETS_DIR / "logo_horizontal.png"


def _favicon():
    try:
        return Image.open(LOGO_SHIELD)
    except Exception:
        return "🅱️"


st.set_page_config(page_title="Brave Asset — FIDC", layout="wide", page_icon=_favicon())

# ---------------------------------------------------------------------------
# Identidade visual — Brave Asset (modo escuro, estilo terminal financeiro)
# ---------------------------------------------------------------------------
BRAVE_COBRE = "#C47C5A"      # Pantone 876 C — destaque/accent
BRAVE_MARINHO = "#1D252D"    # Pantone 433 C — fundo secundário/cards
BRAVE_FUNDO = "#12181F"      # fundo principal escuro
BRAVE_CINZA = "#F0F0F0"      # cinza claro da marca (usado com moderação no escuro)
BRAVE_TEXTO = "#E8EAED"      # texto claro
BRAVE_TEXTO_FRACO = "#8A93A0"
BRAVE_VERDE = "#3FB68C"      # positivo (variações)
BRAVE_VERMELHO = "#D9584F"   # negativo (variações)
BRAVE_BORDA = "#2A333D"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,300;0,400;0,600;0,700;1,400&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

    /* Títulos em Spectral (aproximação da identidade: Nimbus Sans não é uma
       fonte web gratuita, então o corpo de texto usa Inter, humanista de
       espírito parecido). Números tabulares em JetBrains Mono, para alinhar
       casas decimais como um terminal financeiro. */
    h1, h2, h3, .stApp [data-testid="stMarkdownContainer"] h1,
    .stApp [data-testid="stMarkdownContainer"] h2,
    .stApp [data-testid="stMarkdownContainer"] h3 {{
        font-family: 'Spectral', serif !important;
        color: {BRAVE_TEXTO} !important;
        font-weight: 600 !important;
    }}
    html, body, .stApp, [class*="css"] {{
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }}
    .stApp {{
        background-color: {BRAVE_FUNDO};
    }}

    /* ---- cabeçalho estilo terminal (logo + título + data de referência) --- */
    .brave-header {{
        display: flex; align-items: center; justify-content: space-between;
        padding: 14px 20px; margin: -1rem -1rem 1.2rem -1rem;
        background: linear-gradient(180deg, {BRAVE_MARINHO} 0%, {BRAVE_FUNDO} 100%);
        border-bottom: 1px solid {BRAVE_BORDA};
    }}
    .brave-header .brand {{ display: flex; align-items: center; gap: 12px; }}
    .brave-header .brand-badge {{
        width: 40px; height: 40px; display: flex; align-items: center;
        justify-content: center;
    }}
    .brave-header .brand-badge img {{
        width: 100%; height: 100%; object-fit: contain;
    }}
    .brave-header .brand-title {{ font-family: 'Spectral', serif; font-weight: 600;
        font-size: 1.15rem; color: {BRAVE_TEXTO}; line-height: 1.1; }}
    .brave-header .brand-sub {{ font-size: 0.7rem; letter-spacing: 0.12em;
        color: {BRAVE_COBRE}; text-transform: uppercase; }}
    .brave-header .ref-date {{ font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem; color: {BRAVE_TEXTO_FRACO}; }}

    /* ---- sidebar como barra de navegação com "pills" -------------------- */
    [data-testid="stSidebar"] {{
        background-color: {BRAVE_MARINHO};
        border-right: 1px solid {BRAVE_BORDA};
    }}
    [data-testid="stSidebar"] h1 {{
        font-size: 1.1rem !important; color: {BRAVE_TEXTO} !important;
    }}
    [data-testid="stSidebar"] [role="radiogroup"] label {{
        background-color: transparent;
        border-radius: 8px;
        padding: 9px 12px;
        margin-bottom: 4px;
        width: 100%;
        transition: background-color 0.15s ease;
    }}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {{
        background-color: rgba(196,124,90,0.12);
    }}
    [data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] {{
        background-color: {BRAVE_COBRE};
    }}

    /* ---- cards de métrica (estilo "ATIVOS MONITORADOS 1.224") ----------- */
    [data-testid="stMetric"] {{
        background-color: {BRAVE_MARINHO};
        border: 1px solid {BRAVE_BORDA};
        border-radius: 10px;
        padding: 14px 16px 10px 16px;
        overflow: hidden;
    }}
    [data-testid="stMetricValue"] {{
        color: {BRAVE_TEXTO} !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 500;
        font-size: clamp(1.05rem, 2.1vw, 1.55rem) !important;
        white-space: normal !important;
        overflow-wrap: break-word;
        line-height: 1.25 !important;
    }}
    [data-testid="stMetricValue"] div {{
        overflow: visible !important;
        text-overflow: clip !important;
        white-space: normal !important;
    }}
    [data-testid="stMetricLabel"] {{
        color: {BRAVE_TEXTO_FRACO} !important;
        font-size: 0.72rem !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }}

    /* ---- botões ----------------------------------------------------------- */
    .stButton>button, .stDownloadButton>button, .stFormSubmitButton>button {{
        border-radius: 6px;
        border: 1px solid {BRAVE_COBRE};
        background-color: transparent;
        color: {BRAVE_TEXTO};
    }}
    .stButton>button:hover, .stDownloadButton>button:hover {{
        border-color: {BRAVE_COBRE};
        background-color: {BRAVE_COBRE};
        color: {BRAVE_MARINHO};
    }}

    /* ---- tabelas / dataframes --------------------------------------------- */
    [data-testid="stDataFrame"] {{
        border: 1px solid {BRAVE_BORDA};
        border-radius: 8px;
        overflow: hidden;
    }}

    hr {{ border-color: {BRAVE_BORDA} !important; }}

    /* números positivos/negativos (usado via HTML nas tabelas de variação) */
    .brave-pos {{ color: {BRAVE_VERDE}; font-family: 'JetBrains Mono', monospace; }}
    .brave-neg {{ color: {BRAVE_VERMELHO}; font-family: 'JetBrains Mono', monospace; }}
</style>
""", unsafe_allow_html=True)

import datetime as _dt  # noqa: E402


def _img_b64(path: Path) -> str:
    try:
        return base64.b64encode(path.read_bytes()).decode()
    except Exception:
        return ""


_shield_b64 = _img_b64(LOGO_SHIELD)
_badge_html = (f'<img src="data:image/png;base64,{_shield_b64}" alt="Brave Asset" />'
              if _shield_b64 else "B")

st.markdown(f"""
<div class="brave-header">
    <div class="brand">
        <div class="brand-badge">{_badge_html}</div>
        <div>
            <div class="brand-title">Plataforma FIDC — Brave Asset</div>
            <div class="brand-sub">Inteligência competitiva</div>
        </div>
    </div>
    <div class="ref-date">Atualizado em: {_dt.date.today().strftime('%Y-%m-%d')}</div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Autenticação — tela de senha protegendo todo o app (CDA + Emissões)
# ---------------------------------------------------------------------------
SENHA_CORRETA = "Brave2026"

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    col_l, col_c, col_r = st.columns([1, 1.2, 1])
    with col_c:
        if LOGO_SHIELD.exists():
            st.image(str(LOGO_SHIELD), width=90)
        st.markdown("### Plataforma FIDC — Brave Asset")
        st.caption("Inteligência competitiva · acesso restrito")
        senha = st.text_input("Senha de acesso", type="password",
                              placeholder="Digite a senha…", key="senha_login")
        if st.button("Entrar", use_container_width=True):
            if senha == SENHA_CORRETA:
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()


def fmt_cnpj(c):
    return formatar_cnpj(c) or (c or "—")


def fmt_moeda(v):
    if v is None or pd.isna(v):
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render_chips(itens, cor="neutro"):
    """Renderiza uma lista de textos como "chips" (badges) coloridos, em vez
    de deixar o Streamlit exibir a lista Python crua como uma árvore JSON."""
    paleta = {
        "verde": (BRAVE_VERDE, "rgba(63,182,140,0.12)"),
        "vermelho": (BRAVE_VERMELHO, "rgba(217,88,79,0.12)"),
        "neutro": (BRAVE_TEXTO_FRACO, "rgba(138,147,160,0.12)"),
    }
    cor_txt, cor_bg = paleta.get(cor, paleta["neutro"])
    if not itens:
        st.markdown(
            f'<span style="color:{BRAVE_TEXTO_FRACO};font-size:0.85rem;">'
            f'Nenhum.</span>', unsafe_allow_html=True)
        return
    chips = "".join(
        f'<span style="display:inline-block; margin:3px 6px 3px 0; padding:4px 10px; '
        f'border-radius:14px; background:{cor_bg}; color:{cor_txt}; '
        f'font-family:\'JetBrains Mono\', monospace; font-size:0.82rem; '
        f'border:1px solid {cor_txt}33;">{html.escape(str(item))}</span>'
        for item in itens
    )
    st.markdown(f'<div>{chips}</div>', unsafe_allow_html=True)


if not Path(settings.DB_PATH).exists():
    st.error("Banco não encontrado. Rode primeiro:  `python main.py init-db` e `python main.py import-cdas`.")
    st.stop()

# garante a tabela de anotações manuais mesmo em bancos antigos
from src.database import garantir_tabela_anotacoes  # noqa: E402
garantir_tabela_anotacoes()

if LOGO_HORIZONTAL.exists():
    st.sidebar.image(str(LOGO_HORIZONTAL), use_container_width=True)
else:
    st.sidebar.title("FIDC-CDA MVP")
pagina = st.sidebar.radio(
    "Página",
    ["1 · Visão da gestora", "2 · Carteira por fundo",
     "3 · Comparação mês a mês", "4 · Exposição consolidada", "5 · Alertas",
     "6 · Rankings", "7 · Enviar CDA", "8 · Emissões (CVM)"],
)

gestoras = svc.listar_gestoras()


# ===========================================================================
# Página 1 — Inteligência competitiva por gestora
# ===========================================================================
if pagina.startswith("1"):
    st.header("Visão da gestora (concorrente)")
    st.caption(
        "Selecione uma gestora concorrente para ver os fundos dela que você já "
        "monitora (com CDA importado) e o que cada um carrega na carteira."
    )
    if gestoras.empty:
        st.info("Nenhuma gestora cadastrada. Rode `python main.py import-cadastro`.")
        st.stop()

    gestora = st.selectbox("Gestora", gestoras["nome"].tolist())
    resumo = svc.resumo_gestora(gestora)

    # ---- Big numbers da GESTORA (apenas fundos com CDA) -------------------
    st.subheader("Big numbers da gestora")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fundos com CDA", resumo["n_com_cda"])
    c2.metric("Meses disponíveis", len(resumo["meses"]))
    c3.metric("PL consolidado (últ. mês)", fmt_moeda(resumo["pl_total"]))
    c4.metric("CNPJs investidos (distintos)", resumo.get("n_cnpjs_investidos", 0))

    evo = svc.evolucao_pl(gestora)
    if not evo.empty and len(evo) > 1:
        st.caption("Evolução do PL consolidado da gestora")
        import plotly.graph_objects as go

        evo_plot = evo.sort_values("competencia")
        fig_evo = go.Figure()
        fig_evo.add_trace(go.Scatter(
            x=evo_plot["competencia"], y=evo_plot["pl_total"],
            mode="lines+markers",
            line=dict(color=BRAVE_COBRE, width=2.5, shape="spline", smoothing=0.3),
            marker=dict(color=BRAVE_COBRE, size=7, line=dict(color=BRAVE_FUNDO, width=1.5)),
            fill="tozeroy", fillcolor="rgba(196,124,90,0.12)",
            hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>",
        ))
        fig_evo.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, Segoe UI, Arial", size=12, color=BRAVE_TEXTO),
            xaxis=dict(showgrid=False, color=BRAVE_TEXTO_FRACO,
                      linecolor=BRAVE_BORDA, type="category"),
            yaxis=dict(showgrid=True, gridcolor=BRAVE_BORDA, zeroline=False,
                      color=BRAVE_TEXTO_FRACO, tickformat=",.0f"),
            hovermode="x unified",
        )
        st.plotly_chart(fig_evo, use_container_width=True, config={"displayModeBar": False})

    # ---- Fundos com CDA + posição de cada um -----------------------------
    st.divider()
    fundos_cda = svc.fundos_com_cda(gestora)

    if fundos_cda.empty:
        st.warning(
            "Esta gestora ainda não tem nenhum fundo com CDA importado. "
            "Coloque o arquivo em `data/import/<gestora>/<cnpj>/<aaaa-mm>/` e "
            "rode `python main.py import-cdas`."
        )
        st.stop()

    st.subheader(f"Fundos monitorados com CDA ({len(fundos_cda)})")

    for _, frow in fundos_cda.iterrows():
        fundo_cnpj = frow["cnpj"]
        titulo = f"{frow['nome'] or '(sem nome)'} — {fmt_cnpj(fundo_cnpj)}"
        with st.expander(titulo, expanded=(len(fundos_cda) == 1)):
            comps = svc.competencias_disponiveis(fundo_cnpj)
            comp = st.selectbox(
                "Mês (competência)", comps, key=f"comp_{fundo_cnpj}"
            )

            rf = svc.resumo_fundo(fundo_cnpj, comp)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("PL do fundo", fmt_moeda(rf["pl"]))
            m2.metric("Posições", rf["n_posicoes"])
            m3.metric("CNPJs investidos", rf["n_cnpjs"])
            top_txt = f"{rf['top_pct']:.2f}%" if rf["top_pct"] is not None else "—"
            m4.metric("Maior posição", top_txt)
            if rf["top_cnpj"] or rf["top_nome"]:
                if rf["top_nome"]:
                    alvo = f"{rf['top_nome']} ({fmt_cnpj(rf['top_cnpj'])})"
                else:
                    alvo = fmt_cnpj(rf["top_cnpj"])
                st.caption(f"Maior exposição: {alvo}")

            df = svc.carteira(fundo_cnpj, comp)
            n_sem_nome = int(df["nome_ativo"].isna().sum())
            if n_sem_nome:
                st.caption(
                    f"ℹ️ {n_sem_nome} ativo(s) sem nome. Rode "
                    "`python main.py enriquecer-cvm` para buscar os nomes na CVM."
                )
            df_show = df.copy()
            df_show["nome_ativo"] = df_show["nome_ativo"].fillna("—")
            df_show["cnpj_investido"] = df_show["cnpj_investido"].map(fmt_cnpj)
            df_show["valor_financeiro"] = df_show["valor_financeiro"].map(fmt_moeda)
            df_show["percentual"] = df_show["percentual"].map(
                lambda x: f"{x:.2f}%" if pd.notna(x) else "—")
            st.dataframe(df_show, use_container_width=True, hide_index=True)

            e1, e2 = st.columns(2)
            e1.download_button(
                "Exportar CSV", svc.exportar_csv(df),
                file_name=f"carteira_{fundo_cnpj}_{comp}.csv", mime="text/csv",
                key=f"csv_{fundo_cnpj}")
            e2.download_button(
                "Exportar Excel", svc.exportar_excel(df),
                file_name=f"carteira_{fundo_cnpj}_{comp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"xlsx_{fundo_cnpj}")


# ===========================================================================
# Página 2 — Carteira por fundo
# ===========================================================================
elif pagina.startswith("2"):
    st.header("Carteira por fundo")
    if gestoras.empty:
        st.info("Cadastre gestoras/fundos primeiro.")
        st.stop()

    gestora = st.selectbox("Gestora", gestoras["nome"].tolist())
    fundos = svc.listar_fundos(gestora)
    if fundos.empty:
        st.info("Nenhum fundo para esta gestora.")
        st.stop()

    rotulos = {f"{r['nome'] or '(sem nome)'} — {fmt_cnpj(r['cnpj'])}": r["cnpj"]
               for _, r in fundos.iterrows()}
    escolha = st.selectbox("Fundo", list(rotulos.keys()))
    fundo_cnpj = rotulos[escolha]

    comps = svc.competencias_disponiveis(fundo_cnpj)
    if not comps:
        st.warning("Este fundo ainda não tem CDA importado.")
        st.stop()
    comp = st.selectbox("Mês (competência)", comps)

    df = svc.carteira(fundo_cnpj, comp)
    st.caption(f"{len(df)} posições • {df['cnpj_investido'].nunique()} CNPJs investidos")

    # ---- Gráfico de rosca: top 15 posições por % do PL + "Outros" ----------
    st.subheader("Top 15 posições — % do PL")
    dfg = df.dropna(subset=["percentual"]).copy()
    if dfg.empty:
        st.caption("Sem percentual calculado para montar o gráfico.")
    else:
        dfg["rotulo"] = dfg["nome_ativo"].fillna(dfg["cnpj_investido"].map(fmt_cnpj))
        dfg["rotulo"] = dfg["rotulo"].fillna(dfg["tipo_ativo"]).fillna("(sem identificação)")
        dfg = dfg.sort_values("percentual", ascending=False)

        top15 = dfg.head(15)[["rotulo", "percentual"]].copy()
        resto_pct = dfg.iloc[15:]["percentual"].sum()
        n_outros = len(dfg) - len(top15)
        partes = [top15]
        if resto_pct > 0 and n_outros > 0:
            partes.append(pd.DataFrame(
                [{"rotulo": f"Outros ({n_outros})", "percentual": resto_pct}]))
        rosca = pd.concat(partes, ignore_index=True)

        try:
            import plotly.graph_objects as go

            # paleta profissional: degradê contínuo de azul-marinho (maior
            # posição) até ciano claro (menor), sempre com N tons ÚNICOS —
            # nunca repete cor mesmo com mais de 10 posições. "Outros" fica
            # em cinza neutro, propositalmente sem competir com as posições.
            n_posicoes = len(top15)

            def _interp_hex(c1, c2, t):
                r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
                r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
                r = round(r1 + (r2 - r1) * t)
                g = round(g1 + (g2 - g1) * t)
                b = round(b1 + (b2 - b1) * t)
                return f"#{r:02X}{g:02X}{b:02X}"

            # Paleta da identidade Brave Asset: degradê do azul-marinho da marca
            # (posição maior) até o cobre da marca (posição menor); "Outros" no
            # cinza claro da marca.
            AZUL_MARINHO, COBRE = BRAVE_MARINHO, BRAVE_COBRE
            if n_posicoes <= 1:
                cores_pos = [AZUL_MARINHO]
            else:
                cores_pos = [_interp_hex(AZUL_MARINHO, COBRE, i / (n_posicoes - 1))
                            for i in range(n_posicoes)]
            cores = cores_pos + (["#4A5561"] if n_outros > 0 else [])  # cinza médio, visível no escuro

            # rótulo truncado para não poluir a legenda; nome completo no hover
            def _trunc(s, n=42):
                s = str(s)
                return s if len(s) <= n else s[: n - 1] + "…"

            rosca["rotulo_curto"] = rosca["rotulo"].map(_trunc)
            rosca["legenda"] = rosca["rotulo_curto"] + "  —  " + \
                rosca["percentual"].map(lambda x: f"{x:.1f}%".replace(".", ","))

            # só rotula na fatia quem tem tamanho visual suficiente (>=3%)
            rosca["texto_fatia"] = rosca["percentual"].map(
                lambda x: f"{x:.1f}%".replace(".", ",") if x >= 3 else "")

            fig = go.Figure(data=[go.Pie(
                labels=rosca["legenda"], values=rosca["percentual"],
                text=rosca["texto_fatia"], textinfo="text",
                customdata=rosca["rotulo"],
                hovertemplate="<b>%{customdata}</b><br>%{value:.2f}% do PL<extra></extra>",
                hole=0.62, sort=False, direction="clockwise", rotation=90,
                marker=dict(colors=cores, line=dict(color="#12181F", width=2)),
                textfont=dict(size=13, color="#FFFFFF", family="Inter, Segoe UI, Arial"),
                insidetextorientation="horizontal",  # evita texto inclinado ("torto")
                pull=[0.02 if i < 3 else 0 for i in range(len(rosca))],
            )])

            pl_fundo = svc.resumo_fundo(fundo_cnpj, comp).get("pl")
            fig.update_layout(
                height=520,
                margin=dict(l=10, r=10, t=10, b=10),
                font=dict(family="Inter, Segoe UI, Arial", size=12, color=BRAVE_TEXTO),
                legend=dict(
                    orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02,
                    font=dict(size=11), itemsizing="constant", traceorder="normal",
                ),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                annotations=[dict(
                    text=(f"<b>{len(dfg)}</b> posições<br>"
                          f"<span style='font-size:12px;color:{BRAVE_TEXTO_FRACO}'>"
                          f"{fmt_moeda(pl_fundo) if pl_fundo else ''}</span>"),
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(size=16, color=BRAVE_TEXTO, family="Spectral, serif"),
                )],
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        except ImportError:
            st.warning(
                "Para ver o gráfico de rosca, instale o plotly: "
                "`pip install plotly` (ou `pip install -r requirements.txt`)."
            )
            rosca_show = rosca.copy()
            rosca_show["percentual"] = rosca_show["percentual"].map(lambda x: f"{x:.2f}%")
            st.dataframe(rosca_show[["rotulo", "percentual"]],
                        use_container_width=True, hide_index=True)

    st.divider()
    st.info(
        "✏️ As colunas **Classe** e **Observação** são suas: edite direto na "
        "tabela. Elas são salvas por CNPJ investido e valem para todos os "
        "fundos e meses. Clique em **Salvar anotações** ao terminar.",
        icon="✏️",
    )

    # monta a tabela editável — só Classe e Observação são editáveis
    edit_df = df.copy()
    edit_df["cnpj_fmt"] = edit_df["cnpj_investido"].map(fmt_cnpj)
    edit_df["valor_fmt"] = edit_df["valor_financeiro"].map(fmt_moeda)
    edit_df["pct_fmt"] = edit_df["percentual"].map(
        lambda x: f"{x:.2f}%" if pd.notna(x) else "—")
    edit_df["nome_ativo"] = edit_df["nome_ativo"].fillna("—")
    # garante que as colunas editáveis sejam texto puro (evita travas por dtype)
    edit_df["classe_manual"] = edit_df["classe_manual"].fillna("").astype(str)
    edit_df["observacao"] = edit_df["observacao"].fillna("").astype(str)

    vis = edit_df[[
        "cnpj_fmt", "nome_ativo", "tipo_ativo", "valor_fmt", "pct_fmt",
        "quantidade", "empresa_ligada", "classe_manual", "observacao",
    ]].rename(columns={
        "cnpj_fmt": "CNPJ investido", "nome_ativo": "Nome do ativo",
        "tipo_ativo": "Tipo", "valor_fmt": "Valor financeiro",
        "pct_fmt": "% carteira", "quantidade": "Quantidade",
        "empresa_ligada": "Ligada", "classe_manual": "Classe",
        "observacao": "Observação",
    })

    # colunas travadas = todas menos Classe e Observação
    travadas = ["CNPJ investido", "Nome do ativo", "Tipo", "Valor financeiro",
                "% carteira", "Quantidade", "Ligada"]

    # column_config só é usado se a versão do Streamlit suportar (>=1.23)
    kwargs = dict(use_container_width=True, hide_index=True,
                  disabled=travadas, key=f"editor_{fundo_cnpj}_{comp}")
    if hasattr(st, "column_config") and hasattr(st.column_config, "TextColumn"):
        kwargs["column_config"] = {
            "Classe": st.column_config.TextColumn(
                "Classe", help="Preencha como quiser (ex.: Sênior, Mezanino, "
                "Subordinada, Multi...). Vale para este CNPJ em todos os fundos."),
            "Observação": st.column_config.TextColumn(
                "Observação", help="Anotação livre sobre este ativo/CNPJ."),
        }

    try:
        editado = st.data_editor(vis, **kwargs)
    except TypeError:
        # versões antigas do Streamlit: sem 'disabled'/'column_config'.
        # Edita numa tabela reduzida (só as 3 colunas necessárias).
        st.caption("Editando em modo compatível (Streamlit antigo). "
                   "Recomendo atualizar: pip install -U streamlit")
        reduzida = edit_df[["cnpj_fmt", "nome_ativo", "classe_manual", "observacao"]].rename(
            columns={"cnpj_fmt": "CNPJ investido", "nome_ativo": "Nome do ativo",
                     "classe_manual": "Classe", "observacao": "Observação"})
        editado_r = st.data_editor(reduzida, use_container_width=True,
                                   hide_index=True, key=f"editor2_{fundo_cnpj}_{comp}")
        # reconstrói o formato esperado pelo bloco de salvar
        editado = vis.copy()
        editado["Classe"] = editado_r["Classe"].values
        editado["Observação"] = editado_r["Observação"].values

    if st.button("💾 Salvar anotações", key=f"save_{fundo_cnpj}_{comp}"):
        cnpjs = edit_df["cnpj_investido"].tolist()
        n = 0
        for cnpj, classe_nova, obs_nova in zip(
                cnpjs, editado["Classe"].tolist(), editado["Observação"].tolist()):
            if not cnpj:
                continue  # posições sem CNPJ não recebem anotação
            svc.salvar_anotacao(cnpj, classe_nova, obs_nova)
            n += 1
        st.success(f"Anotações salvas para {n} CNPJ(s). "
                   "Elas aparecerão em qualquer fundo/mês que tenha esses CNPJs.")

    # exportações incluem as anotações (recarrega do banco para refletir o salvo)
    df_export = svc.carteira(fundo_cnpj, comp)
    col1, col2 = st.columns(2)
    col1.download_button("Exportar CSV", svc.exportar_csv(df_export),
                         file_name=f"carteira_{fundo_cnpj}_{comp}.csv", mime="text/csv")
    col2.download_button("Exportar Excel", svc.exportar_excel(df_export),
                         file_name=f"carteira_{fundo_cnpj}_{comp}.xlsx",
                         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ===========================================================================
# Página 3 — Comparação mês a mês
# ===========================================================================
elif pagina.startswith("3"):
    st.header("Comparação mês a mês")
    fundos = svc.listar_fundos()
    if fundos.empty:
        st.info("Cadastre fundos primeiro.")
        st.stop()

    rotulos = {f"{r['nome'] or '(sem nome)'} — {fmt_cnpj(r['cnpj'])}": r["cnpj"]
               for _, r in fundos.iterrows()}
    escolha = st.selectbox("Fundo", list(rotulos.keys()))
    fundo_cnpj = rotulos[escolha]

    comps = svc.competencias_disponiveis(fundo_cnpj)
    if len(comps) < 2:
        st.warning("São necessários pelo menos 2 meses importados para comparar.")
        st.stop()

    c1, c2 = st.columns(2)
    comp_atual = c1.selectbox("Mês atual", comps, index=0)
    comp_ant = c2.selectbox("Mês anterior", comps, index=1)

    r = svc.comparar_meses(fundo_cnpj, comp_atual, comp_ant)
    a, b, c = st.columns(3)
    a.metric("Entraram", len(r["entraram"]))
    b.metric("Saíram", len(r["sairam"]))
    c.metric("Permaneceram", len(r["permaneceram"]))

    def _rotulo_chip(item):
        cnpj_fmt = fmt_cnpj(item["cnpj"])
        return f"{cnpj_fmt} — {item['nome']}" if item.get("nome") else cnpj_fmt

    st.subheader("CNPJs que entraram")
    render_chips([_rotulo_chip(x) for x in r["entraram"]], cor="verde")
    st.subheader("CNPJs que saíram")
    render_chips([_rotulo_chip(x) for x in r["sairam"]], cor="vermelho")

    st.subheader("Variação de exposição (permaneceram)")
    var = r["variacoes"]
    if var.empty:
        st.caption("Sem dados de variação.")
    else:
        var = var.copy()
        var["cnpj_investido"] = var["cnpj_investido"].map(fmt_cnpj)

        def _cor_variacao(v):
            if pd.isna(v):
                return ""
            cor = BRAVE_VERDE if v > 0 else (BRAVE_VERMELHO if v < 0 else BRAVE_TEXTO_FRACO)
            return f"color: {cor}; font-family: 'JetBrains Mono', monospace;"

        estilo = var.style
        # Styler.map (pandas >= 2.1) substituiu applymap (removido em versões
        # mais novas); tenta o novo primeiro, cai para o antigo se necessário.
        if hasattr(estilo, "map"):
            estilo = estilo.map(_cor_variacao, subset=["delta_pct"])
        else:
            estilo = estilo.applymap(_cor_variacao, subset=["delta_pct"])
        estilo = estilo.format(
            {"pct_anterior": "{:.2f}%", "pct_atual": "{:.2f}%",
             "delta_pct": "{:+.2f} p.p.", "valor_anterior": "R$ {:,.2f}",
             "valor_atual": "R$ {:,.2f}"}, na_rep="—")
        st.dataframe(estilo, use_container_width=True)


# ===========================================================================
# Página 4 — Exposição consolidada
# ===========================================================================
elif pagina.startswith("4"):
    st.header("Exposição consolidada")
    opcoes_g = ["(todas)"] + gestoras["nome"].tolist()
    gestora = st.selectbox("Gestora", opcoes_g)
    gestora_f = None if gestora == "(todas)" else gestora

    todas_comps = svc.competencias_disponiveis()
    comp = st.selectbox("Competência", ["(todas)"] + todas_comps)
    comp_f = None if comp == "(todas)" else comp

    df = svc.exposicao_consolidada(gestora_f, comp_f)
    if df.empty:
        st.info("Sem dados. Importe CDAs primeiro.")
        st.stop()

    st.subheader("Ranking de CNPJs mais recorrentes")
    st.caption("Quantos fundos investem no mesmo CNPJ e valor total consolidado.")
    df_show = df.copy()
    df_show["cnpj_investido"] = df_show["cnpj_investido"].map(fmt_cnpj)
    df_show["fundos"] = df_show["fundos"].map(
        lambda s: ", ".join(fmt_cnpj(x) for x in str(s).split(",")) if s else "")
    df_show["valor_total"] = df_show["valor_total"].map(fmt_moeda)
    st.dataframe(df_show, use_container_width=True)

    st.download_button("Exportar consolidado (CSV)", svc.exportar_csv(df),
                       file_name="exposicao_consolidada.csv", mime="text/csv")


# ===========================================================================
# Página 5 — Alertas
# ===========================================================================
elif pagina.startswith("5"):
    st.header("Alertas")
    limite = st.slider("Limite de concentração por CNPJ (%)", 5.0, 50.0,
                       settings.LIMITE_CONCENTRACAO_PADRAO, 1.0)
    opcoes_g = ["(todas)"] + gestoras["nome"].tolist()
    gestora = st.selectbox("Gestora", opcoes_g)
    gestora_f = None if gestora == "(todas)" else gestora

    al = svc.alertas(gestora_f, limite_concentracao=limite)

    st.subheader("Fundos cadastrados sem CDA importado")
    df = al["fundos_sem_cda"]
    if not df.empty:
        df = df.copy(); df["cnpj"] = df["cnpj"].map(fmt_cnpj)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.success("Nenhum.")

    st.subheader("Importações com erro / parcial / duplicadas")
    if not al["importacoes_erro"].empty:
        st.dataframe(al["importacoes_erro"], use_container_width=True)
    else:
        st.success("Nenhuma.")

    st.subheader(f"Concentração ≥ {limite:.0f}% em um único CNPJ")
    conc = al["concentracao"]
    if not conc.empty:
        conc = conc.copy()
        conc["fundo_cnpj"] = conc["fundo_cnpj"].map(fmt_cnpj)
        conc["cnpj_investido"] = conc["cnpj_investido"].map(fmt_cnpj)
        conc["percentual"] = conc["percentual"].map(lambda x: f"{x:.2f}%")
        st.dataframe(conc, use_container_width=True)
    else:
        st.success("Nenhuma concentração acima do limite.")


# ===========================================================================
# Página 6 — Rankings (visão consolidada dos concorrentes)
# ===========================================================================
elif pagina.startswith("6"):
    st.header("Rankings")
    st.caption("Visão consolidada dos fundos concorrentes que você monitora "
               "(apenas fundos com CDA importado).")

    opcoes_g = ["(todas)"] + gestoras["nome"].tolist()
    gestora = st.selectbox("Gestora", opcoes_g, key="rk_gestora")
    gestora_f = None if gestora == "(todas)" else gestora

    try:
        import plotly.express as px
        _TEM_PLOTLY = True
    except ImportError:
        _TEM_PLOTLY = False

    aba1, aba2, aba3, aba4 = st.tabs(
        ["Maiores fundos por PL", "Gestoras por PL",
         "Maiores concentrações", "CNPJs recorrentes"])

    # ---- Maiores fundos por PL -------------------------------------------
    with aba1:
        df = svc.ranking_fundos_por_pl(gestora_f)
        if df.empty:
            st.info("Nenhum fundo com CDA importado ainda.")
        else:
            top = df.head(15).dropna(subset=["pl"]).copy()
            if _TEM_PLOTLY and not top.empty:
                top_plot = top.sort_values("pl")
                top_plot["rotulo"] = top_plot["nome"].fillna(top_plot["cnpj"])
                fig = px.bar(top_plot, x="pl", y="rotulo", orientation="h",
                             labels={"pl": "PL (R$)", "rotulo": ""},
                             color="pl", color_continuous_scale=["#3A4753", BRAVE_COBRE])
                fig.update_layout(height=480, coloraxis_showscale=False,
                                  margin=dict(l=10, r=10, t=10, b=10),
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font=dict(family="Inter, Segoe UI, Arial", color=BRAVE_TEXTO))
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})
            tbl = df.copy()
            tbl["cnpj"] = tbl["cnpj"].map(fmt_cnpj)
            tbl["pl"] = tbl["pl"].map(fmt_moeda)
            tbl = tbl.rename(columns={"nome": "Fundo", "cnpj": "CNPJ",
                                      "gestora": "Gestora", "pl": "PL",
                                      "ultima_competencia": "Últ. competência"})
            st.dataframe(tbl, use_container_width=True, hide_index=True)
            st.download_button("Exportar CSV", svc.exportar_csv(df),
                               file_name="ranking_fundos_pl.csv", mime="text/csv")

    # ---- Gestoras por PL --------------------------------------------------
    with aba2:
        dg = svc.ranking_gestoras_por_pl()
        if dg.empty:
            st.info("Sem dados ainda.")
        else:
            if _TEM_PLOTLY:
                dgp = dg.sort_values("pl_total")
                fig = px.bar(dgp, x="pl_total", y="gestora", orientation="h",
                             labels={"pl_total": "PL total (R$)", "gestora": ""},
                             color="pl_total", color_continuous_scale=["#3A4753", BRAVE_COBRE])
                fig.update_layout(height=420, coloraxis_showscale=False,
                                  margin=dict(l=10, r=10, t=10, b=10),
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font=dict(family="Inter, Segoe UI, Arial", color=BRAVE_TEXTO))
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})
            tbl = dg.copy()
            tbl["pl_total"] = tbl["pl_total"].map(fmt_moeda)
            tbl = tbl.rename(columns={"gestora": "Gestora", "n_fundos": "Nº fundos",
                                      "pl_total": "PL total"})
            st.dataframe(tbl, use_container_width=True, hide_index=True)

    # ---- Maiores concentrações -------------------------------------------
    with aba3:
        dc = svc.ranking_maiores_concentracoes(gestora_f)
        if dc.empty:
            st.info("Sem dados de concentração ainda.")
        else:
            tbl = dc.head(30).copy()
            tbl["fundo_cnpj"] = tbl["fundo_cnpj"].map(fmt_cnpj)
            tbl["cnpj_investido"] = tbl["cnpj_investido"].map(fmt_cnpj)
            tbl["percentual"] = tbl["percentual"].map(lambda x: f"{x:.2f}%")
            tbl["valor_financeiro"] = tbl["valor_financeiro"].map(fmt_moeda)
            tbl = tbl.rename(columns={
                "fundo": "Fundo", "fundo_cnpj": "CNPJ fundo", "ativo": "Ativo",
                "cnpj_investido": "CNPJ investido", "percentual": "% do PL",
                "valor_financeiro": "Valor", "competencia": "Competência"})
            st.dataframe(tbl, use_container_width=True, hide_index=True)
            st.download_button("Exportar CSV", svc.exportar_csv(dc),
                               file_name="ranking_concentracoes.csv", mime="text/csv")

    # ---- CNPJs recorrentes ------------------------------------------------
    with aba4:
        dr = svc.ranking_cnpjs_recorrentes(gestora_f)
        if dr.empty:
            st.info("Sem dados ainda.")
        else:
            st.caption("Ativos/CNPJs que aparecem em mais de um fundo monitorado.")
            tbl = dr.copy()
            tbl["cnpj_investido"] = tbl["cnpj_investido"].map(fmt_cnpj)
            if "fundos" in tbl.columns:
                tbl = tbl.drop(columns=["fundos"])
            if "valor_total" in tbl.columns:
                tbl["valor_total"] = tbl["valor_total"].map(fmt_moeda)
            tbl = tbl.rename(columns={
                "cnpj_investido": "CNPJ investido", "nome_ativo": "Ativo",
                "qtd_fundos": "Nº fundos", "valor_total": "Valor total"})
            st.dataframe(tbl, use_container_width=True, hide_index=True)
            st.download_button("Exportar CSV", svc.exportar_csv(dr),
                               file_name="cnpjs_recorrentes.csv", mime="text/csv")


# ===========================================================================
# Página 7 — Enviar CDA (upload direto, sem terminal)
# ===========================================================================
elif pagina.startswith("7"):
    st.header("Enviar CDA")
    st.caption("Envie o arquivo do CDA aqui e o sistema importa direto — sem "
               "precisar colocar na pasta nem rodar comando no terminal.")

    # o file_uploader fica FORA do form para disparar a detecção assim que o
    # arquivo é selecionado (dentro de um st.form, os widgets só atualizam a
    # tela depois do clique em enviar — aqui queremos o preenchimento antes).
    arquivo = st.file_uploader(
        "Arquivo do CDA",
        type=["xml", "pdf", "xlsx", "xls", "csv", "txt", "zip"])

    detectado = {}
    if arquivo is not None:
        file_key = f"{arquivo.name}_{arquivo.size}"
        if st.session_state.get("_upload_peek_key") != file_key:
            with st.spinner("Lendo o arquivo..."):
                detectado = svc.detectar_dados_do_arquivo(arquivo.name, arquivo.getvalue())
            st.session_state["_upload_peek_key"] = file_key
            st.session_state["_upload_peek_data"] = detectado
        else:
            detectado = st.session_state.get("_upload_peek_data", {})

        if detectado.get("competencia") or detectado.get("fundo_cnpj"):
            partes = []
            if detectado.get("fundo_cnpj"):
                partes.append(f"CNPJ **{fmt_cnpj(detectado['fundo_cnpj'])}**")
            if detectado.get("competencia"):
                partes.append(f"competência **{detectado['competencia']}**")
            st.success("Detectado no arquivo: " + " · ".join(partes) +
                      ". Já preenchi abaixo — confira antes de importar.")
        else:
            st.info("Não consegui ler CNPJ/competência automaticamente deste "
                    "arquivo. Preencha manualmente abaixo.")
    else:
        st.session_state.pop("_upload_peek_key", None)
        st.session_state.pop("_upload_peek_data", None)

    file_key = f"{arquivo.name}_{arquivo.size}" if arquivo is not None else "nenhum"

    with st.form("form_upload"):
        c1, c2 = st.columns(2)
        gestora_in = c1.text_input(
            "Gestora (concorrente)", placeholder="Ex.: M8 Capital",
            value=detectado.get("gestora_sugerida") or "", key=f"up_gestora_{file_key}")
        fundo_cnpj_in = c2.text_input(
            "CNPJ do fundo", placeholder="00.000.000/0001-00",
            value=fmt_cnpj(detectado["fundo_cnpj"]) if detectado.get("fundo_cnpj") else "",
            key=f"up_cnpj_{file_key}")
        comp_in = st.text_input(
            "Competência (AAAA-MM)", placeholder="2026-05",
            value=detectado.get("competencia") or "", key=f"up_comp_{file_key}")
        enviar = st.form_submit_button("📤 Importar CDA")

    if enviar:
        if arquivo is None:
            st.error("Selecione um arquivo primeiro.")
        elif not (gestora_in and fundo_cnpj_in and comp_in):
            st.error("Preencha gestora, CNPJ do fundo e competência.")
        else:
            with st.spinner("Importando..."):
                r = svc.importar_arquivo_enviado(
                    arquivo.name, arquivo.getvalue(),
                    gestora_in, fundo_cnpj_in, comp_in)
            status = r.get("status")
            if status in ("OK", "PARCIAL"):
                st.success(
                    f"Importado ({status}): {r.get('arquivo')} — "
                    f"{r.get('cnpjs', 0)} CNPJs investidos, "
                    f"fundo {fmt_cnpj(r.get('fundo_cnpj'))}, "
                    f"competência {r.get('competencia')}.")
                if status == "PARCIAL" and r.get("mensagem"):
                    st.warning(
                        f"⚠️ Importado com aviso: {r['mensagem']}\n\n"
                        "Dica: PARCIAL costuma acontecer quando a competência "
                        "digitada é diferente da que está dentro do arquivo. "
                        "O sistema usa a competência do arquivo e importa mesmo assim.")
                # limpa qualquer cache do Streamlit para as outras abas verem o novo dado
                try:
                    st.cache_data.clear()
                except Exception:
                    pass
            elif status == "DUPLICADO":
                st.warning("Este arquivo já havia sido importado antes "
                           "(mesmo conteúdo). Nada foi duplicado.")
            else:
                st.error(f"Falha na importação: {r.get('mensagem', 'erro desconhecido')}")

    # ---- Reparo: cadastrar fundos que já têm CDA mas não aparecem ---------
    st.divider()
    st.subheader("Reparar fundos que não aparecem")
    st.caption("Se você importou um CDA mas o fundo não aparece nas outras "
               "páginas, clique aqui para cadastrá-lo a partir dos documentos "
               "já importados.")
    if st.button("🛠️ Reparar fundos faltantes"):
        rep = svc.cadastrar_fundos_faltantes()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        if rep["criados"] == 0 and rep.get("corrigidos", 0) == 0:
            st.info("Nenhum ajuste necessário — todos os fundos já estão "
                    "cadastrados e com gestora.")
        else:
            partes = []
            for f in rep["fundos"]:
                g = f" (gestora: {f['gestora']})" if f.get("gestora") else " (sem gestora)"
                partes.append("cadastrado " + fmt_cnpj(f["cnpj"]) + g)
            for f in rep.get("fundos_corrigidos", []):
                partes.append(f"gestora associada a {fmt_cnpj(f['cnpj'])} "
                              f"→ {f['gestora']}")
            st.success("Reparo concluído: " + "; ".join(partes) + ". "
                       "Já aparecem nas outras páginas. Clique em "
                       "'Atualizar nomes pela CVM' abaixo para preencher os nomes.")

    # ---- Enriquecer nomes via CVM (sem terminal) --------------------------
    st.divider()
    st.subheader("Preencher nomes dos fundos investidos (CVM)")
    st.caption("O CDA traz só o CNPJ dos fundos investidos, não o nome. Este "
               "botão baixa as bases públicas da CVM e preenche os nomes. "
               "Precisa de internet e pode levar de alguns segundos a poucos "
               "minutos na primeira vez.")
    if st.button("🔄 Atualizar nomes pela CVM"):
        with st.spinner("Baixando bases da CVM e cruzando por CNPJ..."):
            try:
                from src.services.cvm_service import enriquecer_cvm
                res = enriquecer_cvm()
            except Exception as e:
                res = {"status": "erro", "mensagem": str(e)}
        if res.get("status") == "ok":
            st.success(
                f"Nomes atualizados: {res.get('ativos', 0)} ativos investidos e "
                f"{res.get('fundos', 0)} fundos. "
                f"(Bases lidas: registro_fundo={res.get('fontes', {}).get('registro_fundo', 0)}, "
                f"cad_fi={res.get('fontes', {}).get('cad_fi', 0)}.)")
            if res.get("ativos", 0) == 0 and res.get("fundos", 0) == 0:
                st.info("Nenhum nome novo — os CNPJs já tinham nome ou não estão "
                        "nas bases públicas.")
            else:
                st.info("Abra a página **Carteira por fundo** e os nomes já "
                        "aparecerão na coluna do ativo.")
        elif res.get("status") == "indisponivel":
            st.warning("Não foi possível baixar as bases da CVM agora (sem "
                       "internet ou site fora do ar). Tente novamente mais tarde. "
                       "O sistema continua funcionando com os CNPJs.")
        else:
            st.error(f"Erro ao enriquecer: {res.get('mensagem', 'desconhecido')}")

    # ---- Excluir dados (fundo completo, um mês, ou gestora inteira) -------
    st.divider()
    st.subheader("🗑️ Excluir dados")
    st.caption("Remove permanentemente do banco. Não afeta os arquivos em "
               "`data/import/` nem `data/raw/` — se quiser reimportar depois, "
               "os arquivos originais continuam lá.")

    modo_exclusao = st.radio(
        "O que você quer apagar?",
        ["Um mês específico de um fundo", "Um fundo inteiro (todos os meses)",
         "Uma gestora inteira (todos os fundos dela)"],
        key="modo_exclusao",
    )

    gestoras_disp = svc.listar_gestoras()["nome"].tolist()
    if not gestoras_disp:
        st.info("Nenhuma gestora cadastrada ainda.")
    else:
        if modo_exclusao == "Uma gestora inteira (todos os fundos dela)":
            gestora_del = st.selectbox("Gestora", gestoras_disp, key="del_gestora")
            fundos_da_gestora = svc.listar_fundos(gestora_del)
            st.warning(
                f"Isso vai apagar **{len(fundos_da_gestora)} fundo(s)** da "
                f"gestora **{gestora_del}**, com toda a carteira e histórico "
                "de cada um, além da própria gestora. **Não pode ser desfeito.**")
            confirmar = st.checkbox(
                f"Sim, tenho certeza que quero apagar a gestora '{gestora_del}' inteira",
                key="conf_gestora")
            if st.button("🗑️ Apagar gestora", disabled=not confirmar):
                r = svc.excluir_gestora(gestora_del)
                try:
                    st.cache_data.clear()
                except Exception:
                    pass
                if r.get("status") == "ok":
                    st.success(
                        f"Gestora '{gestora_del}' apagada: {r['n_fundos']} fundo(s), "
                        f"{r['documentos']} documento(s), {r['carteira']} linha(s) "
                        "de carteira removidas.")
                else:
                    st.error(r.get("mensagem", "Erro ao apagar."))

        else:
            gestora_del = st.selectbox("Gestora", gestoras_disp, key="del_gestora2")
            fundos_df = svc.listar_fundos(gestora_del)
            if fundos_df.empty:
                st.info("Esta gestora não tem fundos com CDA importado.")
            else:
                opcoes_fundo = {
                    f"{r['nome'] if pd.notna(r['nome']) else '(sem nome)'} — {fmt_cnpj(r['cnpj'])}": r["cnpj"]
                    for _, r in fundos_df.iterrows()
                }
                escolha_fundo = st.selectbox("Fundo", list(opcoes_fundo.keys()),
                                             key="del_fundo")
                cnpj_del = opcoes_fundo[escolha_fundo]

                if modo_exclusao == "Um fundo inteiro (todos os meses)":
                    comps_fundo = svc.competencias_disponiveis(cnpj_del)
                    st.warning(
                        f"Isso vai apagar o fundo inteiro ({fmt_cnpj(cnpj_del)}), "
                        f"com **{len(comps_fundo)} competência(s)** e toda a "
                        "carteira. **Não pode ser desfeito.**")
                    confirmar = st.checkbox(
                        "Sim, tenho certeza que quero apagar este fundo inteiro",
                        key="conf_fundo")
                    if st.button("🗑️ Apagar fundo", disabled=not confirmar):
                        r = svc.excluir_fundo(cnpj_del)
                        try:
                            st.cache_data.clear()
                        except Exception:
                            pass
                        st.success(
                            f"Fundo apagado: {r['documentos']} documento(s), "
                            f"{r['carteira']} linha(s) de carteira removidas.")

                else:  # um mês específico
                    comps_fundo = svc.competencias_disponiveis(cnpj_del)
                    if not comps_fundo:
                        st.info("Este fundo não tem competências importadas.")
                    else:
                        comp_del = st.selectbox("Competência", comps_fundo, key="del_comp")
                        st.warning(
                            f"Isso vai apagar só a competência **{comp_del}** do "
                            f"fundo {fmt_cnpj(cnpj_del)}. As demais competências "
                            "continuam intactas. **Não pode ser desfeito.**")
                        confirmar = st.checkbox(
                            f"Sim, tenho certeza que quero apagar {comp_del} deste fundo",
                            key="conf_mes")
                        if st.button("🗑️ Apagar este mês", disabled=not confirmar):
                            r = svc.excluir_mes_fundo(cnpj_del, comp_del)
                            try:
                                st.cache_data.clear()
                            except Exception:
                                pass
                            st.success(
                                f"Competência {comp_del} apagada: {r['documentos']} "
                                f"documento(s), {r['carteira']} linha(s) removidas.")


# ===========================================================================
# Página 8 — Emissões de FIDC (CVM)
# ===========================================================================
elif pagina.startswith("8"):
    from dashboard.paginas import emissoes
    emissoes.render({
        "COBRE": BRAVE_COBRE,
        "MARINHO": BRAVE_MARINHO,
        "FUNDO": BRAVE_FUNDO,
        "TEXTO": BRAVE_TEXTO,
        "TEXTO_FRACO": BRAVE_TEXTO_FRACO,
        "BORDA": BRAVE_BORDA,
    })

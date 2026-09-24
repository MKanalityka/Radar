import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google import genai

# 1. USTAWIENIA STRONY
st.set_page_config(page_title="Monitoring Budżetu JST", layout="wide")

# Funkcja pomocnicza do tworzenia bardzo cienkich linii podziału
def thin_divider():
    st.markdown("<hr style='margin: 25px 0; height: 1px; background-color: #e5e7eb; border: none;'>", unsafe_allow_html=True)

# Funkcja pomocnicza do formatowania kwot walutowych w tys. PLN (liczby całkowite)
def format_pln(val):
    if pd.isna(val):
        return "0 tys. PLN"
    val_tys = round(val / 1000.0)
    return f"{val_tys:,.0f}".replace(",", " ") + " tys. PLN"

# 2. WCZYTYWANIE DANYCH
@st.cache_data
def load_data():
    file_path = "JST_dashboard_dane_syntetyczne.xlsx"
    df_jst = pd.read_excel(file_path, sheet_name="JST")
    df_fin = pd.read_excel(file_path, sheet_name="Finanse_kategorie")
    df_rbnds = pd.read_excel(file_path, sheet_name="RbNDS")
    df_rbz = pd.read_excel(file_path, sheet_name="RbZ")
    
    # Dołączenie nazwy i typu jednostki do tabel faktów
    df_fin = df_fin.merge(df_jst[['jst_id', 'jst_nazwa', 'rodzaj_jednostki', 'typ_jst']], on='jst_id', how='left')
    df_rbnds = df_rbnds.merge(df_jst[['jst_id', 'jst_nazwa', 'rodzaj_jednostki', 'typ_jst']], on='jst_id', how='left')
    df_rbz = df_rbz.merge(df_jst[['jst_id', 'jst_nazwa', 'rodzaj_jednostki', 'typ_jst']], on='jst_id', how='left')
    
    return df_jst, df_fin, df_rbnds, df_rbz

df_jst, df_fin, df_rbnds, df_rbz = load_data()

# 3. ZARZĄDZANIE STANEM NAWIGACJI I CZATU
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "Wskaźniki per kwartał"

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

def set_tab(tab_name):
    st.session_state.active_tab = tab_name

# 4. PANEL BOCZNY (SIDEBAR) - OPCJE FILTROWANIA
st.sidebar.header("🎛️ Opcje filtrowania")

# Wybór JST
jst_list = sorted(df_jst['jst_nazwa'].dropna().unique())
selected_jst = st.sidebar.selectbox("🏛️ Wybierz jednostkę (JST)", jst_list)

# Dane przefiltrowane dla wybranej JST
df_fin_jst = df_fin[df_fin['jst_nazwa'] == selected_jst]
df_rbnds_jst = df_rbnds[df_rbnds['jst_nazwa'] == selected_jst]
df_rbz_jst = df_rbz[df_rbz['jst_nazwa'] == selected_jst]

# DYNAMICZNY WYBÓR W ZALEŻNOŚCI OD AKTYWNEJ ZAKŁADKI
selected_okres = None
selected_rok = None

if st.session_state.active_tab == "Wskaźniki per kwartał":
    st.sidebar.markdown("---")
    okres_list = sorted(df_rbnds_jst['okres'].dropna().unique(), reverse=True)
    selected_okres = st.sidebar.selectbox("📅 Wybierz kwartał", okres_list if okres_list else ["Q1"])
elif st.session_state.active_tab == "Analiza roczna":
    st.sidebar.markdown("---")
    rok_list = sorted(df_rbnds_jst['rok'].dropna().unique(), reverse=True)
    selected_rok = st.sidebar.selectbox("📈 Wybierz rok", rok_list if rok_list else [2024])
else:
    # Wartości domyślne dla asystenta AI
    okres_list = sorted(df_rbnds_jst['okres'].dropna().unique(), reverse=True)
    selected_okres = okres_list[0] if okres_list else "Q4"
    rok_list = sorted(df_rbnds_jst['rok'].dropna().unique(), reverse=True)
    selected_rok = rok_list[0] if rok_list else 2024

# Pobranie rodzaju jednostki dla wybranej JST
jst_info = df_jst[df_jst['jst_nazwa'] == selected_jst]
rodzaj_jednostki = jst_info['rodzaj_jednostki'].values[0] if not jst_info.empty else "miasto"
typ_jst = jst_info['typ_jst'].values[0] if 'typ_jst' in jst_info.columns and not jst_info.empty else ""

# KONFIGURACJA AI W PANELU BOCZNYM
st.sidebar.markdown("---")
st.sidebar.header("🤖 Finansowy Asystent AI")
api_key = st.sidebar.text_input("🔑 Klucz API Gemini", type="password", help="Wprowadź swój klucz Google Gemini API, aby aktywować asystenta")

# 5. DYNAMICZNY DOBÓR OBRAZU W ZALEŻNOŚCI OD WYBRANEJ JEDNOSTKI (JST)
jst_specific_images = {
    "Gmina Nibylandia": "https://images.unsplash.com/photo-1519197700284-0c4e7ab56f0d?auto=format&fit=crop&w=1600&q=80",
    "Miasto Zmyślów": "https://images.unsplash.com/photo-1511527844065-bc06034429f4?auto=format&fit=crop&w=1600&q=80",
    "Powiat Fikcyjny": "https://images.unsplash.com/photo-1558717865-1d413349c289?auto=format&fit=crop&w=1600&q=80",
    "Gmina Zielone Wzgórza": "https://images.unsplash.com/photo-1584811644269-e748b9fe6b5b?auto=format&fit=crop&w=1600&q=80",
}

fallback_type_images = {
    "miejska": "https://images.unsplash.com/photo-1480714378408-67cf0d13bc1b?auto=format&fit=crop&w=1600&q=80",
    "wiejska": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1600&q=80",
    "miejsko-wiejska": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?auto=format&fit=crop&w=1600&q=80"
}

current_banner_url = jst_specific_images.get(
    selected_jst, 
    fallback_type_images.get(str(rodzaj_jednostki).lower(), fallback_type_images["miejsko-wiejska"])
)

# --- BANER (PEŁNA SZEROKOŚĆ STRONY) ---
banner_html = f"""
<style>
    .custom-banner-wrapper {{
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 0 20px 0 !important;
        padding: 0 !important;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }}
    .custom-banner-img {{
        width: 100% !important;
        max-width: 100% !important;
        height: 120px !important;
        object-fit: cover !important;
        object-position: center 30% !important;
        display: block !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
    }}
    .custom-info-bar {{
        background-color: #1a2436;
        color: #60a5fa;
        padding: 10px 16px;
        font-size: 14px;
        border-top: 1px solid #2d3748;
        width: 100% !important;
        box-sizing: border-box;
    }}
</style>

<div class="custom-banner-wrapper">
    <img src="{current_banner_url}" class="custom-banner-img" alt="Baner JST" />
    <div class="custom-info-bar">
        🏛️ • <b>Jednostka:</b> {selected_jst} &nbsp;|&nbsp; 🏷️ <b>Typ:</b> {str(rodzaj_jednostki).capitalize()}
    </div>
</div>
"""

st.markdown(banner_html, unsafe_allow_html=True)

st.title(f"📊 Monitoring budżetu jednostki: {selected_jst}")

col_btn1, col_btn2, col_btn3, _ = st.columns([2, 2, 3, 5])
with col_btn1:
    st.button("📊 Wskaźniki per kwartał", on_click=set_tab, args=["Wskaźniki per kwartał"], 
              use_container_width=True, 
              type="primary" if st.session_state.active_tab == "Wskaźniki per kwartał" else "secondary")
with col_btn2:
    st.button("📈 Analiza roczna", on_click=set_tab, args=["Analiza roczna"], 
              use_container_width=True, 
              type="primary" if st.session_state.active_tab == "Analiza roczna" else "secondary")
with col_btn3:
    st.button("🤖 Finansowy Asystent AI", on_click=set_tab, args=["Finansowy Asystent AI"], 
              use_container_width=True, 
              type="primary" if st.session_state.active_tab == "Finansowy Asystent AI" else "secondary")

thin_divider()

# 6. ZAKŁADKA 1: WSKAŹNIKI PER KWARTAŁ
if st.session_state.active_tab == "Wskaźniki per kwartał":
    
    df_fin_q = df_fin_jst[df_fin_jst['okres'] == selected_okres]
    df_rbnds_q = df_rbnds_jst[df_rbnds_jst['okres'] == selected_okres]
    df_rbz_q = df_rbz_jst[df_rbz_jst['okres'] == selected_okres]
    
    # KARTY KPI
    st.subheader(f"📌 Podsumowanie kluczowych wskaźników ({selected_okres})")
    if not df_rbnds_q.empty:
        rbnds_row = df_rbnds_q.iloc[0]
        rbz_row = df_rbz_q.iloc[0] if not df_rbz_q.empty else None
        
        dochody_q = rbnds_row['dochody_wykonanie']
        wydatki_q = rbnds_row['wydatki_wykonanie']
        wynik_q = rbnds_row['wynik_wykonanie']
        zobowiazania_q = rbz_row['zobowiazania_ogolem'] if rbz_row is not None else 0
        
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric(f"💰 Dochody ogółem", format_pln(dochody_q))
        kpi2.metric(f"💸 Wydatki ogółem", format_pln(wydatki_q))
        kpi3.metric(f"⚖️ Wynik budżetu", format_pln(wynik_q), delta=format_pln(wynik_q), delta_color="normal")
        kpi4.metric(f"📑 Zobowiązania ogółem", format_pln(zobowiazania_q))
        
        # Analiza opisowa KPI
        st.markdown(f"""
        > 💡 **Krótka analiza:** W wybranym okresie ({selected_okres}) jednostka odnotowała dochody na poziomie **{format_pln(dochody_q)}** oraz wydatki w wysokości **{format_pln(wydatki_q)}**. 
        > Wynik budżetu wynosi **{format_pln(wynik_q)}**, co wskazuje na aktualną sytuację nadwyżkową/deficytową. Łączne zobowiązania kształtują się na poziomie **{format_pln(zobowiazania_q)}**.
        """)
    
    thin_divider()
    
    # 1. REALIZACJA PLANU WYBRANYCH KATEGORII
    st.subheader(f"🎯 Stopień realizacji planu rocznego dla kluczowych kategorii ({selected_okres})")
    top_kategorie = df_fin_q.sort_values('plan_roczny', ascending=False).head(4)
    
    if not top_kategorie.empty:
        gauge_cols = st.columns(len(top_kategorie))
        for idx, row in enumerate(top_kategorie.itertuples()):
            pct_val = row.wykonanie_pct_planu
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=pct_val,
                number={'suffix': "%", 'valueformat': ".2f"},
                title={
                    'text': f"<b>{row.kategoria}</b><br>"
                            f"<span style='font-size:0.75em;color:gray'>"
                            f"Wyk.: {format_pln(row.wykonanie_narastajaco)} / Plan: {format_pln(row.plan_roczny)}"
                            f"</span>"
                },
                gauge={
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "#1f77b4"},
                    'threshold': {'line': {'color': "red", 'width': 3}, 'thickness': 0.75, 'value': 100}
                }
            ))
            fig_gauge.update_layout(height=270, margin=dict(l=20, r=20, t=50, b=20))
            gauge_cols[idx].plotly_chart(fig_gauge, use_container_width=True)

        st.markdown(f"""
        > 💡 **Wnioski analityczne:** Wykresy wskaźnikowe (gauge) prezentują stopień zaawansowania realizacji rocznego planu finansowego w czterech największych pozycjach budżetowych. Warto monitorować pozycje zbliżające się do 100% wykonania pod kątem konieczności ewentualnych korekt budżetowych.
        """)

    thin_divider()

    # 2. STRUKTURA DOCHODÓW I WYDATKÓW
    st.subheader(f"🧩 Struktura dochodów i wydatków ({selected_okres})")
    
    col_mode1, col_mode2 = st.columns([3, 7])
    with col_mode1:
        chart_display_mode = st.radio(
            "Wybierz format wartości:",
            options=["Procenty (%)", "Wartości w tys. PLN"],
            horizontal=True,
            key="pie_display_mode"
        )
    
    col_str1, col_str2 = st.columns(2)
    
    if chart_display_mode == "Wartości w tys. PLN":
        text_info_setting = 'value'
        hover_template_str = '<b>%{label}</b><br>Wartość: %{value:,.0f} tys. PLN<br>Udział: %{percent}<extra></extra>'
    else:
        text_info_setting = 'percent'
        hover_template_str = '<b>%{label}</b><br>Udział: %{percent}<br>Wartość: %{value:,.0f} tys. PLN<extra></extra>'

    with col_str1:
        st.markdown("**🟢 Struktura dochodów wg kategorii**")
        df_dochody_q = df_fin_q[df_fin_q['obszar'] == 'dochody'].copy()
        if not df_dochody_q.empty:
            df_dochody_q['wykonanie_tys'] = (df_dochody_q['wykonanie_narastajaco'] / 1000.0).round()
            fig_inc = px.pie(df_dochody_q, values='wykonanie_tys', names='kategoria', hole=0.4,
                             color_discrete_sequence=px.colors.sequential.Teal)
            fig_inc.update_traces(textinfo=text_info_setting, textposition='inside', hovertemplate=hover_template_str)  
            fig_inc.update_layout(showlegend=True, legend=dict(orientation="v", x=1.02, y=0.5, xanchor="left", yanchor="middle"), margin=dict(l=10, r=150, t=20, b=20))
            st.plotly_chart(fig_inc, use_container_width=True)
            
    with col_str2:
        st.markdown("**🔴 Struktura wydatków wg kategorii**")
        df_wydatki_q = df_fin_q[df_fin_q['obszar'] == 'wydatki'].copy()
        if not df_wydatki_q.empty:
            df_wydatki_q['wykonanie_tys'] = (df_wydatki_q['wykonanie_narastajaco'] / 1000.0).round()
            fig_exp = px.pie(df_wydatki_q, values='wykonanie_tys', names='kategoria', hole=0.4,
                             color_discrete_sequence=px.colors.sequential.OrRd)
            fig_exp.update_traces(textinfo=text_info_setting, textposition='inside', hovertemplate=hover_template_str)  
            fig_exp.update_layout(showlegend=True, legend=dict(orientation="v", x=1.02, y=0.5, xanchor="left", yanchor="middle"), margin=dict(l=10, r=150, t=20, b=20))
            st.plotly_chart(fig_exp, use_container_width=True)

    st.markdown(f"""
    > 💡 **Krótka analiza strukturalna:** Powyższe wykresy pierścieniowe pozwalają zidentyfikować główne źródła zasilania budżetu jednostki oraz główne obszary generujące wydatki bieżące i majątkowe.
    """)

    thin_divider()

    # 3. WYKONANIE PROCENTOWE WSZYSTKICH PLANÓW
    st.subheader(f"📊 Wykonanie procentowe wszystkich kategorii budżetowych ({selected_okres})")
    if not df_fin_q.empty:
        df_pct_sorted = df_fin_q.sort_values('wykonanie_pct_planu', ascending=True)
        fig_pct = px.bar(
            df_pct_sorted, x='wykonanie_pct_planu', y='kategoria', color='obszar', orientation='h',
            labels={'wykonanie_pct_planu': 'Wykonanie (% planu)', 'kategoria': 'Kategoria', 'obszar': 'Obszar'},
            color_discrete_map={'dochody': '#2ca02c', 'wydatki': '#d62728'}, text='wykonanie_pct_planu'
        )
        fig_pct.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
        fig_pct.update_layout(height=520, xaxis=dict(ticksuffix="%"), margin=dict(l=10, r=40, t=20, b=20))
        st.plotly_chart(fig_pct, use_container_width=True)

    thin_divider()

    # 4. RAPORT RbNDS
    st.subheader(f"📋 Pełne zestawienie z raportu RbNDS ({selected_okres})")
    if not df_rbnds_q.empty:
        row_nd = df_rbnds_q.iloc[0]
        rbnds_data = [
            {"Pozycja": "Dochody ogółem", "Wykonanie": round(row_nd['dochody_wykonanie'] / 1000.0), "Plan": round(row_nd['dochody_plan'] / 1000.0)},
            {"Pozycja": "Dochody bieżące", "Wykonanie": round(row_nd['dochody_biezace_wykonanie'] / 1000.0), "Plan": round(row_nd['dochody_biezace_plan'] / 1000.0)},
            {"Pozycja": "Wydatki ogółem", "Wykonanie": round(row_nd['wydatki_wykonanie'] / 1000.0), "Plan": round(row_nd['wydatki_plan'] / 1000.0)},
            {"Pozycja": "Wydatki bieżące", "Wykonanie": round(row_nd['wydatki_biezace_wykonanie'] / 1000.0), "Plan": round(row_nd['wydatki_biezace_plan'] / 1000.0)},
            {"Pozycja": "Wynik budżetu", "Wykonanie": round(row_nd['wynik_wykonanie'] / 1000.0), "Plan": round(row_nd['wynik_plan'] / 1000.0)},
            {"Pozycja": "Przychody", "Wykonanie": round(row_nd['przychody_wykonanie'] / 1000.0), "Plan": round(row_nd['przychody_plan'] / 1000.0)},
            {"Pozycja": "Rozchody", "Wykonanie": round(row_nd['rozchody_wykonanie'] / 1000.0), "Plan": round(row_nd['rozchody_plan'] / 1000.0)},
        ]
        df_rbnds_table = pd.DataFrame(rbnds_data)
        
        df_rbnds_table['% Wykonania'] = df_rbnds_table.apply(
            lambda row: round((row['Wykonanie'] / row['Plan'] * 100), 2) if row['Plan'] != 0 else 0.0,
            axis=1
        )
        
        col_rb1, col_rb2 = st.columns([3, 2])
        with col_rb1:
            fig_rbnds = go.Figure()
            fig_rbnds.add_trace(go.Bar(x=df_rbnds_table['Pozycja'], y=df_rbnds_table['Wykonanie'], name='Wykonanie', marker_color='#0f766e'))
            fig_rbnds.add_trace(go.Bar(x=df_rbnds_table['Pozycja'], y=df_rbnds_table['Plan'], name='Plan', marker_color='#9ca3af'))
            fig_rbnds.update_layout(barmode='group', xaxis_title="", yaxis_title="tys. PLN", height=380)
            st.plotly_chart(fig_rbnds, use_container_width=True)
            
        with col_rb2:
            st.markdown("**Tabela wskaźników RbNDS (w tys. PLN)**")
            df_display = df_rbnds_table.copy()
            df_display.columns = ["Pozycja", "Wykonanie (tys. PLN)", "Plan (tys. PLN)", "% Wykonania"]
            df_display['Wykonanie (tys. PLN)'] = df_display['Wykonanie (tys. PLN)'].map('{:,.0f}'.format).str.replace(',', ' ') + " tys. PLN"
            df_display['Plan (tys. PLN)'] = df_display['Plan (tys. PLN)'].map('{:,.0f}'.format).str.replace(',', ' ') + " tys. PLN"
            df_display['% Wykonania'] = df_display['% Wykonania'].astype(str) + "%"
            st.dataframe(df_display, hide_index=True, use_container_width=True)

    thin_divider()

    # 5. STRUKTURA ZADŁUŻENIA (RbZ)
    st.subheader(f"💳 Struktura zadłużenia z raportu RbZ ({selected_okres})")
    if not df_rbz_q.empty:
        rbz_row = df_rbz_q.iloc[0]
        rbz_items = pd.DataFrame({
            'Kategoria zobowiązania': ['Kredyty i pożyczki', 'Papiery wartościowe', 'Zobowiązania wymagalne', 'Pozostałe zobowiązania'],
            'Wartość (tys. PLN)': [
                round(rbz_row['kredyty_i_pozyczki'] / 1000.0), 
                round(rbz_row['papiery_wartosciowe'] / 1000.0), 
                round(rbz_row['zobowiazania_wymagalne'] / 1000.0), 
                round(rbz_row['pozostale_zobowiazania'] / 1000.0)
            ]
        })
        rbz_items = rbz_items[rbz_items['Wartość (tys. PLN)'] > 0]
        
        col_z1, col_z2 = st.columns([3, 2])
        with col_z1:
            fig_rbz = px.pie(rbz_items, values='Wartość (tys. PLN)', names='Kategoria zobowiązania', hole=0.45,
                             color_discrete_sequence=px.colors.qualitative.Set3)
            fig_rbz.update_traces(textinfo='percent', textposition='inside')  
            fig_rbz.update_layout(showlegend=True, legend=dict(orientation="v", x=1.02, y=0.5, xanchor="left", yanchor="middle"), margin=dict(l=10, r=150, t=20, b=20))
            st.plotly_chart(fig_rbz, use_container_width=True)
            
        with col_z2:
            st.markdown("**Szczegóły zobowiązań (w tys. PLN):**")
            st.write(f"- **Zobowiązania ogółem:** {format_pln(rbz_row['zobowiazania_ogolem'])}")
            st.write(f"- **Kredyty i pożyczki:** {format_pln(rbz_row['kredyty_i_pozyczki'])}")
            st.write(f"- **Papiery wartościowe:** {format_pln(rbz_row['papiery_wartosciowe'])}")
            st.write(f"- **Zobowiązania wymagalne:** {format_pln(rbz_row['zobowiazania_wymagalne'])}")
            st.write(f"- **Odsetki należne:** {format_pln(rbz_row['odsetki_nalezace'])}")

        st.markdown(f"""
        > 💡 **Krótka analiza zadłużenia:** Struktura zadłużenia wskazuje na główny udział kredytów i pożyczek. Brak istotnych zobowiązań wymagalnych świadczy o zachowaniu płynności finansowej przez jednostkę.
        """)

# 7. ZAKŁADKA 2: ANALIZA ROCZNA
elif st.session_state.active_tab == "Analiza roczna":
    
    df_rbnds_rok = df_rbnds_jst[df_rbnds_jst['rok'] == selected_rok].sort_values('okres').copy()
    df_fin_rok = df_fin_jst[df_fin_jst['rok'] == selected_rok].copy()
    df_rbz_rok = df_rbz_jst[df_rbz_jst['rok'] == selected_rok].sort_values('okres').copy()
    
    df_rbnds_rok['dochody_tys'] = (df_rbnds_rok['dochody_wykonanie'] / 1000.0).round()
    df_rbnds_rok['wydatki_tys'] = (df_rbnds_rok['wydatki_wykonanie'] / 1000.0).round()
    df_rbnds_rok['wynik_tys'] = (df_rbnds_rok['wynik_wykonanie'] / 1000.0).round()
    
    col_wyk1, col_wyk2 = st.columns(2)
    
    with col_wyk1:
        st.subheader(f"📈 Dochody vs Wydatki w roku {selected_rok}")
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(x=df_rbnds_rok['okres'], y=df_rbnds_rok['dochody_tys'], name='Dochody wykonane', marker_color='#2ca02c'))
        fig_trend.add_trace(go.Bar(x=df_rbnds_rok['okres'], y=df_rbnds_rok['wydatki_tys'], name='Wydatki wykonane', marker_color='#d62728'))
        fig_trend.update_layout(barmode='group', xaxis_title='Okres', yaxis_title='tys. PLN')
        st.plotly_chart(fig_trend, use_container_width=True)
        
    with col_wyk2:
        st.subheader(f"🍕 Podział dochodów na kategorie ({selected_rok})")
        if not df_fin_rok.empty:
            latest_okres_w_roku = df_fin_rok['okres'].max()
            df_fin_latest = df_fin_rok[(df_fin_rok['okres'] == latest_okres_w_roku) & (df_fin_rok['obszar'] == 'dochody')].copy()
            df_fin_latest['wykonanie_tys'] = (df_fin_latest['wykonanie_narastajaco'] / 1000.0).round()
            fig_pie_annual = px.pie(df_fin_latest, values='wykonanie_tys', names='kategoria', hole=0.3)
            fig_pie_annual.update_traces(textinfo='percent', textposition='inside')
            st.plotly_chart(fig_pie_annual, use_container_width=True)

    st.markdown(f"""
    > 💡 **Analiza roczna (rok {selected_rok}):** Zestawienie kwartalne pozwala ocenić płynność realizacji dochodów i wydatków na przestrzeni całego roku budżetowego.
    """)

    thin_divider()
    
    # 1. OGÓLNY WYKRES TRENDÓW
    st.subheader(f"📉 Ogólny trend głównych wskaźników finansowych w roku {selected_rok}")
    
    fig_main_trend = go.Figure()
    fig_main_trend.add_trace(go.Scatter(x=df_rbnds_rok['okres'], y=df_rbnds_rok['dochody_tys'], mode='lines+markers', name='Dochody ogółem', line=dict(width=3, color='#2ca02c')))
    fig_main_trend.add_trace(go.Scatter(x=df_rbnds_rok['okres'], y=df_rbnds_rok['wydatki_tys'], mode='lines+markers', name='Wydatki ogółem', line=dict(width=3, color='#d62728')))
    fig_main_trend.add_trace(go.Scatter(x=df_rbnds_rok['okres'], y=df_rbnds_rok['wynik_tys'], mode='lines+markers+text', name='Wynik budżetu', line=dict(width=3, color='#1f77b4', dash='dot'), text=[f"{v:,.0f} tys." for v in df_rbnds_rok['wynik_tys']], textposition="top center"))
    
    if not df_rbz_rok.empty:
        df_rbz_rok['zobowiazania_tys'] = (df_rbz_rok['zobowiazania_ogolem'] / 1000.0).round()
        fig_main_trend.add_trace(go.Scatter(x=df_rbz_rok['okres'], y=df_rbz_rok['zobowiazania_tys'], mode='lines+markers', name='Zobowiązania ogółem', line=dict(width=2, color='#ff7f0e')))
        
    fig_main_trend.update_layout(xaxis_title='Okres kwartalny', yaxis_title='Wartość w tys. PLN', height=400, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig_main_trend, use_container_width=True)

    thin_divider()

    # 2. SEKCJA FILTROWANIA I KONTROLI DLA SZCZEGÓŁOWEGO WYKRESU LINIOWEGO
    st.subheader("🔍 Szczegółowa analiza w czasie z opcją filtrowania")
    
    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        range_years = st.radio(
            "Wybierz zakres czasowy wstecz (od wybranego roku):",
            options=[1, 2, 3],
            format_func=lambda x: f"Ostatnie {x} lata ({x*4} kwartałów)" if x > 1 else "Ostatni 1 rok (4 kwartały)",
            index=2,
            key="range_years_select"
        )
    
    min_year = selected_rok - range_years + 1
    df_fin_multi = df_fin_jst[(df_fin_jst['rok'] >= min_year) & (df_fin_jst['rok'] <= selected_rok)].copy()
    
    dostepne_podkategorie = sorted(df_fin_multi['kategoria'].dropna().unique()) if not df_fin_multi.empty else []
    
    with col_f2:
        selected_podkategorie = st.multiselect(
            "Wybierz konkretne kategorie budżetowe do porównania:",
            options=dostepne_podkategorie,
            default=dostepne_podkategorie[:2] if len(dostepne_podkategorie) >= 2 else dostepne_podkategorie,
            key="multi_kat_select"
        )
        
    fig_detail_trend = go.Figure()
    
    if selected_podkategorie:
        for kat in selected_podkategorie:
            df_kat_filtered = df_fin_multi[df_fin_multi['kategoria'] == kat].sort_values('okres').copy()
            if not df_kat_filtered.empty:
                df_kat_filtered['wykonanie_tys'] = (df_kat_filtered['wykonanie_narastajaco'] / 1000.0).round()
                fig_detail_trend.add_trace(go.Scatter(
                    x=df_kat_filtered['okres'], 
                    y=df_kat_filtered['wykonanie_tys'], 
                    mode='lines+markers', 
                    name=kat
                ))
        fig_detail_trend.update_layout(
            xaxis_title='Okres kwartalny', 
            yaxis_title='Wartość w tys. PLN', 
            height=450, 
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_detail_trend, use_container_width=True)
    else:
        st.info("Wybierz co najmniej jedną kategorię budżetową z powyższej listy, aby wyświetlić wykres trendu.")

# 8. ZAKŁADKA 3: FINANSOWY ASYSTENT AI
elif st.session_state.active_tab == "Finansowy Asystent AI":
    st.subheader(f"🤖 Finansowy Asystent AI – Doradca dla: {selected_jst}")
    st.caption("Zapytaj Finansowego Asystenta AI o wykonanie planu, saldo budżetowe, dynamikę dochodów/wydatków lub poziom zadłużenia wybranej jednostki.")

    # Wyświetlanie dotychczasowej historii czatu
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Pole wprowadzania pytania
    if prompt := st.chat_input("Napisz pytanie, np. 'Jaki jest poziom wykonania dochodów i główne źródła zobowiązań?'"):
        if not api_key:
            st.error("Proszę wpisać klucz API Gemini w panelu bocznym (Sidebar), aby uruchomić Finansowego Asystenta AI.")
        else:
            # Dodanie pytania użytkownika do historii i widoku
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Przygotowanie pełnego kontekstu danych dla wybranej JST
            fin_summary = df_fin_jst[['okres', 'obszar', 'kategoria', 'plan_roczny', 'wykonanie_narastajaco', 'wykonanie_pct_planu']].to_csv(index=False)
            rbnds_summary = df_rbnds_jst[['okres', 'dochody_wykonanie', 'wydatki_wykonanie', 'wynik_wykonanie', 'przychody_wykonanie', 'rozchody_wykonanie']].to_csv(index=False)
            rbz_summary = df_rbz_jst[['okres', 'zobowiazania_ogolem', 'kredyty_i_pozyczki', 'papiery_wartosciowe', 'zobowiazania_wymagalne']].to_csv(index=False)

            system_instruction = f"""
            Nazywasz się **Finansowy Asystent AI**. Jesteś ekspertem ds. finansów publicznych i opiekunem budżetu dla jednostki: {selected_jst} (Rodzaj: {rodzaj_jednostki}, Typ: {typ_jst}).
            Twoim zadaniem jest ochrona stabilności finansowej, analiza wskaźników budżetowych oraz udzielanie precyzyjnych i wyczerpujących odpowiedzi na pytania użytkownika.

            Oto aktualne dane z bazy danych dotyczące tej jednostki:

            --- TABELA FINANSE (KATEGORIE BUDŻETOWE) ---
            {fin_summary}

            --- TABELA RbNDS (DOCHODY, WYDATKI, WYNIK BUDŻETU) ---
            {rbnds_summary}

            --- TABELA RbZ (ZADŁUŻENIE I ZOBOWIĄZANIA) ---
            {rbz_summary}

            Zasady odpowiedzi:
            1. Odpowiadaj profesjonalnie, czytelnie i wyczerpująco w języku polskim.
            2. Formatuj kwoty w tysiącach PLN lub milionach PLN.
            3. Bazuj wyłącznie na przekazanych wyżej danych. Jeśli w bazie brak szukanych szczegółów, poinformuj o tym użytkownika.
            4. Jeśli użytkownik pyta o stan finansów, oceniaj sytuację budżetową i zwracaj uwagę na ewentualne ryzyka (np. wysokie zobowiązania, deficyt).
            """

            try:
                client = genai.Client(api_key=api_key)
                
                with st.chat_message("assistant"):
                    with st.spinner("Finansowy Asystent AI analizuje dane..."):
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=f"{system_instruction}\n\nPytanie użytkownika: {prompt}"
                        )
                        st.markdown(response.text)
                        st.session_state.chat_history.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Błąd podczas połączenia z Gemini API: {e}")
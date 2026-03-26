import streamlit as st
import pandas as pd
import numpy as np
import math
import io

st.set_page_config(page_title="NormDealer — Нормативная модель", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }
.stApp { background: #0e0f11; color: #f0eeea; }
[data-testid="stSidebar"] { background: #161719 !important; border-right: 1px solid rgba(255,255,255,0.07); }
[data-testid="stSidebar"] * { color: #f0eeea !important; }
[data-testid="metric-container"] { background: #161719; border: 1px solid rgba(255,255,255,0.07); border-radius: 12px; padding: 16px 20px; }
[data-testid="stMetricLabel"] { color: #7a7975 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: .08em; font-family: 'IBM Plex Mono', monospace !important; }
[data-testid="stMetricValue"] { color: #f0eeea !important; font-family: 'Manrope', sans-serif !important; font-weight: 700 !important; }
[data-testid="stTabs"] button { font-family: 'Manrope', sans-serif !important; font-weight: 500; color: #7a7975 !important; border-radius: 8px; }
[data-testid="stTabs"] button[aria-selected="true"] { color: #c8f04a !important; border-bottom-color: #c8f04a !important; }
.stButton > button { background: #1e2024; border: 1px solid rgba(255,255,255,0.14); color: #f0eeea; border-radius: 8px; font-family: 'Manrope', sans-serif; font-weight: 500; }
h1, h2, h3 { color: #f0eeea !important; font-family: 'Manrope', sans-serif !important; }
hr { border-color: rgba(255,255,255,0.07) !important; }
.mono  { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: #c8f04a; }
.muted { color: #7a7975; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

DEALERS = {
    "Бахтиёр Абу-Сахий":  {"sap": "1000001081", "rev": 1303952, "pallets": 11101, "area": 5002.8, "gross_pct": 0.0592},
    "Улугбек Самарканд":  {"sap": "1000000029", "rev": 1060885, "pallets": 4854,  "area": 2187.5, "gross_pct": 0.0607},
    "Шодмон Денов":       {"sap": "1000000430", "rev": 1040169, "pallets": 5763,  "area": 2597.2, "gross_pct": 0.0635},
    "Ахмаджон Коканд":    {"sap": "1000000646", "rev": 721601,  "pallets": 8070,  "area": 3636.8, "gross_pct": 0.0658},
    "Шавкат Самарканд":   {"sap": "1000000766", "rev": 759541,  "pallets": 4623,  "area": 2083.4, "gross_pct": 0.0592},
    "Аскар Карши":        {"sap": "1000000234", "rev": 615169,  "pallets": 5190,  "area": 2338.9, "gross_pct": 0.0558},
    "Шариф Термез":       {"sap": "1000000426", "rev": 697567,  "pallets": 6327,  "area": 2851.3, "gross_pct": 0.0503},
    "Акмал Бухара":       {"sap": "1000001233", "rev": 497470,  "pallets": 6131,  "area": 2763.0, "gross_pct": 0.0594},
    "Обид Бухара":        {"sap": "1000000564", "rev": 511097,  "pallets": 3269,  "area": 1473.2, "gross_pct": 0.0599},
    "Кахрамон Навои":     {"sap": "1000001100", "rev": 375131,  "pallets": 7805,  "area": 3517.4, "gross_pct": 0.0506},
}

DEFAULT_ASSUMPTIONS = {
    "vat": 0.12, "profit_tax": 0.15, "payroll_tax": 0.12,
    "sal_mgr": 600, "sal_acc": 700, "sal_log": 400, "sal_off": 500, "sal_dir": 1200,
    "rev_per_mgr": 350000, "rent_per_m2": 2.0, "trip_cost": 50, "floors": 2,
}

if "assumptions"    not in st.session_state: st.session_state.assumptions    = DEFAULT_ASSUMPTIONS.copy()
if "stock_override" not in st.session_state: st.session_state.stock_override = {}

def calc_norms(rev, pallets, area, gross_pct, a):
    gross       = rev * gross_pct
    mgr_count   = max(1, math.ceil(rev / a["rev_per_mgr"]))
    log_count   = max(1, math.floor(pallets / 5))
    personnel   = mgr_count*a["sal_mgr"] + a["sal_acc"] + log_count*a["sal_log"] + a["sal_off"] + a["sal_dir"]
    tax_vat     = gross     * a["vat"]
    tax_profit  = gross     * a["profit_tax"]
    tax_payroll = personnel * a["payroll_tax"]
    taxes       = tax_vat + tax_profit + tax_payroll
    norm_area   = area / a["floors"]
    rent        = norm_area * a["rent_per_m2"]
    trips       = max(1, math.ceil(pallets / 500) * 2)
    loading     = trips * a["trip_cost"]
    warehouse   = rent + loading
    fuel        = 200 + trips * 40
    mobile      = 100 + mgr_count * 30
    other       = fuel + mobile + 50 + rev * 0.001
    total       = personnel + taxes + warehouse + other
    return dict(rev=rev, gross=gross, personnel=personnel, mgr_count=mgr_count, log_count=log_count,
                tax_vat=tax_vat, tax_profit=tax_profit, tax_payroll=tax_payroll, taxes=taxes,
                norm_area=norm_area, rent=rent, trips=trips, loading=loading, warehouse=warehouse,
                fuel=fuel, mobile=mobile, other=other, total=total,
                net_profit=gross-total, pct_of_rev=total/rev if rev else 0)

def process_stock_file(df):
    df.columns = [str(c).strip() for c in df.columns]
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if any(x in cl for x in ["артикул","article","sku","код"]):             col_map["sku"] = c
        elif any(x in cl for x in ["остаток","qty","quantity","stock","кол"]):  col_map["qty"] = c
        elif any(x in cl for x in ["шт/поддон","поддон","pallet","шт/п"]):     col_map["ppu"] = c
        elif any(x in cl for x in ["объем","объём","volume","м³"]):             col_map["vol"] = c
    if "qty" not in col_map or "ppu" not in col_map:
        return None, "Не найдены колонки «Остаток (шт)» и «Шт/поддон»"
    df = df.rename(columns=col_map)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0)
    df["ppu"] = pd.to_numeric(df.get("ppu", 1), errors="coerce").fillna(1).replace(0, 1)
    total_pallets = int(np.ceil(df["qty"] / df["ppu"]).sum())
    area = round(math.ceil(total_pallets / math.floor(6.0/0.75)) * 0.322 * 1.4, 1)
    return {"pallets": total_pallets, "area": area, "sku_count": int((df["qty"]>0).sum())}, None

def build_excel_report(name, n, d):
    rows = [
        ("Выручка",           n["rev"],       n["rev"]/n["rev"]),
        ("Валовая прибыль",   n["gross"],     n["gross"]/n["rev"]),
        ("",                  None,           None),
        ("Персонал",          n["personnel"], n["personnel"]/n["rev"]),
        ("Налоги",            n["taxes"],     n["taxes"]/n["rev"]),
        ("Склад и логистика", n["warehouse"], n["warehouse"]/n["rev"]),
        ("Прочие расходы",    n["other"],     n["other"]/n["rev"]),
        ("ИТОГО РАСХОДЫ",     n["total"],     n["pct_of_rev"]),
        ("",                  None,           None),
        ("Чистая прибыль",    n["net_profit"],n["net_profit"]/n["rev"]),
    ]
    df = pd.DataFrame(rows, columns=["Статья","$/мес","% выручки"])
    df["$/мес"]     = df["$/мес"].apply(lambda x: f"${x:,.0f}" if x is not None else "")
    df["% выручки"] = df["% выручки"].apply(lambda x: f"{x*100:.2f}%" if x is not None else "")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Норматив")
    buf.seek(0)
    return buf

def build_stock_template():
    df = pd.DataFrame([
        ("FKN90014BEL-IN",   "Конд ВБ ARCSIJ3AW09BE Crystal Inv.",  40,  1, 0.423, 65, 93),
        ("FKN12021BEL/S-IN", "Конд ВБ SHVSIJ2AW12BE Sensei Inv.",  540,  1, 0.423, 65, 93),
        ("FKN12044BEL/A-IN", "Конд ВБ AVLSIQ1AW12BE Brugge Inv.", 3004,  1, 0.423, 65, 93),
        ("FTHD001076SER/D",  "Холод Samsung RB29 FERNDSA Серый",    87,   1, 0.380, 60, 167),
        ("FKV0760BEL",       "Кух вытяжка ART-0760 Белый Prima",    10,   2, 0.212, 60, 45),
    ], columns=["Артикул *","Описание","Остаток (шт) *","Шт/поддон *","Объем ед. (м³)","Ширина (см)","Высота (см)"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Сток дилера")
    buf.seek(0)
    return buf

def fmt(v):    return f"${v:,.0f}"
def fmtpct(v): return f"{v*100:.2f}%"
def get_dealer(name):
    d = DEALERS[name].copy()
    if name in st.session_state.stock_override:
        d.update(st.session_state.stock_override[name])
    return d

# ── SIDEBAR ──
with st.sidebar:
    st.markdown("### 📊 NormDealer")
    st.markdown("<div class='muted' style='font-size:11px;margin-bottom:16px'>Нормативная модель · 2026</div>", unsafe_allow_html=True)
    dealer_name = st.selectbox("Дилер", list(DEALERS.keys()))
    st.divider()
    st.markdown("**⚙️ Допущения**")
    with st.expander("💰 Оклады ($/мес)"):
        st.session_state.assumptions["sal_mgr"] = st.number_input("Менеджер",     value=st.session_state.assumptions["sal_mgr"], step=50)
        st.session_state.assumptions["sal_acc"] = st.number_input("Бухгалтер",    value=st.session_state.assumptions["sal_acc"], step=50)
        st.session_state.assumptions["sal_log"] = st.number_input("Логистика",    value=st.session_state.assumptions["sal_log"], step=50)
        st.session_state.assumptions["sal_off"] = st.number_input("Офис менеджер",value=st.session_state.assumptions["sal_off"], step=50)
        st.session_state.assumptions["sal_dir"] = st.number_input("Директор",     value=st.session_state.assumptions["sal_dir"], step=50)
    with st.expander("🏦 Налоги (%)"):
        st.session_state.assumptions["vat"]         = st.number_input("НДС",               value=st.session_state.assumptions["vat"]*100,        step=1.0) / 100
        st.session_state.assumptions["profit_tax"]  = st.number_input("Налог на прибыль",  value=st.session_state.assumptions["profit_tax"]*100,  step=1.0) / 100
        st.session_state.assumptions["payroll_tax"] = st.number_input("Зарплатный налог",  value=st.session_state.assumptions["payroll_tax"]*100, step=1.0) / 100
    with st.expander("🏭 Склад"):
        st.session_state.assumptions["rent_per_m2"] = st.number_input("Аренда ($/м²/мес)",  value=st.session_state.assumptions["rent_per_m2"], step=0.5)
        st.session_state.assumptions["floors"]      = st.number_input("Этажность",          value=st.session_state.assumptions["floors"], step=1, min_value=1)
        st.session_state.assumptions["trip_cost"]   = st.number_input("Стоимость рейса ($)",value=st.session_state.assumptions["trip_cost"], step=10)
    st.divider()
    st.markdown("<div class='mono'>● Сток синхронизирован</div>", unsafe_allow_html=True)

# ── MAIN ──
d = get_dealer(dealer_name)
n = calc_norms(d["rev"], d["pallets"], d["area"], d["gross_pct"], st.session_state.assumptions)
a = st.session_state.assumptions

col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(f"## {dealer_name}")
    st.markdown(f"<div class='muted'>SAP: {d['sap']} · Паллетомест: {d['pallets']:,} · Площадь: {d['area']:,.0f} м²</div>", unsafe_allow_html=True)
with col_h2:
    st.download_button("⬇ Скачать отчёт Excel", data=build_excel_report(dealer_name, n, d),
        file_name=f"норматив_{dealer_name.replace(' ','_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

st.divider()
tab1, tab2, tab3, tab4 = st.tabs(["📈 Дашборд", "📋 Детализация расходов", "📂 Загрузить сток", "⊞ Все дилеры"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Выручка / месяц",  fmt(d["rev"]),        delta="активный дилер")
    with c2: st.metric("Валовая прибыль",  fmt(n["gross"]),      delta=fmtpct(d["gross_pct"]) + " маржа")
    with c3: st.metric("Норм. расходы",    fmt(n["total"]),      delta=fmtpct(n["pct_of_rev"]) + " от выручки", delta_color="inverse")
    with c4: st.metric("Чистая прибыль",   fmt(n["net_profit"]), delta="✓ Жизнеспособен" if n["net_profit"]>0 else "⚠ Проверить")

    st.markdown("---")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Расходы по категориям**")
        cats = [("👤 Персонал",n["personnel"],"#5b9ef5"),("🏦 Налоги",n["taxes"],"#f0a832"),
                ("🏭 Склад и логистика",n["warehouse"],"#e85c3e"),("⚡ Прочие",n["other"],"#c8f04a")]
        mx = max(c[1] for c in cats)
        for cat, val, color in cats:
            st.markdown(f"""<div style="background:#161719;border:1px solid rgba(255,255,255,0.07);border-radius:10px;
                padding:14px 16px;margin-bottom:8px;display:flex;align-items:center;gap:14px">
                <span style="font-size:18px;width:24px">{cat.split()[0]}</span>
                <div style="flex:1">
                    <div style="font-size:13px;font-weight:600;margin-bottom:6px">{' '.join(cat.split()[1:])}</div>
                    <div style="height:4px;background:rgba(255,255,255,0.07);border-radius:2px">
                        <div style="height:4px;width:{int(val/mx*100)}%;background:{color};border-radius:2px"></div></div></div>
                <div style="text-align:right">
                    <div style="font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:600">{fmt(val)}</div>
                    <div style="font-size:11px;color:#7a7975">{fmtpct(val/d['rev'])}</div></div></div>""", unsafe_allow_html=True)
    with right:
        st.markdown("**Статус нормативов**")
        if   n["pct_of_rev"] < 0.025: st.success(f"✓ Расходы {fmtpct(n['pct_of_rev'])} — в норме (< 2.5%)")
        elif n["pct_of_rev"] < 0.04:  st.warning(f"⚠ Расходы {fmtpct(n['pct_of_rev'])} — немного выше ориентира")
        else:                          st.error(f"✗ Расходы {fmtpct(n['pct_of_rev'])} — выше нормы")
        if n["net_profit"] > 0: st.success(f"✓ Чистая прибыль: {fmt(n['net_profit'])}/мес")
        else:                   st.error(f"✗ Убыток: {fmt(n['net_profit'])}/мес")
        st.info(f"ℹ Нормативная площадь: {n['norm_area']:.0f} м²  ·  Рейсов/мес: {n['trips']}")
        st.markdown("---")
        for k, v in {"Паллетомест": f"{d['pallets']:,}", "Площадь (м²)": f"{d['area']:,.0f}",
                     "Норм. площадь (м²)": f"{n['norm_area']:.0f}", "Аренда / мес": fmt(n["rent"])}.items():
            st.markdown(f"""<div style="display:flex;justify-content:space-between;padding:7px 0;
                border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px">
                <span style="color:#7a7975">{k}</span>
                <span style="font-family:'IBM Plex Mono',monospace;color:#c8f04a">{v}</span></div>""", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Структура затрат vs. норматив**")
    st.dataframe(pd.DataFrame([
        {"Категория":"Персонал",         "$/мес":fmt(n["personnel"]),"% выручки":fmtpct(n["personnel"]/d["rev"]),"Ориентир":"0.8–1.4%","Статус":"✓" if n["personnel"]/d["rev"]<=0.014 else "⚠"},
        {"Категория":"Налоги",           "$/мес":fmt(n["taxes"]),    "% выручки":fmtpct(n["taxes"]/d["rev"]),    "Ориентир":"0.4–0.8%","Статус":"✓" if n["taxes"]/d["rev"]    <=0.008 else "⚠"},
        {"Категория":"Склад/логистика",  "$/мес":fmt(n["warehouse"]),"% выручки":fmtpct(n["warehouse"]/d["rev"]),"Ориентир":"0.5–0.9%","Статус":"✓" if n["warehouse"]/d["rev"]<=0.009 else "⚠"},
        {"Категория":"Прочее",           "$/мес":fmt(n["other"]),    "% выручки":fmtpct(n["other"]/d["rev"]),    "Ориентир":"0.3–0.7%","Статус":"✓" if n["other"]/d["rev"]    <=0.007 else "⚠"},
        {"Категория":"ИТОГО",            "$/мес":fmt(n["total"]),    "% выручки":fmtpct(n["pct_of_rev"]),        "Ориентир":"2.0–3.5%","Статус":"✓" if n["pct_of_rev"]        <=0.035 else "⚠"},
    ]), use_container_width=True, hide_index=True)

with tab2:
    st.markdown("### Детализация по статьям")
    for title, total, rows in [
        ("1. Персонал", n["personnel"], [
            (f"Менеджеры ({n['mgr_count']} × ${a['sal_mgr']})", n["mgr_count"]*a["sal_mgr"]),
            (f"Бухгалтер (1 × ${a['sal_acc']})",                a["sal_acc"]),
            (f"Логистика ({n['log_count']} × ${a['sal_log']})", n["log_count"]*a["sal_log"]),
            (f"Офис менеджер (1 × ${a['sal_off']})",            a["sal_off"]),
            (f"Директор (1 × ${a['sal_dir']})",                 a["sal_dir"]),
        ]),
        ("2. Налоги", n["taxes"], [
            (f"НДС ({fmt(n['gross'])} × {a['vat']*100:.0f}%)",                      n["tax_vat"]),
            (f"Налог на прибыль ({fmt(n['gross'])} × {a['profit_tax']*100:.0f}%)",  n["tax_profit"]),
            (f"Зарплатный налог ({fmt(n['personnel'])} × {a['payroll_tax']*100:.0f}%)", n["tax_payroll"]),
        ]),
        ("3. Склад и логистика", n["warehouse"], [
            (f"Аренда ({n['norm_area']:.0f} м² × ${a['rent_per_m2']}/м²)", n["rent"]),
            (f"Погрузка/разгрузка ({n['trips']} рейсов × ${a['trip_cost']})", n["loading"]),
        ]),
        ("4. Прочие расходы", n["other"], [
            ("Топливо",          n["fuel"]),
            ("Мобильная связь",  n["mobile"]),
            ("Интернет",         50),
            (f"Банк ({fmt(d['rev'])} × 0.1%)", d["rev"]*0.001),
        ]),
    ]:
        with st.expander(f"{title}  —  {fmt(total)}/мес  ({fmtpct(total/d['rev'])} выручки)", expanded=True):
            st.dataframe(pd.DataFrame(
                [(lb, f"${v:,.0f}", f"{v/d['rev']*100:.3f}%") for lb,v in rows] +
                [("── Итого", f"${total:,.0f}", f"{total/d['rev']*100:.3f}%")],
                columns=["Статья","$/мес","% выручки"]), use_container_width=True, hide_index=True)

with tab3:
    st.markdown("### Загрузить данные стока")
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        st.markdown("**Загрузка Excel файла**")
        uploaded = st.file_uploader("Перетащите .xlsx файл", type=["xlsx","xls"], label_visibility="collapsed")
        if uploaded:
            try:
                df_raw = pd.read_excel(uploaded, header=None)
                header_row = 0
                for i, row in df_raw.iterrows():
                    if any(x in " ".join(str(v).lower() for v in row) for x in ["артикул","остаток","sku"]):
                        header_row = i; break
                result, err = process_stock_file(pd.read_excel(uploaded, header=header_row))
                if err: st.error(f"❌ {err}")
                else:
                    st.success(f"✓ Файл обработан: {result['sku_count']} SKU с остатком")
                    r1, r2 = st.columns(2)
                    with r1: st.metric("Паллетомест", f"{result['pallets']:,}")
                    with r2: st.metric("Расч. площадь", f"{result['area']:,.0f} м²")
                    if st.button("✓ Применить к модели", type="primary"):
                        st.session_state.stock_override[dealer_name] = {"pallets": result["pallets"], "area": result["area"]}
                        st.success("Данные обновлены.")
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")
        st.markdown("---")
        st.download_button("⬇ Скачать шаблон", data=build_stock_template(),
            file_name="шаблон_сток_дилера.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    with col_up2:
        st.markdown("**Требования к файлу**")
        st.dataframe(pd.DataFrame([
            {"Колонка":"Артикул",       "Тип":"текст","Пример":"FKN90014BEL-IN","Обязательно":"✓ Да"},
            {"Колонка":"Остаток (шт)",  "Тип":"число","Пример":"42",            "Обязательно":"✓ Да"},
            {"Колонка":"Шт/поддон",     "Тип":"число","Пример":"1",             "Обязательно":"✓ Да"},
            {"Колонка":"Описание",      "Тип":"текст","Пример":"Конд ВБ...",    "Обязательно":"Нет"},
            {"Колонка":"Объем ед.(м³)", "Тип":"число","Пример":"0.423",        "Обязательно":"Нет"},
        ]), use_container_width=True, hide_index=True)
        st.info("💡 Названия колонок определяются автоматически.")
        if dealer_name in st.session_state.stock_override:
            ovr = st.session_state.stock_override[dealer_name]
            st.success(f"✓ Загружено: {ovr['pallets']:,} паллетомест, {ovr['area']:,.0f} м²")
            if st.button("✕ Сбросить к исходным"):
                del st.session_state.stock_override[dealer_name]; st.rerun()

with tab4:
    st.markdown("### Все дилеры")
    all_rows = []
    for name in DEALERS:
        d_ = get_dealer(name)
        n_ = calc_norms(d_["rev"], d_["pallets"], d_["area"], d_["gross_pct"], st.session_state.assumptions)
        all_rows.append({"Дилер":name,"Выручка/мес":fmt(d_["rev"]),"Норм. расходы":fmt(n_["total"]),
            "% выручки":fmtpct(n_["pct_of_rev"]),"Паллетомест":f"{d_['pallets']:,}",
            "Чистая прибыль":fmt(n_["net_profit"]),"Статус":"✓ Жизнеспособен" if n_["net_profit"]>0 else "⚠ Убыток"})
    df_all = pd.DataFrame(all_rows)
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Дилеров", len(DEALERS))
    with c2: st.metric("Средняя выручка", fmt(sum(DEALERS[n]["rev"] for n in DEALERS)/len(DEALERS)))
    with c3:
        avg_pct = sum(calc_norms(DEALERS[n]["rev"],DEALERS[n]["pallets"],DEALERS[n]["area"],
                      DEALERS[n]["gross_pct"],st.session_state.assumptions)["pct_of_rev"] for n in DEALERS)/len(DEALERS)
        st.metric("Средний % расходов", fmtpct(avg_pct))
    st.markdown("---")
    st.dataframe(df_all, use_container_width=True, hide_index=True)
    buf_all = io.BytesIO()
    with pd.ExcelWriter(buf_all, engine="openpyxl") as writer:
        df_all.to_excel(writer, index=False, sheet_name="Все дилеры")
    buf_all.seek(0)
    st.download_button("⬇ Экспорт в Excel", data=buf_all, file_name="все_дилеры_нормативы.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

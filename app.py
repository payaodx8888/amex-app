import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
import traceback

# --- 0. ページ設定＆デザイン（タイトルだけ黒×金、他はスッキリ標準） ---
st.set_page_config(layout="wide", page_title="THE SETTLEMENT | AMEX", page_icon="💳")

st.markdown("""
<style>
/* タイトルバナーだけ高級感のある黒×金 */
.luxury-banner {
    background: linear-gradient(135deg, #0a0a0a 0%, #1c1c1c 50%, #050505 100%);
    border: 1px solid #d4af37;
    border-radius: 8px;
    padding: 14px 10px;
    text-align: center;
    margin-bottom: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}
.luxury-title {
    color: #d4af37;
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 20px;
    font-weight: bold;
    letter-spacing: 2px;
    margin: 0;
}
.luxury-subtitle {
    color: #b89f5d;
    font-size: 9px;
    letter-spacing: 1px;
    margin-top: 3px;
}
/* 操作ボタンが画面外に行かないよう、最上部に固定するコンテナのスタイル */
.sticky-actions {
    position: sticky;
    top: 0;
    z-index: 999;
    background-color: var(--background-color);
    padding: 8px 0;
    border-bottom: 1px solid #e0e0e0;
    margin-bottom: 10px;
}
</style>
<div class="luxury-banner">
    <div class="luxury-title">THE SETTLEMENT</div>
    <div class="luxury-subtitle">AMEX PRIVATE LEDGER & ANALYTICS</div>
</div>
""", unsafe_allow_html=True)

# --- 1. セッション状態の初期化 ---
if "pending_changes" not in st.session_state:
    st.session_state.pending_changes = {}

# --- 2. Google スプレッドシート接続 ---
@st.cache_resource
def init_gspread():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            return gspread.service_account_from_dict(creds_dict)
    except Exception:
        pass
    return gspread.service_account(filename=r'C:\Users\tsu81\OneDrive\Desktop\クレカ精算\key.json')

try:
    client = init_gspread()
    sheet = client.open("アメックス明細_仕分けDB").sheet1
except Exception as e:
    st.error("🚨 スプレッドシートに接続できませんでした。")
    st.code(traceback.format_exc(), language="python")
    st.stop()

# --- 3. ユーティリティ関数 ---
def calc_billing_month(date_str):
    try:
        dt = pd.to_datetime(str(date_str), errors='coerce')
        if pd.isna(dt):
            return "日付不明"
        if dt.day > 5:
            if dt.month == 12:
                return f"{dt.year + 1}年01月請求"
            else:
                return f"{dt.year}年{dt.month + 1:02d}月請求"
        else:
            return f"{dt.year}年{dt.month:02d}月請求"
    except:
        return "日付不明"

def clean_merchant_name(raw_name):
    """アメックスの長すぎる住所やカタカナをスッキリさせる簡易クレンジング"""
    name = str(raw_name)
    # よくある不要な文字列を削る
    for word in [" ｶﾌﾞｼｷｶﾞｲｼ", " ﾄｳｷｮｳ", " ｼﾌﾞﾔ", " ｼﾝｼﾞｭｸ", "ｼﾞｬﾊﾟﾝ", "ｺｳｷﾞｮｳ"]:
        name = name.replace(word, "")
    return name.strip()

def clean_and_format_csv(uploaded_file):
    try:
        new_df = pd.read_csv(uploaded_file, encoding="shift-jis")
    except:
        new_df = pd.read_csv(uploaded_file, encoding="utf-8")
        
    if "金額" in new_df.columns:
        new_df["金額"] = new_df["金額"].astype(str).str.replace(',', '').str.replace('¥', '').str.replace(' ', '').astype(float).fillna(0).astype(int)
        
    if "仕分け" not in new_df.columns:
        new_df.insert(0, "仕分け", "未分類")
        new_df.loc[new_df["金額"] < 0, "仕分け"] = "集計外"
        
    # クレンジング用の列を準備
    if "ご利用内容" in new_df.columns:
        new_df["表示名"] = new_df["ご利用内容"].apply(clean_merchant_name)
    
    keep_columns = ["仕分け", "金額", "表示名", "ご利用内容", "ご利用日", "カード会員様名"]
    keep_columns = [col for col in keep_columns if col in new_df.columns]
    new_df = new_df[keep_columns]
    return new_df

def save_changes_to_cloud(changes_dict, cols_order):
    latest_records = sheet.get_all_records()
    latest_df = pd.DataFrame(latest_records)
    latest_df = latest_df[cols_order]

    for idx, choice in changes_dict.items():
        if idx < len(latest_df):
            if choice == "🔄 未分類に戻す":
                latest_df.loc[idx, "仕分け"] = "未分類"
            elif choice != "未分類":
                latest_df.loc[idx, "仕分け"] = choice

    sheet.clear()
    data_to_write = [latest_df.columns.values.tolist()] + latest_df.values.tolist()
    try:
        sheet.update(range_name='A1', values=data_to_write)
    except:
        sheet.update('A1', data_to_write)

# --- 4. データの読み込みと整備 ---
existing_data = sheet.get_all_records()

if not existing_data:
    st.info("💡 スプレッドシートにまだデータがありません。最初のCSVをアップロードして初期化してください。")
    uploaded_file = st.file_uploader("アメックスのCSVを選択", type="csv")
    
    if uploaded_file is not None:
        df = clean_and_format_csv(uploaded_file)
        if "ご利用日" in df.columns:
            df = df.sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
            
        data_to_write = [df.columns.values.tolist()] + df.values.tolist()
        try:
            sheet.update(range_name='A1', values=data_to_write)
        except:
            sheet.update('A1', data_to_write)
            
        st.success("✅ 初期保存が完了しました！")
        st.rerun()

else:
    df = pd.DataFrame(existing_data)
    
    # 古いデータ構造への配慮（表示名列がなければ作る）
    if "表示名" not in df.columns and "ご利用内容" in df.columns:
        df.insert(2, "表示名", df["ご利用内容"].apply(clean_merchant_name))

    preferred_order = ["仕分け", "金額", "表示名", "ご利用内容", "ご利用日", "カード会員様名"]
    cols = [c for c in preferred_order if c in df.columns] + [c for c in df.columns if c not in preferred_order]
    df = df[cols]
    
    for idx, choice in st.session_state.pending_changes.items():
        if idx < len(df):
            df.loc[idx, "仕分け"] = "未分類" if choice == "🔄 未分類に戻す" else choice

    df["金額"] = pd.to_numeric(df["金額"], errors='coerce').fillna(0).astype(int)
    df["請求月"] = df["ご利用日"].apply(calc_billing_month)
    
    billing_months = sorted([m for m in df["請求月"].unique() if m != "日付不明"], reverse=True)
    if "日付不明" in df["請求月"].unique():
        billing_months.append("日付不明")
    billing_options = billing_months + ["すべて表示"]

    # 画面上部：請求月の選択 ＆ 保存ボタン（常に一番上に固定表示）
    st.markdown('<div class="sticky-actions">', unsafe_allow_html=True)
    top_c1, top_c2, top_c3 = st.columns([4, 3, 3])
    with top_c1:
        selected_month = st.selectbox("📅 対象の請求月（毎月5日締め）", options=billing_options, index=0, label_visibility="collapsed")
    with top_c2:
        if st.button("☁️ 変更をクラウドに保存", type="primary", use_container_width=True):
            with st.spinner("保存中..."):
                save_changes_to_cloud(st.session_state.pending_changes, cols)
                st.session_state.pending_changes.clear()
            st.success("✅ 保存しました！")
            st.rerun()
    with top_c3:
        if st.button("🔄 最新状況に更新", use_container_width=True):
            st.session_state.pending_changes.clear()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 5. メイン画面：3つのタブ ---
    tab1, tab2, tab3 = st.tabs(["📋 一覧仕分け", "📊 月別精算", "📈 推移・CSV追加"])

    # ================= タブ1：一覧表サクサク選択式 =================
    with tab1:
        if selected_month != "すべて表示":
            month_df = df[df["請求月"] == selected_month].copy()
        else:
            month_df = df.copy()

        c_filter, c_unclass = st.columns([6, 4])
        with c_filter:
            only_unclassified = st.toggle("🔍「未分類」のみ表示", value=True)
        with c_unclass:
            unclass_count = len(month_df[month_df["仕分け"] == "未分類"])
            st.caption(f"⚠️ 未分類の残り: {unclass_count} 件")

        table_df = month_df[month_df["仕分け"] == "未分類"].copy() if only_unclassified else month_df.copy()
        display_df = table_df[cols].copy()

        st.caption("💡 表の「仕分け」列からプルダウンで変更できます。変更後は一番上の「☁️ 変更をクラウドに保存」を押してください。")
        
        edited_df = st.data_editor(
            display_df,
            column_config={
                "仕分け": st.column_config.SelectboxColumn(
                    "仕分け",
                    options=["未分類", "共有", "ハヤト", "マナ", "不明(保留)", "集計外", "🔄 未分類に戻す"],
                    required=True,
                    width="small"
                ),
                "金額": st.column_config.NumberColumn("金額", format="¥%d", disabled=True, width="small"),
                "表示名": st.column_config.TextColumn("お店・内容（スッキリ）", disabled=True, width="medium"),
                "ご利用内容": st.column_config.TextColumn("正規データ（元表記）", disabled=True, width="medium"),
                "ご利用日": st.column_config.TextColumn("利用日", disabled=True, width="small"),
                "カード会員様名": st.column_config.TextColumn("会員", disabled=True, width="small")
            },
            hide_index=True,
            use_container_width=True,
            height=500
        )

        # 編集内容を一時メモリに反映
        for idx in edited_df.index:
            new_choice = edited_df.loc[idx, "仕分け"]
            orig_choice = df.loc[idx, "仕分け"]
            if new_choice != orig_choice:
                st.session_state.pending_changes[idx] = new_choice

    # ================= タブ2：月別精算 =================
    with tab2:
        st.subheader(f"📊 {selected_month} の集計")
        
        if selected_month != "すべて表示":
            month_df = df[df["請求月"] == selected_month].copy()
        else:
            month_df = df.copy()
            
        calc_df = month_df[month_df["仕分け"] != "集計外"]
        summary = calc_df.groupby("仕分け")["金額"].sum().reset_index()
        
        def get_sum(category):
            val = summary[summary["仕分け"] == category]["金額"].sum()
            return int(val) if pd.notna(val) else 0

        total_shared = get_sum("共有")
        total_hayato = get_sum("ハヤト")
        total_mana = get_sum("マナ")
        total_unknown = get_sum("不明(保留)")
        total_unclassified = get_sum("未分類")

        if total_unclassified > 0:
            st.warning(f"⚠️ 未分類の明細が **¥ {total_unclassified:,}** 残っています")
        else:
            st.success("✨ この月の仕分けはすべて完了しています！")

        m1, m2 = st.columns(2)
        m1.metric("👫 共有", f"¥ {total_shared:,}")
        m2.metric("❓ 不明(保留)", f"¥ {total_unknown:,}")
        
        m3, m4 = st.columns(2)
        m3.metric("👨 ハヤト", f"¥ {total_hayato:,}")
        m4.metric("👩 マナ", f"¥ {total_mana:,}")

        summary_for_pie = summary[summary["金額"] > 0]
        if not summary_for_pie.empty:
            color_map = {
                "共有": "#D4AF37",
                "ハヤト": "#4A90E2",
                "マナ": "#E26A6A",
                "不明(保留)": "#8E8E93",
                "未分類": "#555555"
            }
            fig = px.pie(
                summary_for_pie, 
                values="金額", 
                names="仕分け", 
                hole=0.45,
                color="仕分け",
                color_discrete_map=color_map
            )
            fig.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=300)
            st.plotly_chart(fig, use_container_width=True)

    # ================= タブ3：月次推移 ＆ CSV追加 =================
    with tab3:
        st.subheader("📈 月ごとの金額推移（5日締め基準）")
        
        trend_df = df[(df["仕分け"] != "集計外") & (df["請求月"] != "日付不明")].copy()
        if not trend_df.empty:
            monthly_summary = trend_df.groupby(["請求月", "仕分け"])["金額"].sum().reset_index()
            monthly_summary = monthly_summary.sort_values("請求月", ascending=True)
            
            color_map = {
                "共有": "#D4AF37",
                "ハヤト": "#4A90E2",
                "マナ": "#E26A6A",
                "不明(保留)": "#8E8E93",
                "未分類": "#555555"
            }
            fig_bar = px.bar(
                monthly_summary,
                x="請求月",
                y="金額",
                color="仕分け",
                barmode="group",
                color_discrete_map=color_map
            )
            fig_bar.update_layout(
                xaxis_title="",
                yaxis_title="金額 (円)",
                margin=dict(t=20, b=20, l=0, r=0),
                height=350,
                legend_title_text=""
            )
            st.plotly_chart(fig_bar, use_container_width=True)
            
            st.markdown("##### 📋 月別・項目別の一覧表")
            pivot_df = monthly_summary.pivot(index="請求月", columns="仕分け", values="金額").fillna(0).astype(int)
            pivot_df["合計"] = pivot_df.sum(axis=1)
            pivot_df = pivot_df.sort_index(ascending=False)
            st.dataframe(pivot_df.style.format("¥{:,}"), use_container_width=True)
        else:
            st.info("推移を表示できるデータがまだありません。")

        st.markdown("---")
        st.subheader("➕ 新しい月のCSVを追加（蓄積）する")
        st.caption("来月以降のCSVをアップロードすると、過去の仕分けデータを残したまま、新しい明細だけを自動判別して追加します。")
        
        new_csv = st.file_uploader("追加するアメックスのCSVを選択", type="csv", key="append_csv")
        if new_csv is not None:
            if st.button("📥 重複を除いてクラウドに追加する", type="primary", use_container_width=True):
                with st.spinner("新しい明細を分析して追加中..."):
                    new_df = clean_and_format_csv(new_csv)
                    
                    latest_records = sheet.get_all_records()
                    base_df = pd.DataFrame(latest_records)
                    base_df = base_df[cols]
                    
                    check_cols = ["ご利用日", "ご利用内容", "金額", "カード会員様名"]
                    check_cols = [c for c in check_cols if c in base_df.columns and c in new_df.columns]
                    
                    base_keys = set(base_df[check_cols].astype(str).agg('-'.join, axis=1))
                    new_df["_key"] = new_df[check_cols].astype(str).agg('-'.join, axis=1)
                    
                    to_add_df = new_df[~new_df["_key"].isin(base_keys)].drop(columns=["_key"])
                    
                    if to_add_df.empty:
                        st.warning("⚠️ アップロードされたCSVの明細は、すべて既に登録済みです。")
                    else:
                        combined_df = pd.concat([base_df, to_add_df], ignore_index=True)
                        if "ご利用日" in combined_df.columns:
                            combined_df = combined_df.sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
                        
                        sheet.clear()
                        data_to_write = [combined_df.columns.values.tolist()] + combined_df.values.tolist()
                        try:
                            sheet.update(range_name='A1', values=data_to_write)
                        except:
                            sheet.update('A1', data_to_write)
                            
                        st.success(f"🎉 新しく {len(to_add_df)} 件の明細を追加しました！")
                        st.rerun()

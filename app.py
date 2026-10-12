import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import traceback

st.set_page_config(layout="wide", page_title="アメックス爆速仕分け")
st.title("💳 アメックス明細 爆速仕分けツール")

# --- 1. Google スプレッドシートに接続（クラウド＆PC両対応版） ---
@st.cache_resource
def init_gspread():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # クラウドの金庫（st.secrets）に鍵があればそれを使い、なければPCのkey.jsonを使う
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(r'C:\Users\tsu81\OneDrive\Desktop\クレカ精算\key.json', scope)
        
    return gspread.authorize(creds)

try:
    client = init_gspread()
    SPREADSHEET_ID = "1r-VtdWM5cpTC_Ib2pA6QVLnH9lZsmerzJzZVvSi940s"
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1
except Exception as e:
    st.error("🚨 エラー: Googleスプレッドシートに接続できませんでした。")
    st.code(traceback.format_exc(), language="python")
    st.stop()

# --- 2. データの読み込み ---
existing_data = sheet.get_all_records()

if not existing_data:
    st.info("💡 スプレッドシートにまだデータがありません。アメックスのCSVをアップロードして初期化してください。")
    uploaded_file = st.file_uploader("アメックスのCSVファイルをアップロードしてください", type="csv")
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file, encoding="shift-jis")
        except:
            df = pd.read_csv(uploaded_file, encoding="utf-8")
        
        if "金額" in df.columns:
            df["金額"] = df["金額"].astype(str).str.replace(',', '').str.replace('¥', '').str.replace(' ', '').astype(float).fillna(0).astype(int)

        if "仕分け" not in df.columns:
            df.insert(0, "仕分け", "未分類")
            df.loc[df["金額"] < 0, "仕分け"] = "集計外"
        
        keep_columns = ["仕分け", "ご利用日", "ご利用内容", "金額", "カード会員様名"] 
        keep_columns = [col for col in keep_columns if col in df.columns]
        df = df[keep_columns]
        
        if "ご利用日" in df.columns:
            df = df.sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
            
        data_to_write = [df.columns.values.tolist()] + df.values.tolist()
        try:
            sheet.update(range_name='A1', values=data_to_write)
        except:
            sheet.update('A1', data_to_write)
            
        st.success("✅ クラウドへの初期保存が完了しました！ページを再読み込みしてください。")

else:
    st.write("▼ 一覧表をタップして仕分け。終わったら一番下の「クラウドに保存」ボタンを押してください。")
    df = pd.DataFrame(existing_data)
    
    col1, col2 = st.columns([7, 3])

    with col1:
        edited_df = st.data_editor(
            df,
            column_config={
                "仕分け": st.column_config.SelectboxColumn(
                    "仕分け",
                    options=["未分類", "共有", "ハヤト", "マナ", "不明(保留)", "集計外"],
                    required=True,
                )
            },
            use_container_width=True,
            height=500
        )

    with col2:
        st.subheader("📊 リアルタイム集計")
        target_column = "金額" 
        
        if target_column in edited_df.columns:
            edited_df[target_column] = pd.to_numeric(edited_df[target_column], errors='coerce').fillna(0).astype(int)
            calc_df = edited_df[edited_df["仕分け"] != "集計外"]
            summary = calc_df.groupby("仕分け")[target_column].sum().reset_index()
            
            def get_sum(category):
                val = summary[summary["仕分け"] == category][target_column].sum()
                return val if pd.notna(val) else 0

            total_shared = get_sum("共有")
            total_hayato = get_sum("ハヤト")
            total_mana = get_sum("マナ")
            total_unknown = get_sum("不明(保留)")
            total_unclassified = get_sum("未分類")

            m1, m2 = st.columns(2)
            m1.metric("👫 共有", f"¥ {total_shared:,}")
            m2.metric("❓ 不明(保留)", f"¥ {total_unknown:,}")
            
            m3, m4 = st.columns(2)
            m3.metric("👨 ハヤト", f"¥ {total_hayato:,}")
            m4.metric("👩 マナ", f"¥ {total_mana:,}")
            
            st.metric("⚠️ 未分類（残り）", f"¥ {total_unclassified:,}")

            summary_for_pie = summary[summary[target_column] > 0]
            
            if not summary_for_pie.empty:
                fig = px.pie(
                    summary_for_pie, 
                    values=target_column, 
                    names="仕分け", 
                    title="📊 分類結果",
                    hole=0.4
                )
                fig.update_layout(margin=dict(t=40, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("グラフを表示できるデータがありません。")

    st.markdown("---")
    
    if st.button("☁️ この状態をクラウド（スプレッドシート）に保存する", type="primary"):
        with st.spinner("クラウドに保存中..."):
            sheet.clear()
            data_to_write = [edited_df.columns.values.tolist()] + edited_df.values.tolist()
            try:
                sheet.update(range_name='A1', values=data_to_write)
            except:
                sheet.update('A1', data_to_write)
        st.success("✅ クラウドに保存しました！")
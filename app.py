import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.auth.transport.requests import AuthorizedSession
import urllib.parse
import re
import io
import traceback

# --- 0. ページ設定＆デザイン（タイトルだけ黒×金、操作パネルは上部固定） ---
st.set_page_config(layout="wide", page_title="THE SETTLEMENT | AMEX", page_icon="💳")

st.markdown("""
<style>
/* タイトルバナーだけ高級感のある黒×金 */
.luxury-banner {
    background: linear-gradient(135deg, #0a0a0a 0%, #1c1c1c 50%, #050505 100%);
    border: 1px solid #d4af37;
    border-radius: 8px;
    padding: 12px 10px;
    text-align: center;
    margin-bottom: 10px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}
.luxury-title {
    color: #d4af37;
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 20px;
    font-weight: bold;
    letter-spacing: 3px;
    margin: 0;
}
.luxury-subtitle {
    color: #b89f5d;
    font-size: 9px;
    letter-spacing: 1.5px;
    margin-top: 2px;
}

/* ★ 操作ボタンパネルを画面上部にピタッと固定（スクロールしても消えない） */
div[data-testid="stVerticalBlock"] > div:has(div.fixed-action-bar) {
    position: sticky;
    top: 2.8rem;
    z-index: 999;
    background-color: var(--background-color, #ffffff);
    padding: 10px 12px;
    border: 2px solid #d4af37;
    border-radius: 10px;
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
    margin-bottom: 12px;
}

/* 選択中の明細プレビューボックス */
.target-box {
    background-color: #fff9db;
    border-left: 5px solid #f59f00;
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 8px;
    color: #1a1a1a;
}
.target-main {
    font-size: 16px;
    font-weight: bold;
    color: #111111;
}
.target-raw {
    font-size: 11px;
    color: #666666;
    margin-top: 3px;
}
</style>
<div class="luxury-banner">
<div class="luxury-title">THE SETTLEMENT</div>
<div class="luxury-subtitle">AMEX PRIVATE LEDGER & ANALYTICS</div>
</div>
""", unsafe_allow_html=True)

# --- 1. セッション状態の初期化 ---
if "pending_changes" not in st.session_state:
    st.session_state.pending_changes = {}  # {行index: "分類"}
if "history_stack" not in st.session_state:
    st.session_state.history_stack = []    # Undo履歴 [(対象indexリスト, {変更前状態})]
if "cursor_idx" not in st.session_state:
    st.session_state.cursor_idx = None     # 現在注目している基準行
if "selected_indices" not in st.session_state:
    st.session_state.selected_indices = [] # 現在強調（ハイライト）されている行リスト
if "table_key" not in st.session_state:
    st.session_state.table_key = 0         # テーブル選択リセット用カウンター

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

# --- 3. ユーティリティ関数（5日締め計算 ＆ アメックス文字列クレンジング） ---
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

def format

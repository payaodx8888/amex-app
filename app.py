import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.auth.transport.requests import AuthorizedSession
import datetime
import re
import io
import traceback

# --- 0. ページ設定＆デザイン ---
st.set_page_config(layout="wide", page_title="THE SETTLEMENT | AMEX", page_icon="💳")

st.markdown("""
<style>
/* タイトルバナーのみ黒×金のラグジュアリー仕様 */
.luxury-banner {
    background: linear-gradient(135deg, #0a0a0a 0%, #1c1c1c 50%, #050505 100%);
    border: 1px solid #d4af37;
    border-radius: 8px;
    padding: 8px 10px;
    text-align: center;
    margin-bottom: 6px;
    box-shadow: 0 3px 10px rgba(0, 0, 0, 0.2);
}
.luxury-title {
    color: #d4af37;
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 18px;
    font-weight: bold;
    letter-spacing: 3px;
    margin: 0;
}
.luxury-subtitle {
    color: #b89f5d;
    font-size: 8px;
    letter-spacing: 1.5px;
    margin-top: 1px;
}

/* ★ 仕分けタブの操作バーだけを画面上部にピタッと固定 */
div[data-testid="stVerticalBlock"]:has(div.fixed-action-bar):not(:has(div[data-testid="stVerticalBlock"] div.fixed-action-bar)) {
    position: sticky;
    top: 2.6rem;
    z-index: 999;
    background-color: var(--background-color, #ffffff);
    padding: 6px 6px;
    border-bottom: 2px solid #d4af37;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
    margin-bottom: 6px;
}

/* ★ スマホでも「最上部の月選択バー」と「仕分けボタンバー」だけは横1列を維持 */
div[data-testid="stVerticalBlock"]:has(div.nowrap-bar):not(:has(div[data-testid="stVerticalBlock"] div.nowrap-bar)) div[data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 0.25rem !important;
    align-items: center !important;
}
div[data-testid="stVerticalBlock"]:has(div.nowrap-bar):not(:has(div[data-testid="stVerticalBlock"] div.nowrap-bar)) div[data-testid="stHorizontalBlock"] > div {
    min-width: 0px !important;
    width: auto !important;
    flex: 1 1 0% !important;
}

/* 精算完了・未完了のステータスバナー */
.status-badge-done {
    background-color: #ebfbee;
    border: 2px solid #2b8a3e;
    color: #1b5e20;
    border-radius: 8px;
    padding: 10px 14px;
    font-weight: bold;
    font-size: 15px;
    text-align: center;
    margin-bottom: 10px;
}
.status-badge-pending {
    background-color: #fff9db;
    border: 2px solid #f59f00;
    color: #7c4d00;
    border-radius: 8px;
    padding: 10px 14px;
    font-weight: bold;
    font-size: 15px;
    text-align: center;
    margin-bottom: 10px;
}

/* 月別精算：クレカ＆現金の総額照合バー */
.total-check-box {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-top: 3px solid #343a40;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
}
.total-check-label {
    font-size: 12px;
    color: #555555;
    font-weight: bold;
}
.total-check-val {
    font-size: 20px;
    font-weight: 800;
    color: #111111;
    margin-top: 2px;
}

/* 月別精算：最終振込額のハイライトカード */
.settlement-card {
    background: linear-gradient(135deg, #141414 0%, #242424 100%);
    border-left: 5px solid #d4af37;
    border-radius: 8px;
    padding: 14px 16px;
    color: #ffffff;
    margin-bottom: 10px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.15);
}
.settlement-name {
    color: #d4af37;
    font-size: 14px;
    font-weight: bold;
}
.settlement-amount {
    color: #ffffff;
    font-size: 28px;
    font-weight: 800;
    margin: 4px 0;
}
.settlement-detail {
    color: #cccccc;
    font-size: 12px;
    margin-top: 4px;
}

/* スマホ画面での余白と固定バー・月選択プルダウンの最適化 */
@media (max-width: 900px) {
    .block-container {
        padding-left: 0.4rem !important;
        padding-right: 0.4rem !important;
        padding-top: 0.8rem !important;
    }
    div[data-testid="stVerticalBlock"]:has(div.fixed-action-bar):not(:has(div[data-testid="stVerticalBlock"] div.fixed-action-bar)) {
        top: 2.0rem !important;
        padding: 4px 2px !important;
    }
    div[data-testid="stVerticalBlock"]:has(div.nowrap-bar):not(:has(div[data-testid="stVerticalBlock"] div.nowrap-bar)) div[data-testid="stButton"] button {
        padding: 0.15rem 0.08rem !important;
        min-height: 2.0rem !important;
    }
    div[data-testid="stVerticalBlock"]:has(div.nowrap-bar):not(:has(div[data-testid="stVerticalBlock"] div.nowrap-bar)) div[data-testid="stButton"] button p {
        font-size: 10.5px !important;
        line-height: 1.1 !important;
        white-space: nowrap !important;
    }
    div[data-baseweb="select"] > div {
        padding-left: 6px !important;
        padding-right: 4px !important;
        font-size: 13px !important;
    }
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
if "table_key" not in st.session_state:
    st.session_state.table_key = 0

# --- 2. Google スプレッドシート接続 ＆ キャッシュ読み込み（API制限429防止） ---
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
except Exception as e:
    st.error("🚨 認証情報の読み込みに失敗しました。")
    st.code(traceback.format_exc(), language="python")
    st.stop()

def normalize_month_key(key_str):
    s = str(key_str).strip()
    m = re.match(r'^20(\d{2}年\d{2}月)', s)
    if m:
        return m.group(1)
    return s.replace("請求", "")

# ★ スプレッドシートの読み込みを10分間キャッシュ（チェックボックス操作では通信しない）
@st.cache_data(ttl=600, show_spinner=False)
def fetch_all_sheet_data():
    spreadsheet = client.open("アメックス明細_仕分けDB")
    sheet = spreadsheet.sheet1
    main_records = sheet.get_all_records()

    default_h, default_m = 200000, 200000
    cols_cfg = ["対象月", "ハヤトお小遣い", "マナお小遣い", "精算状態"]
    try:
        try:
            cfg_sheet = spreadsheet.worksheet("お小遣い設定")
        except Exception:
            cfg_sheet = spreadsheet.add_worksheet(title="お小遣い設定", rows=100, cols=4)
            cfg_sheet.update(range_name='A1', values=[cols_cfg, ["基本設定", default_h, default_m, "-"]])
        
        cfg_records = cfg_sheet.get_all_records()
        cfg_df = pd.DataFrame(cfg_records)
        if cfg_df.empty:
            cfg_df = pd.DataFrame([{"対象月": "基本設定", "ハヤトお小遣い": default_h, "マナお小遣い": default_m, "精算状態": "-"}])
        for c in cols_cfg:
            if c not in cfg_df.columns:
                cfg_df[c] = ""
        cfg_df = cfg_df[cols_cfg].copy()
        cfg_df["対象月_正規"] = cfg_df["対象月"].apply(normalize_month_key)
    except Exception:
        cfg_df = pd.DataFrame([{"対象月": "基本設定", "ハヤトお小遣い": default_h, "マナお小遣い": default_m, "精算状態": "-", "対象月_正規": "基本設定"}])

    return main_records, cfg_df

# --- 3. お小遣い設定 ＆ 月別精算完了ステータスの管理 ---
def get_month_config(cfg_df, target_month):
    default_h, default_m = 200000, 200000
    base_row = cfg_df[cfg_df["対象月"] == "基本設定"]
    base_h = int(pd.to_numeric(base_row["ハヤトお小遣い"].iloc[0], errors='coerce') or default_h) if not base_row.empty else default_h
    base_m = int(pd.to_numeric(base_row["マナお小遣い"].iloc[0], errors='coerce') or default_m) if not base_row.empty else default_m
    
    month_row = cfg_df[cfg_df["対象月_正規"] == target_month]
    if not month_row.empty:
        cur_h = int(pd.to_numeric(month_row["ハヤトお小遣い"].iloc[-1], errors='coerce') or base_h)
        cur_m = int(pd.to_numeric(month_row["マナお小遣い"].iloc[-1], errors='coerce') or base_m)
        status_str = str(month_row["精算状態"].iloc[-1]).strip()
    else:
        cur_h, cur_m, status_str = base_h, base_m, ""
    return cur_h, cur_m, status_str

def update_month_config(target_key, val_h=None, val_m=None, new_status=None):
    try:
        spreadsheet = client.open("アメックス明細_仕分けDB")
        cfg_sheet = spreadsheet.worksheet("お小遣い設定")
        _, cfg_df = fetch_all_sheet_data()
        cfg_df = cfg_df.copy()
        cols_cfg = ["対象月", "ハヤトお小遣い", "マナお小遣い", "精算状態"]
        
        cur_h, cur_m, cur_status = get_month_config(cfg_df, target_key)
        save_h = val_h if val_h is not None else cur_h
        save_m = val_m if val_m is not None else cur_m
        save_st = new_status if new_status is not None else cur_status

        match_mask = (cfg_df["対象月_正規"] == target_key)
        if match_mask.any():
            cfg_df.loc[match_mask, ["対象月", "ハヤトお小遣い", "マナお小遣い", "精算状態"]] = [target_key, save_h, save_m, save_st]
        else:
            new_row = pd.DataFrame([{"対象月": target_key, "ハヤトお小遣い": save_h, "マナお小遣い": save_m, "精算状態": save_st, "対象月_正規": target_key}])
            cfg_df = pd.concat([cfg_df, new_row], ignore_index=True)

        save_df = cfg_df[cols_cfg]
        cfg_sheet.clear()
        data_to_write = [cols_cfg] + save_df.values.tolist()
        try:
            cfg_sheet.update(range_name='A1', values=data_to_write)
        except Exception:
            cfg_sheet.update('A1', data_to_write)
        fetch_all_sheet_data.clear()
    except Exception as e:
        st.error(f"設定の保存に失敗しました: {e}")

# --- 4. ユーティリティ関数 ---
def calc_billing_month(date_str):
    try:
        dt = pd.to_datetime(str(date_str), errors='coerce')
        if pd.isna(dt):
            return "日付不明"
        if dt.day > 5:
            y, m = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
        else:
            y, m = dt.year, dt.month
        return f"{y % 100:02d}年{m:02d}月"
    except Exception:
        return "日付不明"

def format_short_date(date_str):
    try:
        dt = pd.to_datetime(str(date_str), errors='coerce')
        if pd.isna(dt):
            return str(date_str)
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        return f"{dt.month:02d}/{dt.day:02d}({weekdays[dt.weekday()]})"
    except Exception:
        return str(date_str)

def smart_clean_merchant(raw_name):
    if pd.isna(raw_name):
        return "-"
    s = str(raw_name)
    if s.startswith("[現金立替]"):
        return "💴 " + s.replace("[現金立替]", "").strip()
        
    known_rules = [
        ("AMAZON", "📦 Amazon"),
        ("ｱﾏｿﾞﾝ", "📦 Amazon"),
        ("APPLE.COM", "🍎 Apple"),
        ("APPLE COM BILL", "🍎 Apple"),
        ("UBER *EATS", "🍔 Uber Eats"),
        ("UBER EATS", "🍔 Uber Eats"),
        ("ｽﾀｰﾊﾞｯｸｽ", "☕ スタバ"),
        ("STARBUCKS", "☕ スタバ"),
        ("ｾﾌﾞﾝ-ｲﾚﾌﾞﾝ", "🏪 セブン"),
        ("ﾌｧﾐﾘｰﾏｰﾄ", "🏪 ファミマ"),
        ("ﾛｰｿﾝ", "🏪 ローソン"),
        ("ﾓﾊﾞｲﾙﾊﾟｽﾓ", "🚃 PASMO"),
        ("ﾊﾟｽﾓ", "🚃 PASMO"),
        ("ﾓﾊﾞｲﾙｽｲｶ", "🚃 Suica"),
        ("SUICA", "🚃 Suica"),
        ("タクシー", "🚕 タクシー"),
        ("GO ", "🚕 GOタクシー"),
        ("エネオス", "⛽ ENEOS"),
        ("ＥＮＥＯＳ", "⛽ ENEOS"),
    ]
    s_upper = s.upper()
    for key, clean_label in known_rules:
        if key in s_upper:
            return clean_label

    s = re.sub(r'[\s ]+(東京都|神奈川県|千葉県|埼玉県|大阪府|京都府|北海道|福岡県|愛知県|兵庫県|沖縄県).*$', '', s)
    s = re.sub(r'[\s ]+[^\s ]+(都|道|府|県)[\s ]+[^\s ]+(区|市|町|村).*$', '', s)
    
    remove_words = [
        "株式会社", "（株）", "(株)", "ｶﾌﾞｼｷｶﾞｲｼｬ", "ｶﾌﾞｼｷｶﾞｲｼ", "（同）", "合同会社",
        "一般社団法人", "公益社団法人", "ｼﾞｬﾊﾟﾝ", "CO.,LTD.", "LTD."
    ]
    for w in remove_words:
        s = s.replace(w, "")
        
    s = re.sub(r'[\s ]+', ' ', s).strip()
    return s if s else str(raw_name)

def format_short_member(member_str):
    m = str(member_str)
    if "現金(ハヤト" in m:
        return "💴ハヤト"
    elif "現金(マナ" in m:
        return "💴マナ"
    m_up = m.upper()
    if "HAYATO" in m_up:
        return "ハヤト"
    elif "MANA" in m_up:
        return "マナ"
    return m[:6] if m else "-"

def normalize_date_str(date_str):
    try:
        dt = pd.to_datetime(str(date_str), errors='coerce')
        if pd.isna(dt):
            return str(date_str).strip()
        return dt.strftime("%Y/%m/%d")
    except Exception:
        return str(date_str).strip()

def add_occurrence_key(target_df):
    temp = target_df.copy()
    temp["_norm_date"] = temp["ご利用日"].apply(normalize_date_str)
    temp["_norm_amt"] = pd.to_numeric(temp["金額"], errors='coerce').fillna(0).astype(int).astype(str)
    temp["_norm_desc"] = temp["ご利用内容"].astype(str).str.strip()
    temp["_norm_mem"] = temp["カード会員様名"].astype(str).str.strip()
    
    base_sig = temp["_norm_date"] + "|" + temp["_norm_desc"] + "|" + temp["_norm_amt"] + "|" + temp["_norm_mem"]
    occ_num = temp.groupby(base_sig).cumcount().astype(str)
    return base_sig + "|#" + occ_num

def clean_and_format_csv(file_obj):
    try:
        new_df = pd.read_csv(file_obj, encoding="shift-jis")
    except Exception:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        new_df = pd.read_csv(file_obj, encoding="utf-8")
        
    if "金額" in new_df.columns:
        new_df["金額"] = new_df["金額"].astype(str).str.replace(',', '').str.replace('¥', '').str.replace(' ', '').astype(float).fillna(0).astype(int)
    if "ご利用日" in new_df.columns:
        new_df["ご利用日"] = new_df["ご利用日"].apply(normalize_date_str)
        
    if "仕分け" not in new_df.columns:
        new_df.insert(0, "仕分け", "未分類")
        new_df.loc[new_df["金額"] < 0, "仕分け"] = "集計外"
        
    keep_columns = ["仕分け", "金額", "ご利用内容", "ご利用日", "カード会員様名"]
    for col in keep_columns:
        if col not in new_df.columns:
            new_df[col] = ""
    return new_df[keep_columns]

def auto_sync_from_drive():
    try:
        authed_session = AuthorizedSession(client.http_client.auth)
        query = "(mimeType = 'text/csv' or name contains '.csv') and trashed = false"
        resp = authed_session.get(
            "https://www.googleapis.com/drive/v3/files",
            params={"q": query, "fields": "files(id, name)", "pageSize": 50}
        )
        if resp.status_code != 200:
            return 0
            
        files = resp.json().get("files", [])
        if not files:
            return 0
            
        all_new_dfs = []
        for f in files:
            dl_resp = authed_session.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media")
            if dl_resp.status_code == 200:
                try:
                    sub_df = clean_and_format_csv(io.BytesIO(dl_resp.content))
                    sub_df["_key"] = add_occurrence_key(sub_df)
                    all_new_dfs.append(sub_df)
                except Exception:
                    pass
                    
        if not all_new_dfs:
            return 0
            
        merged_new = pd.concat(all_new_dfs, ignore_index=True)
        merged_new = merged_new.drop_duplicates(subset=["_key"], keep="first")
        
        cols_order = ["仕分け", "金額", "ご利用内容", "ご利用日", "カード会員様名"]
        spreadsheet = client.open("アメックス明細_仕分けDB")
        sheet = spreadsheet.sheet1
        existing_records = sheet.get_all_records()
        
        if not existing_records:
            to_save = merged_new[cols_order].sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
            data_to_write = [cols_order] + to_save.values.tolist()
            try:
                sheet.update(range_name='A1', values=data_to_write)
            except Exception:
                sheet.update('A1', data_to_write)
            fetch_all_sheet_data.clear()
            return len(to_save)
            
        base_df = pd.DataFrame(existing_records)
        for c in cols_order:
            if c not in base_df.columns:
                base_df[c] = ""
        base_df = base_df[cols_order]
        base_df["_key"] = add_occurrence_key(base_df)
        
        existing_keys = set(base_df["_key"])
        to_add_df = merged_new[~merged_new["_key"].isin(existing_keys)][cols_order]
        
        if to_add_df.empty:
            return 0
            
        combined_df = pd.concat([base_df[cols_order], to_add_df], ignore_index=True)
        combined_df["ご利用日"] = combined_df["ご利用日"].apply(normalize_date_str)
        combined_df = combined_df.sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
        
        sheet.clear()
        data_to_write = [cols_order] + combined_df.values.tolist()
        try:
            sheet.update(range_name='A1', values=data_to_write)
        except Exception:
            sheet.update('A1', data_to_write)
        fetch_all_sheet_data.clear()
        return len(to_add_df)
    except Exception:
        return 0

def save_changes_to_cloud(changes_dict, cols_order):
    spreadsheet = client.open("アメックス明細_仕分けDB")
    sheet = spreadsheet.sheet1
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
    except Exception:
        sheet.update('A1', data_to_write)
    fetch_all_sheet_data.clear()

# --- 5. データの読み込みと整備（キャッシュから高速取得） ---
try:
    existing_data, cfg_df = fetch_all_sheet_data()
except Exception as e:
    st.error("⏳ Googleスプレッドシートの一時的な通信制限（1分間に60回まで）に達しました。約1分待ってからページを再読み込みしてください。")
    st.stop()

if not existing_data:
    st.info("💡 まだ明細データがありません。下のボタンを押すとGoogleドライブ内のCSVを自動で読み込みます。")
    if st.button("🔄 GoogleドライブからCSVを取り込む", type="primary"):
        with st.spinner("Googleドライブ内のCSVを確認中..."):
            added = auto_sync_from_drive()
        if added > 0:
            st.success(f"🎉 {added} 件の明細を取り込みました！")
            st.rerun()
        else:
            st.warning("まだCSVが見つかりませんでした。共有フォルダにCSVを入れてからもう一度押してください。")
    st.stop()

df = pd.DataFrame(existing_data)
base_cols = ["仕分け", "金額", "ご利用内容", "ご利用日", "カード会員様名"]
cols = [c for c in base_cols if c in df.columns]
df = df[cols].copy()

for idx, choice in st.session_state.pending_changes.items():
    if idx < len(df):
        df.loc[idx, "仕分け"] = "未分類" if choice == "🔄 未分類に戻す" else choice

df["金額"] = pd.to_numeric(df["金額"], errors='coerce').fillna(0).astype(int)
df["請求月"] = df["ご利用日"].apply(calc_billing_month)
df["お店・内容"] = df["ご利用内容"].apply(smart_clean_merchant)
df["利用日"] = df["ご利用日"].apply(format_short_date)
df["会員"] = df["カード会員様名"].apply(format_short_member)

settled_map = {}
for _, r in cfg_df.iterrows():
    st_val = str(r.get("精算状態", "")).strip()
    if st_val.startswith("完了"):
        settled_map[r["対象月_正規"]] = st_val

billing_months = sorted([m for m in df["請求月"].unique() if m != "日付不明"], reverse=True)
if "日付不明" in df["請求月"].unique():
    billing_months.append("日付不明")
billing_options = billing_months + ["すべて"]

# --- 上部：請求月選択（余計なアイコンなし・iPhoneでも月までスッキリ表示） ---
with st.container():
    st.markdown('<div class="nowrap-bar"></div>', unsafe_allow_html=True)
    c_top1, c_top2, c_top3, c_top4 = st.columns([4.4, 1.9, 1.8, 1.9])
    with c_top1:
        selected_month = st.selectbox(
            "📅 請求月",
            options=billing_options,
            index=0,
            label_visibility="collapsed"
        )
    with c_top2:
        only_unclassified = st.toggle("🔍未分類", value=False)
    with c_top3:
        show_raw_text = st.toggle("📄原文", value=False)
    with c_top4:
        if st.button("🔄再読込", use_container_width=True):
            with st.spinner("最新データ＆ドライブCSVを確認中..."):
                added = auto_sync_from_drive()
                fetch_all_sheet_data.clear()
                st.session_state.pending_changes.clear()
                st.session_state.table_key += 1
            if added > 0:
                st.toast(f"📂 ドライブから新規明細を {added} 件追加しました！")
            st.rerun()

# --- 6. メイン画面：4つのタブ ---
tab1, tab2, tab3, tab4 = st.tabs(["⚡ 仕分け", "💴 現金立替", "🏦 月別精算", "📈 推移・年間合計"])

# ================= タブ1：一覧チェックボックス ＆ 上部1列固定バー =================
with tab1:
    if selected_month != "すべて":
        month_df = df[df["請求月"] == selected_month].copy()
    else:
        month_df = df.copy()

    view_df = month_df[month_df["仕分け"] == "未分類"].copy() if only_unclassified else month_df.copy()
    view_indices = list(view_df.index)

    current_table_state = st.session_state.get(f"interactive_table_{st.session_state.table_key}", {})
    selected_row_positions = current_table_state.get("selection", {}).get("rows", [])
    checked_indices = [view_indices[pos] for pos in selected_row_positions if pos < len(view_indices)]

    def apply_category(cat_name):
        targets = checked_indices
        if not targets:
            unclass_list = list(view_df[view_df["仕分け"] == "未分類"].index)
            if unclass_list:
                targets = [unclass_list[0]]
        if not targets:
            return
        for i in targets:
            st.session_state.pending_changes[i] = cat_name
        st.session_state.table_key += 1

    with st.container():
        st.markdown('<div class="fixed-action-bar nowrap-bar"></div>', unsafe_allow_html=True)
        pending_count = len(st.session_state.pending_changes)
        save_label = f"☁️保存({pending_count})" if pending_count > 0 else "☁️保存"

        b1, b2, b3, b4, b5, b6, b7 = st.columns([1.5, 1.5, 1.5, 1.2, 1.1, 1.3, 1.9])
        with b1:
            if st.button("👫共有", type="primary", use_container_width=True):
                apply_category("共有")
                st.rerun()
        with b2:
            if st.button("👨ハヤト", type="primary", use_container_width=True):
                apply_category("ハヤト")
                st.rerun()
        with b3:
            if st.button("👩マナ", type="primary", use_container_width=True):
                apply_category("マナ")
                st.rerun()
        with b4:
            if st.button("❓保留", use_container_width=True):
                apply_category("不明(保留)")
                st.rerun()
        with b5:
            if st.button("🚫外", use_container_width=True):
                apply_category("集計外")
                st.rerun()
        with b6:
            if st.button("🔄未分類", use_container_width=True):
                apply_category("🔄 未分類に戻す")
                st.rerun()
        with b7:
            if st.button(save_label, type="primary" if pending_count > 0 else "secondary", use_container_width=True, disabled=(pending_count == 0)):
                with st.spinner("保存中..."):
                    save_changes_to_cloud(st.session_state.pending_changes, cols)
                    st.session_state.pending_changes.clear()
                    st.session_state.table_key += 1
                st.toast("✅ クラウドに保存しました！")
                st.rerun()

    if view_df.empty:
        st.success(f"🎉 {selected_month} の対象明細はすべて仕分け完了しています！")
    else:
        disp_df = pd.DataFrame(index=view_df.index)
        disp_df["仕分け"] = view_df["仕分け"]
        disp_df["利用日"] = view_df["利用日"]
        disp_df["金額"] = view_df["金額"]
        disp_df["お店・内容"] = view_df["お店・内容"]
        disp_df["会員"] = view_df["会員"]
        if show_raw_text:
            disp_df["📄原文"] = view_df["ご利用内容"]

        def style_rows(row):
            idx = row.name
            cat = view_df.loc[idx, "仕分け"]
            if cat == "共有":
                return ['background-color: #fdfaf0; color: #5c4d1c; font-weight: 600;'] * len(row)
            elif cat == "ハヤト":
                return ['background-color: #f0f7ff; color: #1c4587; font-weight: 600;'] * len(row)
            elif cat == "マナ":
                return ['background-color: #fff0f3; color: #85203b; font-weight: 600;'] * len(row)
            elif cat == "不明(保留)":
                return ['background-color: #fff9db; color: #8a6d3b;'] * len(row)
            elif cat == "集計外":
                return ['color: #aaaaaa;'] * len(row)
            return [''] * len(row)

        styled_table = disp_df.style.apply(style_rows, axis=1)

        col_cfg = {
            "仕分け": st.column_config.TextColumn("仕分け", width="small"),
            "利用日": st.column_config.TextColumn("利用日", width="small"),
            "金額": st.column_config.NumberColumn("金額", format="¥%d", width="small"),
            "お店・内容": st.column_config.TextColumn("お店・内容", width="large"),
            "会員": st.column_config.TextColumn("会員", width="small"),
        }
        if show_raw_text:
            col_cfg["📄原文"] = st.column_config.TextColumn("📄原文", width="large")

        st.dataframe(
            styled_table,
            column_config=col_cfg,
            use_container_width=True,
            height=560,
            hide_index=True,
            on_select="rerun",
            selection_mode="multi-row",
            key=f"interactive_table_{st.session_state.table_key}"
        )

# ================= タブ2：現金立替の入力 =================
with tab2:
    st.subheader("💴 現金の立て替えを記録")

    with st.form("cash_entry_form", clear_on_submit=True):
        f1, f2 = st.columns(2)
        with f1:
            cash_date = st.date_input("📅 利用日", value=datetime.date.today())
        with f2:
            cash_amount = st.number_input("💴 金額（円）", min_value=1, step=100, value=1000)

        cash_desc = st.text_input("📝 内容", placeholder="例：ラーメン、駐車場、病院など")

        p1, p2 = st.columns(2)
        with p1:
            cash_payer = st.radio("👛 払った人", options=["👩 マナ", "👨 ハヤト"], horizontal=True)
        with p2:
            cash_target = st.radio("🎯 誰の分？", options=["👫 共有", "👨 ハヤト", "👩 マナ"], horizontal=True)
        
        submitted = st.form_submit_button("➕ 登録する", type="primary", use_container_width=True)

        if submitted:
            if not cash_desc.strip():
                st.warning("⚠️ 「内容」を入力してください。")
            else:
                target_map = {"👫 共有": "共有", "👨 ハヤト": "ハヤト", "👩 マナ": "マナ"}
                payer_label = "💴現金(マナ立替)" if "マナ" in cash_payer else "💴現金(ハヤト立替)"
                new_row_df = pd.DataFrame([{
                    "仕分け": target_map[cash_target],
                    "金額": int(cash_amount),
                    "ご利用内容": f"[現金立替] {cash_desc.strip()}",
                    "ご利用日": cash_date.strftime("%Y/%m/%d"),
                    "カード会員様名": payer_label
                }])
                
                spreadsheet = client.open("アメックス明細_仕分けDB")
                sheet = spreadsheet.sheet1
                latest_records = sheet.get_all_records()
                base_df = pd.DataFrame(latest_records)[cols]
                combined_df = pd.concat([base_df, new_row_df[cols]], ignore_index=True)
                combined_df["ご利用日"] = combined_df["ご利用日"].apply(normalize_date_str)
                combined_df = combined_df.sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
                
                sheet.clear()
                data_to_write = [cols] + combined_df.values.tolist()
                try:
                    sheet.update(range_name='A1', values=data_to_write)
                except Exception:
                    sheet.update('A1', data_to_write)
                fetch_all_sheet_data.clear()
                st.success(f"✅ 現金立替（{cash_desc}：¥{int(cash_amount):,}）を登録しました！")
                st.rerun()

    cash_history_df = df[df["カード会員様名"].astype(str).str.contains("現金", na=False)].copy()
    if not cash_history_df.empty:
        st.markdown("##### 📋 現金立替の履歴")
        show_cash = cash_history_df[["請求月", "利用日", "金額", "お店・内容", "会員", "仕分け"]].sort_index(ascending=False)
        st.dataframe(show_cash.style.format({"金額": "¥{:,}"}), hide_index=True, use_container_width=True)

# ================= タブ3：月別精算（ステータス管理 ＆ 2段階ロック付き） =================
with tab3:
    target_m = selected_month if selected_month != "すべて" else (billing_months[0] if billing_months else "26年09月")
    st.subheader(f"🏦 {target_m}請求分 の精算")

    month_df = df[df["請求月"] == target_m].copy()
    calc_df = month_df[month_df["仕分け"] != "集計外"].copy()

    allow_h, allow_m, cur_status = get_month_config(cfg_df, target_m)
    is_settled = cur_status.startswith("完了")

    is_cash = calc_df["カード会員様名"].astype(str).str.contains("現金", na=False)
    amex_df = calc_df[~is_cash]
    cash_df = calc_df[is_cash]

    amex_total_all = int(amex_df["金額"].sum())
    cash_total_all = int(cash_df["金額"].sum())

    amex_shared = int(amex_df[amex_df["仕分け"] == "共有"]["金額"].sum())
    amex_hayato = int(amex_df[amex_df["仕分け"] == "ハヤト"]["金額"].sum())
    amex_mana = int(amex_df[amex_df["仕分け"] == "マナ"]["金額"].sum())
    amex_unknown = int(amex_df[amex_df["仕分け"] == "不明(保留)"]["金額"].sum())
    unclassified_total = int(calc_df[calc_df["仕分け"] == "未分類"]["金額"].sum())

    cash_paid_by_h = int(cash_df[cash_df["カード会員様名"].astype(str).str.contains("ハヤト", na=False)]["金額"].sum())
    cash_paid_by_m = int(cash_df[cash_df["カード会員様名"].astype(str).str.contains("マナ", na=False)]["金額"].sum())

    cash_burden_h = int(cash_df[cash_df["仕分け"] == "ハヤト"]["金額"].sum())
    cash_burden_m = int(cash_df[cash_df["仕分け"] == "マナ"]["金額"].sum())
    cash_burden_shared = int(cash_df[cash_df["仕分け"] == "共有"]["金額"].sum())

    cash_net_h = cash_paid_by_h - cash_burden_h
    cash_net_m = cash_paid_by_m - cash_burden_m

    transfer_to_hayato = allow_h - amex_hayato + cash_net_h
    transfer_to_mana = allow_m - amex_mana + cash_net_m

    if is_settled:
        st.markdown(f'<div class="status-badge-done">✅ {target_m} の口座振込・精算は【{cur_status}】しています</div>', unsafe_allow_html=True)
    else:
        if unclassified_total > 0:
            st.markdown(f'<div class="status-badge-pending">⏳ 【未精算】未分類の明細が ¥ {unclassified_total:,} 残っています</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="status-badge-pending">⏳ 【未精算】仕分け完了済！口座振込がまだ完了していません</div>', unsafe_allow_html=True)

    t_col1, t_col2 = st.columns(2)
    with t_col1:
        st.markdown(
            f'<div class="total-check-box">'
            f'<div class="total-check-label">💳 クレジット利用 総額（請求書照合用）</div>'
            f'<div class="total-check-val">¥ {amex_total_all:,}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with t_col2:
        st.markdown(
            f'<div class="total-check-box">'
            f'<div class="total-check-label">💴 現金立替 総額</div>'
            f'<div class="total-check-val">¥ {cash_total_all:,}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    col_res1, col_res2 = st.columns(2)
    with col_res1:
        action_h = "共用口座 ➡️ ハヤト口座へ振込" if transfer_to_hayato >= 0 else "⚠️ ハヤト口座 ➡️ 共用口座へ入金"
        sign_h = "＋" if cash_net_h >= 0 else "－"
        st.markdown(
            f'<div class="settlement-card">'
            f'<div class="settlement-name">👨 {action_h}</div>'
            f'<div class="settlement-amount">¥ {abs(transfer_to_hayato):,}</div>'
            f'<div class="settlement-detail">'
            f'お小遣い ¥{allow_h:,} － クレカ個人 ¥{amex_hayato:,} {sign_h} 現金精算 ¥{abs(cash_net_h):,}'
            f'</div></div>',
            unsafe_allow_html=True
        )
    with col_res2:
        action_m = "共用口座 ➡️ マナ口座へ振込" if transfer_to_mana >= 0 else "⚠️ マナ口座 ➡️ 共用口座へ入金"
        sign_m = "＋" if cash_net_m >= 0 else "－"
        st.markdown(
            f'<div class="settlement-card">'
            f'<div class="settlement-name">👩 {action_m}</div>'
            f'<div class="settlement-amount">¥ {abs(transfer_to_mana):,}</div>'
            f'<div class="settlement-detail">'
            f'お小遣い ¥{allow_m:,} － クレカ個人 ¥{amex_mana:,} {sign_m} 現金精算 ¥{abs(cash_net_m):,}'
            f'</div></div>',
            unsafe_allow_html=True
        )

    with st.expander("🔒 振込・精算完了ステータスの変更（誤操作防止ロック付）", expanded=False):
        if not is_settled:
            if unclassified_total > 0:
                st.warning("⚠️ 未分類の明細が残っているため、まだ精算完了にできません。すべて仕分けてから操作してください。")
            else:
                st.caption("誤タップ防止のため、下のチェックを入れると完了ボタンが押せるようになります。")
                unlock = st.checkbox("☑️ 口座振込が完了したことを確認しました（ロック解除）", key=f"unlock_{target_m}")
                if st.button("✅ この月の精算を【完了】として記録する", type="primary", disabled=not unlock, use_container_width=True):
                    today_str = datetime.date.today().strftime("%m/%d")
                    update_month_config(target_m, new_status=f"完了({today_str})")
                    st.success(f"🎉 {target_m} を精算完了として記録しました！")
                    st.rerun()
        else:
            st.caption(f"現在、{target_m} は「{cur_status}」として記録されています。未精算に戻す場合は下のロックを解除してください。")
            unlock_revert = st.checkbox("☑️ 未精算の状態に戻すことを確認しました（ロック解除）", key=f"revert_{target_m}")
            if st.button("↩️ 【未精算】の状態に戻す", disabled=not unlock_revert, use_container_width=True):
                update_month_config(target_m, new_status="")
                st.info(f"⏳ {target_m} を未精算に戻しました。")
                st.rerun()

    with st.expander("📊 詳しい内訳（共有・個人・保留）を見る", expanded=True):
        m1, m2 = st.columns(2)
        m1.metric("👫 共有 合計", f"¥ {amex_shared + cash_burden_shared:,}", f"クレカ ¥{amex_shared:,} / 現金 ¥{cash_burden_shared:,}")
        m2.metric("❓ 不明(保留)", f"¥ {amex_unknown:,}")
        
        m3, m4 = st.columns(2)
        m3.metric("👨 ハヤト個人 合計", f"¥ {amex_hayato + cash_burden_h:,}", f"クレカ ¥{amex_hayato:,} / 現金 ¥{cash_burden_h:,}")
        m4.metric("👩 マナ個人 合計", f"¥ {amex_mana + cash_burden_m:,}", f"クレカ ¥{amex_mana:,} / 現金 ¥{cash_burden_m:,}")

    with st.expander("⚙️ お小遣い額の調整（基本：20万円）", expanded=False):
        a_col1, a_col2 = st.columns(2)
        with a_col1:
            new_allow_h = st.number_input("👨 ハヤトお小遣い", value=allow_h, step=10000)
        with a_col2:
            new_allow_m = st.number_input("👩 マナお小遣い", value=allow_m, step=10000)
        save_scope = st.radio("反映範囲", options=[f"{target_m}のみ変更", "今後の基本設定として変更"], horizontal=True)
        if st.button("💾 設定を保存", type="primary", use_container_width=True):
            key_to_save = target_m if "のみ" in save_scope else "基本設定"
            update_month_config(key_to_save, val_h=int(new_allow_h), val_m=int(new_allow_m))
            st.success("✅ 保存しました！")
            st.rerun()

# ================= タブ4：月次推移 ＆ 年別の年間合計一覧表（精算状況つき） =================
with tab4:
    trend_df = df[(df["仕分け"] != "集計外") & (df["請求月"] != "日付不明")].copy()
    if not trend_df.empty:
        trend_df["対象年"] = trend_df["請求月"].str.extract(r'^(\d{2})年')[0].apply(
            lambda x: f"20{x}年" if pd.notna(x) else "その他"
        )
        available_years = sorted(trend_df["対象年"].unique().tolist(), reverse=True)
        year_options = available_years + ["全期間すべて"]

        st.subheader("📈 月ごとの金額推移")
        selected_year = st.selectbox("📅 集計・表示する年（年度）を選択", options=year_options, index=0)
        filtered_trend_df = trend_df[trend_df["対象年"] == selected_year].copy() if selected_year != "全期間すべて" else trend_df.copy()

        monthly_summary = filtered_trend_df.groupby(["請求月", "仕分け"])["金額"].sum().reset_index()
        monthly_summary = monthly_summary.sort_values("請求月", ascending=True)
        
        color_map = {
            "共有": "#D4AF37",
            "ハヤト": "#4A90E2",
            "マナ": "#E26A6A",
            "不明(保留)": "#8E8E93",
            "未分類": "#CCCCCC"
        }
        fig_bar = px.bar(
            monthly_summary,
            x="請求月",
            y="金額",
            color="仕分け",
            barmode="group",
            color_discrete_map=color_map
        )
        fig_bar.update_layout(xaxis_title="", yaxis_title="金額 (円)", margin=dict(t=10, b=10, l=0, r=0), height=300, legend_title_text="")
        st.plotly_chart(fig_bar, use_container_width=True)
        
        st.markdown("---")
        st.subheader(f"📋 {selected_year} の年間合計・月別一覧表")

        pivot_df = monthly_summary.pivot(index="請求月", columns="仕分け", values="金額").fillna(0).astype(int)
        ordered_cats = [c for c in ["共有", "ハヤト", "マナ", "不明(保留)", "未分類"] if c in pivot_df.columns]
        pivot_df = pivot_df[ordered_cats]
        pivot_df["月間合計"] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_index(ascending=False)

        yearly_totals = pivot_df.sum(axis=0)

        display_pivot = pivot_df.copy()
        for c in display_pivot.columns:
            display_pivot[c] = display_pivot[c].apply(lambda v: f"¥{v:,}")
        display_pivot.insert(0, "精算状況", [f"✅{settled_map[m]}" if m in settled_map else "⏳未精算" for m in display_pivot.index])

        total_row = {"精算状況": "-"}
        for c in pivot_df.columns:
            total_row[c] = f"¥{int(yearly_totals[c]):,}"
        display_pivot.loc[f"🏆 {selected_year} 合計"] = total_row

        ym1, ym2 = st.columns(2)
        ym1.metric(f"🏆 {selected_year} 総合計", f"¥ {int(yearly_totals.get('月間合計', 0)):,}")
        ym2.metric("👫 共有 年間合計", f"¥ {int(yearly_totals.get('共有', 0)):,}")
        
        ym3, ym4 = st.columns(2)
        ym3.metric("👨 ハヤト 年間合計", f"¥ {int(yearly_totals.get('ハヤト', 0)):,}")
        ym4.metric("👩 マナ 年間合計", f"¥ {int(yearly_totals.get('マナ', 0)):,}")

        st.dataframe(display_pivot, use_container_width=True)
    else:
        st.info("推移を表示できるデータがまだありません。")

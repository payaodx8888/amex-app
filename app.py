import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.auth.transport.requests import AuthorizedSession
import datetime
import re
import io
import traceback

# --- 0. ページ設定＆デザイン（タイトルだけ黒×金、上部は超スリム1段固定） ---
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

/* ★ 超スリム1段の操作バーを画面上部にピタッと固定 */
div[data-testid="stVerticalBlock"] > div:has(div.fixed-action-bar) {
    position: sticky;
    top: 2.6rem;
    z-index: 999;
    background-color: var(--background-color, #ffffff);
    padding: 6px 6px;
    border-bottom: 2px solid #d4af37;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
    margin-bottom: 6px;
}

/* スマホでもボタンが縦に崩れず横1列を維持する設定 */
div[data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 0.25rem !important;
    align-items: center !important;
}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    min-width: 0px !important;
    width: auto !important;
    flex: 1 1 0% !important;
}

/* 精算結果のハイライトカード */
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
    color: #c0b283;
    font-size: 13px;
    font-weight: bold;
}
.settlement-amount {
    color: #f7ef8a;
    font-size: 26px;
    font-weight: 800;
    margin: 4px 0;
}
.settlement-detail {
    color: #cccccc;
    font-size: 12px;
    line-height: 1.5;
}

/* スマホでの余白とボタンサイズの最適化 */
@media (max-width: 900px) {
    .block-container {
        padding-left: 0.3rem !important;
        padding-right: 0.3rem !important;
        padding-top: 0.8rem !important;
    }
    div[data-testid="stVerticalBlock"] > div:has(div.fixed-action-bar) {
        top: 2.0rem !important;
        padding: 4px 2px !important;
    }
    div[data-testid="stButton"] button {
        padding: 0.15rem 0.08rem !important;
        min-height: 2.0rem !important;
    }
    div[data-testid="stButton"] button p {
        font-size: 10.5px !important;
        line-height: 1.1 !important;
        white-space: nowrap !important;
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
if "drive_synced" not in st.session_state:
    st.session_state.drive_synced = False

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
    spreadsheet = client.open("アメックス明細_仕分けDB")
    sheet = spreadsheet.sheet1
except Exception as e:
    st.error("🚨 スプレッドシートに接続できませんでした。")
    st.code(traceback.format_exc(), language="python")
    st.stop()

# --- 3. お小遣い設定シートの読み込み・保存（基本20万円） ---
def get_allowance_settings(target_month):
    """お小遣い設定シートから基本額と月別調整額を取得（シートがなければ自動作成）"""
    default_h, default_m = 200000, 200000
    try:
        try:
            cfg_sheet = spreadsheet.worksheet("お小遣い設定")
        except Exception:
            cfg_sheet = spreadsheet.add_worksheet(title="お小遣い設定", rows=100, cols=4)
            cfg_sheet.update(range_name='A1', values=[["対象月", "ハヤトお小遣い", "マナお小遣い"], ["基本設定", default_h, default_m]])
        
        records = cfg_sheet.get_all_records()
        cfg_df = pd.DataFrame(records)
        if cfg_df.empty:
            return default_h, default_m, default_h, default_m
            
        base_row = cfg_df[cfg_df["対象月"] == "基本設定"]
        base_h = int(base_row["ハヤトお小遣い"].iloc[0]) if not base_row.empty else default_h
        base_m = int(base_row["マナお小遣い"].iloc[0]) if not base_row.empty else default_m
        
        month_row = cfg_df[cfg_df["対象月"] == target_month]
        cur_h = int(month_row["ハヤトお小遣い"].iloc[0]) if not month_row.empty else base_h
        cur_m = int(month_row["マナお小遣い"].iloc[0]) if not month_row.empty else base_m
        return cur_h, cur_m, base_h, base_m
    except Exception:
        return default_h, default_m, default_h, default_m

def save_allowance_setting(target_key, val_h, val_m):
    try:
        cfg_sheet = spreadsheet.worksheet("お小遣い設定")
        records = cfg_sheet.get_all_records()
        cfg_df = pd.DataFrame(records)
        if cfg_df.empty:
            cfg_df = pd.DataFrame([{"対象月": "基本設定", "ハヤトお小遣い": 200000, "マナお小遣い": 200000}])
        if target_key in cfg_df["対象月"].values:
            cfg_df.loc[cfg_df["対象月"] == target_key, ["ハヤトお小遣い", "マナお小遣い"]] = [val_h, val_m]
        else:
            new_row = pd.DataFrame([{"対象月": target_key, "ハヤトお小遣い": val_h, "マナお小遣い": val_m}])
            cfg_df = pd.concat([cfg_df, new_row], ignore_index=True)
        cfg_sheet.clear()
        data_to_write = [cfg_df.columns.values.tolist()] + cfg_df.values.tolist()
        try:
            cfg_sheet.update(range_name='A1', values=data_to_write)
        except Exception:
            cfg_sheet.update('A1', data_to_write)
    except Exception as e:
        st.error(f"設定の保存に失敗しました: {e}")

# --- 4. ユーティリティ関数（5日締め計算・店名整形・重複防止ID） ---
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
        return "💴ハヤト立替"
    elif "現金(マナ" in m:
        return "💴マナ立替"
    m_up = m.upper()
    if "HAYATO" in m_up:
        return "ハヤト"
    elif "MANA" in m_up:
        return "マナ"
    return m[:6] if m else "-"

def normalize_date_str(date_str):
    """日付表記の揺れ（2026/8/6 と 2026/08/06 など）を統一して重複判定を正確にする"""
    try:
        dt = pd.to_datetime(str(date_str), errors='coerce')
        if pd.isna(dt):
            return str(date_str).strip()
        return dt.strftime("%Y/%m/%d")
    except Exception:
        return str(date_str).strip()

def add_occurrence_key(target_df):
    """
    同じ日に同じ店で同じ金額を複数回使った場合は別明細として残し（#0, #1...）、
    翌月のCSVと期間が被った場合は同じ枝番になるため100%正確に重複スキップできるキーを生成
    """
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
    """バックグラウンドでGoogleドライブのCSVを自動検出し、未登録の明細だけを安全に追記する"""
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
        # 複数CSV間で期間が被っている場合も、同じ枝番キー（_key）の重複を排除
        merged_new = merged_new.drop_duplicates(subset=["_key"], keep="first")
        
        cols_order = ["仕分け", "金額", "ご利用内容", "ご利用日", "カード会員様名"]
        existing_records = sheet.get_all_records()
        
        if not existing_records:
            to_save = merged_new[cols_order].sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
            data_to_write = [cols_order] + to_save.values.tolist()
            try:
                sheet.update(range_name='A1', values=data_to_write)
            except Exception:
                sheet.update('A1', data_to_write)
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
        return len(to_add_df)
    except Exception:
        return 0

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
    except Exception:
        sheet.update('A1', data_to_write)

# --- 5. 初回アクセス時・更新時のGoogleドライブ自動同期 ---
if not st.session_state.drive_synced:
    added_count = auto_sync_from_drive()
    st.session_state.drive_synced = True
    if added_count > 0:
        st.toast(f"📂 Googleドライブから新しい明細を {added_count} 件自動追加しました！")

# --- 6. データの読み込みと整備 ---
existing_data = sheet.get_all_records()

if not existing_data:
    st.info(
        "💡 まだ明細データがありません。\n\n"
        "Googleドライブにフォルダを作って `amex-bot@amexapp.iam.gserviceaccount.com` に共有し、"
        "その中にアメックスのCSVを入れると自動で読み込まれます！"
    )
    if st.button("🔄 ドライブを再チェックする", type="primary"):
        st.session_state.drive_synced = False
        st.rerun()
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

billing_months = sorted([m for m in df["請求月"].unique() if m != "日付不明"], reverse=True)
if "日付不明" in df["請求月"].unique():
    billing_months.append("日付不明")
billing_options = billing_months + ["すべて表示"]

# --- 上部：請求月選択 ＆ 未分類スイッチ ＆ 原文表示スイッチ ＆ 再読込（ドライブ自動同期） ---
c_top1, c_top2, c_top3, c_top4 = st.columns([3.8, 2.3, 2.1, 1.8])
with c_top1:
    selected_month = st.selectbox("📅 請求月", options=billing_options, index=0, label_visibility="collapsed")
with c_top2:
    only_unclassified = st.toggle("🔍未分類", value=False)
with c_top3:
    show_raw_text = st.toggle("📄原文", value=False)
with c_top4:
    if st.button("🔄再読込", use_container_width=True):
        st.session_state.pending_changes.clear()
        st.session_state.drive_synced = False
        st.session_state.table_key += 1
        st.rerun()

# --- 7. メイン画面：4つのタブ ---
tab1, tab2, tab3, tab4 = st.tabs(["⚡ 仕分け", "💴 現金立替", "🏦 月別精算", "📈 推移・年間合計"])

# ================= タブ1：一覧チェックボックス ＆ 上部1列固定バー =================
with tab1:
    if selected_month != "すべて表示":
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

    # ★ 画面上部に固定される超スリム1段ボタンバー
    with st.container():
        st.markdown('<div class="fixed-action-bar"></div>', unsafe_allow_html=True)
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

    # --- 一覧表（利用日のすぐ右に金額を配置、PCでも広がりすぎない設計） ---
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
            "仕分け": st.column_config.TextColumn("仕分け", width=75),
            "利用日": st.column_config.TextColumn("利用日", width=80),
            "金額": st.column_config.NumberColumn("金額", format="¥%d", width=85),
            "お店・内容": st.column_config.TextColumn("お店・内容", width=210),
            "会員": st.column_config.TextColumn("会員", width=75),
        }
        if show_raw_text:
            col_cfg["📄原文"] = st.column_config.TextColumn("📄原文", width=260)

        st.dataframe(
            styled_table,
            column_config=col_cfg,
            use_container_width=False,
            height=560,
            hide_index=True,
            on_select="rerun",
            selection_mode="multi-row",
            key=f"interactive_table_{st.session_state.table_key}"
        )

# ================= タブ2：現金立替の入力（5日締め連動） =================
with tab2:
    st.subheader("💴 現金での立て替え払いを記録")
    st.caption("個人の現金で支払った「共有の買い物」や「相手の買い物」を登録すると、毎月5日締めで自動的に月別精算（共用口座からの振込額）に反映されます。")

    with st.form("cash_entry_form", clear_on_submit=True):
        f1, f2 = st.columns(2)
        with f1:
            cash_date = st.date_input("📅 利用日（5日締め基準で自動分類）", value=datetime.date.today())
            cash_payer = st.radio("👛 現金を出した人（立て替えた人）", options=["👩 マナ", "👨 ハヤト"], horizontal=True)
        with f2:
            cash_amount = st.number_input("💴 金額（円）", min_value=1, step=100, value=1000)
            cash_target = st.radio("🎯 何の支払い？（負担する人）", options=["👫 共有", "👨 ハヤト個人", "👩 マナ個人"], horizontal=True)
        
        cash_desc = st.text_input("📝 お店・内容（例：ラーメン、駐車場代、病院など）", placeholder="内容を入力してください")
        submitted = st.form_submit_button("➕ この内容で現金立替を登録する", type="primary", use_container_width=True)

        if submitted:
            if not cash_desc.strip():
                st.warning("⚠️ 「お店・内容」を入力してください。")
            else:
                target_map = {"👫 共有": "共有", "👨 ハヤト個人": "ハヤト", "👩 マナ個人": "マナ"}
                payer_label = "💴現金(マナ立替)" if "マナ" in cash_payer else "💴現金(ハヤト立替)"
                new_row_df = pd.DataFrame([{
                    "仕分け": target_map[cash_target],
                    "金額": int(cash_amount),
                    "ご利用内容": f"[現金立替] {cash_desc.strip()}",
                    "ご利用日": cash_date.strftime("%Y/%m/%d"),
                    "カード会員様名": payer_label
                }])
                
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
                st.success(f"✅ 現金立替（{cash_desc}：¥{int(cash_amount):,}）を登録しました！")
                st.rerun()

    # 登録済みの現金立替一覧
    cash_history_df = df[df["カード会員様名"].astype(str).str.contains("現金", na=False)].copy()
    if not cash_history_df.empty:
        st.markdown("##### 📋 登録済みの現金立替履歴（※削除したい場合は「⚡仕分け」タブで『🚫外』にしてください）")
        show_cash = cash_history_df[["請求月", "利用日", "金額", "お店・内容", "会員", "仕分け"]].sort_index(ascending=False)
        st.dataframe(show_cash.style.format({"金額": "¥{:,}"}), hide_index=True, use_container_width=False)

# ================= タブ3：月別精算（3口座＆お小遣い全自動計算） =================
with tab3:
    target_m = selected_month if selected_month != "すべて表示" else (billing_months[0] if billing_months else "2026年09月請求")
    st.subheader(f"🏦 {target_m} の最終精算（共用口座 ➡️ 個人口座）")

    month_df = df[df["請求月"] == target_m].copy()
    calc_df = month_df[month_df["仕分け"] != "集計外"].copy()

    # お小遣い設定の取得（基本20万円）
    allow_h, allow_m, base_h, base_m = get_allowance_settings(target_m)

    # アメックス明細と現金立替を分離して集計
    is_cash = calc_df["カード会員様名"].astype(str).str.contains("現金", na=False)
    amex_df = calc_df[~is_cash]
    cash_df = calc_df[is_cash]

    # 1. アメックスでの各項目合計
    amex_shared = int(amex_df[amex_df["仕分け"] == "共有"]["金額"].sum())
    amex_hayato = int(amex_df[amex_df["仕分け"] == "ハヤト"]["金額"].sum())
    amex_mana = int(amex_df[amex_df["仕分け"] == "マナ"]["金額"].sum())
    amex_unknown = int(amex_df[amex_df["仕分け"] == "不明(保留)"]["金額"].sum())
    unclassified_total = int(calc_df[calc_df["仕分け"] == "未分類"]["金額"].sum())

    # 2. 現金立替の精算計算
    # ハヤトが現金を出した立替総額 ＆ マナが現金を出した立替総額
    cash_paid_by_h = int(cash_df[cash_df["カード会員様名"].astype(str).str.contains("ハヤト", na=False)]["金額"].sum())
    cash_paid_by_m = int(cash_df[cash_df["カード会員様名"].astype(str).str.contains("マナ", na=False)]["金額"].sum())

    # 現金立替のうち、ハヤト個人の負担分 ＆ マナ個人の負担分 ＆ 共有分
    cash_burden_h = int(cash_df[cash_df["仕分け"] == "ハヤト"]["金額"].sum())
    cash_burden_m = int(cash_df[cash_df["仕分け"] == "マナ"]["金額"].sum())
    cash_burden_shared = int(cash_df[cash_df["仕分け"] == "共有"]["金額"].sum())

    # 現金立替によるネット加減算額（自分が立て替えた分 － 現金での自分負担分）
    cash_net_h = cash_paid_by_h - cash_burden_h
    cash_net_m = cash_paid_by_m - cash_burden_m

    # ★ 最終結論：共用口座から各個人口座へ振り込む金額
    transfer_to_hayato = allow_h - amex_hayato + cash_net_h
    transfer_to_mana = allow_m - amex_mana + cash_net_m

    if unclassified_total > 0:
        st.warning(f"⚠️ 未分類の明細が **¥ {unclassified_total:,}** 残っています（すべて仕分けると正確な振込額が確定します）")
    else:
        st.success("✨ この月の仕分けはすべて完了し、振込額が確定しています！")

    # 最終振込額の大型カード表示
    col_res1, col_res2 = st.columns(2)
    with col_res1:
        action_h = f"共用口座 ➡️ ハヤト口座へ振込" if transfer_to_hayato >= 0 else "⚠️ ハヤト口座 ➡️ 共用口座へ入金"
        st.markdown(
            f'<div class="settlement-card">'
            f'<div class="settlement-name">👨 {action_h}</div>'
            f'<div class="settlement-amount">¥ {abs(transfer_to_hayato):,}</div>'
            f'<div class="settlement-detail">'
            f'・今月のお小遣い枠: ¥ {allow_h:,}<br>'
            f'・AMEX個人利用: － ¥ {amex_hayato:,}<br>'
            f'・現金立替精算: {"＋" if cash_net_h >= 0 else "－"} ¥ {abs(cash_net_h):,} '
            f'<span style="font-size:11px; color:#aaa;">(立替出金 ¥{cash_paid_by_h:,} / 現金自己負担 ¥{cash_burden_h:,})</span>'
            f'</div></div>',
            unsafe_allow_html=True
        )
    with col_res2:
        action_m = f"共用口座 ➡️ マナ口座へ振込" if transfer_to_mana >= 0 else "⚠️ マナ口座 ➡️ 共用口座へ入金"
        st.markdown(
            f'<div class="settlement-card">'
            f'<div class="settlement-name">👩 {action_m}</div>'
            f'<div class="settlement-amount">¥ {abs(transfer_to_mana):,}</div>'
            f'<div class="settlement-detail">'
            f'・今月のお小遣い枠: ¥ {allow_m:,}<br>'
            f'・AMEX個人利用: － ¥ {amex_mana:,}<br>'
            f'・現金立替精算: {"＋" if cash_net_m >= 0 else "－"} ¥ {abs(cash_net_m):,} '
            f'<span style="font-size:11px; color:#aaa;">(立替出金 ¥{cash_paid_by_m:,} / 現金自己負担 ¥{cash_burden_m:,})</span>'
            f'</div></div>',
            unsafe_allow_html=True
        )

    # お小遣い額の調整パネル（折りたたみ）
    with st.expander("⚙️ 月のお小遣い額の調整（基本設定：20万円）", expanded=False):
        st.caption("普段は変更不要です。特定の月だけ金額を調整したい場合や、基本額を変更したい場合に保存してください。")
        a_col1, a_col2, a_col3 = st.columns([3, 3, 4])
        with a_col1:
            new_allow_h = st.number_input("👨 ハヤトお小遣い", value=allow_h, step=10000)
        with a_col2:
            new_allow_m = st.number_input("👩 マナお小遣い", value=allow_m, step=10000)
        with a_col3:
            save_scope = st.radio("反映範囲", options=[f"{target_m}のみ変更", "今後の基本設定として変更"], horizontal=True)
            if st.button("💾 お小遣い設定を保存", type="primary", use_container_width=True):
                key_to_save = target_m if "のみ" in save_scope else "基本設定"
                save_allowance_setting(key_to_save, int(new_allow_h), int(new_allow_m))
                st.success("✅ お小遣い設定を更新しました！")
                st.rerun()

    st.markdown("---")
    st.markdown("##### 📊 支出の内訳（AMEX ＋ 現金）")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("👫 共有支出 合計", f"¥ {amex_shared + cash_burden_shared:,}", f"内 現金立替 ¥{cash_burden_shared:,}")
    m2.metric("👨 ハヤト支出 合計", f"¥ {amex_hayato + cash_burden_h:,}", f"お小遣い残 ¥{allow_h - (amex_hayato + cash_burden_h):,}")
    m3.metric("👩 マナ支出 合計", f"¥ {amex_mana + cash_burden_m:,}", f"お小遣い残 ¥{allow_m - (amex_mana + cash_burden_m):,}")
    m4.metric("❓ 不明(保留)", f"¥ {amex_unknown:,}")

# ================= タブ4：月次推移 ＆ 年度別一覧表（年間合計つき） =================
with tab4:
    st.subheader("📈 月ごとの金額推移（5日締め基準）")
    
    trend_df = df[(df["仕分け"] != "集計外") & (df["請求月"] != "日付不明")].copy()
    if not trend_df.empty:
        # 請求月から「年度（年）」を抽出（例: "2026年09月請求" -> "2026年"）
        trend_df["対象年"] = trend_df["請求月"].str.extract(r'^(\d{4}年)')[0].fillna("その他")
        available_years = sorted(trend_df["対象年"].unique().tolist(), reverse=True)
        year_options = available_years + ["すべての年"]

        y_col1, y_col2 = st.columns([4, 6])
        with y_col1:
            selected_year = st.selectbox("📅 表示する年を選択", options=year_options, index=0)

        filtered_trend_df = trend_df[trend_df["対象年"] == selected_year].copy() if selected_year != "すべての年" else trend_df.copy()

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
        fig_bar.update_layout(xaxis_title="", yaxis_title="金額 (円)", margin=dict(t=10, b=10, l=0, r=0), height=320, legend_title_text="")
        st.plotly_chart(fig_bar, use_container_width=True)
        
        st.markdown(f"##### 📋 {selected_year} の月別・項目別一覧表（年間合計つき）")
        pivot_df = monthly_summary.pivot(index="請求月", columns="仕分け", values="金額").fillna(0).astype(int)
        
        # 列の並び順を整える
        ordered_cats = [c for c in ["共有", "ハヤト", "マナ", "不明(保留)", "未分類"] if c in pivot_df.columns]
        pivot_df = pivot_df[ordered_cats]
        pivot_df["月間合計"] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_index(ascending=False)

        # ★ 最下部に「年間合計」の行を追加
        yearly_totals = pivot_df.sum(axis=0)
        pivot_with_total = pivot_df.copy()
        pivot_with_total.loc[f"🏆 {selected_year} 合計"] = yearly_totals

        # 年間合計のサマリーカードも上に表示
        ym1, ym2, ym3, ym4 = st.columns(4)
        ym1.metric(f"🏆 {selected_year} 総合計", f"¥ {int(yearly_totals.get('月間合計', 0)):,}")
        ym2.metric("👫 共有 年間合計", f"¥ {int(yearly_totals.get('共有', 0)):,}")
        ym3.metric("👨 ハヤト 年間合計", f"¥ {int(yearly_totals.get('ハヤト', 0)):,}")
        ym4.metric("👩 マナ 年間合計", f"¥ {int(yearly_totals.get('マナ', 0)):,}")

        st.dataframe(pivot_with_total.style.format("¥{:,}"), use_container_width=False)
    else:
        st.info("推移を表示できるデータがまだありません。")

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

def format_short_date(date_str):
    """日付を『08/06(木)』のように曜日付きで見やすく変換"""
    try:
        dt = pd.to_datetime(str(date_str), errors='coerce')
        if pd.isna(dt):
            return str(date_str)
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        return f"{dt.month:02d}/{dt.day:02d}({weekdays[dt.weekday()]})"
    except:
        return str(date_str)

def smart_clean_merchant(raw_name):
    """アメックスの分かりづらい明細文字列から本社住所や法人格を除去してスッキリ変換"""
    if pd.isna(raw_name):
        return "-"
    s = str(raw_name)
    
    # よく使うサービスのスマート変換辞書
    known_rules = [
        ("AMAZON", "📦 Amazon"),
        ("ｱﾏｿﾞﾝ", "📦 Amazon"),
        ("APPLE.COM", "🍎 Apple (課金/サブスク)"),
        ("APPLE COM BILL", "🍎 Apple (課金/サブスク)"),
        ("UBER *EATS", "🍔 Uber Eats"),
        ("UBER EATS", "🍔 Uber Eats"),
        ("ｽﾀｰﾊﾞｯｸｽ", "☕ スターバックス"),
        ("STARBUCKS", "☕ スターバックス"),
        ("ｾﾌﾞﾝ-ｲﾚﾌﾞﾝ", "🏪 セブンイレブン"),
        ("ﾌｧﾐﾘｰﾏｰﾄ", "🏪 ファミリーマート"),
        ("ﾛｰｿﾝ", "🏪 ローソン"),
        ("ﾓﾊﾞｲﾙﾊﾟｽﾓ", "🚃 モバイルPASMO"),
        ("ﾊﾟｽﾓ", "🚃 PASMO"),
        ("ﾓﾊﾞｲﾙｽｲｶ", "🚃 モバイルSuica"),
        ("SUICA", "🚃 Suica"),
        ("タクシー", "🚕 タクシー"),
        ("GO ", "🚕 タクシー(GO)"),
        ("エネオス", "⛽ ENEOS"),
        ("ＥＮＥＯＳ", "⛽ ENEOS"),
    ]
    s_upper = s.upper()
    for key, clean_label in known_rules:
        if key in s_upper:
            return clean_label

    # 1. 全角スペース・連続スペースの後ろにある「都道府県＋市区町村」の住所表記をカット
    s = re.sub(r'[\s ]+(東京都|神奈川県|千葉県|埼玉県|大阪府|京都府|北海道|福岡県|愛知県|兵庫県|沖縄県).*$', '', s)
    s = re.sub(r'[\s ]+[^\s ]+(都|道|府|県)[\s ]+[^\s ]+(区|市|町|村).*$', '', s)
    
    # 2. 法人格や不要な記号をカット
    remove_words = [
        "株式会社", "（株）", "(株)", "ｶﾌﾞｼｷｶﾞｲｼｬ", "ｶﾌﾞｼｷｶﾞｲｼ", "（同）", "合同会社",
        "一般社団法人", "公益社団法人", "ｼﾞｬﾊﾟﾝ", "CO.,LTD.", "LTD."
    ]
    for w in remove_words:
        s = s.replace(w, "")
        
    # 余分な空白を整理
    s = re.sub(r'[\s ]+', ' ', s).strip()
    return s if s else str(raw_name)

def format_short_member(member_str):
    """カード会員名をスマホで見やすいように短縮"""
    m = str(member_str).upper()
    if "HAYATO" in m:
        return "👨 ハヤト"
    elif "MANA" in m:
        return "👩 マナ"
    return str(member_str)[:8] if member_str else "-"

def clean_and_format_csv(file_obj):
    try:
        new_df = pd.read_csv(file_obj, encoding="shift-jis")
    except:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        new_df = pd.read_csv(file_obj, encoding="utf-8")
        
    if "金額" in new_df.columns:
        new_df["金額"] = new_df["金額"].astype(str).str.replace(',', '').str.replace('¥', '').str.replace(' ', '').astype(float).fillna(0).astype(int)
        
    if "仕分け" not in new_df.columns:
        new_df.insert(0, "仕分け", "未分類")
        new_df.loc[new_df["金額"] < 0, "仕分け"] = "集計外"
        
    keep_columns = ["仕分け", "金額", "ご利用内容", "ご利用日", "カード会員様名"]
    keep_columns = [col for col in keep_columns if col in new_df.columns]
    return new_df[keep_columns]

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

def sync_csvs_from_drive(base_df, cols_order):
    """Googleドライブ内の共有フォルダにあるCSVを自動で探してスプレッドシートへ追加する"""
    authed_session = AuthorizedSession(client.http_client.auth)
    query = "mimeType = 'text/csv' and trashed = false"
    resp = authed_session.get(
        "https://www.googleapis.com/drive/v3/files",
        params={"q": query, "fields": "files(id, name, createdTime)", "pageSize": 50}
    )
    if resp.status_code != 200:
        return 0, 0, "Googleドライブの検索に失敗しました。"
        
    files = resp.json().get("files", [])
    if not files:
        return 0, 0, "共有されたGoogleドライブ内にCSVファイルが見つかりませんでした。"
        
    all_new_dfs = []
    for f in files:
        dl_resp = authed_session.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media")
        if dl_resp.status_code == 200:
            try:
                sub_df = clean_and_format_csv(io.BytesIO(dl_resp.content))
                all_new_dfs.append(sub_df)
            except Exception:
                pass
                
    if not all_new_dfs:
        return len(files), 0, "読み込める形式のCSVがありませんでした。"
        
    merged_new = pd.concat(all_new_dfs, ignore_index=True)
    check_cols = ["ご利用日", "ご利用内容", "金額", "カード会員様名"]
    check_cols = [c for c in check_cols if c in base_df.columns and c in merged_new.columns]
    
    base_keys = set(base_df[check_cols].astype(str).agg('-'.join, axis=1))
    merged_new["_key"] = merged_new[check_cols].astype(str).agg('-'.join, axis=1)
    merged_new = merged_new.drop_duplicates(subset=["_key"])
    
    to_add_df = merged_new[~merged_new["_key"].isin(base_keys)].drop(columns=["_key"])
    if to_add_df.empty:
        return len(files), 0, "すべてのCSV明細はすでに取込済みです！"
        
    combined_df = pd.concat([base_df[cols_order], to_add_df[cols_order]], ignore_index=True)
    if "ご利用日" in combined_df.columns:
        combined_df = combined_df.sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
        
    sheet.clear()
    data_to_write = [combined_df.columns.values.tolist()] + combined_df.values.tolist()
    try:
        sheet.update(range_name='A1', values=data_to_write)
    except:
        sheet.update('A1', data_to_write)
        
    return len(files), len(to_add_df), f"🎉 ドライブ内の {len(files)} 個のCSVから、新規明細 {len(to_add_df)} 件を追加しました！"

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
    base_cols = ["仕分け", "金額", "ご利用内容", "ご利用日", "カード会員様名"]
    cols = [c for c in base_cols if c in df.columns]
    df = df[cols].copy()
    
    # 一時変更メモリを画面のdfに反映
    for idx, choice in st.session_state.pending_changes.items():
        if idx < len(df):
            df.loc[idx, "仕分け"] = "未分類" if choice == "🔄 未分類に戻す" else choice

    df["金額"] = pd.to_numeric(df["金額"], errors='coerce').fillna(0).astype(int)
    df["請求月"] = df["ご利用日"].apply(calc_billing_month)
    df["スッキリ店名"] = df["ご利用内容"].apply(smart_clean_merchant)
    df["曜日付日付"] = df["ご利用日"].apply(format_short_date)
    df["会員短縮"] = df["カード会員様名"].apply(format_short_member)
    
    billing_months = sorted([m for m in df["請求月"].unique() if m != "日付不明"], reverse=True)
    if "日付不明" in df["請求月"].unique():
        billing_months.append("日付不明")
    billing_options = billing_months + ["すべて表示"]

    # 上部：月選択 ＆ 未分類フィルター
    c_top1, c_top2, c_top3 = st.columns([5, 3, 2])
    with c_top1:
        selected_month = st.selectbox("📅 請求月（毎月5日締め）", options=billing_options, index=0, label_visibility="collapsed")
    with c_top2:
        only_unclassified = st.toggle("🔍「未分類」のみ表示", value=False)
    with c_top3:
        if st.button("🔄 最新再読込", use_container_width=True):
            st.session_state.pending_changes.clear()
            st.session_state.selected_indices = []
            st.rerun()

    # --- 5. メイン画面：3つのタブ ---
    tab1, tab2, tab3 = st.tabs(["⚡ 一覧＆ボタン仕分け", "📊 月別精算", "📈 推移・ドライブ自動連携"])

    # ================= タブ1：一覧ハイライト ＆ 固定ワンタップボタン =================
    with tab1:
        if selected_month != "すべて表示":
            month_df = df[df["請求月"] == selected_month].copy()
        else:
            month_df = df.copy()

        view_df = month_df[month_df["仕分け"] == "未分類"].copy() if only_unclassified else month_df.copy()
        view_indices = list(view_df.index)
        unclassified_indices = list(view_df[view_df["仕分け"] == "未分類"].index)

        # カーソル（現在選択されている行）の自動調整
        valid_selected = [i for i in st.session_state.selected_indices if i in view_indices]
        if not valid_selected:
            if st.session_state.cursor_idx in view_indices:
                valid_selected = [st.session_state.cursor_idx]
            elif unclassified_indices:
                valid_selected = [unclassified_indices[0]]
            elif view_indices:
                valid_selected = [view_indices[0]]
        st.session_state.selected_indices = valid_selected
        if valid_selected:
            st.session_state.cursor_idx = valid_selected[0]

        # ★ 画面上部にピタッと固定される操作パネル（スクロールしても付いてくる！）
        with st.container():
            st.markdown('<div class="fixed-action-bar"></div>', unsafe_allow_html=True)
            
            # 1) 現在ハイライト中の明細プレビュー ＆ 欄外に小さく正式データを表示
            if valid_selected:
                first_row = df.loc[valid_selected[0]]
                if len(valid_selected) == 1:
                    raw_text = str(first_row.get("ご利用内容", ""))
                    search_url = f"https://www.google.com/search?q={urllib.parse.quote(raw_text)}"
                    st.markdown(
                        f'<div class="target-box">'
                        f'<div class="target-main">🎯 選択中: {first_row["曜日付日付"]} ｜ {first_row["スッキリ店名"]} ｜ ¥ {first_row["金額"]:,} <span style="font-size:12px; font-weight:normal;">({first_row["会員短縮"]} / 現在: {first_row["仕分け"]})</span></div>'
                        f'<div class="target-raw">📄 請求書原文: {raw_text} &nbsp; <a href="{search_url}" target="_blank" style="color:#b8860b;">🔍 Googleで調べる</a></div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                else:
                    total_sel_amt = df.loc[valid_selected, "金額"].sum()
                    names_preview = "、".join(df.loc[valid_selected[:3], "スッキリ店名"].tolist())
                    if len(valid_selected) > 3:
                        names_preview += f" ほか{len(valid_selected)-3}件"
                    raw_list = " / ".join(df.loc[valid_selected[:3], "ご利用内容"].astype(str).tolist())
                    st.markdown(
                        f'<div class="target-box">'
                        f'<div class="target-main">🎯 {len(valid_selected)}件 まとめて選択中 （合計 ¥ {total_sel_amt:,}）: {names_preview}</div>'
                        f'<div class="target-raw">📄 請求書原文: {raw_list}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

            # 仕分け実行関数（選択行を一括変更し、自動で次の未分類行へ進む）
            def apply_category(cat_name):
                if not st.session_state.selected_indices:
                    return
                last_selected = st.session_state.selected_indices[-1]
                prev_state = {i: df.loc[i, "仕分け"] for i in st.session_state.selected_indices}
                st.session_state.history_stack.append((list(st.session_state.selected_indices), prev_state))
                
                for i in st.session_state.selected_indices:
                    st.session_state.pending_changes[i] = cat_name
                
                # 次の未分類の行を自動で探してカーソルを進める
                remaining_unclass = [
                    i for i in view_indices 
                    if i not in st.session_state.selected_indices 
                    and (st.session_state.pending_changes.get(i, df.loc[i, "仕分け"]) == "未分類")
                ]
                after_current = [i for i in remaining_unclass if i > last_selected]
                if after_current:
                    next_idx = after_current[0]
                elif remaining_unclass:
                    next_idx = remaining_unclass[0]
                else:
                    # 未分類がもうなければ1つ下の行へ
                    pos = view_indices.index(last_selected) if last_selected in view_indices else 0
                    next_idx = view_indices[min(pos + 1, len(view_indices) - 1)]
                
                st.session_state.cursor_idx = next_idx
                st.session_state.selected_indices = [next_idx]
                st.session_state.table_key += 1

            # 2) ワンタップ仕分けボタン（メイン：共有・ハヤト・マナ）
            b1, b2, b3, b4, b5, b6 = st.columns([2, 2, 2, 1.3, 1.3, 1.4])
            with b1:
                if st.button("👫 共有", type="primary", use_container_width=True):
                    apply_category("共有")
                    st.rerun()
            with b2:
                if st.button("👨 ハヤト", type="primary", use_container_width=True):
                    apply_category("ハヤト")
                    st.rerun()
            with b3:
                if st.button("👩 マナ", type="primary", use_container_width=True):
                    apply_category("マナ")
                    st.rerun()
            with b4:
                if st.button("❓ 保留", use_container_width=True):
                    apply_category("不明(保留)")
                    st.rerun()
            with b5:
                if st.button("🚫 集計外", use_container_width=True):
                    apply_category("集計外")
                    st.rerun()
            with b6:
                if st.button("⬅️ 1つ戻る", use_container_width=True, disabled=(len(st.session_state.history_stack) == 0)):
                    indices_to_restore, prev_map = st.session_state.history_stack.pop()
                    for i, old_cat in prev_map.items():
                        st.session_state.pending_changes[i] = "🔄 未分類に戻す" if old_cat == "未分類" else old_cat
                    st.session_state.selected_indices = indices_to_restore
                    st.session_state.cursor_idx = indices_to_restore[0]
                    st.session_state.table_key += 1
                    st.rerun()

            # 3) 選択範囲を広げる・移動する調整ボタン群
            r1, r2, r3, r4, r5, r6 = st.columns([1.8, 1.8, 2.2, 2.2, 1.5, 1.5])
            with r1:
                if st.button("➕ 下に広げる(+1)", use_container_width=True):
                    if valid_selected:
                        last_i = valid_selected[-1]
                        pos = view_indices.index(last_i)
                        if pos + 1 < len(view_indices):
                            st.session_state.selected_indices.append(view_indices[pos + 1])
                            st.session_state.table_key += 1
                            st.rerun()
            with r2:
                if st.button("➕ 下に広げる(+5)", use_container_width=True):
                    if valid_selected:
                        last_i = valid_selected[-1]
                        pos = view_indices.index(last_i)
                        extra = view_indices[pos + 1 : pos + 6]
                        for x in extra:
                            if x not in st.session_state.selected_indices:
                                st.session_state.selected_indices.append(x)
                        st.session_state.table_key += 1
                        st.rerun()
            with r3:
                target_date_str = df.loc[valid_selected[0], "曜日付日付"] if valid_selected else ""
                if st.button(f"📅 {target_date_str} を全選択", use_container_width=True, disabled=not valid_selected):
                    raw_d = df.loc[valid_selected[0], "ご利用日"]
                    same_day_idx = list(view_df[view_df["ご利用日"] == raw_d].index)
                    st.session_state.selected_indices = same_day_idx
                    st.session_state.table_key += 1
                    st.rerun()
            with r4:
                if st.button("🏪 同じ店名を全選択", use_container_width=True, disabled=not valid_selected):
                    clean_s = df.loc[valid_selected[0], "スッキリ店名"]
                    same_store_idx = list(view_df[view_df["スッキリ店名"] == clean_s].index)
                    st.session_state.selected_indices = same_store_idx
                    st.session_state.table_key += 1
                    st.rerun()
            with r5:
                if st.button("⬇️ 次の行へ", use_container_width=True, disabled=not valid_selected):
                    last_i = valid_selected[-1]
                    pos = view_indices.index(last_i)
                    next_i = view_indices[(pos + 1) % len(view_indices)]
                    st.session_state.cursor_idx = next_i
                    st.session_state.selected_indices = [next_i]
                    st.session_state.table_key += 1
                    st.rerun()
            with r6:
                if len(valid_selected) > 1:
                    if st.button("✖️ 1行に戻す", use_container_width=True):
                        st.session_state.selected_indices = [valid_selected[0]]
                        st.session_state.table_key += 1
                        st.rerun()
                else:
                    if st.button("🔄 未分類へ戻す", use_container_width=True, disabled=not valid_selected):
                        apply_category("🔄 未分類に戻す")
                        st.rerun()

            # 4) 未保存の変更があるときは、同じ固定パネル内に保存ボタンを表示
            pending_count = len(st.session_state.pending_changes)
            if pending_count > 0:
                if st.button(f"☁️ 現在 {pending_count} 件の変更あり！ここを押してクラウドに一括保存する", type="primary", use_container_width=True):
                    with st.spinner("クラウドの最新データと合体して保存中..."):
                        save_changes_to_cloud(st.session_state.pending_changes, cols)
                        st.session_state.pending_changes.clear()
                        st.session_state.history_stack.clear()
                    st.success("✅ クラウドへの保存が完了しました！")
                    st.rerun()

        # --- 一覧表（選択中の行を黄色で強調表示 ＆ 左端のチェックでも選択可能） ---
        if view_df.empty:
            st.success(f"🎉 {selected_month} の対象明細はすべて仕分け完了しています！")
        else:
            st.caption("💡 上のボタンで選択範囲を広げるか、表の左端のチェックボックスをタップして複数行を直接選ぶこともできます。")
            
            # 表示用のテーブル作成
            disp_df = pd.DataFrame(index=view_df.index)
            disp_df["状態"] = [
                f"👉 🎯 選択中 ({view_df.loc[i, '仕分け']})" if i in valid_selected else view_df.loc[i, "仕分け"]
                for i in view_df.index
            ]
            disp_df["利用日"] = view_df["曜日付日付"]
            disp_df["お店・内容（スッキリ）"] = view_df["スッキリ店名"]
            disp_df["金額"] = view_df["金額"]
            disp_df["会員"] = view_df["会員短縮"]
            disp_df["請求書原文（正式データ）"] = view_df["ご利用内容"]

            # 強調表示（ハイライト）のスタイリング関数
            def highlight_rows(row):
                idx = row.name
                if idx in valid_selected:
                    # 選択中の行は鮮やかなゴールドイエロー＋太字で強調！
                    return ['background-color: #fff3bf; color: #000000; font-weight: bold; border-top: 2px solid #f59f00; border-bottom: 2px solid #f59f00;'] * len(row)
                
                cat = view_df.loc[idx, "仕分け"]
                if cat == "共有":
                    return ['background-color: #fdfaf0; color: #5c4d1c;'] * len(row)
                elif cat == "ハヤト":
                    return ['background-color: #f0f7ff; color: #1c4587;'] * len(row)
                elif cat == "マナ":
                    return ['background-color: #fff0f3; color: #85203b;'] * len(row)
                elif cat == "集計外":
                    return ['color: #aaaaaa;'] * len(row)
                return [''] * len(row)

            styled_table = disp_df.style.apply(highlight_rows, axis=1).format({"金額": "¥{:,.0f}"})

            event = st.dataframe(
                styled_table,
                use_container_width=True,
                height=520,
                hide_index=True,
                on_select="rerun",
                selection_mode="multi-row",
                key=f" interactive_table_{st.session_state.table_key}"
            )

            # ユーザーが表の左端のチェックボックスをタップして行を選んだ場合、その行をハイライト対象にする
            if event and event.selection and event.selection.rows:
                clicked_indices = [view_indices[pos] for pos in event.selection.rows if pos < len(view_indices)]
                if clicked_indices and clicked_indices != st.session_state.selected_indices:
                    st.session_state.selected_indices = clicked_indices
                    st.session_state.cursor_idx = clicked_indices[0]
                    st.rerun()

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
                "未分類": "#CCCCCC"
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

    # ================= タブ3：月次推移 ＆ Googleドライブ自動取込 =================
    with tab3:
        st.subheader("📂 Googleドライブから明細を自動取込")
        st.caption(
            "Googleドライブにフォルダ（例：『アメックスCSV』）を作り、`amex-bot@amexapp.iam.gserviceaccount.com` に共有しておけば、"
            "そのフォルダに毎月CSVを入れるだけで、下のボタン1つで未登録の明細だけを自動追加できます！"
        )
        if st.button("🔄 Googleドライブ内のCSVをスキャンして自動追加する", type="primary", use_container_width=True):
            with st.spinner("Googleドライブ内のCSVを検索・取込中..."):
                latest_records = sheet.get_all_records()
                base_df = pd.DataFrame(latest_records)
                file_cnt, added_cnt, msg = sync_csvs_from_drive(base_df, cols)
            if added_cnt > 0:
                st.success(msg)
                st.rerun()
            else:
                st.info(msg)

        with st.expander("📥 手動でCSVファイルを直接アップロードする場合（予備）"):
            new_csv = st.file_uploader("追加するアメックスのCSVを選択", type="csv", key="append_csv")
            if new_csv is not None:
                if st.button("📥 重複を除いてクラウドに追加する", use_container_width=True):
                    with st.spinner("新しい明細を分析して追加中..."):
                        new_df = clean_and_format_csv(new_csv)
                        latest_records = sheet.get_all_records()
                        base_df = pd.DataFrame(latest_records)[cols]
                        
                        check_cols = ["ご利用日", "ご利用内容", "金額", "カード会員様名"]
                        base_keys = set(base_df[check_cols].astype(str).agg('-'.join, axis=1))
                        new_df["_key"] = new_df[check_cols].astype(str).agg('-'.join, axis=1)
                        to_add_df = new_df[~new_df["_key"].isin(base_keys)].drop(columns=["_key"])
                        
                        if to_add_df.empty:
                            st.warning("⚠️ すべて既に登録済みです。")
                        else:
                            combined_df = pd.concat([base_df, to_add_df[cols]], ignore_index=True)
                            combined_df = combined_df.sort_values(by="ご利用日", ascending=True).reset_index(drop=True)
                            sheet.clear()
                            data_to_write = [combined_df.columns.values.tolist()] + combined_df.values.tolist()
                            try:
                                sheet.update(range_name='A1', values=data_to_write)
                            except:
                                sheet.update('A1', data_to_write)
                            st.success(f"🎉 新しく {len(to_add_df)} 件の明細を追加しました！")
                            st.rerun()

        st.markdown("---")
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
            fig_bar.update_layout(xaxis_title="", yaxis_title="金額 (円)", margin=dict(t=20, b=20, l=0, r=0), height=350, legend_title_text="")
            st.plotly_chart(fig_bar, use_container_width=True)
            
            st.markdown("##### 📋 月別・項目別の一覧表")
            pivot_df = monthly_summary.pivot(index="請求月", columns="仕分け", values="金額").fillna(0).astype(int)
            pivot_df["合計"] = pivot_df.sum(axis=1)
            pivot_df = pivot_df.sort_index(ascending=False)
            st.dataframe(pivot_df.style.format("¥{:,}"), use_container_width=True)

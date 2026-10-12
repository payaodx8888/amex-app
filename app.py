import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.auth.transport.requests import AuthorizedSession
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
    padding: 6px 8px;
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

/* スマホ（横画面・縦画面）での余白とボタンサイズの最適化 */
@media (max-width: 900px) {
    .block-container {
        padding-left: 0.4rem !important;
        padding-right: 0.4rem !important;
        padding-top: 1rem !important;
    }
    div[data-testid="stVerticalBlock"] > div:has(div.fixed-action-bar) {
        top: 2.0rem !important;
        padding: 4px 4px !important;
    }
    div[data-testid="stButton"] button {
        padding: 0.15rem 0.1rem !important;
        min-height: 2.0rem !important;
    }
    div[data-testid="stButton"] button p {
        font-size: 11px !important;
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

def format_short_date(date_str):
    try:
        dt = pd.to_datetime(str(date_str), errors='coerce')
        if pd.isna(dt):
            return str(date_str)
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        return f"{dt.month:02d}/{dt.day:02d}({weekdays[dt.weekday()]})"
    except:
        return str(date_str)

def smart_clean_merchant(raw_name):
    if pd.isna(raw_name):
        return "-"
    s = str(raw_name)
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
    m = str(member_str).upper()
    if "HAYATO" in m:
        return "ハヤト"
    elif "MANA" in m:
        return "マナ"
    return str(member_str)[:6] if member_str else "-"

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

    # 上部：月選択 ＆ 未分類フィルター（横1列でコンパクトに配置）
    c_top1, c_top2, c_top3 = st.columns([4.5, 3.5, 2])
    with c_top1:
        selected_month = st.selectbox("📅 請求月", options=billing_options, index=0, label_visibility="collapsed")
    with c_top2:
        only_unclassified = st.toggle("🔍未分類のみ", value=False)
    with c_top3:
        if st.button("🔄 再読込", use_container_width=True):
            st.session_state.pending_changes.clear()
            st.session_state.table_key += 1
            st.rerun()

    # --- 5. メイン画面：3つのタブ ---
    tab1, tab2, tab3 = st.tabs(["⚡ 仕分け", "📊 月別精算", "📈 推移・連携"])

    # ================= タブ1：チェックボックス選択 ＆ 上部1列固定バー =================
    with tab1:
        if selected_month != "すべて表示":
            month_df = df[df["請求月"] == selected_month].copy()
        else:
            month_df = df.copy()

        view_df = month_df[month_df["仕分け"] == "未分類"].copy() if only_unclassified else month_df.copy()
        view_indices = list(view_df.index)

        # 現在チェックボックスで選択されている行を取得
        current_table_state = st.session_state.get(f"interactive_table_{st.session_state.table_key}", {})
        selected_row_positions = current_table_state.get("selection", {}).get("rows", [])
        checked_indices = [view_indices[pos] for pos in selected_row_positions if pos < len(view_indices)]

        def apply_category(cat_name):
            targets = checked_indices
            # もしチェックを1つも入れずにボタンを押した場合は、一番上の「未分類」の行を自動で対象にする
            if not targets:
                unclass_list = list(view_df[view_df["仕分け"] == "未分類"].index)
                if unclass_list:
                    targets = [unclass_list[0]]
            if not targets:
                return
            for i in targets:
                st.session_state.pending_changes[i] = cat_name
            # 変更後、チェックボックスを自動クリアして次を選びやすくする
            st.session_state.table_key += 1

        # ★ 画面上部に固定される超スリム1段ボタンバー
        with st.container():
            st.markdown('<div class="fixed-action-bar"></div>', unsafe_allow_html=True)
            pending_count = len(st.session_state.pending_changes)
            save_label = f"☁️保存({pending_count})" if pending_count > 0 else "☁️保存"

            b1, b2, b3, b4, b5, b6, b7 = st.columns([1.5, 1.5, 1.5, 1.2, 1.2, 1.2, 1.9])
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

        # --- 一覧表（右端に極小の「📄原文」列を配置） ---
        if view_df.empty:
            st.success(f"🎉 {selected_month} の対象明細はすべて仕分け完了しています！")
        else:
            disp_df = pd.DataFrame(index=view_df.index)
            disp_df["仕分け"] = view_df["仕分け"]
            disp_df["利用日"] = view_df["利用日"]
            disp_df["お店・内容"] = view_df["お店・内容"]
            disp_df["金額"] = view_df["金額"]
            disp_df["会員"] = view_df["会員"]
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

            st.dataframe(
                styled_table,
                column_config={
                    "仕分け": st.column_config.TextColumn("仕分け", width="small"),
                    "利用日": st.column_config.TextColumn("利用日", width="small"),
                    "お店・内容": st.column_config.TextColumn("お店・内容", width="medium"),
                    "金額": st.column_config.NumberColumn("金額", format="¥%d", width="small"),
                    "会員": st.column_config.TextColumn("会員", width="small"),
                    # ★ 一番右端に小さく縮めて配置（ダブルタップで全文がポップアップ展開）
                    "📄原文": st.column_config.TextColumn("📄原文", width="small"),
                },
                use_container_width=True,
                height=560,
                hide_index=True,
                on_select="rerun",
                selection_mode="multi-row",
                key=f"interactive_table_{st.session_state.table_key}"
            )

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

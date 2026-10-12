import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
import traceback

# --- 0. ページ設定＆高級感のあるカスタムデザイン（黒背景×金文字＋カードUI） ---
st.set_page_config(layout="wide", page_title="THE SETTLEMENT | AMEX", page_icon="💳")

st.markdown("""
<style>
/* 高級感のある黒×金ヘッダーバナー */
.luxury-banner {
    background: linear-gradient(135deg, #0a0a0a 0%, #1c1c1c 50%, #050505 100%);
    border: 1px solid #d4af37;
    border-radius: 10px;
    padding: 18px 15px;
    text-align: center;
    margin-bottom: 16px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
}
.luxury-title {
    color: #d4af37;
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 22px;
    font-weight: bold;
    letter-spacing: 3px;
    margin: 0;
}
.luxury-subtitle {
    color: #b89f5d;
    font-size: 10px;
    letter-spacing: 2px;
    margin-top: 4px;
}
/* ティンダー風スワイプカードのデザイン */
.tinder-card {
    background: linear-gradient(145deg, #161616, #0d0d0d);
    border: 2px solid #d4af37;
    border-radius: 16px;
    padding: 22px 18px;
    text-align: center;
    margin: 8px 0 16px 0;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
}
.card-badge {
    display: inline-block;
    background-color: #d4af37;
    color: #000000;
    font-weight: bold;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    margin-bottom: 10px;
}
.card-date {
    color: #c0b283;
    font-size: 13px;
    letter-spacing: 1px;
    margin-bottom: 8px;
}
.card-store {
    color: #ffffff;
    font-size: 19px;
    font-weight: bold;
    margin: 10px 0;
    line-height: 1.4;
    word-break: break-word;
}
.card-amount {
    color: #f7ef8a;
    font-size: 34px;
    font-weight: 800;
    font-family: 'Arial', sans-serif;
    margin: 10px 0 6px 0;
    text-shadow: 0px 2px 8px rgba(212, 175, 55, 0.3);
}
.card-member {
    display: inline-block;
    background-color: #262626;
    color: #d4af37;
    border: 1px solid #554411;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 12px;
    margin-top: 6px;
}
/* 集計カードの装飾 */
div[data-testid="stMetric"] {
    background-color: #141414;
    border-left: 3px solid #d4af37;
    padding: 12px 15px;
    border-radius: 6px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
}
div[data-testid="stMetricLabel"] p {
    color: #c0b283 !important;
    font-weight: bold;
}
div[data-testid="stMetricValue"] div {
    color: #f7ef8a !important;
}
</style>
<div class="luxury-banner">
    <div class="luxury-title">THE SETTLEMENT</div>
    <div class="luxury-subtitle">AMEX PRIVATE LEDGER & ANALYTICS</div>
</div>
""", unsafe_allow_html=True)

# --- 1. セッション状態（一時保存メモリ）の初期化 ---
if "pending_changes" not in st.session_state:
    st.session_state.pending_changes = {}  # {行番号: "選んだ分類"}
if "skipped_indices" not in st.session_state:
    st.session_state.skipped_indices = set()  # この画面でパスした行番号
if "history_stack" not in st.session_state:
    st.session_state.history_stack = []  # 「1つ戻る」用の履歴
if "card_mode" not in st.session_state:
    st.session_state.card_mode = "unclassified"  # unclassified / skipped / review_done
if "reviewed_indices" not in st.session_state:
    st.session_state.reviewed_indices = set()  # 最終確認で「OK」した行番号

# --- 2. Google スプレッドシート接続 ---
@st.cache_resource
def init_gspread():
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        return gspread.service_account_from_dict(creds_dict)
    else:
        return gspread.service_account(filename=r'C:\Users\tsu81\OneDrive\Desktop\クレカ精算\key.json')

try:
    client = init_gspread()
    sheet = client.open("アメックス明細_仕分けDB").sheet1
except Exception as e:
    st.error("🚨 スプレッドシートに接続できませんでした。")
    st.code(traceback.format_exc(), language="python")
    st.stop()

# --- 3. 毎月5日締め「請求月」の自動計算ロジック ---
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
        
    keep_columns = ["仕分け", "金額", "ご利用内容", "ご利用日", "カード会員様名"]
    keep_columns = [col for col in keep_columns if col in new_df.columns]
    new_df = new_df[keep_columns]
    return new_df

def save_changes_to_cloud(changes_dict, cols_order):
    """一時メモリや表で変更された内容を、クラウドの最新状態と安全に合体して保存する関数"""
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
    
    preferred_order = ["仕分け", "金額", "ご利用内容", "ご利用日", "カード会員様名"]
    cols = [c for c in preferred_order if c in df.columns] + [c for c in df.columns if c not in preferred_order]
    df = df[cols]
    
    # カード画面で仕分け中の一時データを画面上のdfにも仮反映させる
    for idx, choice in st.session_state.pending_changes.items():
        if idx < len(df):
            df.loc[idx, "仕分け"] = "未分類" if choice == "🔄 未分類に戻す" else choice

    df["金額"] = pd.to_numeric(df["金額"], errors='coerce').fillna(0).astype(int)
    df["請求月"] = df["ご利用日"].apply(calc_billing_month)
    
    billing_months = sorted([m for m in df["請求月"].unique() if m != "日付不明"], reverse=True)
    if "日付不明" in df["請求月"].unique():
        billing_months.append("日付不明")
    billing_options = billing_months + ["すべて表示"]

    # 画面上部：請求月の選択 ＆ 最新同期ボタン
    top_c1, top_c2 = st.columns([7, 3])
    with top_c1:
        selected_month = st.selectbox("📅 対象の請求月（毎月5日締め基準）", options=billing_options, index=0)
    with top_c2:
        st.write("") # 余白調整
        if st.button("🔄 相手の最新状況を反映", use_container_width=True):
            st.rerun()

    # 未保存のカード仕分けがある場合は、どこからでもすぐ保存できる目立つバーを表示
    pending_count = len(st.session_state.pending_changes)
    if pending_count > 0:
        st.warning(f"⚡ 現在 **{pending_count}件** の仕分けが一時保存されています。作業が終わったら下のボタンでクラウドへ反映してください。")
        if st.button(f"☁️ {pending_count}件の変更をクラウドにまとめて保存する", type="primary", use_container_width=True):
            with st.spinner("クラウドの最新データと合体して保存中..."):
                save_changes_to_cloud(st.session_state.pending_changes, cols)
                st.session_state.pending_changes.clear()
                st.session_state.history_stack.clear()
            st.success("✅ クラウドへの保存が完了しました！相手の画面にも反映されます。")
            st.rerun()

    # --- 5. メイン画面：3つのタブ ---
    tab1, tab2, tab3 = st.tabs(["⚡ カード仕分け", "📊 月別精算", "📈 推移・CSV追加"])

    # ================= タブ1：カード仕分け ＆ 最終確認 ＆ 一覧表 =================
    with tab1:
        if selected_month != "すべて表示":
            month_df = df[df["請求月"] == selected_month].copy()
        else:
            month_df = df.copy()

        # ① まっさらな未分類（パスしていないもの）
        pure_unclassified_df = month_df[
            (month_df["仕分け"] == "未分類") & 
            (~month_df.index.isin(st.session_state.skipped_indices))
        ]
        # ② パスして後回しにした未分類
        skipped_df = month_df[
            (month_df["仕分け"] == "未分類") & 
            (month_df.index.isin(st.session_state.skipped_indices))
        ]
        # ③ すでに仕分け済みの項目（相手または自分が仕分けたもの）で、まだ最終OKしていないもの
        done_review_df = month_df[
            (month_df["仕分け"] != "未分類") & 
            (~month_df.index.isin(st.session_state.reviewed_indices))
        ]

        total_month_count = len(month_df)
        done_month_count = len(month_df[month_df["仕分け"] != "未分類"])
        
        if total_month_count > 0:
            progress_ratio = done_month_count / total_month_count
            st.progress(progress_ratio, text=f"仕分け進捗: {done_month_count} / {total_month_count} 件完了 ({int(progress_ratio*100)}%) ※すでに仕分け済みの項目は自動でスキップされます")

        # 現在のモードに応じて表示するカードデッキを決定
        active_deck = pd.DataFrame()
        mode_title = ""

        if st.session_state.card_mode == "unclassified":
            if not pure_unclassified_df.empty:
                active_deck = pure_unclassified_df
                mode_title = f"🆕 未分類のカード（残り {len(active_deck)} 件）"
            else:
                # 未分類が終わったら自動で選択画面へ
                active_deck = pd.DataFrame()
        elif st.session_state.card_mode == "skipped":
            if not skipped_df.empty:
                active_deck = skipped_df
                mode_title = f"⏭️ パスしたカードの確認（残り {len(active_deck)} 件）"
            else:
                st.session_state.card_mode = "unclassified"
                st.rerun()
        elif st.session_state.card_mode == "review_done":
            if not done_review_df.empty:
                active_deck = done_review_df
                mode_title = f"👀 仕分け済み項目の最終チェック（残り {len(active_deck)} 件）"
            else:
                st.success("✨ すべての仕分け済みカードの最終チェックが完了しました！")
                if st.button("🔙 通常モードに戻る", use_container_width=True):
                    st.session_state.card_mode = "unclassified"
                    st.session_state.reviewed_indices.clear()
                    st.rerun()

        # --- カードデッキに中身がある場合の表示 ---
        if not active_deck.empty:
            current_idx = active_deck.index[0]
            row = active_deck.loc[current_idx]
            
            date_val = row.get("ご利用日", "-")
            store_val = row.get("ご利用内容", "-")
            amount_val = int(row.get("金額", 0))
            member_val = row.get("カード会員様名", "")
            current_cat = row.get("仕分け", "未分類")

            # 最終確認モードの時は「現在どの分類になっているか」を金色のバッジで表示
            badge_html = f'<div class="card-badge">現在の分類：{current_cat}</div>' if st.session_state.card_mode == "review_done" else ""

            st.markdown(f"""
            <div class="tinder-card">
                {badge_html}
                <div class="card-date">📅 {date_val} ｜ {mode_title}</div>
                <div class="card-store">{store_val}</div>
                <div class="card-amount">¥ {amount_val:,}</div>
                {f'<div class="card-member">💳 {member_val}</div>' if member_val else ''}
            </div>
            """, unsafe_allow_html=True)

            def select_category(cat):
                st.session_state.pending_changes[current_idx] = cat
                st.session_state.skipped_indices.discard(current_idx)
                if st.session_state.card_mode == "review_done":
                    st.session_state.reviewed_indices.add(current_idx)
                    st.session_state.history_stack.append(("review_change", current_idx))
                else:
                    st.session_state.history_stack.append(("classify", current_idx))

            # 最終確認モードの場合は、一番上にデカデカと「👌 OK（そのまま次へ）」ボタンを配置！
            if st.session_state.card_mode == "review_done":
                if st.button(f"👌 「{current_cat}」のままでOK！（次へ）", type="primary", use_container_width=True):
                    st.session_state.reviewed_indices.add(current_idx)
                    st.session_state.history_stack.append(("review_ok", current_idx))
                    st.rerun()
                st.caption("▼ もし分類を修正したい場合は、下のボタンを押すと上書きできます")

            # メインの3大ボタン（共有・ハヤト・マナ）
            btn_type = "secondary" if st.session_state.card_mode == "review_done" else "primary"
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("👫 共有", use_container_width=True, type=btn_type):
                    select_category("共有")
                    st.rerun()
            with b2:
                if st.button("👨 ハヤト", use_container_width=True, type=btn_type):
                    select_category("ハヤト")
                    st.rerun()
            with b3:
                if st.button("👩 マナ", use_container_width=True, type=btn_type):
                    select_category("マナ")
                    st.rerun()

            # サブボタン（保留・集計外・パス・1つ戻る）
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                if st.button("❓ 保留", use_container_width=True):
                    select_category("不明(保留)")
                    st.rerun()
            with s2:
                if st.button("🚫 集計外", use_container_width=True):
                    select_category("集計外")
                    st.rerun()
            with s3:
                if st.session_state.card_mode == "unclassified":
                    if st.button("⏭️ パス(後で)", use_container_width=True):
                        st.session_state.skipped_indices.add(current_idx)
                        st.session_state.history_stack.append(("skip", current_idx))
                        st.rerun()
                else:
                    if st.button("🔙 通常へ戻る", use_container_width=True):
                        st.session_state.card_mode = "unclassified"
                        st.rerun()
            with s4:
                if st.button("⬅️ 1つ戻る", use_container_width=True, disabled=(len(st.session_state.history_stack) == 0)):
                    last_action, last_idx = st.session_state.history_stack.pop()
                    if last_action == "classify":
                        st.session_state.pending_changes.pop(last_idx, None)
                    elif last_action == "skip":
                        st.session_state.skipped_indices.discard(last_idx)
                    elif last_action == "review_ok":
                        st.session_state.reviewed_indices.discard(last_idx)
                    elif last_action == "review_change":
                        st.session_state.pending_changes.pop(last_idx, None)
                        st.session_state.reviewed_indices.discard(last_idx)
                    st.rerun()

        # --- 未分類カードがすべて終わった後の「最終確認メニュー」 ---
        elif st.session_state.card_mode != "review_done":
            st.success(f"🎉 {selected_month} の新しい未分類カードはすべて処理しました！")
            
            c_after1, c_after2 = st.columns(2)
            with c_after1:
                if not skipped_df.empty:
                    if st.button(f"⏭️ パスした明細 ({len(skipped_df)}件) を確認する", type="primary", use_container_width=True):
                        st.session_state.card_mode = "skipped"
                        st.rerun()
                else:
                    st.info("⏭️ パスして残っている明細はありません。")
                    
            with c_after2:
                if done_month_count > 0:
                    if st.button(f"👀 仕分け済み ({done_month_count}件) を最終チェックする", use_container_width=True):
                        st.session_state.reviewed_indices.clear()
                        st.session_state.card_mode = "review_done"
                        st.rerun()

        st.markdown("---")

        # --- 一覧表モード（折りたたみ式でいつでも確認・修正可能） ---
        with st.expander("📋 一覧表でまとめて確認・修正する", expanded=False):
            c_filter, c_reload = st.columns([6, 4])
            with c_filter:
                only_unclassified = st.toggle("🔍「未分類」のみ表示", value=False)
            with c_reload:
                if st.button("🔄 一時変更を破棄して再読込", use_container_width=True):
                    st.session_state.pending_changes.clear()
                    st.session_state.skipped_indices.clear()
                    st.session_state.history_stack.clear()
                    st.rerun()

            table_df = month_df[month_df["仕分け"] == "未分類"].copy() if only_unclassified else month_df.copy()
            display_df = table_df[cols].copy()

            st.caption("💡 間違えて仕分けた項目を元に戻す時は「🔄 未分類に戻す」を選んで下の保存ボタンを押してください。")
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
                    "ご利用内容": st.column_config.TextColumn("内容", disabled=True, width="medium"),
                    "ご利用日": st.column_config.TextColumn("利用日", disabled=True, width="small"),
                    "カード会員様名": st.column_config.TextColumn("会員", disabled=True, width="small")
                },
                hide_index=True,
                use_container_width=True,
                height=380
            )

            if st.button("☁️ 一覧表の変更をクラウドに保存する", use_container_width=True):
                with st.spinner("最新の状態と合体して保存中..."):
                    combined_changes = dict(st.session_state.pending_changes)
                    for idx in edited_df.index:
                        combined_changes[idx] = edited_df.loc[idx, "仕分け"]
                    save_changes_to_cloud(combined_changes, cols)
                    st.session_state.pending_changes.clear()
                    st.session_state.history_stack.clear()
                st.success("✅ 保存完了！")
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

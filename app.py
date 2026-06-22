from datetime import datetime
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# =========================
# 기본 설정
# =========================
st.set_page_config(
    page_title="팀 예산 관리 시스템",
    page_icon="📊",
    layout="wide",
)

SHEET_COLUMNS = [
    "id",
    "created_at",
    "month",
    "member",
    "category",
    "amount",
    "memo",
]

DEFAULT_MEMBERS = ["부장님", "팀원1", "팀원2", "팀원3", "팀원4"]
DEFAULT_CATEGORIES = ["수선유지비", "비품", "개량공사", "대회 활동비"]


# =========================
# Apps Script API 설정
# =========================
def get_api_url() -> str:
    api_url = st.secrets.get("apps_script", {}).get("api_url", "")

    if not api_url:
        st.error("Streamlit Secrets에 Apps Script 웹앱 URL이 설정되어 있지 않습니다.")
        st.info(
            """
            `.streamlit/secrets.toml` 또는 Streamlit Cloud Secrets에 아래 형식으로 입력하세요.

            [apps_script]
            api_url = "https://script.google.com/macros/s/배포_ID/exec"
            """
        )
        st.stop()

    return api_url


def call_api(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    api_url = get_api_url()

    data = {"action": action}
    if payload:
        data.update(payload)

    try:
        response = requests.post(api_url, json=data, timeout=20)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        st.error("Apps Script API 호출에 실패했습니다.")
        st.exception(e)
        st.stop()
    except ValueError as e:
        st.error("Apps Script API 응답을 JSON으로 해석하지 못했습니다.")
        st.exception(e)
        st.stop()

    if not result.get("ok"):
        st.error(result.get("message", "Apps Script API 처리 중 오류가 발생했습니다."))
        st.stop()

    return result


@st.cache_data(ttl=10)
def load_data() -> pd.DataFrame:
    result = call_api("list")
    records = result.get("data", [])

    if not records:
        return pd.DataFrame(columns=SHEET_COLUMNS)

    df = pd.DataFrame(records)

    for col in SHEET_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[SHEET_COLUMNS]
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).astype(int)
    df["month"] = df["month"].astype(str)
    df["category"] = df["category"].astype(str)
    df["member"] = df["member"].astype(str)

    return df


def append_budget_entry(month: str, member: str, category: str, amount: int, memo: str):
    call_api(
        "append",
        {
            "month": month,
            "member": member,
            "category": category,
            "amount": int(amount),
            "memo": memo,
        },
    )
    st.cache_data.clear()


def delete_budget_entry(entry_id: int):
    call_api("delete", {"id": str(entry_id)})
    st.cache_data.clear()


# =========================
# UI 유틸
# =========================
def format_won(value: int) -> str:
    return f"{int(value):,}원"


def get_month_options(df: pd.DataFrame):
    if df.empty:
        return []
    return sorted(df["month"].dropna().unique().tolist(), reverse=True)


def render_metric_cards(df: pd.DataFrame):
    total = int(df["amount"].sum()) if not df.empty else 0
    count = len(df)

    if df.empty:
        top_category = "-"
    else:
        cat_sum = df.groupby("category")["amount"].sum().sort_values(ascending=False)
        top_category = f"{cat_sum.index[0]} ({format_won(cat_sum.iloc[0])})"

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("전체 누적 사용액", format_won(total))

    with col2:
        st.metric("최대 사용 항목", top_category)

    with col3:
        st.metric("데이터 건수", f"{count:,}건")


def render_dashboard(df: pd.DataFrame):
    st.subheader("전체 대시보드")

    if df.empty:
        st.info("아직 등록된 예산 데이터가 없습니다.")
        return

    month_options = get_month_options(df)
    selected_months = st.multiselect(
        "조회할 월을 선택하세요",
        options=month_options,
        default=month_options,
    )

    filtered_df = df[df["month"].isin(selected_months)] if selected_months else df.iloc[0:0]

    render_metric_cards(filtered_df)

    if filtered_df.empty:
        st.warning("선택한 조건에 해당하는 데이터가 없습니다.")
        return

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("#### 항목별 예산 분포")
        cat_df = (
            filtered_df.groupby("category", as_index=False)["amount"]
            .sum()
            .sort_values("amount", ascending=False)
        )
        fig = px.pie(
            cat_df,
            names="category",
            values="amount",
            hole=0.55,
        )
        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        st.markdown("#### 팀원별 누적 사용액")
        member_df = (
            filtered_df.groupby("member", as_index=False)["amount"]
            .sum()
            .sort_values("amount", ascending=False)
        )
        fig = px.bar(
            member_df,
            x="member",
            y="amount",
            text="amount",
        )
        fig.update_traces(texttemplate="%{text:,}원", textposition="outside")
        fig.update_layout(yaxis_title="사용 금액", xaxis_title="팀원")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 월별/항목별 요약 테이블")

    summary = pd.pivot_table(
        filtered_df,
        index="month",
        columns="category",
        values="amount",
        aggfunc="sum",
        fill_value=0,
    )

    for category in DEFAULT_CATEGORIES:
        if category not in summary.columns:
            summary[category] = 0

    summary = summary[DEFAULT_CATEGORIES]
    summary["합계"] = summary.sum(axis=1)
    summary = summary.sort_index(ascending=False)

    st.dataframe(
        summary.style.format("{:,.0f}"),
        use_container_width=True,
    )

    csv = filtered_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "CSV 다운로드",
        data=csv,
        file_name="team_budget_data.csv",
        mime="text/csv",
    )


def render_input_form(df: pd.DataFrame):
    st.subheader("데이터 입력")

    with st.form("budget_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            member = st.selectbox("팀원 선택", DEFAULT_MEMBERS)
            month = st.text_input(
                "해당 월",
                value=datetime.now().strftime("%Y-%m"),
                help="예: 2026-06",
            )

        with col2:
            category = st.selectbox("예산 항목", DEFAULT_CATEGORIES)
            amount = st.number_input(
                "사용 금액",
                min_value=0,
                step=1000,
                format="%d",
            )

        memo = st.text_area("메모", placeholder="선택 입력")

        submitted = st.form_submit_button("기록 저장하기", type="primary")

        if submitted:
            if not month or len(month) != 7 or month[4] != "-":
                st.error("해당 월은 YYYY-MM 형식으로 입력해주세요. 예: 2026-06")
            elif amount <= 0:
                st.error("사용 금액은 0보다 커야 합니다.")
            else:
                append_budget_entry(
                    month=month,
                    member=member,
                    category=category,
                    amount=int(amount),
                    memo=memo,
                )
                st.success("예산 데이터가 Google Sheet에 저장되었습니다.")
                st.rerun()

    st.markdown("---")
    st.subheader("최근 입력 내역")

    if df.empty:
        st.info("등록된 데이터가 없습니다.")
        return

    recent_df = df.sort_values("created_at", ascending=False).head(50).copy()
    recent_df["amount_text"] = recent_df["amount"].apply(format_won)

    st.dataframe(
        recent_df[["created_at", "month", "member", "category", "amount_text", "memo"]]
        .rename(columns={"amount_text": "amount"}),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("입력 내역 삭제"):
        delete_id = st.selectbox(
            "삭제할 내역을 선택하세요",
            options=recent_df["id"].tolist(),
            format_func=lambda x: (
                f"{recent_df[recent_df['id'] == x].iloc[0]['created_at']} | "
                f"{recent_df[recent_df['id'] == x].iloc[0]['member']} | "
                f"{recent_df[recent_df['id'] == x].iloc[0]['category']} | "
                f"{recent_df[recent_df['id'] == x].iloc[0]['amount_text']}"
            ),
        )

        if st.button("선택 내역 삭제", type="secondary"):
            delete_budget_entry(delete_id)
            st.success("선택한 내역을 삭제했습니다.")
            st.rerun()


def main():
    st.title("📊 팀 예산 관리 시스템")
    st.caption("Google Apps Script + Google Sheets 기반 월별 예산 취합 및 Streamlit 대시보드")

    df = load_data()

    tab_input, tab_dashboard = st.tabs(["데이터 입력", "전체 대시보드"])

    with tab_input:
        render_input_form(df)

    with tab_dashboard:
        render_dashboard(df)


if __name__ == "__main__":
    main()

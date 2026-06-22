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

            [admin]
            password = "관리자_비밀번호"
            """
        )
        st.stop()

    return api_url


def get_admin_password() -> str:
    return st.secrets.get("admin", {}).get("password", "")


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


@st.cache_data(ttl=10)
def load_config() -> dict[str, list[str]]:
    result = call_api("config")
    config = result.get("data", {})

    members = config.get("members") or DEFAULT_MEMBERS
    categories = config.get("categories") or DEFAULT_CATEGORIES

    return {
        "members": members,
        "categories": categories,
    }


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


def add_config_item(config_type: str, value: str):
    call_api(
        "addConfig",
        {
            "type": config_type,
            "value": value.strip(),
        },
    )
    st.cache_data.clear()


def delete_config_item(config_type: str, value: str):
    call_api(
        "deleteConfig",
        {
            "type": config_type,
            "value": value.strip(),
        },
    )
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


def render_dashboard(df: pd.DataFrame, categories: list[str]):
    st.subheader("전체 대시보드")

    if df.empty:
        st.info("아직 등록된 예산 데이터가 없습니다.")
        return

    month_options = get_month_options(df)

    selected_month = st.selectbox(
        "조회할 월을 선택하세요",
        options=["전체"] + month_options,
        index=0,
    )

    if selected_month == "전체":
        filtered_df = df.copy()
        period_label = "전체 기간"
    else:
        filtered_df = df[df["month"] == selected_month].copy()
        period_label = selected_month

    st.markdown(f"### 조회 기간: {period_label}")

    render_metric_cards(filtered_df)

    if filtered_df.empty:
        st.warning("선택한 월에 해당하는 데이터가 없습니다.")
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

        fig.update_traces(
            textinfo="label+percent+value",
            hovertemplate="%{label}<br>%{value:,}원<extra></extra>",
        )

        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        st.markdown("#### 팀원별 누적 사용액")

        member_category_df = (
            filtered_df.groupby(["member", "category"], as_index=False)["amount"]
            .sum()
        )

        member_total_df = (
            filtered_df.groupby("member", as_index=False)["amount"]
            .sum()
            .rename(columns={"amount": "member_total"})
            .sort_values("member_total", ascending=False)
        )

        member_order = member_total_df["member"].tolist()

        member_category_df["label"] = member_category_df.apply(
            lambda row: f"{row['category']}<br>{int(row['amount']):,}원",
            axis=1,
        )

        fig = px.bar(
            member_category_df,
            x="member",
            y="amount",
            color="category",
            text="label",
            category_orders={
                "member": member_order,
                "category": categories,
            },
            labels={
                "member": "팀원",
                "amount": "사용 금액",
                "category": "예산 항목",
            },
            title="팀원별 / 항목별 누적 사용액",
        )

        fig.update_layout(
            barmode="stack",
            yaxis_title="사용 금액",
            xaxis_title="팀원",
            legend_title_text="예산 항목",
            uniformtext_minsize=10,
            uniformtext_mode="hide",
        )

        fig.update_traces(
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate=(
                "팀원=%{x}<br>"
                "사용 금액=%{y:,}원<br>"
                "<extra></extra>"
            ),
        )

        # 팀원별 총액 라벨을 막대 위에 표시
        max_total = int(member_total_df["member_total"].max()) if not member_total_df.empty else 0

        for _, row in member_total_df.iterrows():
            fig.add_annotation(
                x=row["member"],
                y=row["member_total"],
                text=f"{int(row['member_total']):,}원",
                showarrow=False,
                yshift=12,
                font=dict(size=13),
            )

        fig.update_yaxes(range=[0, max_total * 1.15 if max_total > 0 else 1])

        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 팀원별 / 항목별 상세 사용 내역")

    detail_table = pd.pivot_table(
        filtered_df,
        index="member",
        columns="category",
        values="amount",
        aggfunc="sum",
        fill_value=0,
    )

    for category in categories:
        if category not in detail_table.columns:
            detail_table[category] = 0

    detail_table = detail_table[categories]
    detail_table["합계"] = detail_table.sum(axis=1)
    detail_table = detail_table.sort_values("합계", ascending=False)

    st.dataframe(
        detail_table.style.format("{:,.0f}"),
        use_container_width=True,
    )

    st.markdown("#### 월별/항목별 요약 테이블")

    summary = pd.pivot_table(
        filtered_df,
        index="month",
        columns="category",
        values="amount",
        aggfunc="sum",
        fill_value=0,
    )

    for category in categories:
        if category not in summary.columns:
            summary[category] = 0

    summary = summary[categories]
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
        file_name=f"team_budget_data_{selected_month}.csv",
        mime="text/csv",
    )


def render_input_form(df: pd.DataFrame, members: list[str], categories: list[str]):
    st.subheader("데이터 입력")

    if not members:
        st.warning("등록된 팀원이 없습니다. 관리자 페이지에서 팀원을 추가하세요.")
        return

    if not categories:
        st.warning("등록된 예산 항목이 없습니다. 관리자 페이지에서 예산 항목을 추가하세요.")
        return

    with st.form("budget_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            member = st.selectbox("팀원 선택", members)
            month = st.text_input(
                "해당 월",
                value=datetime.now().strftime("%Y-%m"),
                help="예: 2026-06",
            )

        with col2:
            category = st.selectbox("예산 항목", categories)
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


def render_admin_login():
    st.subheader("관리자 로그인")

    admin_password = get_admin_password()

    if not admin_password:
        st.warning(
            """
            관리자 비밀번호가 설정되어 있지 않습니다.

            Streamlit Secrets에 아래 내용을 추가하세요.

            [admin]
            password = "원하는_관리자_비밀번호"
            """
        )
        return False

    with st.form("admin_login_form"):
        password = st.text_input("관리자 비밀번호", type="password")
        submitted = st.form_submit_button("관리자 페이지 접속")

    if submitted:
        if password == admin_password:
            st.session_state["admin_authenticated"] = True
            st.success("관리자 인증이 완료되었습니다.")
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")

    return False


def render_admin_page(members: list[str], categories: list[str]):
    st.subheader("관리자 페이지")

    if not st.session_state.get("admin_authenticated", False):
        render_admin_login()
        return

    col_logout, _ = st.columns([1, 4])
    with col_logout:
        if st.button("관리자 로그아웃"):
            st.session_state["admin_authenticated"] = False
            st.rerun()

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 팀원 관리")

        if members:
            st.write("현재 팀원 목록")
            st.dataframe(pd.DataFrame({"팀원": members}), use_container_width=True, hide_index=True)
        else:
            st.info("등록된 팀원이 없습니다.")

        with st.form("add_member_form", clear_on_submit=True):
            new_member = st.text_input("추가할 팀원 이름")
            submitted = st.form_submit_button("팀원 추가", type="primary")

            if submitted:
                if not new_member.strip():
                    st.error("팀원 이름을 입력하세요.")
                elif new_member.strip() in members:
                    st.error("이미 등록된 팀원입니다.")
                else:
                    add_config_item("member", new_member)
                    st.success(f"팀원 '{new_member.strip()}'을 추가했습니다.")
                    st.rerun()

        with st.expander("팀원 삭제"):
            if members:
                remove_member = st.selectbox("삭제할 팀원", members, key="remove_member")
                st.caption("주의: 기존 예산 데이터에 이미 저장된 팀원명은 변경되지 않습니다.")
                if st.button("선택한 팀원 삭제"):
                    delete_config_item("member", remove_member)
                    st.success(f"팀원 '{remove_member}'을 삭제했습니다.")
                    st.rerun()
            else:
                st.info("삭제할 팀원이 없습니다.")

    with col2:
        st.markdown("### 예산 항목 관리")

        if categories:
            st.write("현재 예산 항목 목록")
            st.dataframe(pd.DataFrame({"예산 항목": categories}), use_container_width=True, hide_index=True)
        else:
            st.info("등록된 예산 항목이 없습니다.")

        with st.form("add_category_form", clear_on_submit=True):
            new_category = st.text_input("추가할 예산 항목")
            submitted = st.form_submit_button("예산 항목 추가", type="primary")

            if submitted:
                if not new_category.strip():
                    st.error("예산 항목명을 입력하세요.")
                elif new_category.strip() in categories:
                    st.error("이미 등록된 예산 항목입니다.")
                else:
                    add_config_item("category", new_category)
                    st.success(f"예산 항목 '{new_category.strip()}'을 추가했습니다.")
                    st.rerun()

        with st.expander("예산 항목 삭제"):
            if categories:
                remove_category = st.selectbox("삭제할 예산 항목", categories, key="remove_category")
                st.caption("주의: 기존 예산 데이터에 이미 저장된 항목명은 변경되지 않습니다.")
                if st.button("선택한 예산 항목 삭제"):
                    delete_config_item("category", remove_category)
                    st.success(f"예산 항목 '{remove_category}'을 삭제했습니다.")
                    st.rerun()
            else:
                st.info("삭제할 예산 항목이 없습니다.")


def main():
    st.title("📊 팀 예산 관리 시스템")
    st.caption("Google Apps Script + Google Sheets 기반 월별 예산 취합 및 Streamlit 대시보드")

    config = load_config()
    members = config["members"]
    categories = config["categories"]

    df = load_data()

    tab_input, tab_dashboard, tab_admin = st.tabs(["데이터 입력", "전체 대시보드", "관리자"])

    with tab_input:
        render_input_form(df, members, categories)

    with tab_dashboard:
        render_dashboard(df, categories)

    with tab_admin:
        render_admin_page(members, categories)


if __name__ == "__main__":
    main()

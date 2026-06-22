from datetime import datetime
from typing import Any
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="팀 예산 관리 시스템", page_icon="📊", layout="wide")
SHEET_COLUMNS=["id","created_at","month","member","category","amount","memo"]
DEFAULT_MEMBERS=["부장님","팀원1","팀원2","팀원3","팀원4"]
DEFAULT_CATEGORIES=["수선유지비","비품","개량공사","대회 활동비"]

def get_api_url():
    api_url=st.secrets.get("apps_script",{}).get("api_url","")
    if not api_url:
        st.error("Streamlit Secrets에 Apps Script 웹앱 URL이 없습니다.")
        st.code('[apps_script]\napi_url = "https://script.google.com/macros/s/배포_ID/exec"\n\n[admin]\npassword = "관리자_비밀번호"', language='toml')
        st.stop()
    return api_url

def get_admin_password():
    return st.secrets.get("admin",{}).get("password","")

def call_api(action:str, payload:dict[str,Any]|None=None):
    data={"action":action}
    if payload: data.update(payload)
    try:
        res=requests.post(get_api_url(), json=data, timeout=20)
        res.raise_for_status()
        result=res.json()
    except Exception as e:
        st.error("Apps Script API 호출에 실패했습니다.")
        st.exception(e)
        st.stop()
    if not result.get("ok"):
        st.error(result.get("message","Apps Script API 오류"))
        st.stop()
    return result

@st.cache_data(ttl=10)
def load_data():
    records=call_api("list").get("data",[])
    if not records: return pd.DataFrame(columns=SHEET_COLUMNS)
    df=pd.DataFrame(records)
    for c in SHEET_COLUMNS:
        if c not in df.columns: df[c]=""
    df=df[SHEET_COLUMNS]
    df["amount"]=pd.to_numeric(df["amount"], errors="coerce").fillna(0).astype(int)
    for c in ["month","member","category"]: df[c]=df[c].astype(str)
    return df

@st.cache_data(ttl=10)
def load_config():
    cfg=call_api("config").get("data",{})
    return {"members":cfg.get("members") or DEFAULT_MEMBERS, "categories":cfg.get("categories") or DEFAULT_CATEGORIES}

def append_budget_entry(month,member,category,amount,memo):
    call_api("append", {"month":month,"member":member,"category":category,"amount":int(amount),"memo":memo})
    st.cache_data.clear()

def delete_budget_entry(entry_id):
    call_api("delete", {"id":str(entry_id)})
    st.cache_data.clear()

def add_config_item(config_type,value):
    call_api("addConfig", {"type":config_type,"value":value.strip()})
    st.cache_data.clear()

def delete_config_item(config_type,value):
    call_api("deleteConfig", {"type":config_type,"value":value.strip()})
    st.cache_data.clear()

def format_won(v): return f"{int(v):,}원"

def render_metric_cards(df):
    total=int(df["amount"].sum()) if not df.empty else 0
    count=len(df)
    top="-" if df.empty else (lambda s: f"{s.index[0]} ({format_won(s.iloc[0])})")(df.groupby("category")["amount"].sum().sort_values(ascending=False))
    c1,c2,c3=st.columns(3)
    c1.metric("전체 누적 사용액",format_won(total)); c2.metric("최대 사용 항목",top); c3.metric("데이터 건수",f"{count:,}건")

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
def render_input_form(df,members,categories):
    st.subheader("데이터 입력")
    if not members: st.warning("관리자 페이지에서 팀원을 추가하세요."); return
    if not categories: st.warning("관리자 페이지에서 예산 항목을 추가하세요."); return
    with st.form("budget_form", clear_on_submit=True):
        c1,c2=st.columns(2)
        with c1:
            member=st.selectbox("팀원 선택",members)
            month=st.text_input("해당 월",value=datetime.now().strftime("%Y-%m"),help="예: 2026-06")
        with c2:
            category=st.selectbox("예산 항목",categories)
            amount=st.number_input("사용 금액",min_value=0,step=1000,format="%d")
        memo=st.text_area("메모",placeholder="선택 입력")
        if st.form_submit_button("기록 저장하기",type="primary"):
            if not month or len(month)!=7 or month[4]!="-": st.error("해당 월은 YYYY-MM 형식으로 입력해주세요.")
            elif amount<=0: st.error("사용 금액은 0보다 커야 합니다.")
            else:
                append_budget_entry(month,member,category,int(amount),memo); st.success("저장되었습니다."); st.rerun()
    st.markdown("---"); st.subheader("최근 입력 내역")
    if df.empty: st.info("등록된 데이터가 없습니다."); return
    recent=df.sort_values("created_at",ascending=False).head(50).copy(); recent["amount_text"]=recent["amount"].apply(format_won)
    st.dataframe(recent[["created_at","month","member","category","amount_text","memo"]].rename(columns={"amount_text":"amount"}), use_container_width=True, hide_index=True)
    with st.expander("입력 내역 삭제"):
        delete_id=st.selectbox("삭제할 내역", recent["id"].tolist(), format_func=lambda x: f"{recent[recent['id']==x].iloc[0]['created_at']} | {recent[recent['id']==x].iloc[0]['member']} | {recent[recent['id']==x].iloc[0]['category']} | {recent[recent['id']==x].iloc[0]['amount_text']}")
        if st.button("선택 내역 삭제"):
            delete_budget_entry(delete_id); st.success("삭제했습니다."); st.rerun()

def render_admin_login():
    st.subheader("관리자 로그인")
    admin_password=get_admin_password()
    if not admin_password:
        st.warning("관리자 비밀번호가 설정되어 있지 않습니다. Streamlit Secrets에 [admin] password를 추가하세요.")
        st.code('[admin]\npassword = "관리자_비밀번호"', language='toml')
        return
    with st.form("admin_login_form"):
        pw=st.text_input("관리자 비밀번호",type="password")
        submitted=st.form_submit_button("관리자 페이지 접속")
    if submitted:
        if pw==admin_password:
            st.session_state["admin_authenticated"]=True; st.success("관리자 인증 완료"); st.rerun()
        else: st.error("비밀번호가 올바르지 않습니다.")

def render_admin_page(members,categories):
    st.subheader("관리자 페이지")
    if not st.session_state.get("admin_authenticated",False):
        render_admin_login(); return
    if st.button("관리자 로그아웃"):
        st.session_state["admin_authenticated"]=False; st.rerun()
    st.markdown("---")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("### 팀원 관리")
        st.dataframe(pd.DataFrame({"팀원":members}), use_container_width=True, hide_index=True)
        with st.form("add_member_form", clear_on_submit=True):
            new=st.text_input("추가할 팀원 이름")
            if st.form_submit_button("팀원 추가",type="primary"):
                if not new.strip(): st.error("팀원 이름을 입력하세요.")
                elif new.strip() in members: st.error("이미 등록된 팀원입니다.")
                else: add_config_item("member",new); st.success(f"'{new.strip()}' 추가 완료"); st.rerun()
        with st.expander("팀원 삭제"):
            if members:
                rm=st.selectbox("삭제할 팀원",members,key="remove_member")
                st.caption("기존 예산 데이터에 저장된 팀원명은 변경되지 않습니다.")
                if st.button("선택한 팀원 삭제"):
                    delete_config_item("member",rm); st.success(f"'{rm}' 삭제 완료"); st.rerun()
    with c2:
        st.markdown("### 예산 항목 관리")
        st.dataframe(pd.DataFrame({"예산 항목":categories}), use_container_width=True, hide_index=True)
        with st.form("add_category_form", clear_on_submit=True):
            new=st.text_input("추가할 예산 항목")
            if st.form_submit_button("예산 항목 추가",type="primary"):
                if not new.strip(): st.error("예산 항목명을 입력하세요.")
                elif new.strip() in categories: st.error("이미 등록된 예산 항목입니다.")
                else: add_config_item("category",new); st.success(f"'{new.strip()}' 추가 완료"); st.rerun()
        with st.expander("예산 항목 삭제"):
            if categories:
                rm=st.selectbox("삭제할 예산 항목",categories,key="remove_category")
                st.caption("기존 예산 데이터에 저장된 항목명은 변경되지 않습니다.")
                if st.button("선택한 예산 항목 삭제"):
                    delete_config_item("category",rm); st.success(f"'{rm}' 삭제 완료"); st.rerun()

def main():
    st.title("📊 팀 예산 관리 시스템")
    st.caption("Google Apps Script + Google Sheets 기반 월별 예산 취합 및 Streamlit 대시보드")
    cfg=load_config(); members=cfg["members"]; categories=cfg["categories"]
    df=load_data()
    t1,t2,t3=st.tabs(["데이터 입력","전체 대시보드","관리자"])
    with t1: render_input_form(df,members,categories)
    with t2: render_dashboard(df,categories)
    with t3: render_admin_page(members,categories)

if __name__=="__main__": main()

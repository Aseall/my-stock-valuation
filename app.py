import streamlit as st
import yfinance as yf
import time

def fetch_stock_data_via_yahoo_integrated(ticker_code, time_unit, time_value):
    """야후 파이낸스 엔진으로 데이터를 가져오고 네이버 금융 링크를 동적으로 생성하는 함수"""
    
    if time_unit == "분 (Min)":
        ttl_seconds = time_value * 60
    else:
        ttl_seconds = time_value
        
    if ttl_seconds < 1:
        ttl_seconds = 1
        
    @st.cache_data(ttl=ttl_seconds, show_spinner=False)
    def _inner_fetch(code, timestamp_block):
        try:
            yahoo_ticker = f"{code}.KS"
            stock = yf.Ticker(yahoo_ticker)
            info = stock.info
            
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            eps = info.get('trailingEps') or info.get('forwardEps') or 0
            pbr = info.get('priceToBook') or 1.0
            bps = info.get('bookValue') or (current_price / pbr if current_price else 0)

            # 가치평가 타깃가 수식 연산
            if eps <= 0:
                income_target = current_price * 1.15
                relative_target = current_price * 1.0
            else:
                income_target = eps * 12
                relative_target = eps * 10
                
            asset_target = bps * 1.2
            
            # 사용자가 바로 점프해서 확인할 수 있는 네이버 금융 링크 자동 맵핑
            naver_url = f"https://finance.naver.com/item/main.naver?code={code}"

            return {
                "current_price": int(current_price),
                "raw_eps": eps,
                "raw_bps": bps,
                "income_target": int(income_target),
                "asset_target": int(asset_target),
                "relative_target": int(relative_target),
                "fetched_time": time.strftime('%H시 %M분 %S초'),
                "source_url": naver_url
            }
        except Exception:
            return None

    current_block = int(time.time() // ttl_seconds)
    return _inner_fetch(ticker_code, current_block)

# --- Streamlit UI 구성 ---
st.set_page_config(page_title="실시간 상장주식 가치평가 툴", layout="wide")

st.title("📊 실시간 상장주식 3대 가치평가 툴")
st.caption("가장 정확한 Yahoo Finance 데이터 엔진과 검증용 네이버 금융 워프 시스템이 통합되었습니다.")

STOCKS = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "현대차": "005380",
    "NAVER": "035420"
}

# --- 사이드바 컨트롤러 영역 ---
st.sidebar.header("🔎 종목 검색 및 설정")
selected_stock = st.sidebar.selectbox("분석할 주식을 선택하세요", list(STOCKS.keys()))
safety_margin = st.sidebar.slider("원하는 안전마진 비율 (%)", min_value=0, max_value=50, value=20, step=5)

st.sidebar.markdown("---")
st.sidebar.subheader("⏱️ 데이터 갱신 설정")

time_unit = st.sidebar.radio("시간 단위를 선택하세요", ["분 (Min)", "초 (Sec)"])

if time_unit == "분 (Min)":
    cache_time = st.sidebar.slider("자동 갱신 주기 (분)", min_value=1, max_value=30, value=5)
else:
    cache_time = st.sidebar.slider("자동 갱신 주기 (초)", min_value=5, max_value=60, value=10, step=5)

code = STOCKS[selected_stock]

with st.spinner("금융 마켓 엔진에서 실시간 신뢰 데이터를 빌드하는 중..."):
    stock_data = fetch_stock_data_via_yahoo_integrated(code, time_unit, cache_time)

if stock_data:
    st.subheader(f"📈 {selected_stock} ({code}) 현재 주가")
    
    col_p, col_t = st.columns([2, 1])
    with col_p:
        st.metric(label="현재 시장 가격", value=f"{stock_data['current_price']:,} 원")
    with col_t:
        st.info(f"**⏰ 마지막 데이터 동기화 시간:** {stock_data['fetched_time']}")
        st.caption(f"*(설정하신 대로 {cache_time}{time_unit[0]} 동안 이 데이터가 유지됩니다)*")
    
    # --- 🔎 롤백 앤 빌드: 수식 디버깅 및 출처 점프 버튼 시스템 ---
    st.markdown("### 🔎 수식 디버깅 및 데이터 출처 검증")
    with st.expander("📂 가치평가 파라미터 변수 및 데이터 출처 확인 (클릭하여 열기)", expanded=True):
        c_eps, c_bps, c_sm, c_btn = st.columns([1.2, 1.2, 1, 1.2])
        c_eps.markdown(f"**수익성 지표 (Yahoo EPS):**\n`{stock_data['raw_eps']:,.2f} 원`")
        c_bps.markdown(f"**자산성 지표 (Yahoo BPS):**\n`{stock_data['raw_bps']:,.2f} 원`")
        c_sm.markdown(f"**설정된 안전마진:**\n`{safety_margin} %` (할인율: `{1 - safety_margin/100:.2f}`)")
        
        # 🔗 사용자가 값을 보고 싶을 때 네이버 공식 사이트로 바로 점프하는 버튼
        c_btn.markdown("**🔗 원천 지표 검증**")
        c_btn.link_button("네이버 금융 종목 홈 이동", stock_data["source_url"])

    st.markdown("---")
    st.subheader("📉 독립형 3대 가치평가 모델 및 계산 과정")
    
    col1, col2, col3 = st.columns(3)
    margin_factor = 1 - safety_margin / 100
    
    with col1:
        st.info("### 1. 수익 중심 모델 (EPS 가치)")
        target = stock_data["income_target"]
        max_buy = int(target * margin_factor)
        
        st.markdown(f"**⚙️ 계산 과정:**")
        if stock_data['raw_eps'] <= 0:
            st.code(f"적정가 = 적자 기업 우회 수식 가동\n       = 현재가 × 1.15\n       = {target:,} 원", language="text")
        else:
            st.code(f"적정가 = EPS × PER 12배\n       = {stock_data['raw_eps']:,.0f} × 12\n       = {target:,} 원", language="text")
            
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
            
    with col2:
        st.warning("### 2. 자산 중심 모델 (BPS 청산가치)")
        target = stock_data["asset_target"]
        max_buy = int(target * margin_factor)
        
        st.markdown(f"**⚙️ 계산 과정:**")
        st.code(f"적정가 = BPS × PBR 1.2배\n       = {stock_data['raw_bps']:,.0f} × 1.2\n       = {target:,} 원", language="text")
        
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
            
    with col3:
        st.success("### 3. 상대 비교 모델 (PER 멀티플)")
        target = stock_data["relative_target"]
        max_buy = int(target * margin_factor)
        
        st.markdown(f"**⚙️ 계산 과정:**")
        if stock_data['raw_eps'] <= 0:
            st.code(f"적정가 = 적자 기업 우회 수식 가동\n       = 현재가 × 1.0\n       = {target:,} 원", language="text")
        else:
            st.code(f"적정가 = EPS × 타깃 PER 10배\n       = {stock_data['raw_eps']:,.0f} × 10\n       = {target:,} 원", language="text")
            
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
else:
    st.error("데이터 서버와 통신이 원활하지 않습니다. 잠시 후 페이지를 새로고침 해주세요.")
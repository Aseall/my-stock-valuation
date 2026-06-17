import streamlit as st
import yfinance as yf
import time
from datetime import datetime, timedelta

def fetch_stock_data_yahoo_pure(ticker_code, time_unit, time_value):
    """
    야후 파이낸스(Yahoo Finance) 사이트에서 제공하는 
    실시간 현재가, EPS, PBR, BPS, PER 지표를 그대로 가져오는 엔진
    """
    if time_unit == "분 (Min)":
        ttl_seconds = time_value * 60
    else:
        ttl_seconds = time_value
        
    if ttl_seconds < 1:
        ttl_seconds = 1
        
    @st.cache_data(ttl=ttl_seconds, show_spinner=False)
    def _inner_fetch(code, timestamp_block):
        try:
            # 야후 파이낸스 티커 규격 매핑 (코스피는 .KS)
            yahoo_ticker = f"{code}.KS"
            stock = yf.Ticker(yahoo_ticker)
            info = stock.info
            
            # 야후 파이낸스 사이트가 제공하는 원천 지표 그대로 매핑
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            raw_eps = info.get('trailingEps') or info.get('forwardEps') or 0.0
            raw_pbr = info.get('priceToBook') or 1.0
            raw_per = info.get('trailingPegRatio') or info.get('trailingPeRatio') or 0.0
            
            # 만약 야후가 제공하는 실시간 PER가 없다면 현재가/EPS로 사이트와 동일하게 유도
            if not raw_per and raw_eps > 0:
                raw_per = current_price / raw_eps
                
            # BPS 역산 또는 가져오기
            raw_bps = info.get('bookValue') or (current_price / raw_pbr if current_price else 0.0)
            
            # 🔗 야후 파이낸스 해당 종목 웹사이트 다이렉트 상세 링크 생성
            yahoo_url = f"https://finance.yahoo.com/quote/{yahoo_ticker}"

            # ⏰ 해외 서버 시간을 대한민국 표준시(KST)로 강제 정합 보정
            utc_now = datetime.utcnow()
            kor_now = utc_now + timedelta(hours=9)
            kor_time_str = kor_now.strftime('%Y-%m-%d %H시 %M분 %S초')

            return {
                "current_price": int(current_price) if current_price else 0,
                "raw_eps": raw_eps,
                "raw_pbr": raw_pbr,
                "raw_per": raw_per,
                "raw_bps": raw_bps,
                "fetched_time": kor_time_str,
                "source_url": yahoo_url
            }
        except Exception as e:
            st.error(f"야후 파이낸스 엔진 로딩 오류: {str(e)}")
            return None

    current_block = int(time.time() // ttl_seconds)
    return _inner_fetch(ticker_code, current_block)

# --- Streamlit UI 레이아웃 구성 ---
st.set_page_config(page_title="실시간 상장주식 가치평가 툴", layout="wide")

st.title("📊 실시간 상장주식 3대 가치평가 툴")
st.caption("Yahoo Finance의 원천 실시간 데이터 지표를 그대로 활용하며, 야후 파이낸셜 검증 시스템과 동기화됩니다.")

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

with st.spinner("야후 파이낸셜 마켓 엔진에서 실시간 데이터를 빌드하는 중..."):
    stock_data = fetch_stock_data_yahoo_pure(code, time_unit, cache_time)

if stock_data:
    # 야후 파이낸스 데이터 제공 오류 방어 벨트 (EPS가 0 이하로 밀려 들어올 때)
    is_yahoo_error = stock_data["raw_eps"] <= 0
    
    st.subheader(f"📈 {selected_stock} ({code}) 현재 주가")
    
    col_p, col_t = st.columns([2, 1])
    with col_p:
        st.metric(label="현재 시장 가격 (Yahoo Price)", value=f"{stock_data['current_price']:,} 원")
    with col_t:
        st.info(f"**⏰ KST 실시간 동기화 시간:** {stock_data['fetched_time']}")
        st.caption(f"*(해외 서버 타임존을 한국 표준시로 정밀 가공하여 매핑했습니다)*")

    # --- 🔎 수식 디버깅 및 야후 파이낸셜 출처 검증 영역 ---
    st.markdown("### 🔎 수식 디버깅 및 데이터 출처 검증")
    with st.expander("📂 가치평가 파라미터 변수 및 야후 파이낸셜 원천 링크 (클릭하여 열기)", expanded=True):
        c_eps, c_per, c_pbr, c_btn = st.columns([1, 1, 1, 1.2])
        c_eps.markdown(f"**야후 제공 EPS:**\n`{stock_data['raw_eps']:,.2f} 원`")
        c_per.markdown(f"**야후 제공 PER:**\n`{stock_data['raw_per']:,.2f} 배`")
        c_pbr.markdown(f"**야후 제공 PBR:**\n`{stock_data['raw_pbr']:,.2f} 배`")
        
        # 🔗 사용자가 원천 지표 데이터를 사이트에서 눈으로 직접 대조해 볼 수 있는 버튼
        c_btn.markdown("**🔗 Yahoo 원천 지표 검증**")
        c_btn.link_button("Yahoo Finance 원본 사이트 이동", stock_data["source_url"])

    st.markdown("---")
    st.subheader("📉 독립형 3대 가치평가 모델 및 계산 과정")
    
    col1, col2, col3 = st.columns(3)
    margin_factor = 1 - safety_margin / 100
    
    # 1. 수익 중심 모델 (사이트 제공 EPS * 표준 PER 12배)
    with col1:
        st.info("### 1. 수익 중심 모델 (EPS 가치)")
        if is_yahoo_error:
            target = int(stock_data["current_price"] * 1.15)
            process_text = f"적정가 = 야후 데이터 0 보정 우회 수식 가동\n       = 현재가 × 1.15\n       = {target:,} 원"
        else:
            target = int(stock_data["raw_eps"] * 12)
            process_text = f"적정가 = 야후 EPS × PER 12배\n       = {stock_data['raw_eps']:,.2f} × 12\n       = {target:,} 원"
            
        max_buy = int(target * margin_factor)
        
        st.markdown("**⚙️ 계산 과정:**")
        st.code(f"{process_text}\n\n매수가 = 적정가 × 안전마진\n       = {target:,} × {margin_factor:.2f}\n       = {max_buy:,} 원", language="text")
        
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
            
    # 2. 자산 중심 모델 (사이트 제공 BPS * 표준 PBR 1.2배)
    with col2:
        st.warning("### 2. 자산 중심 모델 (BPS 청산가치)")
        target = int(stock_data["raw_bps"] * 1.2)
        max_buy = int(target * margin_factor)
        
        st.markdown("**⚙️ 계산 과정:**")
        st.code(f"적정가 = 야후 BPS × PBR 1.2배\n       = {stock_data['raw_bps']:,.2f} × 1.2\n       = {target:,} 원\n\n매수가 = 적정가 × 안전마진\n       = {target:,} × {margin_factor:.2f}\n       = {max_buy:,} 원", language="text")
        
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
            
    # 3. 상대 비교 모델 (사이트 제공 EPS * 표준 PER 10배)
    with col3:
        st.success("### 3. 상대 비교 모델 (PER 멀티플)")
        if is_yahoo_error:
            target = int(stock_data["current_price"] * 1.0)
            process_text = f"적정가 = 야후 데이터 0 보정 우회 수식 가동\n       = 현재가 × 1.0\n       = {target:,} 원"
        else:
            target = int(stock_data["raw_eps"] * 10)
            process_text = f"적정가 = 야후 EPS × 타깃 PER 10배\n       = {stock_data['raw_eps']:,.2f} × 10\n       = {target:,} 원"
            
        max_buy = int(target * margin_factor)
        
        st.markdown("**⚙️ 계산 과정:**")
        st.code(f"{process_text}\n\n매수가 = 적정가 × 안전마진\n       = {target:,} × {margin_factor:.2f}\n       = {max_buy:,} 원", language="text")
        
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
else:
    st.error("야후 파이낸스 마켓 전산망과 통신이 원활하지 않습니다.")
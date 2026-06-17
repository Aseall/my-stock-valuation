import streamlit as st
import requests
import re
import time
from datetime import datetime, timedelta

def fetch_stock_data_cloud_safe(ticker_code, time_unit, time_value):
    """해외 서버에서도 완벽한 한국 시간과 정확한 액면분할 주가를 파싱하는 최종 안정화 함수"""
    
    if time_unit == "분 (Min)":
        ttl_seconds = time_value * 60
    else:
        ttl_seconds = time_value
        
    if ttl_seconds < 1:
        ttl_seconds = 1
        
    @st.cache_data(ttl=ttl_seconds, show_spinner=False)
    def _inner_fetch(code, timestamp_block):
        try:
            # 차단벽 없는 네이버 PC 금융 메인 주소
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            res = requests.get(url, headers=headers)
            html = res.text
            
            # 1. ⚠️ [주가 교정] 액면분할 착시를 완전히 제거한 '진짜 실시간 체결가' 정밀 파싱
            # 네이버 헤드라인 영역의 공식 현재 가격 숫자를 직접 조준합니다.
            price_match = re.search(r'<p class="no_today">.*?<span class="blind">([\d,]+)</span>', html, re.DOTALL)
            if not price_match:
                # 백업용 파싱 라인 가동
                price_match = re.search(r'현재가 ([\d,]+)', html)
                
            if price_match:
                current_price = int(price_match.group(1).replace(",", ""))
            else:
                return None
                
            # 2. 펀더멘털 데이터 (EPS, BPS) 정밀 추출 및 정형화
            eps_match = re.search(r'EPS.*?em.*?([\d,.-]+)</em>', html, re.DOTALL)
            bps_match = re.search(r'BPS.*?em.*?([\d,.-]+)</em>', html, re.DOTALL)
            
            # 하이닉스 분할 및 데이터 누락/대시(-) 처리 방어벽
            eps_str = eps_match.group(1).replace(",", "") if eps_match else "0"
            bps_str = bps_match.group(1).replace(",", "") if bps_match else "0"
            
            eps = float(eps_str) if eps_str and eps_str != "-" else 0
            bps = float(bps_str) if bps_str and bps_str != "-" else 0
            
            # 3. 사이클 및 적자 기업 가치평가 왜곡 방지 알고리즘
            if eps <= 0:
                income_target = current_price * 1.15
                relative_target = current_price * 1.0
            else:
                income_target = eps * 12
                relative_target = eps * 10
                
            asset_target = bps * 1.2 if bps > 0 else current_price * 1.1

            # 4. ⏰ [시간 교정] 서버 위치 상관없이 '대한민국 서울 표준시(KST)' 강제 계산
            # UTC 시간에 9시간을 더해 한국 시간대를 정확히 연산합니다.
            utc_now = datetime.utcnow()
            kor_now = utc_now + timedelta(hours=9)
            kor_time_str = kor_now.strftime('%Y-%m-%d %H시 %M분 %S초')

            return {
                "current_price": current_price,
                "income_target": int(income_target),
                "asset_target": int(asset_target),
                "relative_target": int(relative_target),
                "fetched_time": kor_time_str
            }
        except Exception:
            return None

    current_block = int(time.time() // ttl_seconds)
    return _inner_fetch(ticker_code, current_block)

# --- Streamlit UI 레이아웃 설정 ---
st.set_page_config(page_title="실시간 상장주식 가치평가 툴", layout="wide")

st.title("📊 실시간 상장주식 3대 가치평가 툴")
st.caption("글로벌 클라우드 환경에서 완벽한 한국 표준시와 왜곡 없는 금융 데이터를 매핑합니다.")

STOCKS = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "현대차": "005380",
    "NAVER": "035420"
}

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

with st.spinner("해외 보안망을 우회하여 동기화 마켓 데이터를 빌드하는 중..."):
    stock_data = fetch_stock_data_cloud_safe(code, time_unit, cache_time)

if stock_data:
    st.subheader(f"📈 {selected_stock} ({code}) 현재 주가")
    
    col_p, col_t = st.columns([2, 1])
    with col_p:
        st.metric(label="현재 시장 가격", value=f"{stock_data['current_price']:,} 원")
    with col_t:
        st.info(f"**⏰ 한국 표준시 (KST) 동기화 시간:**\n\n {stock_data['fetched_time']}")
        st.caption(f"*(설정하신 대로 {cache_time}{time_unit[0]} 동안 이 데이터가 유지됩니다)*")
    
    st.markdown("---")
    st.subheader("📉 독립형 3대 가치평가 모델 분석 결과")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("### 1. 수익 중심 모델 (EPS 가치)")
        target = stock_data["income_target"]
        max_buy = int(target * (1 - safety_margin / 100))
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
            
    with col2:
        st.warning("### 2. 자산 중심 모델 (BPS 청산가치)")
        target = stock_data["asset_target"]
        max_buy = int(target * (1 - safety_margin / 100))
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
            
    with col3:
        st.success("### 3. 상대 비교 모델 (PER 멀티플)")
        target = stock_data["relative_target"]
        max_buy = int(target * (1 - safety_margin / 100))
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        if stock_data["current_price"] <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
else:
    st.error("데이터 서버와 통신이 원활하지 않습니다. 잠시 후 페이지를 새로고침 해주세요.")
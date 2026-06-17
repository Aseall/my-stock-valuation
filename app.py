import streamlit as st
import yfinance as yf
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import os
import json

# --- 평가 모델 유틸리티 함수 ---
def compute_srim_advanced(b0, roe_path, r, g, years):
    """
    Advanced S-RIM (residual income) calculation.
    b0: initial book value per share
    roe_path: list of ROE values for each forecast year (length <= years)
              if shorter, last value is repeated to fill years
    r: required return (decimal)
    g: terminal growth rate (decimal), used for terminal residual income
    years: forecast horizon (int)

    Returns: tuple(total_value, pv_residuals_list, terminal_value)
    """
    # prepare ROE series
    roe_series = []
    for i in range(years):
        if i < len(roe_path):
            roe_series.append(float(roe_path[i]))
        else:
            roe_series.append(float(roe_path[-1]))

    B_prev = float(b0)
    pv_residuals = []
    total_pv = 0.0
    for t in range(1, years + 1):
        roe_t = roe_series[t - 1]
        # residual income = (ROE_t - r) * B_{t-1}
        res_income = (roe_t - r) * B_prev
        # discount
        pv = res_income / ((1 + r) ** t)
        pv_residuals.append(pv)
        total_pv += pv
        # update book value: B_t = B_{t-1} + net income (assume retained earnings, no dividends)
        # net income = ROE_t * B_prev
        B_prev = B_prev + (roe_t * B_prev)

    # Terminal residual income at year T: (ROE_T+1 - r) * B_T
    # Use ROE at last forecast year for terminal
    roe_terminal = roe_series[-1]
    B_T = B_prev
    terminal_residual = (roe_terminal - r) * B_T
    # Terminal value as perpetuity of residual incomes: terminal_residual / (r - g)
    if (r - g) <= 0:
        terminal_value = 0.0
    else:
        terminal_value = terminal_residual / (r - g)

    # discount terminal to present
    pv_terminal = terminal_value / ((1 + r) ** years)
    total_value = b0 + total_pv + pv_terminal
    return total_value, pv_residuals, pv_terminal

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

            # EPS: 우선 trailing, 없으면 forward 사용
            raw_eps = info.get('trailingEps')
            if raw_eps is None:
                raw_eps = info.get('forwardEps') or 0.0

            # PBR: 사이트 제공값을 우선 사용 (없으면 1.0로 보정)
            raw_pbr = info.get('priceToBook') or 1.0

            # PER: trailingPE, forwardPE 우선, 없으면 (current_price / EPS)로 안전하게 역산
            raw_per = info.get('trailingPE') or info.get('forwardPE')
            if (not raw_per) and raw_eps and raw_eps > 0 and current_price:
                try:
                    raw_per = current_price / raw_eps
                except Exception:
                    raw_per = 0.0
            raw_per = raw_per or 0.0

            # BPS: 가능하면 사이트 제공값 사용, 없으면 current_price / PBR (PBR이 0이 아닌 경우)
            raw_bps = info.get('bookValue')
            if not raw_bps:
                try:
                    raw_bps = (current_price / raw_pbr) if (current_price and raw_pbr) else 0.0
                except Exception:
                    raw_bps = 0.0
            # ROE (가능하면 가져오기)
            raw_roe = info.get('returnOnEquity') or info.get('returnOnAssets') or None
            
            # 🔗 야후 파이낸스 해당 종목 웹사이트 다이렉트 상세 링크 생성
            yahoo_url = f"https://finance.yahoo.com/quote/{yahoo_ticker}"

            # ⏰ 해외 서버 시간을 대한민국 표준시(KST)로 강제 정합 보정
            utc_now = datetime.utcnow()
            kor_now = utc_now + timedelta(hours=9)
            kor_time_str = kor_now.strftime('%Y-%m-%d %H시 %M분 %S초')

            return {
                "current_price": current_price if current_price is not None else 0,
                "raw_eps": raw_eps,
                "raw_pbr": raw_pbr,
                "raw_per": raw_per,
                "raw_bps": raw_bps,
                "raw_roe": raw_roe,
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

# 로컬에 종목별 기본 파라미터 저장/로드 (간단한 JSON 파일)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "valuation_config.json")
def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

CONFIG = load_config()

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
# --- 사용자 조정 가능한 멀티플 및 보정값 (UI) ---
st.sidebar.markdown("---")
st.sidebar.subheader("🔧 모델 파라미터 (조정 가능)")
eps_per_default = st.sidebar.number_input("EPS 기반 표준 PER (EPS 모델)", min_value=1, max_value=50, value=12)
rel_per_default = st.sidebar.number_input("상대비교 표준 PER (비교 모델)", min_value=1, max_value=50, value=10)
pbr_multiplier_default = st.sidebar.number_input("BPS 기반 표준 PBR (자산 모델)", min_value=0.1, max_value=5.0, value=1.2, step=0.1, format="%.1f")

# 정규화 EPS 입력 (선택): 사용자가 직접 넣으면 EPS 기반 모델에 우선 사용
normalized_eps = st.sidebar.number_input("정규화 EPS (선택, 없으면 야후 EPS 사용)", value=0.0, step=0.01, format="%.2f")

# S-RIM / 반도체 전용값
st.sidebar.markdown("---")
required_return = st.sidebar.number_input("요구수익률 r (S-RIM, 소수)", min_value=0.01, max_value=0.2, value=0.08, step=0.01, format="%.2f")
expected_roe_input = st.sidebar.number_input("예상 ROE (S-RIM, 소수, 0이면 야후값 사용)", min_value=0.0, max_value=1.0, value=0.0, step=0.01, format="%.2f")
growth_rate = st.sidebar.number_input("지속성장률 g (S-RIM, 소수)", min_value=0.0, max_value=0.2, value=0.02, step=0.01, format="%.2f")

# 불러온 CONFIG에 종목별 기본값이 있으면 사이드바 기본값으로 반영
stock_cfg = CONFIG.get(code, {})
if stock_cfg:
    eps_per_default = stock_cfg.get('eps_per', eps_per_default)
    rel_per_default = stock_cfg.get('rel_per', rel_per_default)
    pbr_multiplier_default = stock_cfg.get('pbr_mult', pbr_multiplier_default)
    required_return = stock_cfg.get('required_return', required_return)
    expected_roe_input = stock_cfg.get('expected_roe', expected_roe_input)
    growth_rate = stock_cfg.get('growth_rate', growth_rate)

# 저장 버튼: 현재 사이드바 파라미터를 종목 기본값으로 저장
if st.sidebar.button("✨ 현재 파라미터를 이 종목 기본값으로 저장"):
    CONFIG[code] = {
        'eps_per': eps_per_default,
        'rel_per': rel_per_default,
        'pbr_mult': pbr_multiplier_default,
        'required_return': required_return,
        'expected_roe': expected_roe_input,
        'growth_rate': growth_rate
    }
    ok = save_config(CONFIG)
    if ok:
        st.sidebar.success("저장 완료: valuation_config.json")
    else:
        st.sidebar.error("저장 실패: 파일 쓰기 오류")
# 내보내기 / 초기화 버튼
if st.sidebar.button("📤 현재 종목 파라미터 내보내기 (다운로드)"):
    payload = CONFIG.get(code, {})
    payload_bytes = json.dumps({code: payload}, ensure_ascii=False, indent=2).encode('utf-8')
    st.sidebar.download_button(label="Download JSON", data=payload_bytes, file_name=f"{code}_params.json", mime='application/json')

if st.sidebar.button("♻️ 이 종목 기본값 초기화 (삭제)"):
    if CONFIG.pop(code, None) is not None:
        save_config(CONFIG)
        st.sidebar.success("초기화 완료")
    else:
        st.sidebar.info("기본값이 설정되어 있지 않습니다.")

with st.spinner("야후 파이낸셜 마켓 엔진에서 실시간 데이터를 빌드하는 중..."):
    stock_data = fetch_stock_data_yahoo_pure(code, time_unit, cache_time)

if stock_data:
    # 야후 파이낸스 데이터 제공 오류 방어 벨트 (EPS가 0 이하로 밀려 들어올 때)
    is_yahoo_error = stock_data["raw_eps"] <= 0
    
    st.subheader(f"📈 {selected_stock} ({code}) 현재 주가")
    
    col_p, col_t = st.columns([2, 1])
    # 안전한 현재가 표시: 값이 없을 수 있으므로 0 대신 'N/A'로 보이게 함
    with col_p:
        cp = stock_data.get('current_price')
        cp_display = f"{int(cp):,} 원" if cp else "N/A"
        st.metric(label="현재 시장 가격 (Yahoo Price)", value=cp_display)
    with col_t:
        st.info(f"**⏰ KST 실시간 동기화 시간:** {stock_data['fetched_time']}")
        st.caption(f"*(해외 서버 타임존을 한국 표준시로 정밀 가공하여 매핑했습니다)*")

    # --- 🔎 수식 디버깅 및 야후 파이낸셜 출처 검증 영역 ---
    st.markdown("### 🔎 수식 디버깅 및 데이터 출처 검증")
    with st.expander("📂 가치평가 파라미터 변수 및 야후 파이낸셜 원천 링크 (클릭하여 열기)", expanded=True):
        c_eps, c_per, c_pbr, c_btn = st.columns([1, 1, 1, 1.2])
        # 안전한 포맷팅: 값이 없을 수 있으므로 기본값 또는 N/A 표시
        eps_display = f"{stock_data['raw_eps']:,.2f}" if stock_data.get('raw_eps') else "N/A"
        per_display = f"{stock_data['raw_per']:,.2f}" if stock_data.get('raw_per') else "N/A"
        pbr_display = f"{stock_data['raw_pbr']:,.2f}" if stock_data.get('raw_pbr') else "N/A"

        c_eps.markdown(f"**야후 제공 EPS:**\n`{eps_display} 원`")
        c_per.markdown(f"**야후 제공 PER:**\n`{per_display} 배`")
        c_pbr.markdown(f"**야후 제공 PBR:**\n`{pbr_display} 배`")

        # 🔗 사용자가 원천 지표 데이터를 사이트에서 눈으로 직접 대조해 볼 수 있는 링크 (표준 Streamlit 방식)
        c_btn.markdown("**🔗 Yahoo 원천 지표 검증**")
        c_btn.markdown(f"[Yahoo Finance 원본 사이트 이동]({stock_data['source_url']})")

    st.markdown("---")
    st.subheader("📉 독립형 3대 가치평가 모델 및 계산 과정")
    
    col1, col2, col3 = st.columns(3)
    margin_factor = 1 - safety_margin / 100
    
    # 1. 수익 중심 모델 (EPS 기반)
    with col1:
        st.info("### 1. 수익 중심 모델 (EPS 가치)")
        # EPS 우선 순위: 사용자가 입력한 정규화 EPS > trailingEPS > forwardEPS
        eps_to_use = None
        if normalized_eps and normalized_eps > 0:
            eps_to_use = normalized_eps
            eps_source = "사용자 입력 정규화 EPS"
        elif stock_data.get('raw_eps') and stock_data.get('raw_eps') > 0:
            eps_to_use = stock_data['raw_eps']
            eps_source = "야후 EPS"
        else:
            eps_to_use = None
            eps_source = "N/A"

        if eps_to_use:
            target = int(eps_to_use * eps_per_default)
            process_text = f"적정가 = {eps_source} × PER {eps_per_default}배\n       = {eps_to_use:,.2f} × {eps_per_default}\n       = {target:,} 원"
            max_buy = int(target * margin_factor)
        else:
            target = None
            process_text = "EPS 데이터 부족 — EPS 기반 모델 계산 불가 (정규화 EPS 입력 또는 야후 EPS 필요)"
            max_buy = None
        
        st.markdown("**⚙️ 계산 과정:**")
        if target:
            st.code(f"{process_text}\n\n매수가 = 적정가 × 안전마진\n       = {target:,} × {margin_factor:.2f}\n       = {max_buy:,} 원", language="text")
            st.write(f"**적정 가치:** {target:,} 원")
            st.write(f"**안전마진 매수가:** {max_buy:,} 원")
            cp = stock_data.get('current_price') or 0
            if max_buy and cp and cp <= max_buy:
                st.success("🟢 매수 가능 (마진 충분)")
            else:
                st.error("🔴 관망 및 대기 (마진 부족)")
        else:
            st.warning(process_text)
            
    # 2. 자산 중심 모델 (BPS 기반)
    with col2:
        st.warning("### 2. 자산 중심 모델 (BPS 청산가치)")
        bps = stock_data.get('raw_bps') or 0.0
        target = int(bps * pbr_multiplier_default)
        max_buy = int(target * margin_factor)
        
        st.markdown("**⚙️ 계산 과정:**")
        st.code(f"적정가 = 야후 BPS × PBR {pbr_multiplier_default}배\n       = {bps:,.2f} × {pbr_multiplier_default}\n       = {target:,} 원\n\n매수가 = 적정가 × 안전마진\n       = {target:,} × {margin_factor:.2f}\n       = {max_buy:,} 원", language="text")
        
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        cp = stock_data.get('current_price') or 0
        if max_buy and cp and cp <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")
            
    # 3. 상대 비교 모델 (PER 멀티플)
    with col3:
        st.success("### 3. 상대 비교 모델 (PER 멀티플)")
        # 상대비교 모델은 EPS 기반 PER 적용 — EPS가 없으면 현가 기반 대체
        if eps_to_use:
            target = int(eps_to_use * rel_per_default)
            process_text = f"적정가 = EPS × 타깃 PER {rel_per_default}배\n       = {eps_to_use:,.2f} × {rel_per_default}\n       = {target:,} 원"
        else:
            # EPS 없음: 상대비교 대신 현재가 사용(대체)
            cp = stock_data.get('current_price') or 0
            target = int(cp)
            process_text = f"EPS 없음 — 현재가를 기준으로 대체 계산\n       = 현재가 = {target:,} 원"

        max_buy = int(target * margin_factor)
        
        st.markdown("**⚙️ 계산 과정:**")
        st.code(f"{process_text}\n\n매수가 = 적정가 × 안전마진\n       = {target:,} × {margin_factor:.2f}\n       = {max_buy:,} 원", language="text")
        
        st.write(f"**적정 가치:** {target:,} 원")
        st.write(f"**안전마진 매수가:** {max_buy:,} 원")
        cp = stock_data.get('current_price') or 0
        if max_buy and cp and cp <= max_buy:
            st.success("🟢 매수 가능 (마진 충분)")
        else:
            st.error("🔴 관망 및 대기 (마진 부족)")

    # --- 반도체 특화: PBR 밴드 및 S-RIM ---
    st.markdown("---")
    if selected_stock in ("SK하이닉스", "삼성전자"):
        st.subheader("🔬 반도체 전용: PBR 밴드 & S-RIM")
        # 기본 PBR 밴드 (종목별 기본값)
        PBR_BANDS = {
            "SK하이닉스": (0.9, 2.3),
            "삼성전자": (0.8, 1.8)
        }
        lower_band, upper_band = PBR_BANDS.get(selected_stock, (1.0, 1.5))
        bps = stock_data.get('raw_bps') or 0.0
        cp = stock_data.get('current_price') or 0

        if bps and bps > 0:
            current_pbr = cp / bps if cp else 0.0
            lower_target = int(bps * lower_band)
            upper_target = int(bps * upper_band)
            st.write(f"**역사적 PBR 밴드 (기본):** 하단 {lower_band}배, 상단 {upper_band}배")
            st.write(f"**현재 PBR:** {current_pbr:,.2f}배 (BPS {bps:,.2f}원 기준)")
            st.write(f"밴드에 따른 목표가: 하단 {lower_target:,} 원 / 상단 {upper_target:,} 원")
            if current_pbr <= lower_band:
                st.success("🟢 현재는 PBR 밴드 하단 또는 저평가 영역입니다.")
            elif current_pbr >= upper_band:
                st.error("🔴 현재는 PBR 밴드 상단 또는 고평가 영역입니다.")
            else:
                st.info("🟡 현재는 PBR 밴드 중간 구간입니다.")
        else:
            st.warning("BPS 데이터 부족으로 PBR 밴드 분석 불가")

        # --- 히스토리 기반 PBR 밴드 (확장) ---
        st.markdown("**히스토리 기반 PBR 밴드 계산 (과거 분기 기준, 퍼센타일 산출)**")
        try:
            y_ticker = yf.Ticker(f"{code}.KS")
            qbs = y_ticker.quarterly_balance_sheet
            shares = y_ticker.info.get('sharesOutstanding')
            prices = y_ticker.history(period='5y', interval='1d')['Close']
            if qbs is not None and not qbs.empty and shares and not prices.empty:
                # 찾을 수 있는 자본(Equity) 관련 행 찾기
                possible_keys = [k for k in qbs.index if 'Total' in str(k) or 'Stockholders' in str(k) or 'Equity' in str(k)]
                if possible_keys:
                    equity_rows = qbs.loc[possible_keys]
                    # 합계(가장 적절한 행 선택)
                    equity_series = equity_rows.iloc[0]
                else:
                    equity_series = qbs.iloc[0]

                # 각 분기별 BPS 계산
                bps_series = equity_series / shares
                pbr_time = []
                for col in bps_series.index:
                    try:
                        # 컬럼은 Timestamp-like; find nearest price up to that date
                        dt = pd.to_datetime(col)
                        price_on = prices.asof(dt)
                        bps_val = float(bps_series[col])
                        if price_on and bps_val and bps_val > 0:
                            pbr_time.append(float(price_on) / bps_val)
                    except Exception:
                        continue

                if pbr_time:
                    pbr_arr = np.array(pbr_time)
                    low_p = float(np.nanpercentile(pbr_arr, 5))
                    high_p = float(np.nanpercentile(pbr_arr, 95))
                    med_p = float(np.nanpercentile(pbr_arr, 50))
                    st.write(f"히스토리 기반 PBR 밴드 (5th~95th): {low_p:.2f} ~ {high_p:.2f} 배 (중앙값 {med_p:.2f})")
                    st.line_chart(pd.Series(pbr_arr))
                    # 현재 PBR과 밴드 비교
                    if bps and bps > 0:
                        current_pbr = (cp / bps) if cp else 0.0
                        st.write(f"현재 PBR: {current_pbr:,.2f}배 (BPS {bps:,.2f})")
                        if current_pbr <= low_p:
                            st.success("🟢 현재는 히스토리 기반 PBR 밴드 하단 또는 저평가 영역입니다.")
                        elif current_pbr >= high_p:
                            st.error("🔴 현재는 히스토리 기반 PBR 밴드 상단 또는 고평가 영역입니다.")
                        else:
                            st.info("🟡 현재는 히스토리 기반 PBR 밴드 중간 구간입니다.")
                else:
                    st.info("과거 데이터에서 유효한 PBR 시계열을 만들지 못했습니다.")
            else:
                st.info("yfinance로부터 분기 재무제표, 발행주식수 또는 가격 데이터가 부족합니다.")
        except Exception:
            st.info("히스토리 기반 PBR 밴드 계산 중 오류가 발생했습니다.")

        # S-RIM 계산
        st.markdown("**S-RIM (잔여이익 모델, 단순화된 형태)**")
        roe = None
        # yfinance may provide returnOnEquity as 소수 or percent
        roe_info = None
        try:
            roe_info = stock_data.get('raw_roe') if stock_data.get('raw_roe') is not None else None
        except Exception:
            roe_info = None
        if expected_roe_input and expected_roe_input > 0:
            roe = expected_roe_input
        else:
            # fall back to yfinance info if available
            # try to retrieve from yf.Ticker earlier info - we didn't persist it; use stock_data.get
            roe = stock_data.get('raw_roe') or 0.0

        if bps and required_return and roe and roe > 0:
            # 개선된 S-RIM: 잔여이익 영속성 가정 (고정 ROE, 성장률 g)
            # 공식: Value = B0 + ((ROE - r) * B0) / (r - g)
            # 단, r > g 이어야 함
            if required_return <= growth_rate:
                st.error("요구수익률 r은 성장률 g보다 커야 합니다 (r > g). S-RIM 계산 불가")
            else:
                try:
                    srim_value = int(bps + ((roe - required_return) * bps) / (required_return - growth_rate))
                except Exception:
                    srim_value = 0
                srim_buy = int(srim_value * margin_factor)
                st.write(f"예상 ROE: {roe:.2f}, 요구수익률 r: {required_return:.2f}, 성장률 g: {growth_rate:.2f}")
                st.write(f"**S-RIM 적정가:** {srim_value:,} 원")
                st.write(f"**S-RIM 안전마진 매수가:** {srim_buy:,} 원")
        else:
            st.info("S-RIM 계산에 필요한 BPS/ROE/요구수익률 정보가 부족합니다.")
else:
    st.error("야후 파이낸스 마켓 전산망과 통신이 원활하지 않습니다.")
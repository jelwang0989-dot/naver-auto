# -*- coding: utf-8 -*-
"""
AI파트너(aipartner.com) 자동 로그인 및 매물 정렬 / 연속 재광고 진행 프로그램
"""

import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException

# Windows 콘솔 한글 인코딩 지원 설정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==========================================
# 사용자 설정 정보 (환경변수 또는 기본값)
# ==========================================
TARGET_URL = "https://www.aipartner.com/home"
LOGIN_PAGE_URL = "https://www.aipartner.com/integrated/login?serviceCode=1000"

USER_ID = os.environ.get("LOGIN_ID") or "jelwang85"
USER_PW = os.environ.get("LOGIN_PASSWORD") or "ab1223521!"

# 재광고 대상 아파트 단지명 (GitHub Actions inputs 또는 로컬 기본값)
TARGET_COMPLEX = os.environ.get("TARGET_COMPLEX") or "다산팬테리움리버테라스I"

# 연속 재광고 갱신 제한 횟수 (총 7건)
MAX_RE_AD_COUNT = 7

# 홈 화면 로그인 버튼 선택자
SELECTOR_HOME_LOGIN_BTN = "#wrap > div > div.contents > div.wrap-guest > section.section.guest-account > div > div > a.btn.btn-bg-dorg.GTM_non_login_main_login"

# 로그인 페이지 입력창 및 버튼 선택자
SELECTOR_ID_INPUT = "#member-id"
SELECTOR_PW_INPUT = "#member-pw"
SELECTOR_LOGIN_SUBMIT = "a.btn-login"  # 로그인 실행 버튼

# 상단 헤더 '매물 관리' 메뉴 버튼 선택자
SELECTOR_PROPERTY_BTN = "#wrap > header > div.header-wrap > div > ul > li:nth-child(2) > a"


def create_driver(keep_open=False, headless=False):
    """크롬 웹드라이버 옵션 설정 및 생성"""
    options = Options()
    
    # CI/GitHub Actions 또는 리눅스 환경 감지
    is_ci = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"
    is_linux = sys.platform.startswith("linux")
    use_headless = headless or is_ci or is_linux
    
    if use_headless:
        # 클라우드 화면 없는 환경(Linux Headless) 필수 옵션
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    else:
        # 일반 로컬 모드: 브라우저 창 최대화
        options.add_argument("--start-maximized")
    
    # 자동화 제어 메시지 숨기기 및 일반 브라우저처럼 위장
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    # 작업 완료 후 브라우저가 자동으로 닫히지 않고 열린 상태 유지 (로컬 일반 모드일 때만)
    if keep_open and not use_headless:
        options.add_experimental_option("detach", True)
        
    driver = webdriver.Chrome(options=options)
    return driver


def handle_alerts(driver, accept=True, max_tries=3):
    """브라우저 alert/confirm 알림창 감지 및 자동 승인/확인"""
    for _ in range(max_tries):
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            print(f"[*] 브라우저 알림창 감지: {alert_text}")
            if accept:
                alert.accept()
            else:
                alert.dismiss()
            time.sleep(1)
        except Exception:
            break


# 아파트 단지 정보 매핑 (data-complex_cd 및 표기 변형 지원)
COMPLEX_INFO_MAP = {
    "다산팬테리움리버테라스I": {
        "cd": "42227",
        "names": ["다산펜테리움리버테라스Ⅰ", "다산팬테리움리버테라스I", "다산펜테리움리버테라스I", "다산팬테리움리버테라스1"],
    },
    "다산팬테리움리버테라스II": {
        "cd": "42648",
        "names": ["다산펜테리움리버테라스Ⅱ", "다산팬테리움리버테라스II", "다산펜테리움리버테라스II", "다산팬테리움리버테라스2"],
    },
    "다산신안인스빌퍼스트포레": {
        "cd": "45569",
        "names": ["다산신안인스빌퍼스트포레"],
    },
    "다산한강반도유보라": {
        "cd": "42229",
        "names": ["다산한강반도유보라"],
    },
    "다산신안인스빌퍼스트리버": {
        "cd": "42840",
        "names": ["다산신안인스빌퍼스트리버"],
    },
}


def normalize_complex_name(name):
    """단지명 비교를 위한 정규화 (공백 제거, 팬/펜 통일, 로마숫자 1/2 통일, 소문자화)"""
    if not name:
        return ""
    s = name.replace(" ", "").replace("팬", "펜")
    s = s.replace("Ⅰ", "1").replace("I", "1").replace("i", "1")
    s = s.replace("Ⅱ", "2").replace("II", "2").replace("ii", "2")
    return s.lower()


def select_complex_row(driver, wait, target_complex=None):
    """[진행순서 1] 취급 매물 목록에서 지정된 아파트 단지 행을 찾아 클릭해 매물 목록 표시"""
    target = target_complex or TARGET_COMPLEX or "다산팬테리움리버테라스I"
    print(f"      - 취급 매물 목록에서 대상 아파트 단지 ['{target}'] 탐색 중...")
    
    # 목록 로딩 대기
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.filteringTable tbody tr"))
        )
    except Exception:
        pass

    target_norm = normalize_complex_name(target)
    target_info = COMPLEX_INFO_MAP.get(target, {})
    target_cd = target_info.get("cd")

    rows = driver.find_elements(By.CSS_SELECTOR, "table.filteringTable tbody tr")
    matched_elem = None
    matched_name = None

    for row in rows:
        # 1) data-complex_cd 속성으로 매칭 시도
        if target_cd:
            cd_elems = row.find_elements(By.CSS_SELECTOR, f"[data-complex_cd='{target_cd}']")
            if cd_elems:
                link_elems = row.find_elements(By.CSS_SELECTOR, "td.name a, a")
                if link_elems:
                    matched_elem = link_elems[0]
                    matched_name = matched_elem.text.strip() or target
                    break

        # 2) 행 텍스트 정규화 비교
        row_text = row.text.strip()
        row_norm = normalize_complex_name(row_text)
        if target_norm in row_norm:
            link_elems = row.find_elements(By.CSS_SELECTOR, "td.name a, a")
            if link_elems:
                matched_elem = link_elems[0]
                matched_name = matched_elem.text.strip()
                break

        # 3) 별칭(names) 목록 비교
        for alias in target_info.get("names", []):
            if normalize_complex_name(alias) in row_norm:
                link_elems = row.find_elements(By.CSS_SELECTOR, "td.name a, a")
                if link_elems:
                    matched_elem = link_elems[0]
                    matched_name = matched_elem.text.strip()
                    break
        if matched_elem:
            break

    # 매칭 실패 시 fallback: 첫 번째 표시되는 행
    if not matched_elem:
        print(f"      [경고] 대상 단지 '{target}'와 일치하는 행을 찾지 못하여 기본 첫 번째 단지로 대체합니다.")
        elems = driver.find_elements(By.CSS_SELECTOR, "table.filteringTable tbody tr td.name a")
        if elems:
            matched_elem = elems[0]
            matched_name = matched_elem.text.strip()

    if not matched_elem:
        raise Exception(f"취급 매물 목록에서 아파트 단지 행을 찾을 수 없습니다. (대상: {target})")

    print(f"      - 선택된 단지: {matched_name} (목표 단지: {target})")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", matched_elem)
    time.sleep(0.5)
    try:
        matched_elem.click()
    except Exception:
        driver.execute_script("arguments[0].click();", matched_elem)

    time.sleep(2)


def change_sort_to_oldest(driver, wait):
    """[진행순서 2, 3, 4] 정렬 기준을 '오래된 순'으로 변경 (일반 select 및 커스텀 div/ul 모두 지원)"""
    print("      - 매물 리스트 정렬 기준을 '오래된 순'으로 확인 및 변경 중...")
    
    # 1. 일반 <select> 태그인지 먼저 확인
    select_elements = driver.find_elements(By.CSS_SELECTOR, "select#orderBy, select.orderBy, .sortingWrap select")
    if select_elements and select_elements[0].is_displayed():
        print("      - 일반 <select> 태그 감지: '오래된 순' 옵션 선택")
        sel = Select(select_elements[0])
        try:
            sel.select_by_visible_text("오래된 순")
        except Exception:
            try:
                sel.select_by_value("offerAsc")
            except Exception:
                pass
    else:
        # 2. 커스텀 드롭다운 레이어(div / ul / a) 처리
        sort_trigger_selectors = [
            ".sortingWrap .selectBox a.selectInfoOrder",
            ".GTM_offerings_ad_list_listing_sort_filter a.selectInfoOrder",
            "a.selectInfoOrder[data-init*='최신']",
            "a.selectInfoOrder",
        ]
        sort_trigger = None
        for sel in sort_trigger_selectors:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems and any(e.is_displayed() for e in elems):
                sort_trigger = [e for e in elems if e.is_displayed()][0]
                break
                
        if not sort_trigger:
            elems = driver.find_elements(By.CSS_SELECTOR, "a.selectInfoOrder")
            if elems:
                sort_trigger = elems[0]
                
        if not sort_trigger:
            raise Exception("정렬 드롭다운 메뉴를 찾을 수 없습니다.")
            
        # 이미 '오래된 순'이 선택되어 있다면 토글 생략 가능
        if "오래된" in sort_trigger.text:
            print("      - 현재 이미 '오래된 순'으로 정렬되어 있습니다.")
            time.sleep(1)
            return

        # 드롭다운 토글 클릭
        try:
            sort_trigger.click()
        except Exception:
            driver.execute_script("arguments[0].click();", sort_trigger)
            
        time.sleep(1)
        
        # '오래된 순' 옵션 찾기
        oldest_option = None
        oldest_option_selectors = [
            ".selectList a.orderBy[data-cd='offerAsc']",
            ".selectList a[data-cd='offerAsc']",
            "a.orderBy[data-cd='offerAsc']",
        ]
        for sel in oldest_option_selectors:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                oldest_option = elems[0]
                break
                
        if not oldest_option:
            all_options = driver.find_elements(By.CSS_SELECTOR, ".selectList a, .sortingWrap a")
            for opt in all_options:
                if "오래된" in opt.text:
                    oldest_option = opt
                    break
                    
        if not oldest_option:
            raise Exception("'오래된 순' 옵션을 찾을 수 없습니다.")
            
        print("      - 드롭다운 옵션 중 '오래된 순' 클릭!")
        try:
            oldest_option.click()
        except Exception:
            driver.execute_script("arguments[0].click();", oldest_option)

    # 4단계: '오래된 순'으로 목록이 새로 정렬될 때까지 2초간 대기
    print("      - '오래된 순'으로 목록이 새로 정렬될 때까지 대기 중...")
    time.sleep(2)


def refresh_and_ensure_list(driver, wait, target_complex=None):
    """목록 복귀 후 매물 목록 최신화 및 '오래된 순' 정렬 상태 보장"""
    target = target_complex or TARGET_COMPLEX
    if "/offerings/ad_list" not in driver.current_url:
        print("      - 매물 관리(ad_list) 페이지로 이동 중...")
        driver.get("https://www.aipartner.com/offerings/ad_list")
        time.sleep(2)

    # 단지 행 다시 클릭 (서버로부터 최신 매물 목록 리로드)
    try:
        select_complex_row(driver, wait, target_complex=target)
    except Exception as e:
        print(f"      - 단지 새로고침 참고: {e}")

    # '오래된 순' 정렬 상태 확인 및 유지
    try:
        change_sort_to_oldest(driver, wait)
    except Exception as e:
        print(f"      - 정렬 상태 확인 참고: {e}")


def find_next_re_ad_target(driver, processed_ids):
    """
    매물 테이블에서 위에서부터 순회하여
    아직 처리하지 않았고 [재광고] 버튼이 존재하는 첫 번째 행과 버튼을 반환
    """
    print("      - [재광고] 버튼이 있는 다음 대상 매물 탐색 중...")
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.tableAdSale tbody tr"))
        )
    except Exception:
        pass
        
    rows = driver.find_elements(By.CSS_SELECTOR, "table.tableAdSale tbody tr")
    print(f"      - 현재 목록에 표시된 매물 행 수: {len(rows)}개")
    
    for idx, row in enumerate(rows):
        # 해당 행에 [재광고] 버튼이 있는지 확인
        re_ad_btns = row.find_elements(
            By.CSS_SELECTOR,
            "a.btn-re-ad-pop, a.naverReAd, [aria-label='재광고'], #doubleRocketReAd, .re-ad-name"
        )
        if not re_ad_btns:
            continue
            
        target_btn = re_ad_btns[0]
        
        # 매물 식별자 추출 (중복 처리 방지용)
        offering_id = (
            target_btn.get_attribute("data-offerings") or
            target_btn.get_attribute("data-offeringsseq") or
            row.get_attribute("data-offerings") or
            row.get_attribute("data-offeringsseq")
        )
        
        if not offering_id:
            chks = row.find_elements(By.CSS_SELECTOR, "input[type='checkbox'][value]")
            for chk in chks:
                val = chk.get_attribute("value")
                if val and val.isdigit():
                    offering_id = val
                    break

        # 이미 이번 실행에서 처리한 매물이면 건너뜀
        if offering_id and offering_id in processed_ids:
            continue
            
        print(f"      - [재광고 대상 선정] 목록 {idx + 1}번째 행 (매물 ID: {offering_id or '식별자 미확인'})")
        return row, target_btn, offering_id
        
    return None, None, None


def complete_payment_and_return_to_list(driver, wait):
    """
    결제/신청 페이지에서:
    1. [필수 동의 체크] 페이지 상단의 '모바일확인v2 개인정보 처리 위탁 동의' 체크박스 체크
    2. [결제 버튼 클릭] 페이지 맨 아래로 스크롤 후 주황색 [결제하기] 버튼 클릭
    3. [결제 완료 Alert 처리] 브라우저 Alert("로켓전송이 완료되었습니다.") 대기 및 확인(Accept)
    4. [목록 복귀] 전송 완료 화면에서 맨 하단의 [목록] 버튼 클릭하여 원래 매물 관리(ad_list)로 복귀
    """
    print("      - 결제 완료 및 매물 관리 목록 복귀 프로세스 진행...")

    # 결제/신청 페이지 로딩 대기 (최대 20초)
    long_wait = WebDriverWait(driver, 20)
    try:
        long_wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception:
        pass
    time.sleep(2)

    # -------------------------------------------------------------
    # 1. [필수 동의 체크] '모바일확인v2 개인정보 처리 위탁 동의' 체크박스 체크
    # -------------------------------------------------------------
    print("      - [1/4] '모바일확인v2 개인정보 처리 위탁 동의' 필수 체크박스 탐색 중...")
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    checked = False
    xpath_expressions = [
        "//*[contains(text(), '모바일확인') and contains(text(), '동의')]",
        "//*[contains(text(), '개인정보 처리 위탁 동의')]",
        "//*[contains(text(), '모바일확인v2')]",
        "//*[contains(text(), '모바일확인')]",
        "//*[contains(text(), '위탁 동의')]",
    ]
    
    for xpath in xpath_expressions:
        elems = driver.find_elements(By.XPATH, xpath)
        for elem in elems:
            try:
                if elem.tag_name == "label":
                    for_id = elem.get_attribute("for")
                    if for_id:
                        chk_input = driver.find_element(By.ID, for_id)
                        if not chk_input.is_selected():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", elem)
                            driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", chk_input)
                            checked = True
                            print(f"      - [동의 완료] 라벨 클릭으로 체크 완료 (for: {for_id})")
                            break
                    else:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", elem)
                        checked = True
                        print("      - [동의 완료] 라벨 직접 클릭 완료")
                        break
                
                parent = elem.find_element(By.XPATH, "./ancestor::*[self::div or self::li or self::p][contains(@class, 'check') or contains(@class, 'agree') or contains(@class, 'box') or contains(@class, 'wrap') or contains(@class, 'item')][1]")
                chk_inputs = parent.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                for chk in chk_inputs:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", chk)
                    time.sleep(0.5)
                    if not chk.is_selected():
                        lbls = parent.find_elements(By.TAG_NAME, "label")
                        if lbls:
                            driver.execute_script("arguments[0].click();", lbls[0])
                        else:
                            driver.execute_script("arguments[0].click();", chk)
                        driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", chk)
                        checked = True
                        print("      - [동의 완료] 해당 영역 체크박스 체크 완료")
                        break
                if checked:
                    break
            except Exception:
                continue
        if checked:
            break

    # Fallback: 필수/주황색 영역 체크박스
    if not checked:
        candidate_checkboxes = driver.find_elements(
            By.CSS_SELECTOR,
            ".point input[type='checkbox'], .orange input[type='checkbox'], .org input[type='checkbox'], .req input[type='checkbox'], input[type='checkbox'][required], input[type='checkbox'][name*='agree'], input[type='checkbox'][id*='agree'], input[type='checkbox'][id*='v2'], input[type='checkbox'][id*='mobile']"
        )
        for chk in candidate_checkboxes:
            try:
                if not chk.is_selected():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", chk)
                    driver.execute_script("arguments[0].click();", chk)
                    driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", chk)
                    checked = True
                    print(f"      - [동의 완료] 필수/주황색 영역 체크박스 체크 (id: {chk.get_attribute('id')})")
            except Exception:
                pass

    time.sleep(1.5)

    # -------------------------------------------------------------
    # 2. [결제 버튼 클릭] 페이지 맨 아래로 스크롤한 뒤, 주황색 [결제하기] 버튼 클릭
    # -------------------------------------------------------------
    print("      - [2/4] 페이지 맨 아래로 스크롤 및 주황색 [결제하기] 버튼 탐색 중...")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    pay_button = None
    pay_btn_selectors = [
        "//button[contains(normalize-space(.), '결제하기')]",
        "//a[contains(normalize-space(.), '결제하기')]",
        "//button[contains(@class, 'btn-bg-org') or contains(@class, 'btn-bg-dorg') or contains(@class, 'btnPay') or contains(@class, 'btn-pay')]",
        "//a[contains(@class, 'btn-bg-org') or contains(@class, 'btn-bg-dorg') or contains(@class, 'btnPay') or contains(@class, 'btn-pay')]",
        "button.btn-bg-org, button.btn-bg-dorg, button.btnPay, button.btn-pay",
        "a.btn-bg-org, a.btn-bg-dorg, a.btnPay, a.btn-pay",
    ]

    for sel in pay_btn_selectors:
        if sel.startswith("//"):
            elems = driver.find_elements(By.XPATH, sel)
        else:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            
        for el in elems:
            if el.is_displayed():
                pay_button = el
                break
        if pay_button:
            break

    if not pay_button:
        all_btns = driver.find_elements(By.CSS_SELECTOR, "button, a.btn")
        for b in all_btns:
            txt = b.text.strip()
            if "결제하기" in txt or ("결제" in txt and "취소" not in txt):
                pay_button = b
                break

    if not pay_button:
        raise Exception("페이지 하단에서 주황색 [결제하기] 버튼을 찾을 수 없습니다.")

    print(f"      - 주황색 [결제하기] 버튼 클릭! ({pay_button.text.strip()})")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", pay_button)
    time.sleep(0.5)
    try:
        pay_button.click()
    except Exception:
        driver.execute_script("arguments[0].click();", pay_button)

    # -------------------------------------------------------------
    # 3. [결제 완료 Alert 처리] "로켓전송이 완료되었습니다." Alert 대기 및 확인(Accept)
    # -------------------------------------------------------------
    print("      - [3/4] 결제 완료 Alert ('로켓전송이 완료되었습니다.') 대기 중...")
    try:
        alert = WebDriverWait(driver, 15).until(EC.alert_is_present())
        alert_text = alert.text
        print(f"[*] 브라우저 결제 완료 Alert 감지: {alert_text}")
        alert.accept()
        print("      - 결제 완료 Alert 확인(Accept) 완료!")
    except TimeoutException:
        print("      - Alert 대기 시간 초과 또는 Alert가 미발생했습니다.")
    except Exception as e:
        print(f"      - Alert 처리 중 참고: {e}")

    time.sleep(1)
    try:
        alert2 = driver.switch_to.alert
        print(f"[*] 추가 Alert 감지: {alert2.text}")
        alert2.accept()
    except Exception:
        pass

    # -------------------------------------------------------------
    # 4. [목록 복귀] 전송 완료 화면에서 맨 하단의 [목록] 버튼을 클릭하여 원래 매물 관리(ad_list) 복귀
    # -------------------------------------------------------------
    print("      - [4/4] 전송 완료 화면 로딩 대기 및 맨 하단 [목록] 버튼 탐색 중...")
    time.sleep(2.5)

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1.5)

    list_btn = None
    list_btn_selectors = [
        "//button[normalize-space(.)='목록']",
        "//a[normalize-space(.)='목록']",
        "//button[contains(normalize-space(.), '목록')]",
        "//a[contains(normalize-space(.), '목록')]",
        "a[href*='/offerings/ad_list']",
        ".btn-list",
        "button.btn-list",
        "a.btn-list",
    ]

    for sel in list_btn_selectors:
        if sel.startswith("//"):
            elems = driver.find_elements(By.XPATH, sel)
        else:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            
        for el in elems:
            if el.is_displayed():
                list_btn = el
                break
        if list_btn:
            break

    if not list_btn:
        all_bottom_btns = driver.find_elements(By.CSS_SELECTOR, "button, a")
        for b in all_bottom_btns:
            txt = b.text.strip()
            if txt in ["목록", "목록으로", "매물목록"]:
                list_btn = b
                break

    if list_btn:
        print(f"      - 하단 [목록] 버튼 클릭! ({list_btn.text.strip()})")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", list_btn)
        time.sleep(0.5)
        try:
            list_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", list_btn)
    else:
        print("      - [목록] 버튼을 찾지 못하여 매물 관리 주소(/offerings/ad_list)로 직접 이동합니다.")
        driver.get("https://www.aipartner.com/offerings/ad_list")

    # 매물 관리(ad_list) 화면 복귀 대기
    try:
        WebDriverWait(driver, 15).until(EC.url_contains("/offerings/ad_list"))
    except Exception:
        pass

    time.sleep(2)
    print("      - 원래 매물 관리(ad_list) 화면으로 복귀 완료!")


def process_single_re_ad(driver, wait, target_row, re_ad_btn):
    """선택된 매물 1건에 대해 [재광고] 클릭 -> 팝업 동의 -> Alert 승인 -> 결제 및 목록 복귀 수행"""
    # 1. 대상 매물 행의 [재광고] 버튼 클릭
    print("      - [재광고 단계 1] 매물 행의 [재광고] 버튼 클릭!")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", re_ad_btn)
    time.sleep(0.5)
    try:
        re_ad_btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", re_ad_btn)
        
    time.sleep(2)
    
    # 2. 툴팁 팝업이 뜨는 경우 ('바로 재광고' 라디오/버튼 클릭)
    now_re_ad_selectors = [
        ".double-rocket-now-req",
        ".naverReAd",
        "label[for='reAd2']",
        "input#reAd2",
    ]
    for sel in now_re_ad_selectors:
        elems = target_row.find_elements(By.CSS_SELECTOR, sel)
        if elems and any(e.is_displayed() for e in elems):
            target = [e for e in elems if e.is_displayed()][0]
            print("      - [재광고 단계 2] 툴팁에서 '바로 재광고' 선택!")
            try:
                target.click()
            except Exception:
                driver.execute_script("arguments[0].click();", target)
            time.sleep(2)
            break
            
    handle_alerts(driver)
    
    # 3. 재광고 안내 팝업 (.monitoring-regist-pop) 처리: 팝업 동의 및 진행
    print("      - [재광고 단계 3] 재광고 안내 팝업 확인 및 동의 처리...")
    try:
        # 종료 동의 체크박스 확인
        agree_chks = driver.find_elements(By.CSS_SELECTOR, "input[name='acceptAdEnd'], input#popAdEndCheck")
        if agree_chks:
            chk = agree_chks[0]
            if not chk.is_selected():
                print("      - [팝업 동의] 광고 종료 동의 체크박스 체크!")
                try:
                    chk.click()
                except Exception:
                    driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", chk)
            time.sleep(0.8)
            
        # 팝업 내 '바로 재광고' 실행 버튼 클릭
        confirm_btns = driver.find_elements(By.CSS_SELECTOR, "button.register.startReAdOfferings, button[data-callback='verification']")
        if confirm_btns:
            print("      - [팝업 진행] '바로 재광고' 확인 버튼 클릭!")
            try:
                confirm_btns[0].click()
            except Exception:
                driver.execute_script("arguments[0].click();", confirm_btns[0])
                
        time.sleep(1.5)
        # alert/confirm 승인 ('종료가 진행됩니다...')
        handle_alerts(driver)
        time.sleep(1.5)
        handle_alerts(driver)
        
    except Exception as e:
        print(f"      - 재광고 안내 팝업 참고: {e}")
        
    time.sleep(3)
    handle_alerts(driver)
    
    # 4. 결제/신청 페이지 처리 및 매물 관리 목록 복귀
    complete_payment_and_return_to_list(driver, wait)


def run_pipeline(keep_open=True, headless=False, max_count=MAX_RE_AD_COUNT, target_complex=None):
    selected_complex = target_complex or TARGET_COMPLEX or "다산팬테리움리버테라스I"
    print("=" * 60)
    print("AI파트너 자동 로그인 및 매물 정렬 / 연속 재광고 파이프라인 시작")
    print(f"선택된 대상 아파트 단지: {selected_complex}")
    print(f"설정된 최대 처리 건수: {max_count}건")
    print("=" * 60)
    
    driver = create_driver(keep_open=keep_open, headless=headless)
    wait = WebDriverWait(driver, 15)
    
    try:
        # 1. 메인 홈 페이지 접속 및 로그인
        print(f"[1/4] 메인 페이지 접속 중... ({TARGET_URL})")
        driver.get(TARGET_URL)
        
        try:
            home_login_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTOR_HOME_LOGIN_BTN))
            )
            home_login_btn.click()
        except TimeoutException:
            driver.get(LOGIN_PAGE_URL)

        id_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELECTOR_ID_INPUT))
        )
        pw_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELECTOR_PW_INPUT))
        )
        id_input.clear()
        id_input.send_keys(USER_ID)
        pw_input.clear()
        pw_input.send_keys(USER_PW)
        
        submit_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTOR_LOGIN_SUBMIT))
        )
        submit_btn.click()
        
        handle_alerts(driver)
        wait.until(EC.url_contains("/home"))
        time.sleep(1.5)
        print("      로그인 완료 확인!")

        # 2. [매물 관리] 버튼 클릭하여 이동
        print("[2/4] '매물 관리' 메뉴 버튼 클릭 중...")
        property_btn = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELECTOR_PROPERTY_BTN))
        )
        try:
            property_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", property_btn)
            
        wait.until(EC.url_contains("/offerings/"))
        time.sleep(2)

        # 3. 초기 목록 준비: 단지 행 클릭 및 '오래된 순' 정렬
        print(f"[3/4] 취급 매물 목록 초기화 (대상 단지: {selected_complex}) 및 '오래된 순' 정렬 적용 중...")
        select_complex_row(driver, wait, target_complex=selected_complex)
        change_sort_to_oldest(driver, wait)

        # 4. 연속 재광고 반복 루프 (최대 max_count회)
        print(f"[4/4] 연속 재광고 반복 작업 시작 (최대 {max_count}건)...")
        processed_ids = set()
        success_count = 0
        
        for loop_idx in range(1, max_count + 1):
            print("\n" + "=" * 60)
            print(f"★ [매물 재광고 연속 진행: {loop_idx} / {max_count}회차]")
            print("=" * 60)
            
            # 다음 대상 매물 탐색
            target_row, re_ad_btn, offering_id = find_next_re_ad_target(driver, processed_ids)
            
            if not target_row or not re_ad_btn:
                print(f"[*] 더 이상 [재광고] 버튼이 있는 대상 매물이 없습니다. (완료 건수: {success_count}건)")
                break
                
            if offering_id:
                processed_ids.add(offering_id)
                
            # 해당 매물에 대해 재광고 및 결제/목록 복귀 실행
            process_single_re_ad(driver, wait, target_row, re_ad_btn)
            success_count += 1
            print(f"\n      >> [완료] {loop_idx}회차 매물 재광고 완료! (누적 완료: {success_count}/{max_count}건)")
            
            # 다음 매물이 남아있다면, 목록 새로고침 및 '오래된 순' 정렬 상태 보장
            if loop_idx < max_count:
                print("\n      - 다음 매물 처리를 위해 목록 새로고침 및 정렬 상태 확인 중...")
                time.sleep(2.5)
                refresh_and_ensure_list(driver, wait, target_complex=selected_complex)
        
        print("\n" + "=" * 60)
        print(f"★ [작업 완료] 지정된 매물 재광고 작업이 모두 성공적으로 완료되었습니다! (총 {success_count}건 완료)")
        print(f"- 최종 대상 단지 : {selected_complex}")
        print(f"- 최종 완료 URL : {driver.current_url}")
        print(f"- 최종 페이지 제목 : {driver.title}")
        print(f"안내: {max_count}개 매물 재광고 처리가 완료되어 브라우저를 깔끔하게 종료(driver.quit())합니다.")
        print("=" * 60)
        
        time.sleep(3)
        try:
            driver.quit()
            print("브라우저가 정상적으로 종료되었습니다.")
        except Exception:
            pass
        
    except UnexpectedAlertPresentException as e:
        print(f"[오류] 알림창 오류 발생: {e.alert_text}")
        try:
            driver.quit()
        except Exception:
            pass
    except Exception as e:
        print(f"[오류] 자동화 진행 중 오류가 발생했습니다: {e}")
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    is_headless = "--headless" in sys.argv
    run_pipeline(keep_open=False, headless=is_headless, max_count=MAX_RE_AD_COUNT, target_complex=TARGET_COMPLEX)

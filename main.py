import os
import requests
from google import genai
from datetime import datetime

# 1. 환경 변수에서 API 키 불러오기
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. 대마 검색어 및 타겟 저널 리스트 설정
SEARCH_QUERY = "cannabis OR hemp"
TARGET_JOURNALS = [
    "hortscience", 
    "journal of the american society for horticultural science",
    "scientia horticulturae", 
    "frontiers in plant science", 
    "plants", 
    "industrial crops and products"
]
MAX_PAPERS = 3

def process_paper_korean(title, abstract):
    """Gemini API를 사용해 영어 제목을 한국어로 번역하고, 초록을 한국어로 요약합니다."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""다음 대마(Cannabis/Hemp) 논문의 영어 제목과 초록을 읽고, 아래 양식에 맞춰 한국어로 작성해줘.

원문 제목: {title}
원문 초록: {abstract}

[출력 양식]
📝 <b>한국어 제목:</b> (여기에 번역된 한국어 제목 작성)
💡 <b>핵심 요약:</b>
(여기에 광질, 양액 관리, EC 등 환경 제어 및 생리학적 기전 관점에서 분석한 핵심 결과를 한국어로 3줄 요약 작성)"""
    
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt
    )
    return response.text

def send_telegram(message):
    """텔레그램 봇으로 메시지를 전송합니다."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML" 
    }
    requests.post(url, json=payload)

def reconstruct_abstract(inverted_index):
    """OpenAlex의 특수한 초록 데이터(Inverted Index)를 일반 문장으로 복원합니다."""
    if not inverted_index:
        return ""
    try:
        max_idx = max([pos for positions in inverted_index.values() for pos in positions])
        words = [""] * (max_idx + 1)
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(words)
    except Exception:
        return ""

def main():
    # 3. OpenAlex API 사용 (Semantic Scholar 429 차단 우회)
    url = "https://api.openalex.org/works"
    
    # mailto에 이메일을 넣으면 차단 없는 전용 서버(Polite Pool)를 배정받습니다.
    params = {
        "search": SEARCH_QUERY,
        "sort": "publication_date:desc", 
        "mailto": "paperbot_bot@gmail.com", 
        "per-page": 50
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        send_telegram(f"❌ OpenAlex API 오류\n- 코드: {response.status_code}\n- 상세: {response.text}")
        return
        
    papers = response.json().get("results", [])
    
    # 4. 타겟 저널 필터링
    filtered_papers = []
    for p in papers:
        # 저널명 추출
        primary_location = p.get("primary_location") or {}
        source = primary_location.get("source") or {}
        venue = (source.get("display_name") or "").lower()
        
        # 초록 복원
        abstract_idx = p.get("abstract_inverted_index")
        abstract = reconstruct_abstract(abstract_idx)
        
        if not venue or not abstract:
            continue
            
        if any(target in venue for target in TARGET_JOURNALS):
            p['extracted_venue'] = venue
            p['extracted_abstract'] = abstract
            filtered_papers.append(p)
            
        if len(filtered_papers) >= MAX_PAPERS:
            break

    # 5. 텔레그램 메시지 전송
    if not filtered_papers:
        send_telegram("🔍 <b>오늘 지정하신 저널에 새로 올라온 관련 논문이 없습니다.</b>")
        return

    send_telegram("🔍 <b>오늘의 [타겟 저널] 대마 환경제어/생리 최신 논문입니다.</b>")

    for p in filtered_papers:
        title = p.get("title", "제목 없음")
        paper_url = p.get("doi", "") or p.get("id", "")
        venue_name = p.get("extracted_venue", "저널명 없음").title()
        abstract = p.get("extracted_abstract", "")
        
        korean_result = process_paper_korean(title, abstract)
        
        msg = f"🏫 <b>저널:</b> {venue_name}\n🔗 <a href='{paper_url}'>논문 원문 링크</a>\n\n{korean_result}"
        send_telegram(msg)

if __name__ == "__main__":
    main()

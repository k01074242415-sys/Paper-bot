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
    
    # AI에게 제목 번역과 맞춤형 요약을 동시에 지시하는 양식
    prompt = f"""다음 대마(Cannabis/Hemp) 논문의 영어 제목과 초록을 읽고, 아래 양식에 맞춰 한국어로 작성해줘.

원문 제목: {title}
원문 초록: {abstract}

[출력 양식]
📝 <b>한국어 제목:</b> (여기에 번역된 한국어 제목 작성)
💡 <b>핵심 요약:</b>
(여기에 광질, 양액 관리, EC 등 환경 제어 및 생리학적 기전 관점에서 분석한 핵심 결과를 한국어로 3줄 요약 작성)"""
    
    response = client.models.generate_content(
        model='gemini-1.5-flash',
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
    res = requests.post(url, json=payload)
    print(f"텔레그램 전송 상태: {res.status_code}") # 에러 확인용 출력
    print(f"텔레그램 응답: {res.text}") # 에러 내용 상세 출력

def main():
    # 3. Semantic Scholar API 사용
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    current_year = datetime.now().year
    
    params = {
        "query": SEARCH_QUERY,
        "fields": "title,url,abstract,venue",
        "year": f"{current_year-1}-{current_year}",
        "limit": 100 
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        send_telegram("❌ 논문 검색 시스템에 일시적인 오류가 발생했습니다.")
        return
        
    papers = response.json().get("data", [])
    
    # 4. 타겟 저널 필터링
    filtered_papers = []
    for p in papers:
        venue = str(p.get("venue", "")).lower()
        abstract = p.get("abstract")
        
        if not venue or not abstract:
            continue
            
        if any(target in venue for target in TARGET_JOURNALS):
            filtered_papers.append(p)
            
        if len(filtered_papers) >= MAX_PAPERS:
            break

    # 5. 텔레그램 메시지 전송
    if not filtered_papers:
        send_telegram("🔍 <b>오늘 지정하신 원예/식물학 저널에 새로 올라온 대마 관련 논문이 없습니다.</b>")
        return

    send_telegram("🔍 <b>오늘의 [타겟 저널] 대마 환경제어/생리 최신 논문입니다.</b>")

    for p in filtered_papers:
        title = p.get("title", "제목 없음")
        paper_url = p.get("url", "")
        venue_name = p.get("venue", "저널명 없음")
        abstract = p.get("abstract", "")
        
        # 한국어 제목 번역 및 요약 텍스트 받아오기
        korean_result = process_paper_korean(title, abstract)
        
        # 최종 메시지 조립
        msg = f"🏫 <b>저널:</b> {venue_name}\n🔗 <a href='{paper_url}'>논문 원문 링크</a>\n\n{korean_result}"
        send_telegram(msg)

if __name__ == "__main__":
    main()

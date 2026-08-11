import os
import requests
import time
from google import genai

# 1. 환경 변수에서 API 키 불러오기
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. 타겟 저널 리스트 설정 (MDPI 'plants', 'frontiers' 저널 제거)
TARGET_JOURNALS = [
    "hortscience", 
    "journal of the american society for horticultural science",
    "scientia horticulturae", 
    "industrial crops and products"
]
MAX_PAPERS = 3

def process_paper_korean(title, abstract, priority):
    """Gemini API를 사용해 영어 제목을 번역하고 딱 1줄로 요약합니다."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    if priority in [1, 3]:
        topic = "대마(Cannabis/Hemp)"
    else:
        topic = "환경 제어 및 식물 생리"
        
    prompt = f"""다음 {topic} 논문의 영어 제목과 초록을 읽고, 아래 양식에 맞춰 한국어로 작성해줘.

원문 제목: {title}
원문 초록: {abstract}

[출력 양식]
📝 <b>한국어 제목:</b> (여기에 번역된 한국어 제목 작성)
💡 <b>한 줄 요약:</b> (여기에 광질, 양액 관리, 전기전도도(EC), 삼투 스트레스, 이차대사산물 및 식물 생리학적 기전 관점에서 분석한 핵심 결과를 군더더기 없이 딱 1줄로 요약)"""
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            return response.text
        except Exception:
            print(f"⚠️ Gemini API 과부하 발생. 30초 대기 후 재시도합니다... ({attempt+1}/3)")
            time.sleep(30)
            
    return "💡 <b>요약 실패:</b> AI 서버 지연으로 요약을 생성하지 못했습니다. 위 링크를 확인해 주세요."

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
    """OpenAlex의 특수한 초록 데이터를 일반 문장으로 복원합니다."""
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

def fetch_openalex(query):
    """OpenAlex API에서 주어진 검색어로 논문을 가져옵니다."""
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "sort": "publication_date:desc", 
        "mailto": "paperbot_bot@gmail.com", 
        "per-page": 50
    }
    res = requests.get(url, params=params)
    if res.status_code == 200:
        return res.json().get("results", [])
    return []

def is_blocked_publisher(venue, publisher):
    """MDPI 및 Frontiers 관련 출판사와 저널을 필터링합니다."""
    venue = venue.lower()
    publisher = publisher.lower()
    
    # MDPI, Frontiers 출판사이거나, 저널명에 frontiers가 들어가거나, MDPI 대표 저널인 plants인 경우 차단
    if "mdpi" in publisher or "frontiers" in publisher or "frontiers" in venue or venue == "plants":
        return True
    return False

def main():
    collected_papers = []
    seen_ids = set() 
    
    # --- [1순위] 타겟 저널 내 대마 논문 ---
    query_1 = '"cannabis" OR "hemp"'
    papers_1 = fetch_openalex(query_1)
    
    for p in papers_1:
        if len(collected_papers) >= MAX_PAPERS: break
        
        primary_loc = p.get("primary_location", {}) or {}
        source = primary_loc.get("source", {}) or {}
        venue = (source.get("display_name") or "").lower()
        publisher = (source.get("host_organization_name") or "").lower()
        abstract = reconstruct_abstract(p.get("abstract_inverted_index"))
        paper_id = p.get("id")
        
        if venue and abstract and paper_id not in seen_ids:
            if is_blocked_publisher(venue, publisher): continue
            
            if any(target in venue for target in TARGET_JOURNALS):
                p['priority_label'] = "1순위: 지정 저널 대마 논문"
                p['priority_code'] = 1
                p['venue'] = venue
                p['abstract'] = abstract
                collected_papers.append(p)
                seen_ids.add(paper_id)

    # --- [2순위] 타겟 저널 내 환경 제어 또는 식물 생리 논문 ---
    if len(collected_papers) < MAX_PAPERS:
        query_2 = '"environmental control" OR "electrical conductivity" OR "nutrient solution" OR "osmotic stress" OR "plant physiology" OR "GS-GOGAT" OR "glucosinolate" OR "proline"'
        papers_2 = fetch_openalex(query_2)
        
        for p in papers_2:
            if len(collected_papers) >= MAX_PAPERS: break
            
            primary_loc = p.get("primary_location", {}) or {}
            source = primary_loc.get("source", {}) or {}
            venue = (source.get("display_name") or "").lower()
            publisher = (source.get("host_organization_name") or "").lower()
            abstract = reconstruct_abstract(p.get("abstract_inverted_index"))
            paper_id = p.get("id")
            
            if venue and abstract and paper_id not in seen_ids:
                if is_blocked_publisher(venue, publisher): continue
                
                if any(target in venue for target in TARGET_JOURNALS):
                    p['priority_label'] = "2순위: 지정 저널 환경제어/식물생리 논문"
                    p['priority_code'] = 2
                    p['venue'] = venue
                    p['abstract'] = abstract
                    collected_papers.append(p)
                    seen_ids.add(paper_id)

    # --- [3순위] 지정하지 않은 저널에서 대마 논문 (원예학/수직농장 등) ---
    if len(collected_papers) < MAX_PAPERS:
        query_3 = '("cannabis" OR "hemp") AND ("horticulture" OR "vertical farming" OR "adventitious rooting")'
        papers_3 = fetch_openalex(query_3)
        
        for p in papers_3:
            if len(collected_papers) >= MAX_PAPERS: break
            
            primary_loc = p.get("primary_location", {}) or {}
            source = primary_loc.get("source", {}) or {}
            venue = (source.get("display_name") or "").lower()
            publisher = (source.get("host_organization_name") or "").lower()
            abstract = reconstruct_abstract(p.get("abstract_inverted_index"))
            paper_id = p.get("id")
            
            if venue and abstract and paper_id not in seen_ids:
                if is_blocked_publisher(venue, publisher): continue
                
                if not any(target in venue for target in TARGET_JOURNALS):
                    p['priority_label'] = "3순위: 외부 저널 대마/원예 논문"
                    p['priority_code'] = 3
                    p['venue'] = venue
                    p['abstract'] = abstract
                    collected_papers.append(p)
                    seen_ids.add(paper_id)

    # --- 텔레그램 메시지 전송 ---
    if not collected_papers:
        send_telegram("🔍 <b>오늘 조건에 새로 올라온 논문이 없습니다.</b>")
        return

    send_telegram("🔍 <b>오늘의 맞춤형 최신 연구 논문입니다.</b>")

    for p in collected_papers:
        title = p.get("title", "제목 없음")
        paper_url = p.get("doi", "") or p.get("id", "")
        venue_name = p.get("venue", "저널명 없음").title()
        priority_label = p.get("priority_label")
        
        # 한국어 요약 생성 (1줄 요약)
        korean_result = process_paper_korean(title, p['abstract'], p['priority_code'])
        
        # 메시지 전송
        msg = f"📌 <b>[{priority_label}]</b>\n🏫 <b>저널:</b> {venue_name}\n🔗 <a href='{paper_url}'>논문 원문 링크</a>\n\n{korean_result}"
        send_telegram(msg)
        
        time.sleep(15) 

if __name__ == "__main__":
    main()

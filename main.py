import os
import requests
import time
from google import genai
from google.genai import types

# 1. 환경 변수에서 API 키 불러오기
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. Q1 저널 리스트 설정 (식물과학/원예학 주요 Q1 저널)
Q1_JOURNALS = [
    "scientia horticulturae", 
    "industrial crops and products",
    "postharvest biology and technology",
    "environmental and experimental botany",
    "plant physiology",
    "plant science",
    "journal of experimental botany",
    "horticulture research",
    "agricultural water management",
    "food chemistry"
]
MAX_PAPERS = 3

def process_paper_korean(title, abstract, priority):
    """Gemini API를 사용해 영어 제목을 번역하고 딱 1줄로 요약합니다."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    if priority == 1:
        topic = "대마(Cannabis/Hemp)"
    else:
        topic = "수직농장 및 스트레스 생리"
        
    prompt = f"""다음 {topic} 논문의 영어 제목과 초록을 읽고, 아래 양식에 맞춰 한국어로 작성해줘.

원문 제목: {title}
원문 초록: {abstract}

[출력 양식]
📝 <b>한국어 제목:</b> (여기에 번역된 한국어 제목 작성)
💡 <b>한 줄 요약:</b> (광질, 양액 관리, 전기전도도(EC), 삼투 스트레스, 이차대사산물 및 식물 생리학적 기전 관점에서 분석한 핵심 결과를 군더더기 없이 딱 1줄로 요약)"""
    
    last_error = ""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    safety_settings=[
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        )
                    ]
                )
            )
            return response.text
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ API 에러: {last_error} (재시도 {attempt+1}/3)")
            time.sleep(20) # 과부하 방지를 위해 대기 시간 20초로 증가
            
    return f"💡 <b>요약 실패 (에러코드 확인용):</b> {last_error}"

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

def is_blocked_publisher(venue, publisher, doi):
    """MDPI 및 Frontiers 관련 출판사와 저널을 확실하게 필터링합니다."""
    venue = venue.lower()
    publisher = publisher.lower()
    doi = (doi or "").lower()
    
    # 확실한 차단법 1: DOI 번호표 확인 (10.3390=MDPI, 10.3389=Frontiers)
    if "10.3390/" in doi or "10.3389/" in doi or "mdpi.com" in doi or "frontiersin.org" in doi:
        return True
        
    # 확실한 차단법 2: 이름 확인
    if "mdpi" in publisher or "frontiers" in publisher or "frontiers" in venue or venue == "plants":
        return True
        
    return False

def main():
    collected_papers = []
    seen_ids = set() 
    
    # 🌟 퀄리티 향상: 제목과 초록(title_and_abstract)에서만 키워드를 찾도록 쿼리 수정
    # --- [1순위] Q1 저널 내 대마 논문 ---
    query_1 = 'title_and_abstract:("cannabis" OR "hemp")'
    papers_1 = fetch_openalex(query_1)
    
    for p in papers_1:
        if len(collected_papers) >= MAX_PAPERS: break
        
        primary_loc = p.get("primary_location", {}) or {}
        source = primary_loc.get("source", {}) or {}
        venue = (source.get("display_name") or "").lower()
        publisher = (source.get("host_organization_name") or "").lower()
        abstract = reconstruct_abstract(p.get("abstract_inverted_index"))
        doi = p.get("doi", "")
        paper_id = p.get("id")
        
        if venue and abstract and paper_id not in seen_ids:
            if is_blocked_publisher(venue, publisher, doi): continue
            
            if any(target in venue for target in Q1_JOURNALS):
                p['priority_label'] = "1순위: Q1 저널 대마 논문"
                p['priority_code'] = 1
                p['venue'] = venue
                p['abstract'] = abstract
                p['doi'] = doi
                collected_papers.append(p)
                seen_ids.add(paper_id)

    # 🌟 퀄리티 향상: 제목과 초록(title_and_abstract)에서만 키워드를 찾도록 쿼리 수정
    # --- 수직농장, 환경제어, 스트레스 처리 등 포괄적 쿼리 세팅 ---
    query_2_3 = 'title_and_abstract:("vertical farming" OR "controlled environment" OR "osmotic stress" OR "electrical conductivity" OR "adventitious rooting" OR "glucosinolate" OR "proline" OR "GS-GOGAT")'
    
    # --- [2순위] Q1 저널 내 수직농장/스트레스/환경제어 논문 ---
    if len(collected_papers) < MAX_PAPERS:
        papers_2 = fetch_openalex(query_2_3)
        
        for p in papers_2:
            if len(collected_papers) >= MAX_PAPERS: break
            
            primary_loc = p.get("primary_location", {}) or {}
            source = primary_loc.get("source", {}) or {}
            venue = (source.get("display_name") or "").lower()
            publisher = (source.get("host_organization_name") or "").lower()
            abstract = reconstruct_abstract(p.get("abstract_inverted_index"))
            doi = p.get("doi", "")
            paper_id = p.get("id")
            
            if venue and abstract and paper_id not in seen_ids:
                if is_blocked_publisher(venue, publisher, doi): continue
                
                if any(target in venue for target in Q1_JOURNALS):
                    p['priority_label'] = "2순위: Q1 저널 수직농장/스트레스 논문"
                    p['priority_code'] = 2
                    p['venue'] = venue
                    p['abstract'] = abstract
                    p['doi'] = doi
                    collected_papers.append(p)
                    seen_ids.add(paper_id)

    # --- [3순위] 기타 저널(비 Q1)에서 수직농장/스트레스/환경제어 논문 ---
    if len(collected_papers) < MAX_PAPERS:
        papers_3 = fetch_openalex(query_2_3)
        
        for p in papers_3:
            if len(collected_papers) >= MAX_PAPERS: break
            
            primary_loc = p.get("primary_location", {}) or {}
            source = primary_loc.get("source", {}) or {}
            venue = (source.get("display_name") or "").lower()
            publisher = (source.get("host_organization_name") or "").lower()
            abstract = reconstruct_abstract(p.get("abstract_inverted_index"))
            doi = p.get("doi", "")
            paper_id = p.get("id")
            
            if venue and abstract and paper_id not in seen_ids:
                if is_blocked_publisher(venue, publisher, doi): continue
                
                # Q1 저널 리스트에 없는 논문들만 수집
                if not any(target in venue for target in Q1_JOURNALS):
                    p['priority_label'] = "3순위: 기타 저널 수직농장/스트레스 논문"
                    p['priority_code'] = 3
                    p['venue'] = venue
                    p['abstract'] = abstract
                    p['doi'] = doi
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

import os
import arxiv
import requests
from google import genai

# 환경 변수에서 API 키 불러오기 (GitHub에 키를 숨기기 위해 사용)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 💡 대마(Cannabis, Hemp)의 원예, 생리, 유전, 환경제어 관련 검색어 설정
SEARCH_QUERY = '(all:"cannabis" OR all:"hemp") AND (all:"horticulture" OR all:"physiology" OR all:"genetics" OR all:"environmental control" OR all:"cultivation")'
MAX_PAPERS = 3 # 하루에 받을 논문 개수

def summarize_paper(abstract):
    """Gemini API를 사용해 논문 초록을 한국어로 요약합니다."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"다음 논문의 초록을 읽고, 핵심 기여도와 결과를 한국어로 3줄 요약해줘:\n\n{abstract}"
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    return response.text

def send_telegram(message):
    """텔레그램 봇으로 메시지를 전송합니다."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML" # 링크와 굵은 글씨 적용을 위해 HTML 모드 사용
    }
    requests.post(url, json=payload)

def main():
    # arXiv에서 최신 논문 검색
    client = arxiv.Client()
    search = arxiv.Search(
        query=SEARCH_QUERY,
        max_results=MAX_PAPERS,
        sort_by=arxiv.SortCriterion.SubmittedDate # 최신순 정렬
    )

    # 텔레그램으로 보낼 첫 인사말
    send_telegram("🔍 <b>오늘의 [대마/원예/환경제어] 관련 최신 논문입니다.</b>")

    for result in client.results(search):
        title = result.title
        url = result.entry_id
        abstract = result.summary
        
        # 요약 생성
        summary = summarize_paper(abstract)
        
        # 메시지 조립
        msg = f"📝 <b>{title}</b>\n🔗 <a href='{url}'>논문 링크</a>\n\n💡 <b>요약:</b>\n{summary}"
        
        # 텔레그램 전송
        send_telegram(msg)

if __name__ == "__main__":
    main()

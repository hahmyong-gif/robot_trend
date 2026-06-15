#!/usr/bin/env python3
"""
fetch.py — RSS 뉴스 수집 + 중복 제거
"""
import feedparser
import json
import yaml
import hashlib
import re
import os
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

# ── CONFIG ──────────────────────────────────────────────
with open(os.path.join(os.path.dirname(__file__), 'keywords.yml'), 'r') as f:
    CONFIG = yaml.safe_load(f)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# ── HELPERS ─────────────────────────────────────────────
def clean_text(text):
    """HTML 태그 제거, 공백 정리"""
    text = re.sub(r'<[^>]+>', '', text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def article_id(title, url):
    """고유 ID 생성"""
    return hashlib.md5(f"{title}{url}".encode()).hexdigest()[:12]

def similarity(a, b):
    """두 문자열 유사도 (0~1)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# 로봇 전용 엔티티 (이 이름만 나와도 로봇 기사로 판단)
PURE_ROBOT_ENTITIES = {
    'figure ai', 'figure robot', 'boston dynamics', 'physical intelligence',
    '1x technologies', 'agility robotics', 'sanctuary ai', 'apptronik',
    'unitree', '유니트리', 'agibot', '아지봇', 'fourier intelligence',
    'skild ai', 'dextrous robotics', 'neura robotics', 'kepler robotics',
    'ubtech', 'galbot', 'mentee robotics', 'clone robotics',
    'irobot', 'softbank robotics', 'realman robotics',
}

# 비-로봇 주제 제외 키워드 (제목에 있으면 바로 제외)
NEGATIVE_TITLE_KWS = [
    # 금융/주식
    'etf', '주가', '수익률', '레버리지', '주식', 'ipo', 'earnings', 'stock price',
    'share price', 'quarterly results', '배당', '증시', '코스피', '나스닥',
    # 비-로봇 AI
    'llm', 'large language model', 'coding model', 'text model', 'chatbot',
    'gpt-', 'claude-', 'gemini-',
    # 게임/엔터
    'game', 'gaming', 'esports', 'movie', 'film', 'music',
    # 자동차 (Tesla 자동차 기사)
    'electric vehicle', 'ev sales', 'autopilot crash', 'self-driving car',
    'cybertruck', 'model 3', 'model y',
    # 암호화폐
    'bitcoin', 'crypto', 'blockchain', 'nft',
]

# ── 로봇 문맥 키워드 (이 중 하나라도 있으면 로봇 기사로 분류) ──────────
ROBOT_CONTEXT_KWS = {
    # 기체/형태
    'robot', '로봇', 'humanoid', '휴머노이드', 'bipedal', '이족보행',
    'quadruped', '4족보행', 'legged robot', 'wheeled robot', 'exoskeleton',
    '외골격', 'android', '안드로이드 로봇',

    # 구동/메커니즘
    'actuator', '액추에이터', 'gripper', '그리퍼', 'end-effector',
    'robotic arm', 'robot arm', '로봇 팔', 'robotic hand', 'dexterous',
    'torque', 'servo motor', 'linear motor', 'hydraulic robot',

    # 이동/운동
    'locomotion', 'gait', '보행', 'walking robot', 'running robot',
    'jumping robot', 'climbing robot', 'mobile robot', '이동 로봇',

    # 인지/지능
    'embodied ai', 'embodied intelligence', 'physical ai',
    'robot learning', 'robot perception', 'robot vision', 'robot sensing',
    'sim-to-real', 'imitation learning', 'reinforcement learning robot',
    'robot policy', 'robot foundation model', 'manipulation policy',
    'whole-body control', 'loco-manipulation',

    # 협동/산업
    'cobot', 'collaborative robot', '협동 로봇', 'industrial robot', '산업용 로봇',
    'autonomous mobile robot', 'amr', 'agv', '물류 로봇', 'logistics robot',
    'service robot', '서비스 로봇', 'surgical robot', '수술 로봇',
    'welding robot', 'painting robot', 'assembly robot',

    # 센서/HW
    'lidar robot', 'depth sensor robot', 'force sensor', 'tactile sensor',
    'robot camera', 'robot perception',

    # 소프트웨어/플랫폼
    'ros', 'ros2', 'robot operating system', 'isaac sim', 'isaac lab',
    'robot simulation', 'digital twin robot', 'robot sdk',

    # 한국어 로봇 정책/산업
    '로봇 산업', '로봇 정책', '로봇 육성', '로봇 전략', '로봇 법',
    '로봇 규제', '로봇 표준', '로봇 보조금', '로봇 펀드', '로봇 투자',
    '로봇 스타트업', '로봇 기업', '로봇 공학', '로봇 연구',
    'k-로봇', 'k-휴머노이드', '휴머노이드 산업',

    # 영문 로봇 정책/시장
    'robot regulation', 'robot policy', 'robot legislation', 'robot ethics',
    'robot safety standard', 'robot certification',
    'robot market', 'robot industry', 'robot sector', 'robot ecosystem',
    'robot investment', 'robot funding', 'robot venture', 'robot startup',
    'robot deployment', 'robot commercialization', 'robot adoption',
    'robot workforce', 'robot labor', 'robot automation',
    'humanoid market', 'humanoid industry', 'humanoid deployment',
}

def is_robot_related(title, summary):
    """로봇 관련 기사인지 판단"""
    title_lower = title.lower()
    text = f"{title} {summary}".lower()

    # 0) 명백한 비-로봇 주제는 제목에서 바로 제외
    if any(neg in title_lower for neg in NEGATIVE_TITLE_KWS):
        return False

    # 1) 핵심 로봇 키워드 (keywords.yml core)
    core_kws = [k.lower() for k in CONFIG['keywords']['core']]
    if any(kw in text for kw in core_kws):
        return True

    # 2) 로봇 전용 기업명 단독 통과
    if any(ent in text for ent in PURE_ROBOT_ENTITIES):
        return True

    # 3) 광범위 로봇 문맥 키워드
    if any(kw in text for kw in ROBOT_CONTEXT_KWS):
        return True

    return False

def get_tier(title, summary):
    """기사 티어 판단"""
    text = f"{title} {summary}".lower()
    for tier_name, tier_data in CONFIG['tiers'].items():
        for entity in tier_data['entities']:
            if entity.lower() in text:
                return tier_name
    return 'T5'

def recency_score(pub_date_str):
    """최신성 점수 (0.5~1.0)"""
    try:
        import email.utils
        pub_dt = datetime(*email.utils.parsedate(pub_date_str)[:6], tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        hours_ago = (now - pub_dt).total_seconds() / 3600
        if hours_ago <= 6:   return 1.0
        if hours_ago <= 12:  return 0.9
        if hours_ago <= 24:  return 0.8
        if hours_ago <= 48:  return 0.65
        return 0.5
    except:
        return 0.7

# ── DEDUPLICATION ────────────────────────────────────────
def deduplicate(articles, threshold=0.75, title_ratio=0.6):
    """
    중복 제거:
    1. 제목 유사도가 threshold 이상이면 중복
    2. 같은 핵심 키워드 + 48시간 내 → 중복 후보 → 스코어 높은 것만 유지
    """
    seen = []
    deduped = []

    for article in sorted(articles, key=lambda x: x['raw_score'], reverse=True):
        title = article['title']
        is_dup = False

        for kept in seen:
            # 제목 유사도 체크
            title_sim = similarity(title, kept['title'])
            if title_sim >= threshold:
                is_dup = True
                break

            # 핵심 엔티티 + URL 도메인 같으면 중복
            if article.get('entity') and article['entity'] == kept.get('entity'):
                same_domain = (
                    article.get('domain', '') == kept.get('domain', '')
                )
                time_diff = abs(article.get('pub_ts', 0) - kept.get('pub_ts', 0))
                if same_domain and time_diff < 3600 * 48:
                    is_dup = True
                    break

        if not is_dup:
            seen.append(article)
            deduped.append(article)

    return deduped

def extract_domain(url):
    m = re.search(r'https?://([^/]+)', url or '')
    return m.group(1) if m else ''

def extract_main_entity(title, summary):
    """기사의 주요 엔티티 추출"""
    text = f"{title} {summary}".lower()
    for tier_data in CONFIG['tiers'].values():
        for entity in tier_data['entities']:
            if entity.lower() in text:
                return entity.lower()
    return None

# ── FETCH ────────────────────────────────────────────────
MAX_ARTICLE_AGE_DAYS = 21  # 21일 이상 된 기사 제외

def fetch_source(source):
    """단일 RSS 소스 수집"""
    articles = []
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff_ts = now_ts - MAX_ARTICLE_AGE_DAYS * 86400
    try:
        feed = feedparser.parse(source['url'], request_headers={'User-Agent': 'Mozilla/5.0'})
        for entry in feed.entries[:50]:
            title = clean_text(entry.get('title', ''))
            summary = clean_text(entry.get('summary', '') or entry.get('description', ''))
            url = entry.get('link', '')
            pub_date = entry.get('published', '')

            if not title or not is_robot_related(title, summary):
                continue

            # pub timestamp — 날짜 없으면 오늘로 처리, 21일 초과 기사 제외
            try:
                import email.utils
                pub_ts = datetime(*email.utils.parsedate(pub_date)[:6]).timestamp()
                if pub_ts < cutoff_ts:
                    continue
            except:
                pub_ts = now_ts

            tier = get_tier(title, summary)
            tier_weight = CONFIG['tiers'].get(tier, {}).get('weight', 1.0)
            recency = recency_score(pub_date)

            # 키워드 매칭 점수
            text = f"{title} {summary}".lower()
            core_hits = sum(1 for kw in CONFIG['keywords']['core'] if kw.lower() in text)
            relevance = min(1.0, 0.5 + core_hits * 0.1)

            raw_score = round(relevance * tier_weight * recency * 10 / 3, 2)

            articles.append({
                'id': article_id(title, url),
                'title': title,
                'summary': summary,
                'url': url,
                'source': source['name'],
                'region': source['region'],
                'pub_date': pub_date,
                'pub_ts': round(pub_ts),
                'tier': tier,
                'raw_score': raw_score,
                'entity': extract_main_entity(title, summary),
                'domain': extract_domain(url),
            })
    except Exception as e:
        print(f"  ⚠ {source['name']}: {e}")
    return articles

def fetch_all():
    all_articles = []
    sources = (
        CONFIG['sources']['global'] +
        CONFIG['sources']['korea'] +
        CONFIG['sources']['us'] +
        CONFIG['sources']['china']
    )

    print(f"📡 Fetching {len(sources)} sources...")
    for src in sources:
        arts = fetch_source(src)
        print(f"  {src['name']}: {len(arts)} articles")
        all_articles.extend(arts)

    print(f"\n📰 Total collected: {len(all_articles)}")

    # 전체 중복 제거
    deduped = deduplicate(all_articles)
    print(f"🔍 After dedup: {len(deduped)}")

    # 지역별 분리 후 각각 중복 제거
    regions = {'global': [], 'KR': [], 'US': [], 'CN': []}
    for a in deduped:
        r = a['region']
        if r in regions:
            regions[r].append(a)
        else:
            regions['global'].append(a)

    # 글로벌은 전체에서 Top 30
    global_top = sorted(deduped, key=lambda x: x['raw_score'], reverse=True)[:30]

    # 지역별 Top 15 (지역 내 중복 추가 제거)
    regional = {}
    for region, arts in regions.items():
        reg_deduped = deduplicate(arts, threshold=0.65)
        regional[region] = sorted(reg_deduped, key=lambda x: x['raw_score'], reverse=True)[:15]

    return global_top, regional

# ── MAIN ─────────────────────────────────────────────────
if __name__ == '__main__':
    global_top, regional = fetch_all()

    # 저장 (analyze.py가 읽을 원본 데이터)
    raw_output = {
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'global': global_top,
        'regional': regional
    }

    raw_path = os.path.join(DATA_DIR, 'raw.json')
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(raw_output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved to {raw_path}")
    print(f"   Global: {len(global_top)} articles")
    for r, arts in regional.items():
        print(f"   {r}: {len(arts)} articles")

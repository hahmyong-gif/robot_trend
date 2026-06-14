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

def is_robot_related(title, summary):
    """로봇 관련 기사인지 판단"""
    text = f"{title} {summary}".lower()
    core_kws = CONFIG['keywords']['core'] + CONFIG['keywords']['market']
    entity_kws = []
    for tier in CONFIG['tiers'].values():
        entity_kws.extend(tier['entities'])
    all_kws = [k.lower() for k in core_kws + entity_kws]
    return any(kw in text for kw in all_kws)

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
def fetch_source(source):
    """단일 RSS 소스 수집"""
    articles = []
    try:
        feed = feedparser.parse(source['url'])
        for entry in feed.entries[:30]:
            title = clean_text(entry.get('title', ''))
            summary = clean_text(entry.get('summary', '') or entry.get('description', ''))
            url = entry.get('link', '')
            pub_date = entry.get('published', '')

            if not title or not is_robot_related(title, summary):
                continue

            tier = get_tier(title, summary)
            tier_weight = CONFIG['tiers'].get(tier, {}).get('weight', 1.0)
            recency = recency_score(pub_date)

            # 키워드 매칭 점수
            text = f"{title} {summary}".lower()
            core_hits = sum(1 for kw in CONFIG['keywords']['core'] if kw.lower() in text)
            relevance = min(1.0, 0.5 + core_hits * 0.1)

            raw_score = round(relevance * tier_weight * recency * 10 / 3, 2)

            # pub timestamp
            try:
                import email.utils
                pub_ts = datetime(*email.utils.parsedate(pub_date)[:6]).timestamp()
            except:
                pub_ts = 0

            articles.append({
                'id': article_id(title, url),
                'title': title,
                'summary': summary,
                'url': url,
                'source': source['name'],
                'region': source['region'],
                'pub_date': pub_date,
                'pub_ts': pub_ts,
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

    # 글로벌은 전체에서 Top 10
    global_top = sorted(deduped, key=lambda x: x['raw_score'], reverse=True)[:15]

    # 지역별 Top 10 (지역 내 중복 추가 제거)
    regional = {}
    for region, arts in regions.items():
        reg_deduped = deduplicate(arts, threshold=0.65)
        regional[region] = sorted(reg_deduped, key=lambda x: x['raw_score'], reverse=True)[:10]

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

#!/usr/bin/env python3
"""
fetch_tech.py — 로봇 기술 논문/동향 수집
소스: ArXiv (cs.RO/AI/LG/CV), Nature Robotics, Science Robotics,
      IEEE RA-L, IEEE T-RO, Frontiers, BAIR Blog, DeepMind Blog
"""
import feedparser
import json
import re
import os
import hashlib
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

TECH_SOURCES = [
    # ── ArXiv (가장 풍부한 논문 소스) ──────────────────────────
    {"name": "ArXiv cs.RO",  "url": "https://export.arxiv.org/rss/cs.RO",  "type": "arxiv", "filter": False},
    {"name": "ArXiv cs.AI",  "url": "https://export.arxiv.org/rss/cs.AI",  "type": "arxiv", "filter": True},
    {"name": "ArXiv cs.LG",  "url": "https://export.arxiv.org/rss/cs.LG",  "type": "arxiv", "filter": True},
    {"name": "ArXiv cs.CV",  "url": "https://export.arxiv.org/rss/cs.CV",  "type": "arxiv", "filter": True},
    {"name": "ArXiv eess.SY","url": "https://export.arxiv.org/rss/eess.SY","type": "arxiv", "filter": True},
    # ── 저명 저널 ──────────────────────────────────────────────
    {"name": "Nature Robotics",   "url": "https://www.nature.com/nrobt.rss", "type": "journal", "filter": False},
    {"name": "Science Robotics",  "url": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=scirobotics", "type": "journal", "filter": False},
    {"name": "IEEE RA-L",         "url": "https://ieeexplore.ieee.org/rss/TOC7083369.XML", "type": "journal", "filter": False},
    {"name": "IEEE T-RO",         "url": "https://ieeexplore.ieee.org/rss/TOC8860609.XML", "type": "journal", "filter": False},
    {"name": "Frontiers Robotics", "url": "https://www.frontiersin.org/journals/robotics-and-ai/rss", "type": "journal", "filter": False},
    # ── 연구기관 블로그 ────────────────────────────────────────
    {"name": "Google DeepMind",   "url": "https://deepmind.google/research/blog/rss.xml", "type": "blog", "filter": True},
    {"name": "BAIR Blog",         "url": "https://bair.berkeley.edu/blog/feed.xml",         "type": "blog", "filter": True},
    {"name": "OpenAI Research",   "url": "https://openai.com/blog/rss.xml",                "type": "blog", "filter": True},
    {"name": "MIT News Robotics", "url": "https://news.mit.edu/rss/research",              "type": "blog", "filter": True},
    {"name": "CMU RI News",       "url": "https://www.ri.cmu.edu/feed/",                   "type": "blog", "filter": True},
]

# 로봇 기술 관련 키워드 (filter=True 소스에 적용)
TECH_KWS = {
    'robot', 'robotic', 'humanoid', 'manipulation', 'locomotion',
    'dexterous', 'embodied', 'physical ai', 'sim-to-real',
    'imitation learning', 'reinforcement learning robot',
    'whole-body control', 'loco-manipulation', 'gripper',
    'actuator', 'exoskeleton', 'quadruped', 'bipedal', 'legged',
    'teleoperation', 'behavior cloning', 'robot policy',
    'robot learning', 'robot perception', 'robot vision',
    'generalist robot', 'policy learning', 'world model robot',
    'robot foundation', 'vla', 'vision-language-action',
    'motor control', 'kinematic', 'trajectory optimization',
    'contact-rich', 'in-hand', 'bimanual', 'pick and place',
    'mobile manipulation', 'task and motion', 'affordance',
    'proprioception', 'force control', 'torque control',
    'soft robot', 'continuum robot', 'cable-driven',
    'data-driven robot', 'zero-shot robot', 'few-shot robot',
    'robot arm', 'robotic arm', 'robot hand', 'robotic hand',
    'autonomous robot', 'collaborative robot', 'cobot',
}

def clean_text(text):
    text = re.sub(r'<[^>]+>', '', text or '')
    return re.sub(r'\s+', ' ', text).strip()[:600]

def is_tech_relevant(title, summary):
    text = f"{title} {summary}".lower()
    return any(kw in text for kw in TECH_KWS)

def extract_arxiv_id(url):
    m = re.search(r'(\d{4}\.\d{4,5})', url or '')
    return m.group(1) if m else None

def paper_id(title, url):
    arxiv_id = extract_arxiv_id(url)
    key = arxiv_id if arxiv_id else f"{title[:60]}"
    return hashlib.md5(key.encode()).hexdigest()[:12]

def fetch_tech():
    papers = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).timestamp()
    now_ts = datetime.now(timezone.utc).timestamp()

    for source in TECH_SOURCES:
        count_before = len(papers)
        try:
            feed = feedparser.parse(
                source['url'],
                request_headers={'User-Agent': 'Mozilla/5.0 (compatible; RobotIntelligenceBot/1.0)'}
            )
            for entry in feed.entries[:40]:
                title   = clean_text(entry.get('title', ''))
                summary = clean_text(entry.get('summary', '') or entry.get('description', ''))
                url     = entry.get('link', '')
                pub_date= entry.get('published', '')

                if not title:
                    continue

                # 필터 소스는 키워드 체크
                if source['filter'] and not is_tech_relevant(title, summary):
                    continue

                # 날짜 파싱
                try:
                    import email.utils
                    pub_ts = datetime(*email.utils.parsedate(pub_date)[:6], tzinfo=timezone.utc).timestamp()
                    if pub_ts < cutoff:
                        continue
                except Exception:
                    pub_ts = now_ts

                arxiv_id = extract_arxiv_id(url)
                papers.append({
                    'id':          paper_id(title, url),
                    'title':       title,
                    'summary':     summary,
                    'url':         url,
                    'source':      source['name'],
                    'source_type': source['type'],
                    'pub_date':    pub_date,
                    'pub_ts':      round(pub_ts),
                    'arxiv_id':    arxiv_id,
                })
        except Exception as e:
            print(f"  ⚠ {source['name']}: {e}")

        added = len(papers) - count_before
        print(f"  {source['name']}: {added}")

    # 중복 제거 (ArXiv ID 우선, 없으면 제목 유사도)
    seen_ids = set()
    deduped = []
    for p in papers:
        key = p.get('arxiv_id') or p['id']
        if key in seen_ids:
            continue
        seen_ids.add(key)
        deduped.append(p)

    return deduped

if __name__ == '__main__':
    print("📡 Fetching tech papers...")
    papers = fetch_tech()
    print(f"\n📄 Total unique: {len(papers)} papers")

    output = {
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'papers': papers
    }

    path = os.path.join(DATA_DIR, 'raw_tech.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved: {path}")

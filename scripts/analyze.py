#!/usr/bin/env python3
"""
analyze.py — Claude API로 기사 분석 + 최종 JSON 생성
"""
import anthropic
import json
import os
import time
from datetime import datetime, timezone, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

SYSTEM = """당신은 LG Electronics 로봇/Physical AI 전략팀 수석 분석가입니다.
뉴스 기사를 분석해서 반드시 아래 JSON 형식만 반환하세요. 다른 텍스트는 절대 포함하지 마세요."""

def analyze(title, summary, region):
    prompt = f"""기사 분석:
제목: {title}
요약: {summary}
출처 지역: {region}

다음 JSON만 반환 (다른 텍스트 없이):
{{
  "title_ko": "한국어 제목 번역 (영어/중국어인 경우만, 한국어면 원문 그대로)",
  "summary_ko": "한국어 2문장 핵심 요약",
  "signal": "Action 또는 Watch 또는 FYI",
  "signal_reason": "분류 이유 1문장",
  "lg_implication": "LG전자 관점 시사점 1문장",
  "keywords": ["핵심키워드1", "핵심키워드2", "핵심키워드3"]
}}

signal 기준:
- Action: LG 전략/사업에 즉각 영향, 빠른 대응 필요
- Watch: 중기적으로 모니터링 필요한 동향
- FYI: 참고용 정보"""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[
                {"role": "user", "content": prompt}
            ],
            system=SYSTEM
        )
        text = msg.content[0].text.strip()
        start = text.find('{')
        end = text.rfind('}') + 1
        result = json.loads(text[start:end])
        # title_ko가 없으면 원제목 사용
        if not result.get('title_ko'):
            result['title_ko'] = title
        return result
    except Exception as e:
        print(f"    ⚠ analyze error: {e}")
        return {
            "title_ko": title,
            "summary_ko": summary[:150] if summary else title,
            "signal": "FYI",
            "signal_reason": "자동 분석 실패",
            "lg_implication": "",
            "keywords": []
        }

def generate_brief(articles):
    """Intelligence Brief 자동 생성"""
    action_items = [a for a in articles if a.get('signal') == 'Action']
    watch_items = [a for a in articles if a.get('signal') == 'Watch'][:3]
    fyi_items = [a for a in articles if a.get('signal') == 'FYI'][:2]

    # Action/Watch 없으면 상위 FYI 기사로 브리프 생성
    brief_items = (action_items + watch_items)[:8] or fyi_items[:5] or articles[:5]

    items_text = "\n".join([
        f"- [{a.get('signal','FYI')}] {a['title']}: {a.get('summary_ko', a.get('summary',''))}"
        for a in brief_items
    ])

    if not items_text:
        return {
            "action_required": ["오늘 분석 기사 수가 부족합니다"],
            "regional_delta": {"KR": "데이터 없음", "US": "데이터 없음", "CN": "데이터 없음"},
            "cvc_insight": [],
            "bottom_line": "오늘 수집된 기사가 부족합니다. 내일 다시 확인해주세요."
        }

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": f"""오늘 로봇 업계 뉴스 기반으로 LG전자 전략팀을 위한 Intelligence Brief를 작성하세요.

주요 기사:
{items_text}

다음 JSON만 반환:
{{
  "action_required": ["즉각 대응 필요 사항 1문장", "즉각 대응 필요 사항 2문장"],
  "regional_delta": {{
    "KR": "한국 업계 핵심 동향 1문장",
    "US": "미국 업계 핵심 동향 1문장",
    "CN": "중국 업계 핵심 동향 1문장"
  }},
  "cvc_insight": ["CVC/파트너십 관점 인사이트 1문장", "CVC/파트너십 관점 인사이트 2문장"],
  "bottom_line": "오늘 가장 중요한 전략적 메시지 1~2문장"
}}"""}],
            system=SYSTEM
        )
        text = msg.content[0].text.strip()
        start = text.find('{')
        end = text.rfind('}') + 1
        result = json.loads(text[start:end])
        # 빈 배열/문자열 fallback 처리
        if not result.get('action_required'):
            result['action_required'] = [f"주목 기사: {brief_items[0]['title'][:60]}"] if brief_items else []
        if not result.get('bottom_line'):
            result['bottom_line'] = brief_items[0].get('summary_ko', '') if brief_items else ''
        return result
    except Exception as e:
        print(f"  ⚠ brief error: {e}")
        # API 실패 시 기사 데이터로 기본 brief 생성
        top = articles[:3]
        return {
            "action_required": [
                f"{top[0]['title'][:80]}" if top else "기사 없음",
                f"{top[1]['title'][:80]}" if len(top) > 1 else ""
            ],
            "regional_delta": {
                "KR": next((a.get('summary_ko','')[:80] for a in articles if a.get('region')=='KR'), "KR 데이터 없음"),
                "US": next((a.get('summary_ko','')[:80] for a in articles if a.get('region')=='US'), "US 데이터 없음"),
                "CN": next((a.get('summary_ko','')[:80] for a in articles if a.get('region')=='CN'), "CN 데이터 없음"),
            },
            "cvc_insight": [],
            "bottom_line": top[0].get('summary_ko', top[0].get('summary',''))[:120] if top else ""
        }

def detect_weak_signals(history_path, today_articles):
    """Weak Signal 탐지: 30일 평균 대비 급등"""
    # 히스토리 로드
    history = {}
    if os.path.exists(history_path):
        with open(history_path) as f:
            history = json.load(f)

    # 오늘 엔티티 카운트
    today_counts = {}
    for a in today_articles:
        entity = a.get('entity')
        if entity:
            today_counts[entity] = today_counts.get(entity, 0) + 1

    # 30일 평균과 비교
    signals = []
    for entity, count in today_counts.items():
        past = history.get(entity, {}).get('counts', [])
        avg = sum(past[-30:]) / len(past[-30:]) if past else 0.1
        spike_pct = ((count - avg) / avg * 100) if avg > 0 else count * 100

        if spike_pct >= 150:  # 150% 이상 급등만
            signals.append({
                'entity': entity,
                'today_count': count,
                'avg_count': round(avg, 1),
                'spike_pct': round(spike_pct),
                'level': 'hot' if spike_pct >= 500 else ('warm' if spike_pct >= 250 else 'cool')
            })

        # 히스토리 업데이트
        if entity not in history:
            history[entity] = {'counts': []}
        history[entity]['counts'].append(count)
        history[entity]['counts'] = history[entity]['counts'][-60:]  # 60일 보관

    # 히스토리 저장
    with open(history_path, 'w') as f:
        json.dump(history, f, ensure_ascii=False)

    return sorted(signals, key=lambda x: x['spike_pct'], reverse=True)[:6]

def score_final(article):
    """최종 스코어 = raw_score + signal 보정"""
    base = article.get('raw_score', 5.0)
    signal_bonus = {'Action': 1.0, 'Watch': 0.3, 'FYI': 0.0}
    return round(min(10.0, base + signal_bonus.get(article.get('signal', 'FYI'), 0)), 1)

def generate_geopolitical(articles):
    """국가별 지정학/전략 신호 생성"""
    # Use all articles — derive signals from industry trends even without explicit policy news
    sample = articles[:20]
    items_text = "\n".join([
        f"- [{a.get('region','?')}] {a.get('title_ko') or a.get('title','')}: {a.get('summary_ko') or a.get('summary','')[:100]}"
        for a in sample
    ])
    if not items_text:
        return _geo_fallback()
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=SYSTEM,
            messages=[{"role": "user", "content": f"""아래 로봇 업계 뉴스를 바탕으로 KR/US/CN 지정학·전략 신호를 분석하세요.
직접적인 정책 기사가 없어도 투자, 파트너십, 기업 동향에서 각국 전략 방향을 추론하세요.

뉴스:
{items_text}

JSON만 반환:
{{
  "KR": {{"temp": "상승 또는 유지 또는 하락", "policy": "핵심 전략 동향 1줄", "desc": "한국 로봇 생태계 동향 2문장", "items": ["항목1", "항목2", "항목3"]}},
  "US": {{"temp": "상승 또는 유지 또는 하락", "policy": "핵심 전략 동향 1줄", "desc": "미국 로봇 생태계 동향 2문장", "items": ["항목1", "항목2", "항목3"]}},
  "CN": {{"temp": "상승 또는 유지 또는 하락", "policy": "핵심 전략 동향 1줄", "desc": "중국 로봇 생태계 동향 2문장", "items": ["항목1", "항목2", "항목3"]}}
}}"""
        }])
        text = msg.content[0].text.strip()
        result = json.loads(text[text.find('{'):text.rfind('}')+1])
        return result
    except Exception as e:
        print(f"  ⚠ geopolitical error: {e}")
        return _geo_fallback()

def _geo_fallback():
    return {
        "KR": {"temp": "유지", "policy": "데이터 없음", "desc": "", "items": []},
        "US": {"temp": "유지", "policy": "데이터 없음", "desc": "", "items": []},
        "CN": {"temp": "유지", "policy": "데이터 없음", "desc": "", "items": []},
    }

def generate_narrative_shifts(articles):
    """업계 담론 프레이밍 변화 탐지"""
    sample = articles[:20]
    items_text = "\n".join([
        f"- {a.get('title_ko') or a.get('title','')}: {a.get('summary_ko') or a.get('summary','')[:120]}"
        for a in sample
    ])
    if not items_text:
        return []
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            system=SYSTEM,
            messages=[{"role": "user", "content": f"""아래 로봇 업계 뉴스에서 업계 담론/프레이밍 변화를 3개 탐지하세요.

뉴스:
{items_text}

JSON 배열만 반환:
[
  {{"keyword": "주제어", "from_frame": "이전 프레임 (짧게)", "to_frame": "현재 프레임 (짧게)", "desc": "변화 설명 2문장"}},
  {{"keyword": "...", "from_frame": "...", "to_frame": "...", "desc": "..."}},
  {{"keyword": "...", "from_frame": "...", "to_frame": "...", "desc": "..."}}
]"""
        }])
        text = msg.content[0].text.strip()
        start = text.find('[')
        end = text.rfind(']') + 1
        return json.loads(text[start:end])
    except Exception as e:
        print(f"  ⚠ narrative error: {e}")
        return []

def load_archive_articles(archive_dir, days=6):
    """최근 N일 아카이브에서 이미 분석된 기사 로드 (재분석 없이)"""
    articles = []
    today_date = datetime.now(timezone.utc).date()
    for d in range(1, days + 1):
        date_str = (today_date - timedelta(days=d)).strftime('%Y-%m-%d')
        path = os.path.join(archive_dir, f'{date_str}.json')
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                old = json.load(f)
            for a in old.get('global_top10', []):
                a['_age_days'] = d
                articles.append(dict(a))
        except Exception as e:
            print(f"  ⚠ archive {date_str}: {e}")
    return articles

# ── MAIN ─────────────────────────────────────────────────
if __name__ == '__main__':
    raw_path = os.path.join(DATA_DIR, 'raw.json')
    history_path = os.path.join(DATA_DIR, 'entity_history.json')

    with open(raw_path, encoding='utf-8') as f:
        raw = json.load(f)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    all_articles = raw['global']

    # 전체 기사 분석 (중복 없이)
    print(f"🤖 Analyzing {len(all_articles)} articles with Claude...")
    analyzed = []
    for i, article in enumerate(all_articles):
        print(f"  [{i+1}/{len(all_articles)}] {article['title'][:60]}...")
        result = analyze(article['title'], article['summary'], article['region'])
        article.update(result)
        article['score'] = score_final(article)
        analyzed.append(article)
        time.sleep(0.5)

    # 지역별도 분석
    regional_analyzed = {}
    for region, arts in raw['regional'].items():
        regional_analyzed[region] = []
        for article in arts:
            existing = next((a for a in analyzed if a['id'] == article['id']), None)
            if existing:
                regional_analyzed[region].append(existing)
            else:
                result = analyze(article['title'], article['summary'], region)
                article.update(result)
                article['score'] = score_final(article)
                regional_analyzed[region].append(article)
                analyzed.append(article)
                time.sleep(0.3)

    # ── 아카이브 병합: 지난 6일 기사 추가 (재분석 없음) ──────────
    archive_dir = os.path.join(DATA_DIR, 'archive')
    os.makedirs(archive_dir, exist_ok=True)
    print("\n📚 Merging archive articles (past 6 days)...")
    archive_arts = load_archive_articles(archive_dir)
    seen_ids = {a['id'] for a in analyzed}
    archive_added = 0
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=21)).timestamp()
    for a in archive_arts:
        if a['id'] in seen_ids:
            continue
        # 21일 이상 된 기사는 archive에서도 제외
        if a.get('pub_ts', 0) and a['pub_ts'] < cutoff_ts:
            continue
        age = a.get('_age_days', 7)
        # 날짜당 12% 점수 감쇄, 최소 40% 유지
        decay = max(0.4, 1.0 - age * 0.12)
        a['score'] = round(a.get('score', 3.0) * decay, 1)
        analyzed.append(a)
        seen_ids.add(a['id'])
        archive_added += 1
    print(f"   Added {archive_added} archive articles → total {len(analyzed)} unique")

    # 주간 전체에서 Top 20 (날짜 다양성 확보)
    global_top10 = sorted(analyzed, key=lambda x: x['score'], reverse=True)[:20]

    # Weak Signal 탐지
    print("\n📡 Detecting weak signals...")
    weak_signals = detect_weak_signals(history_path, analyzed)

    # Intelligence Brief 생성
    print("\n📝 Generating Intelligence Brief...")
    brief = generate_brief(global_top10)

    # Geopolitical Signal 생성
    print("\n🌏 Generating Geopolitical signals...")
    geopolitical = generate_geopolitical(analyzed)

    # Narrative Shift 생성
    print("\n📊 Generating Narrative shifts...")
    narrative_shifts = generate_narrative_shifts(analyzed[:20])

    # Regional Delta (Claude가 생성)
    try:
        delta_msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=SYSTEM,
            messages=[{"role": "user", "content": f"""오늘 가장 중요한 로봇 뉴스 1건에 대해 KR/US/CN 미디어 시각 차이를 분석하세요.

주요 뉴스: {global_top10[0]['title'] if global_top10 else ''}

JSON만 반환:
{{
  "topic": "분석 대상 이슈",
  "kr_angle": "한국 미디어 관점 1~2문장",
  "us_angle": "미국 미디어 관점 1~2문장",
  "cn_angle": "중국 미디어 관점 1~2문장"
}}"""}]
        )
        delta_text = delta_msg.content[0].text.strip()
        delta = json.loads(delta_text[delta_text.find('{'):delta_text.rfind('}')+1])
    except:
        delta = {"topic": "", "kr_angle": "", "us_angle": "", "cn_angle": ""}

    # ── 최종 JSON 저장 ──
    output = {
        "date": today,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_scanned": len(raw['global']),
            "action_count": sum(1 for a in global_top10 if a.get('signal') == 'Action'),
            "watch_count": sum(1 for a in global_top10 if a.get('signal') == 'Watch'),
            "weak_signal_count": len(weak_signals),
            "top_score": global_top10[0]['score'] if global_top10 else 0
        },
        "global_top10": global_top10,
        "regional": {
            "KR": regional_analyzed.get('KR', [])[:10],
            "US": regional_analyzed.get('US', [])[:10],
            "CN": regional_analyzed.get('CN', [])[:10],
            "EU": regional_analyzed.get('EU', [])[:10],
        },
        "regional_delta": delta,
        "weak_signals": weak_signals,
        "brief": brief,
        "geopolitical": geopolitical,
        "narrative_shifts": narrative_shifts
    }

    # 오늘 파일 저장
    news_path = os.path.join(DATA_DIR, 'news.json')
    with open(news_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 아카이브 저장
    archive_dir = os.path.join(DATA_DIR, 'archive')
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f'{today}.json')
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved: {news_path}")
    print(f"   Global Top 10: {len(global_top10)}")
    print(f"   Weak Signals: {len(weak_signals)}")
    print(f"   Narrative Shifts: {len(narrative_shifts)}")
    print(f"   Brief: generated")

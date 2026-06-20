#!/usr/bin/env python3
"""
analyze.py — Claude API로 기사 분석 + 최종 JSON 생성
최적화: 기사 분석은 Haiku 배치, 전략 합성은 Sonnet 1회 통합 호출
"""
import anthropic
import json
import os
import time
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

HAIKU  = "claude-haiku-4-5-20251001"  # 기사 분석용 (저비용)
SONNET = "claude-sonnet-4-6"           # 전략 브리프용

# 로봇 기술 용어 번역 기준 (Haiku/Sonnet 공통 적용)
ROBOT_GLOSSARY = """
【로봇 전문용어 번역 기준 — 반드시 준수】
- embodied AI / embodiment / embodied → 구현형 AI / 구현체 (절대 '인형' 사용 금지)
- physical AI → 피지컬 AI
- manipulation → 조작 (물체 조작)
- locomotion → 이동 / 보행
- dexterous / dexterity → 정교한 / 정밀 조작
- sim-to-real → sim-to-real 또는 시뮬-실제 전환
- imitation learning → 모방 학습
- behavior cloning → 행동 복제
- reinforcement learning → 강화 학습
- policy (ML 맥락) → 정책 또는 폴리시
- foundation model → 파운데이션 모델
- world model → 월드 모델
- end-effector → 엔드이펙터
- gripper → 그리퍼
- actuator → 액추에이터
- torque → 토크
- proprioception → 자기수용감각
- haptic → 햅틱
- teleoperation → 원격 조작
- whole-body control → 전신 제어
- loco-manipulation → 이동 조작
- VLA / vision-language-action → VLA
- diffusion policy → 확산 정책
- zero-shot / few-shot → 제로샷 / 퓨샷
- deployment → 도입 또는 배포
- humanoid → 휴머노이드
- bimanual → 양손 조작
- contact-rich → 접촉 집약적
- GR00T, Isaac Lab, Isaac Sim, Helix, LeRobot 등 고유명사 → 원문 유지
"""

SYSTEM_HAIKU  = f"LG전자 로봇팀 분석가. JSON만 반환. 다른 텍스트 없음.\n{ROBOT_GLOSSARY}"
SYSTEM_SONNET = f"""LG Electronics 로봇/Physical AI 전략팀 수석 분석가.
핵심 관점: ① 글로벌 빅테크(NVIDIA·Google·Meta·Microsoft·Amazon·Apple·Tesla)의 로봇 전략 방향
          ② 최신 기술 트렌드(VLA·Embodied AI·월드모델·하드웨어 혁신)의 산업 파급효과
          ③ LG전자가 이 흐름에서 취해야 할 전략 포지션
JSON만 반환. 다른 텍스트 없음.
{ROBOT_GLOSSARY}"""

BATCH_SIZE = 5  # 기사 배치 크기

# ── 기사 분석 (Haiku 배치) ────────────────────────────────────

def analyze_batch(articles):
    """여러 기사를 한 번의 Haiku 호출로 분석 (순서 기반 매핑)"""
    n = len(articles)
    items = "\n\n".join([
        f"기사{i+1})\n제목: {a['title'][:120]}\n요약: {(a.get('summary') or '')[:180]}"
        for i, a in enumerate(articles)
    ])
    prompt = f"""아래 로봇 업계 기사 {n}개를 분석하세요. 입력 순서대로 정확히 {n}개 항목을 JSON 배열로 반환하세요.

{items}

반환 형식 (순서 유지, {n}개 모두 포함):
[
  {{
    "title_ko": "영어/중국어 제목은 반드시 한국어로 번역. 한국어 제목은 원문.",
    "summary_ko": "한국어 2문장 핵심 요약",
    "signal": "Action 또는 Watch 또는 FYI",
    "lg_implication": "LG전자 관점 시사점 1문장",
    "keywords": ["키워드1", "키워드2", "키워드3"]
  }},
  ...
]

signal 기준: Action=LG사업 즉각 영향/경쟁위협, Watch=중기 모니터링, FYI=참고용"""

    try:
        msg = client.messages.create(
            model=HAIKU,
            max_tokens=n * 400,
            system=SYSTEM_HAIKU,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        start, end = text.find('['), text.rfind(']') + 1
        if start == -1 or end == 0:
            print(f"    ⚠ batch: no JSON array. Response: {text[:300]}")
            return {}
        results = json.loads(text[start:end])
        # 순서 기반 매핑 (idx 없이)
        mapped = {i: r for i, r in enumerate(results) if i < n}
        if len(mapped) < n:
            print(f"    ⚠ batch: got {len(mapped)}/{n} items")
        return mapped
    except json.JSONDecodeError as e:
        print(f"    ⚠ batch JSON error: {e}")
        return {}
    except Exception as e:
        print(f"    ⚠ batch error: {e}")
        return {}

def apply_analysis(article, result):
    """분석 결과를 기사 dict에 반영"""
    if result:
        article['title_ko']      = result.get('title_ko') or article['title']
        article['summary_ko']    = result.get('summary_ko') or (article.get('summary') or '')[:150]
        article['signal']        = result.get('signal', 'FYI')
        article['lg_implication']= result.get('lg_implication', '')
        article['keywords']      = result.get('keywords', [])
    else:
        article.setdefault('title_ko',       article['title'])
        article.setdefault('summary_ko',     (article.get('summary') or '')[:150])
        article.setdefault('signal',         'FYI')
        article.setdefault('lg_implication', '')
        article.setdefault('keywords',       [])

def analyze_articles(articles):
    """배치로 기사 분석 (Haiku)"""
    total = len(articles)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"🤖 Analyzing {total} articles in {n_batches} batches (Haiku)...")
    result_list = []
    for i in range(0, total, BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        print(f"  Batch {i//BATCH_SIZE + 1}/{n_batches} ({len(batch)} articles)")
        mapped = analyze_batch(batch)
        for j, article in enumerate(batch):
            apply_analysis(article, mapped.get(j))
            result_list.append(article)
        if i + BATCH_SIZE < total:
            time.sleep(0.3)
    return result_list

# ── 스코어 ───────────────────────────────────────────────────

def score_final(article):
    base = article.get('raw_score', 5.0)
    bonus = {'Action': 1.0, 'Watch': 0.3, 'FYI': 0.0}
    return round(min(10.0, base + bonus.get(article.get('signal', 'FYI'), 0)), 1)

# ── Intelligence Brief (Sonnet) ───────────────────────────────

def generate_brief(articles):
    action = [a for a in articles if a.get('signal') == 'Action']
    watch  = [a for a in articles if a.get('signal') == 'Watch'][:3]
    items  = (action + watch)[:6] or articles[:5]

    lines = "\n".join([
        f"[{a.get('signal','FYI')}] {a.get('title_ko') or a['title']}: {(a.get('summary_ko') or a.get('summary',''))[:100]}"
        for a in items
    ])
    if not lines:
        return {"action_required": ["수집 기사 부족"], "regional_delta": {}, "cvc_insight": [], "bottom_line": ""}

    try:
        msg = client.messages.create(
            model=SONNET,
            max_tokens=1200,
            system=SYSTEM_SONNET,
            messages=[{"role": "user", "content": f"""LG전자 로봇 전략팀 Intelligence Brief 작성.
핵심 관점: 빅테크(NVIDIA/Google/Meta/Microsoft/Amazon/Tesla)의 로봇 전략 + 최신 기술 트렌드 + LG전자 대응

주요 기사:
{lines}

JSON만 반환:
{{
  "action_required": ["빅테크/경쟁사 동향 기반 즉각대응 1문장", "기술 트렌드 대응 방향 1문장"],
  "regional_delta": {{"KR":"한국 로봇 산업 동향 1문장","US":"미국 빅테크 로봇 전략 1문장","CN":"중국 로봇 기업 동향 1문장"}},
  "cvc_insight": ["빅테크 파트너십/기술 투자 기회 1문장","LG가 주목할 기술 확보 방향 1문장"],
  "bottom_line": "빅테크 로봇 경쟁 흐름에서 LG전자의 핵심 전략 메시지 1~2문장"
}}"""}]
        )
        text = msg.content[0].text.strip()
        result = json.loads(text[text.find('{'):text.rfind('}')+1])
        if not result.get('action_required'):
            result['action_required'] = [items[0]['title'][:80]] if items else []
        if not result.get('bottom_line'):
            result['bottom_line'] = items[0].get('summary_ko', '') if items else ''
        return result
    except Exception as e:
        print(f"  ⚠ brief error: {e}")
        return {
            "action_required": [a['title'][:80] for a in items[:2]],
            "regional_delta": {"KR": "", "US": "", "CN": ""},
            "cvc_insight": [],
            "bottom_line": items[0].get('summary_ko', '') if items else ''
        }

# ── 전략 합성 (지정학 + 담론변화 + 지역시각) — Sonnet 1회 ────

def generate_synthesis(articles):
    """geopolitical + narrative_shifts + regional_delta 를 단일 Sonnet 호출로 생성"""
    sample = articles[:15]
    lines = "\n".join([
        f"[{a.get('region','?')}][{a.get('signal','FYI')}] {a.get('title_ko') or a['title']}: {(a.get('summary_ko') or a.get('summary',''))[:80]}"
        for a in sample
    ])
    top_title = sample[0].get('title_ko') or sample[0]['title'] if sample else ''

    try:
        msg = client.messages.create(
            model=SONNET,
            max_tokens=1800,
            system=SYSTEM_SONNET,
            messages=[{"role": "user", "content": f"""로봇 업계 뉴스로 전략 인사이트 3종 생성.
핵심 관점: 빅테크(NVIDIA/Google/Meta/Microsoft/Amazon/Tesla)의 로봇 전략 + 기술 트렌드 변화

뉴스:
{lines}

JSON만 반환:
{{
  "geopolitical": {{
    "KR": {{"temp":"상승|유지|하락","policy":"한국 로봇 산업 핵심 동향 1줄","desc":"한국 기업/정부 로봇 전략 방향 2문장","items":["구체 항목1","구체 항목2"]}},
    "US": {{"temp":"상승|유지|하락","policy":"미국 빅테크 로봇 전략 1줄","desc":"NVIDIA/Google/Meta/MS/Amazon 등 빅테크 로봇 방향 2문장","items":["구체 항목1","구체 항목2"]}},
    "CN": {{"temp":"상승|유지|하락","policy":"중국 로봇 기업 전략 1줄","desc":"Unitree/Agibot 등 중국 로봇 생태계 동향 2문장","items":["구체 항목1","구체 항목2"]}}
  }},
  "narrative_shifts": [
    {{"keyword":"주제어","from_frame":"이전 업계 프레임","to_frame":"현재 빅테크/기술 주도 프레임","desc":"기술 트렌드 관점 변화 2문장"}},
    {{"keyword":"...","from_frame":"...","to_frame":"...","desc":"..."}},
    {{"keyword":"...","from_frame":"...","to_frame":"...","desc":"..."}}
  ],
  "regional_delta": {{
    "topic":"{top_title[:60]}",
    "kr_angle":"한국 관점 1~2문장",
    "us_angle":"미국 빅테크 관점 1~2문장",
    "cn_angle":"중국 관점 1~2문장"
  }}
}}"""}]
        )
        text = msg.content[0].text.strip()
        r = json.loads(text[text.find('{'):text.rfind('}')+1])
        geo   = r.get('geopolitical', _geo_fallback())
        narr  = r.get('narrative_shifts', [])
        delta = r.get('regional_delta', {"topic":"","kr_angle":"","us_angle":"","cn_angle":""})
        return geo, narr, delta
    except Exception as e:
        print(f"  ⚠ synthesis error: {e}")
        return _geo_fallback(), [], {"topic":"","kr_angle":"","us_angle":"","cn_angle":""}

def _geo_fallback():
    return {
        "KR": {"temp":"유지","policy":"","desc":"","items":[]},
        "US": {"temp":"유지","policy":"","desc":"","items":[]},
        "CN": {"temp":"유지","policy":"","desc":"","items":[]},
    }

# ── Weak Signal ───────────────────────────────────────────────

def detect_weak_signals(history_path, today_articles):
    history = {}
    if os.path.exists(history_path):
        with open(history_path) as f:
            history = json.load(f)

    today_counts = {}
    for a in today_articles:
        ent = a.get('entity')
        if ent:
            today_counts[ent] = today_counts.get(ent, 0) + 1

    signals = []
    for ent, count in today_counts.items():
        past = history.get(ent, {}).get('counts', [])
        avg  = sum(past[-30:]) / len(past[-30:]) if past else 0.1
        spike = ((count - avg) / avg * 100) if avg > 0 else count * 100
        if spike >= 150:
            signals.append({
                'entity': ent, 'today_count': count,
                'avg_count': round(avg, 1), 'spike_pct': round(spike),
                'level': 'hot' if spike >= 500 else ('warm' if spike >= 250 else 'cool')
            })
        if ent not in history:
            history[ent] = {'counts': []}
        history[ent]['counts'].append(count)
        history[ent]['counts'] = history[ent]['counts'][-60:]

    with open(history_path, 'w') as f:
        json.dump(history, f, ensure_ascii=False)

    return sorted(signals, key=lambda x: x['spike_pct'], reverse=True)[:6]

# ── Archive helpers ───────────────────────────────────────────

def load_archive_articles(archive_dir, days=6):
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

def title_sim(t1, t2):
    return SequenceMatcher(None, t1, t2).ratio()

# ── MAIN ─────────────────────────────────────────────────────

if __name__ == '__main__':
    raw_path     = os.path.join(DATA_DIR, 'raw.json')
    history_path = os.path.join(DATA_DIR, 'entity_history.json')

    with open(raw_path, encoding='utf-8') as f:
        raw = json.load(f)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # ── 1. 글로벌 Top 20 기사 배치 분석 ──────────────────────
    all_articles = raw['global']  # fetch.py가 이미 Top 30으로 줄임
    analyzed = analyze_articles(all_articles)
    for a in analyzed:
        a['score'] = score_final(a)

    analyzed_ids = {a['id'] for a in analyzed}

    # ── 2. 지역별 기사 분석 (중복 제외) ──────────────────────
    regional_new = []
    regional_analyzed = {}
    for region, arts in raw['regional'].items():
        regional_analyzed[region] = []
        for article in arts:
            existing = next((a for a in analyzed if a['id'] == article['id']), None)
            if existing:
                regional_analyzed[region].append(existing)
            else:
                regional_new.append((region, article))

    if regional_new:
        print(f"\n🌏 Analyzing {len(regional_new)} region-only articles...")
        region_articles = [a for _, a in regional_new]
        region_results  = analyze_articles(region_articles)
        for (region, _), article in zip(regional_new, region_results):
            article['score'] = score_final(article)
            regional_analyzed[region].append(article)
            analyzed.append(article)
            analyzed_ids.add(article['id'])

    # ── 3. Fresh/Repeat 분류 (어제 top10과 비교) ──────────────
    archive_dir = os.path.join(DATA_DIR, 'archive')
    os.makedirs(archive_dir, exist_ok=True)

    yesterday_date = (datetime.now(timezone.utc).date() - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_path = os.path.join(archive_dir, f'{yesterday_date}.json')
    yesterday_titles = []
    if os.path.exists(yesterday_path):
        try:
            with open(yesterday_path, encoding='utf-8') as f:
                yd = json.load(f)
            yesterday_titles = [a['title'].lower() for a in yd.get('global_top10', [])]
            print(f"\n📅 Yesterday top10 loaded: {len(yesterday_titles)} titles")
        except Exception as e:
            print(f"  ⚠ yesterday archive: {e}")

    # 48시간 초과 기사는 어제 top10 비교 없이 바로 repeat 처리
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff_48h = now_ts - 48 * 3600

    fresh, repeat = [], []
    for a in analyzed:
        atitle = a['title'].lower()
        pub_ts = a.get('pub_ts', 0)
        if pub_ts and pub_ts < cutoff_48h:
            repeat.append(a)  # 48시간 이상: 항상 repeat
        elif any(title_sim(atitle, yt) >= 0.65 for yt in yesterday_titles):
            repeat.append(a)  # 어제 top10과 유사: repeat
        else:
            fresh.append(a)
    print(f"   Fresh(48h내): {len(fresh)}, Repeat(구기사/중복): {len(repeat)}")

    # ── 4. 아카이브 보충 (fresh < 10일 때만) ─────────────────
    SUPPLEMENT_IF_BELOW = 10
    if len(fresh) < SUPPLEMENT_IF_BELOW:
        print(f"📚 Supplementing from archive (fresh {len(fresh)} < {SUPPLEMENT_IF_BELOW})...")
        archive_arts = load_archive_articles(archive_dir)
        all_today_titles = [a['title'].lower() for a in analyzed]
        added = 0
        cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=21)).timestamp()
        for a in archive_arts:
            if a['id'] in analyzed_ids:
                continue
            if a.get('pub_ts', 0) and a['pub_ts'] < cutoff_ts:
                continue
            atitle = a['title'].lower()
            if any(title_sim(atitle, t) >= 0.65 for t in all_today_titles):
                continue
            age = a.get('_age_days', 7)
            a['score'] = round(a.get('score', 3.0) * max(0.4, 1.0 - age * 0.12), 1)
            fresh.append(a)
            analyzed_ids.add(a['id'])
            all_today_titles.append(atitle)
            added += 1
        print(f"   Added {added} archive articles")
    else:
        print(f"✅ Enough fresh articles ({len(fresh)}), skipping archive merge")

    # fresh 우선, 모자라면 repeat 보충
    global_top10 = (
        sorted(fresh,  key=lambda x: x['score'], reverse=True) +
        sorted(repeat, key=lambda x: x['score'], reverse=True)
    )[:20]
    print(f"   global_top10 pool: {len(global_top10)}")

    # ── 5. Weak Signal ────────────────────────────────────────
    print("\n📡 Detecting weak signals...")
    weak_signals = detect_weak_signals(history_path, analyzed)

    # ── 6. Intelligence Brief (Sonnet 1회) ───────────────────
    print("\n📝 Generating Intelligence Brief...")
    brief = generate_brief(global_top10)

    # ── 7. 전략 합성 — 지정학 + 담론변화 + 지역시각 (Sonnet 1회) ─
    print("\n🌏 Generating strategic synthesis...")
    geopolitical, narrative_shifts, delta = generate_synthesis(global_top10)

    # ── 8. 최종 JSON 저장 ────────────────────────────────────
    output = {
        "date": today,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_scanned":    len(raw['global']),
            "action_count":     sum(1 for a in global_top10 if a.get('signal') == 'Action'),
            "watch_count":      sum(1 for a in global_top10 if a.get('signal') == 'Watch'),
            "weak_signal_count": len(weak_signals),
            "top_score":        global_top10[0]['score'] if global_top10 else 0
        },
        "global_top10":    global_top10,
        "regional": {
            "KR": regional_analyzed.get('KR', [])[:10],
            "US": regional_analyzed.get('US', [])[:10],
            "CN": regional_analyzed.get('CN', [])[:10],
            "EU": regional_analyzed.get('EU', [])[:10],
        },
        "regional_delta":   delta,
        "weak_signals":     weak_signals,
        "brief":            brief,
        "geopolitical":     geopolitical,
        "narrative_shifts": narrative_shifts
    }

    news_path = os.path.join(DATA_DIR, 'news.json')
    with open(news_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    archive_path = os.path.join(archive_dir, f'{today}.json')
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved: {news_path}")
    print(f"   Global pool: {len(global_top10)} | Weak signals: {len(weak_signals)} | Narrative shifts: {len(narrative_shifts)}")
    print(f"   API calls: ~{(len(all_articles)+len(regional_new)+BATCH_SIZE-1)//BATCH_SIZE + 2} (Haiku×배치 + Sonnet×2)")

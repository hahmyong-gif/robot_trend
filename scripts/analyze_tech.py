#!/usr/bin/env python3
"""
analyze_tech.py — 기술 논문 분석 + Top 10 임팩트 기술 선정
Haiku 배치 요약 → Sonnet Top 10 선정
"""
import anthropic
import json
import os
import time
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

HAIKU  = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

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
- humanoid → 휴머노이드
- bimanual → 양손 조작
- contact-rich → 접촉 집약적
- GR00T, Isaac Lab, Isaac Sim, Helix, LeRobot 등 고유명사 → 원문 유지
"""

SYSTEM_H = f"LG전자 로봇 R&D 전략팀. JSON 배열만 반환. 다른 텍스트 없음.\n{ROBOT_GLOSSARY}"
SYSTEM_S = f"LG전자 로봇/Physical AI 전략팀 수석 연구원. JSON만 반환. 다른 텍스트 없음.\n{ROBOT_GLOSSARY}"

BATCH_SIZE = 5

AREA_MAP = {
    '조작': 'manipulation',
    '이동': 'locomotion',
    '인지': 'perception',
    '학습': 'learning',
    'HW':   'hardware',
    '제어': 'control',
    'SW':   'software',
    '기타': 'other',
}

def summarize_batch(papers):
    """논문 배치 요약 (Haiku, 순서 기반 매핑)"""
    n = len(papers)
    items = "\n\n".join([
        f"논문{i+1})\n제목: {p['title'][:150]}\n초록: {(p.get('summary') or '')[:250]}\n출처: {p['source']}"
        for i, p in enumerate(papers)
    ])

    try:
        msg = client.messages.create(
            model=HAIKU,
            max_tokens=n * 420,
            system=SYSTEM_H,
            messages=[{"role": "user", "content": f"""로봇 관련 논문/기술 {n}개 분석. 순서대로 {n}개 항목 JSON 배열 반환:

{items}

[
  {{
    "title_ko": "한국어로 번역한 제목 (영어 제목은 반드시 한국어로)",
    "contribution": "핵심 기술 기여 2문장 (한국어, 구체적으로)",
    "tech_area": "조작|이동|인지|학습|HW|제어|SW|기타 중 하나",
    "is_robot_relevant": true,
    "impact_score": 7
  }},
  ...
]

tech_area: 조작=manipulation/gripper/dexterous, 이동=locomotion/walking, 인지=perception/vision/sensing,
           학습=RL/imitation/policy, HW=actuator/motor/sensor 설계, 제어=control/planning, SW=simulator/framework"""}]
        )
        text = msg.content[0].text.strip()
        s, e = text.find('['), text.rfind(']') + 1
        if s == -1:
            print(f"    ⚠ summarize: no array in response")
            return {}
        results = json.loads(text[s:e])
        mapped = {i: r for i, r in enumerate(results) if i < n}
        if len(mapped) < n:
            print(f"    ⚠ summarize: {len(mapped)}/{n} items returned")
        return mapped
    except Exception as ex:
        print(f"    ⚠ summarize batch error: {ex}")
        return {}

def select_top10(papers):
    """Sonnet으로 Top 10 임팩트 기술 선정"""
    candidates = "\n".join([
        f"[{i+1}][{p.get('tech_area','?')}][임팩트:{p.get('impact_score',5)}] {p.get('title_ko') or p['title'][:80]}: {p.get('contribution','')[:100]}"
        for i, p in enumerate(papers[:35])
    ])

    try:
        msg = client.messages.create(
            model=SONNET,
            max_tokens=800,
            system=SYSTEM_S,
            messages=[{"role": "user", "content": f"""아래 로봇 관련 논문/기술 후보에서 LG전자 관점으로 가장 임팩트 있는 10개 선정.
선정 기준: ① 기술 혁신성 ② 상용화 가능성 ③ LG 로봇 사업 관련성 ④ 최신성

후보:
{candidates}

JSON만 반환:
{{
  "top10_indices": [1, 3, 5, 7, 9, 11, 13, 15, 17, 19],
  "tech_brief": "이번 주 핵심 기술 트렌드 2문장 (한국어)",
  "lg_tech_watch": "LG전자가 가장 주목해야 할 기술 방향 2문장 (한국어)"
}}"""}]
        )
        text = msg.content[0].text.strip()
        return json.loads(text[text.find('{'):text.rfind('}')+1])
    except Exception as e:
        print(f"  ⚠ top10 selection error: {e}")
        return {
            "top10_indices": list(range(1, 11)),
            "tech_brief": "",
            "lg_tech_watch": ""
        }

if __name__ == '__main__':
    raw_path = os.path.join(DATA_DIR, 'raw_tech.json')
    if not os.path.exists(raw_path):
        print("⚠ raw_tech.json not found. Run fetch_tech.py first.")
        exit(1)

    with open(raw_path, encoding='utf-8') as f:
        raw = json.load(f)

    papers = raw.get('papers', [])
    total = len(papers)
    print(f"🔬 Analyzing {total} tech papers with Haiku batches...")

    # Haiku 배치 요약
    analyzed = list(papers)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, total, BATCH_SIZE):
        batch = papers[i:i + BATCH_SIZE]
        print(f"  Batch {i//BATCH_SIZE+1}/{n_batches} ({len(batch)} papers)")
        results = summarize_batch(batch)
        for j, paper in enumerate(batch):
            r = results.get(j, {})
            paper['title_ko']         = r.get('title_ko') or paper['title']
            paper['contribution']     = r.get('contribution') or (paper.get('summary') or '')[:200]
            paper['tech_area']        = r.get('tech_area', '기타')
            paper['is_robot_relevant']= r.get('is_robot_relevant', True)
            paper['impact_score']     = r.get('impact_score', 5)
        if i + BATCH_SIZE < total:
            time.sleep(0.3)

    # 로봇 관련 필터 + 임팩트 정렬
    robot_papers = [p for p in analyzed if p.get('is_robot_relevant', True)]
    robot_papers.sort(key=lambda x: (x.get('impact_score', 0), x.get('pub_ts', 0)), reverse=True)
    print(f"   Robot-relevant: {len(robot_papers)}")

    # Sonnet Top 10 선정
    print("\n🏆 Selecting Top 10 impact technologies (Sonnet)...")
    selection = select_top10(robot_papers)

    indices = [i - 1 for i in selection.get('top10_indices', []) if 1 <= i <= len(robot_papers)]
    top10 = [robot_papers[i] for i in indices[:10]]

    # 10개 미만이면 impact_score 상위로 보충
    if len(top10) < 10:
        existing = {p.get('url') for p in top10}
        for p in robot_papers:
            if len(top10) >= 10:
                break
            if p.get('url') not in existing:
                top10.append(p)
                existing.add(p.get('url'))

    # tech_area 한국어 레이블 정리
    area_ko = {'manipulation':'조작','locomotion':'이동','perception':'인지',
               'learning':'학습','hardware':'HW','control':'제어','software':'SW','other':'기타'}
    for p in top10:
        ta = p.get('tech_area', '기타')
        # 한국어가 이미 있으면 그대로, 영어면 변환
        if ta not in ['조작','이동','인지','학습','HW','제어','SW','기타']:
            p['tech_area'] = area_ko.get(ta, '기타')

    output = {
        "date":          datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "tech_brief":    selection.get('tech_brief', ''),
        "lg_tech_watch": selection.get('lg_tech_watch', ''),
        "top10":         top10,
        "total_scanned": total
    }

    tech_path = os.path.join(DATA_DIR, 'tech.json')
    with open(tech_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved: {tech_path}")
    print(f"   Top 10 selected from {len(robot_papers)} robot-relevant papers ({total} total)")
    for i, p in enumerate(top10, 1):
        print(f"   {i:2}. [{p.get('tech_area','?')}][{p.get('impact_score','?')}] {p.get('title_ko','')[:60]}")

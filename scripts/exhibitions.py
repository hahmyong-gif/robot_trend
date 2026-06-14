#!/usr/bin/env python3
"""
exhibitions.py — 월별 글로벌 로봇 전시회 데이터 생성
매월 1일 실행 or 수동 실행
"""
import anthropic
import json
import os
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

# 고정 전시회 DB (연간 주요 전시회 — 매년 비슷한 시기에 개최)
EXHIBITIONS_DB = [
    {
        "name": "CES",
        "full_name": "Consumer Electronics Show",
        "month": 1,
        "location": "Las Vegas, USA",
        "description": "세계 최대 가전·기술 전시회. 홈 로봇, AI 가전, 스마트홈 분야 핵심 무대.",
        "relevance": "★★★★★",
        "focus": ["home robot", "AI appliance", "smart home"],
        "url": "https://www.ces.tech",
        "tier": "Tier 1"
    },
    {
        "name": "Automatica",
        "full_name": "Automatica Munich",
        "month": 6,
        "location": "Munich, Germany",
        "description": "유럽 최대 산업 자동화·로봇 전시회. 제조 로봇, 협동 로봇 중심.",
        "relevance": "★★★★★",
        "focus": ["industrial robot", "cobot", "automation"],
        "url": "https://www.automatica-munich.com",
        "tier": "Tier 1"
    },
    {
        "name": "ICRA",
        "full_name": "IEEE International Conference on Robotics and Automation",
        "month": 5,
        "location": "Atlanta, USA (2026)",
        "description": "세계 최고 권위 로봇공학 학술대회. 최신 연구 동향 파악 필수.",
        "relevance": "★★★★☆",
        "focus": ["robot research", "AI", "manipulation", "locomotion"],
        "url": "https://2026.ieee-icra.org",
        "tier": "Tier 1"
    },
    {
        "name": "Hannover Messe",
        "full_name": "Hannover Messe",
        "month": 4,
        "location": "Hannover, Germany",
        "description": "세계 최대 산업기술 전시회. 제조 자동화, 산업용 AI, 로봇 통합 솔루션.",
        "relevance": "★★★★☆",
        "focus": ["industrial automation", "robot integration", "smart factory"],
        "url": "https://www.hannovermesse.de",
        "tier": "Tier 1"
    },
    {
        "name": "IROS",
        "full_name": "IEEE/RSJ International Conference on Intelligent Robots and Systems",
        "month": 10,
        "location": "Abu Dhabi, UAE (2026)",
        "description": "ICRA와 함께 세계 양대 로봇 학술대회. 지능형 로봇 시스템 연구 발표.",
        "relevance": "★★★★☆",
        "focus": ["intelligent robot", "autonomous system", "HRI"],
        "url": "https://iros2026.org",
        "tier": "Tier 1"
    },
    {
        "name": "WRS",
        "full_name": "World Robot Summit",
        "month": 10,
        "location": "Nagoya, Japan",
        "description": "일본 주도 글로벌 로봇 경진대회·전시. 서비스 로봇, 재난 로봇 분야 강점.",
        "relevance": "★★★☆☆",
        "focus": ["service robot", "disaster robot", "competition"],
        "url": "https://worldrobotsummit.org",
        "tier": "Tier 2"
    },
    {
        "name": "iREX",
        "full_name": "International Robot Exhibition",
        "month": 11,
        "location": "Tokyo, Japan",
        "description": "아시아 최대 로봇 전시회. 산업·서비스 로봇 전 분야 망라.",
        "relevance": "★★★★☆",
        "focus": ["industrial robot", "service robot", "Asia market"],
        "url": "https://biz.nikkan.co.jp/eve/irex/",
        "tier": "Tier 1"
    },
    {
        "name": "MWC",
        "full_name": "Mobile World Congress",
        "month": 2,
        "location": "Barcelona, Spain",
        "description": "모바일·통신 중심이나 로봇 연결성, AI 에지 컴퓨팅 분야 점점 확대.",
        "relevance": "★★★☆☆",
        "focus": ["connectivity", "edge AI", "5G robot"],
        "url": "https://www.mwcbarcelona.com",
        "tier": "Tier 2"
    },
    {
        "name": "NVIDIA GTC",
        "full_name": "NVIDIA GPU Technology Conference",
        "month": 3,
        "location": "San Jose, USA",
        "description": "NVIDIA 주관. Isaac Lab, GR00T, Jetson 등 Physical AI 스택 핵심 발표 무대.",
        "relevance": "★★★★★",
        "focus": ["Physical AI", "GR00T", "Isaac Sim", "GPU computing"],
        "url": "https://www.nvidia.com/gtc/",
        "tier": "Tier 1"
    },
    {
        "name": "ROSCon",
        "full_name": "ROSCon",
        "month": 10,
        "location": "TBD (2026)",
        "description": "ROS(로봇 운영체제) 개발자 컨퍼런스. 오픈소스 로봇 생태계 동향.",
        "relevance": "★★★☆☆",
        "focus": ["ROS", "open source", "robot middleware"],
        "url": "https://roscon.ros.org",
        "tier": "Tier 2"
    },
    {
        "name": "Korea Robot World",
        "full_name": "Korea Robot World",
        "month": 10,
        "location": "KINTEX, Korea",
        "description": "한국 최대 로봇 전시회. 국내 로봇 기업 현황 파악 및 네트워킹 필수.",
        "relevance": "★★★★☆",
        "focus": ["Korean robot", "service robot", "manufacturing"],
        "url": "https://www.korearobotworld.com",
        "tier": "Tier 2"
    },
    {
        "name": "WIS",
        "full_name": "World IT Show",
        "month": 5,
        "location": "COEX, Seoul, Korea",
        "description": "국내 ICT·로봇 전시. AI 로봇, 스마트홈, 가전 연계 로봇 분야 강세.",
        "relevance": "★★★☆☆",
        "focus": ["AI robot", "smart home", "Korean startup"],
        "url": "https://www.worlditshow.co.kr",
        "tier": "Tier 2"
    },
    {
        "name": "ERF",
        "full_name": "European Robotics Forum",
        "month": 3,
        "location": "Stuttgart, Germany (2026)",
        "description": "유럽 로봇 연구·산업계 최대 네트워킹 행사. EU 로봇 정책 동향 파악.",
        "relevance": "★★★☆☆",
        "focus": ["European robot", "research", "policy"],
        "url": "https://www.eu-robotics.net/robotics_forum/",
        "tier": "Tier 2"
    },
    {
        "name": "COMPUTEX",
        "full_name": "COMPUTEX Taipei",
        "month": 5,
        "location": "Taipei, Taiwan",
        "description": "아시아 최대 IT 전시. AI 칩, 로봇 하드웨어 공급망 파악에 중요.",
        "relevance": "★★★☆☆",
        "focus": ["AI chip", "robot hardware", "supply chain"],
        "url": "https://www.computextaipei.com.tw",
        "tier": "Tier 2"
    },
    {
        "name": "Humanoids Summit",
        "full_name": "The Humanoids Summit",
        "month": 11,
        "location": "San Francisco, USA",
        "description": "휴머노이드 로봇 전문 컨퍼런스. Figure, 1X, Agility 등 주요 기업 참가.",
        "relevance": "★★★★★",
        "focus": ["humanoid", "Physical AI", "embodied AI"],
        "url": "https://humanoidssummit.com",
        "tier": "Tier 1"
    }
]

def get_exhibitions_for_month(month, year):
    """특정 월의 전시회 필터링"""
    return [e for e in EXHIBITIONS_DB if e['month'] == month]

def get_upcoming_exhibitions(months_ahead=3):
    """향후 N개월 전시회"""
    now = datetime.now()
    result = []
    for i in range(months_ahead + 1):
        target_month = (now.month + i - 1) % 12 + 1
        target_year = now.year + (now.month + i - 1) // 12
        expos = get_exhibitions_for_month(target_month, target_year)
        for e in expos:
            e_copy = dict(e)
            e_copy['year'] = target_year
            e_copy['is_this_month'] = (target_month == now.month and target_year == now.year)
            e_copy['month_name'] = datetime(target_year, target_month, 1).strftime('%B %Y')
            result.append(e_copy)
    return result

if __name__ == '__main__':
    now = datetime.now(timezone.utc)
    upcoming = get_upcoming_exhibitions(months_ahead=3)

    output = {
        "generated_at": now.isoformat(),
        "current_month": now.strftime('%B %Y'),
        "exhibitions": upcoming,
        "this_month": [e for e in upcoming if e.get('is_this_month')],
        "upcoming": [e for e in upcoming if not e.get('is_this_month')]
    }

    path = os.path.join(DATA_DIR, 'exhibitions.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ exhibitions.json saved ({len(upcoming)} events)")
    for e in upcoming:
        print(f"  {'🔴' if e.get('is_this_month') else '📅'} {e['month_name']}: {e['name']} — {e['location']}")

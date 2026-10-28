"""Generate deterministic mock data for Nawa Tech into data/seed/*.csv.

    python scripts/generate_seed.py

Same seed -> same CSVs, so the eval set (week 6) can rely on exact numbers.
Demo personas (docs/demo-personas.md) are created with fixed, hand-picked data;
everyone else is random but consistent with the policies in data/documents/.
"""
from __future__ import annotations

import csv
import random
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mock_hris.workdays import count_working_days, is_working_day  # noqa: E402

SEED = 42
REF_DATE = date(2026, 10, 28)          # "today" inside the mock world
YEAR = 2026
BKK = timezone(timedelta(hours=7))
OUT = ROOT / "data" / "seed"
rng = random.Random(SEED)

# --------------------------------------------------------------------------- holidays
# Nawa Tech company holidays 2026 (HR-002). Based on the 2026 Thai public-holiday list;
# government-only days (Royal Ploughing, Buddhist Lent) are not company holidays.
HOLIDAYS: list[tuple[str, str, str, bool]] = [
    ("2026-01-01", "วันขึ้นปีใหม่", "New Year's Day", False),
    ("2026-01-02", "วันหยุดพิเศษต่อเนื่องปีใหม่", "New Year special holiday", False),
    ("2026-03-03", "วันมาฆบูชา", "Makha Bucha Day", False),
    ("2026-04-06", "วันจักรี", "Chakri Memorial Day", False),
    ("2026-04-13", "วันสงกรานต์", "Songkran Festival", False),
    ("2026-04-14", "วันสงกรานต์", "Songkran Festival", False),
    ("2026-04-15", "วันสงกรานต์", "Songkran Festival", False),
    ("2026-05-01", "วันแรงงานแห่งชาติ", "National Labour Day", False),
    ("2026-05-04", "วันฉัตรมงคล", "Coronation Day", False),
    ("2026-06-01", "วันหยุดชดเชยวันวิสาขบูชา", "Substitution for Visakha Bucha Day", True),
    ("2026-06-03", "วันเฉลิมพระชนมพรรษาสมเด็จพระราชินี", "H.M. Queen Suthida's Birthday", False),
    ("2026-07-28", "วันเฉลิมพระชนมพรรษา ร.10", "H.M. King's Birthday", False),
    ("2026-07-29", "วันอาสาฬหบูชา", "Asarnha Bucha Day", False),
    ("2026-08-12", "วันแม่แห่งชาติ", "Mother's Day", False),
    ("2026-10-13", "วันคล้ายวันสวรรคต ร.9", "King Bhumibol Memorial Day", False),
    ("2026-10-23", "วันปิยมหาราช", "Chulalongkorn Day", False),
    ("2026-12-07", "วันหยุดชดเชยวันพ่อแห่งชาติ (5 ธ.ค.)", "Substitution for Father's Day (5 Dec)", True),
    ("2026-12-10", "วันรัฐธรรมนูญ", "Constitution Day", False),
    ("2026-12-31", "วันสิ้นปี", "New Year's Eve", False),
    ("2027-01-01", "วันขึ้นปีใหม่", "New Year's Day", False),
]
HOLIDAY_SET = {date.fromisoformat(h[0]) for h in HOLIDAYS}

# --------------------------------------------------------------------------- org structure
DEPARTMENTS = [  # dept_id, en, th
    ("EXE", "Executive Office", "สำนักผู้บริหาร"),
    ("ENG", "Engineering", "วิศวกรรมซอฟต์แวร์"),
    ("DATA", "Data", "ข้อมูล"),
    ("SALES", "Sales", "ฝ่ายขาย"),
    ("HR", "Human Resources", "ทรัพยากรบุคคล"),
    ("FIN", "Finance", "การเงินและบัญชี"),
    ("IT", "IT", "เทคโนโลยีสารสนเทศ"),
]
# team_id, dept, en, th, member count (excluding the lead), member positions
TEAMS = [
    ("ENG-PLT", "ENG", "Platform", "แพลตฟอร์ม", 18, ["Backend Engineer", "DevOps Engineer"]),
    ("ENG-WEB", "ENG", "Web", "เว็บ", 20, ["Frontend Engineer", "Full-stack Engineer"]),
    ("ENG-MOB", "ENG", "Mobile", "โมบาย", 16, ["Mobile Engineer"]),
    ("ENG-QA", "ENG", "Quality Assurance", "ทดสอบคุณภาพ", 19, ["QA Engineer", "Test Automation Engineer"]),
    ("DATA-DE", "DATA", "Data Engineering", "วิศวกรรมข้อมูล", 13, ["Data Engineer"]),
    ("DATA-DS", "DATA", "Data Science & Analytics", "วิทยาการข้อมูลและวิเคราะห์", 14, ["Data Scientist", "Data Analyst"]),
    ("SALES-ENT", "SALES", "Enterprise Sales", "ขายลูกค้าองค์กร", 18, ["Account Executive", "Sales Engineer"]),
    ("SALES-SMB", "SALES", "SMB Sales", "ขายลูกค้า SMB", 17, ["Sales Executive", "Customer Success Specialist"]),
    ("HR-OPS", "HR", "HR Operations", "งานบุคคล", 5, ["HR Officer", "Payroll Officer"]),
    ("HR-TAL", "HR", "Talent & Culture", "สรรหาและพัฒนาบุคลากร", 4, ["Recruiter", "L&D Specialist"]),
    ("FIN-ACC", "FIN", "Accounting", "บัญชี", 8, ["Accountant"]),
    ("FIN-FPA", "FIN", "FP&A", "วางแผนการเงิน", 5, ["Financial Analyst"]),
    ("IT-SD", "IT", "IT Service Desk", "IT Service Desk", 9, ["IT Support Specialist"]),
    ("IT-INF", "IT", "Infrastructure & Security", "โครงสร้างพื้นฐานและความปลอดภัย", 9, ["System Engineer", "Security Engineer"]),
]
DIRECTOR_TITLE = {
    "ENG": "Director of Engineering", "DATA": "Head of Data", "SALES": "Sales Director",
    "HR": "HR Director", "FIN": "Finance Director", "IT": "IT Director",
}

FIRST_NAMES = [  # (th, en)
    ("สมชาย", "Somchai"), ("สมหญิง", "Somying"), ("ปิยะ", "Piya"), ("กิตติ", "Kitti"), ("อนันต์", "Anan"),
    ("ศิริพร", "Siriporn"), ("วิภาวรรณ", "Wipawan"), ("ชนิดา", "Chanida"), ("ธีรวัฒน์", "Theerawat"),
    ("พงศกร", "Pongsakorn"), ("นภัสสร", "Napatsorn"), ("จิราพร", "Jiraporn"), ("ปวีณา", "Paweena"),
    ("อภิชาติ", "Apichat"), ("ภานุวัฒน์", "Panuwat"), ("สุนิสา", "Sunisa"), ("กัญญารัตน์", "Kanyarat"),
    ("ชัยวัฒน์", "Chaiwat"), ("ศุภชัย", "Supachai"), ("ณัฐธิดา", "Natthida"), ("ธนพล", "Thanapol"),
    ("วีรยุทธ", "Weerayut"), ("อรอุมา", "Onuma"), ("เบญจมาศ", "Benjamas"), ("ปณิตา", "Panita"),
    ("ศักดิ์ชัย", "Sakchai"), ("กฤษดา", "Kritsada"), ("อัญชลี", "Anchalee"), ("ประภาพร", "Praphaporn"),
    ("ณัฐพล", "Nattapon"), ("สิทธิชัย", "Sitthichai"), ("รัชนี", "Ratchanee"), ("ชลธิชา", "Chonticha"),
    ("วรเมธ", "Woramet"), ("ภัทรา", "Pattra"), ("อิทธิพล", "Ittipon"), ("ปรียานุช", "Preeyanut"),
    ("ธนวัฒน์", "Thanawat"), ("จักรพันธ์", "Jakkapan"), ("พิชญา", "Pitchaya"), ("ศิรินทร์", "Sirin"),
    ("เกียรติศักดิ์", "Kiattisak"), ("มณีรัตน์", "Maneerat"), ("ธิดารัตน์", "Thidarat"), ("ปกรณ์", "Pakorn"),
]
LAST_NAMES = [
    ("ใจดี", "Jaidee"), ("สุขสวัสดิ์", "Suksawat"), ("ทองคำ", "Thongkham"), ("ศรีสุข", "Srisuk"),
    ("แก้วประเสริฐ", "Kaewprasert"), ("รุ่งเรือง", "Rungruang"), ("พานิช", "Panich"), ("บุญเรือง", "Boonruang"),
    ("วงศ์สวัสดิ์", "Wongsawat"), ("จันทร์เพ็ญ", "Chanpen"), ("มีสุข", "Meesuk"), ("ประเสริฐศรี", "Prasertsri"),
    ("ชัยประสิทธิ์", "Chaiprasit"), ("สมบูรณ์", "Somboon"), ("อินทร์แก้ว", "Inkaew"), ("เพชรรัตน์", "Petcharat"),
    ("นาคสวัสดิ์", "Naksawat"), ("ศรีวงศ์", "Sriwong"), ("พรหมมา", "Promma"), ("ธนสาร", "Thanasarn"),
    ("กิจเจริญ", "Kitcharoen"), ("ทวีศักดิ์", "Thaweesak"), ("ยิ่งยง", "Yingyong"), ("บุญมี", "Boonmee"),
    ("สายทอง", "Saithong"), ("เจริญผล", "Charoenphol"), ("ศรีทอง", "Srithong"), ("วัฒนกุล", "Wattanakul"),
    ("ลิ้มสกุล", "Limsakul"), ("ตั้งจิตร", "Tangjit"), ("โชติช่วง", "Chotchuang"), ("อ่อนศรี", "Onsri"),
]
NICKNAMES = ["Bee", "Mint", "Golf", "Bank", "Pond", "Nam", "Fah", "Joy", "Beam", "Earth", "Ice", "Pim",
             "Arm", "Oat", "Pang", "Ploy", "Tae", "Gift", "Ball", "Fern", "Jay", "Muk", "Nut", "Aom"]


@dataclass
class Employee:
    employee_id: str = ""
    first_name_th: str = ""
    last_name_th: str = ""
    first_name_en: str = ""
    last_name_en: str = ""
    nickname: str = ""
    email: str = ""
    dept_id: str = ""
    team_id: str = ""
    position: str = ""
    level: str = ""
    manager_id: str = ""
    app_role: str = "employee"
    location: str = "Bangkok HQ"
    hire_date: date = REF_DATE
    probation_end_date: date = REF_DATE
    employment_status: str = "active"
    end_date: date | None = None
    persona: str = field(default="", repr=False)  # not exported to the employees table


# Demo personas: fixed data that the use cases (docs/use-cases.md) rely on.
PERSONAS = {
    "ceo": dict(first_name_th="อรรถพล", last_name_th="นาวาวงศ์", first_name_en="Attaphon", last_name_en="Navawong",
                nickname="Aek", dept_id="EXE", team_id="", position="Chief Executive Officer", level="L6",
                app_role="executive", hire_date=date(2014, 3, 1)),
    "data_lead": dict(first_name_th="ณัฐวุฒิ", last_name_th="ทองดี", first_name_en="Nattawut", last_name_en="Thongdee",
                      nickname="Nat", position="Data Engineering Lead", level="L4", app_role="team_lead",
                      hire_date=date(2019, 8, 1)),
    "employee": dict(first_name_th="พิมพ์ชนก", last_name_th="ศรีสวัสดิ์", first_name_en="Pimchanok",
                     last_name_en="Srisawat", nickname="Ploy", position="Data Engineer", level="L2",
                     hire_date=date(2023, 6, 1)),
    "new_hire": dict(first_name_th="ธนกร", last_name_th="วงศ์ใหญ่", first_name_en="Thanakorn", last_name_en="Wongyai",
                     nickname="Ton", position="Sales Executive", level="L1", hire_date=date(2026, 10, 12)),
    "it_support": dict(first_name_th="สุภาพร", last_name_th="แก้วมณี", first_name_en="Supaporn",
                       last_name_en="Kaewmanee", nickname="Fon", position="IT Support Specialist", level="L2",
                       app_role="it_support", hire_date=date(2021, 2, 15)),
    "admin": dict(first_name_th="วรวุฒิ", last_name_th="ชัยมงคล", first_name_en="Worawut", last_name_en="Chaimongkol",
                  nickname="Wut", position="Infrastructure & Security Lead", level="L4", app_role="admin",
                  hire_date=date(2018, 5, 2)),
    "hr": dict(first_name_th="กมลชนก", last_name_th="บุญมา", first_name_en="Kamonchanok", last_name_en="Boonma",
               nickname="Kwan", position="HR Officer", level="L2", app_role="hr", hire_date=date(2022, 1, 10)),
}
PERSONA_TEAM = {"data_lead": "DATA-DE", "employee": "DATA-DE", "new_hire": "SALES-SMB",
                "it_support": "IT-SD", "admin": "IT-INF", "hr": "HR-OPS"}
LEAD_PERSONA_OF_TEAM = {"DATA-DE": "data_lead", "IT-INF": "admin"}


def random_name() -> dict:
    (fth, fen), (lth, len_) = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    return dict(first_name_th=fth, last_name_th=lth, first_name_en=fen, last_name_en=len_,
                nickname=rng.choice(NICKNAMES))


def random_hire_date(min_year: int) -> date:
    start = date(min_year, 1, 1)
    days = (date(2026, 9, 30) - start).days
    # Skew towards recent hires (company grew fast)
    d = start + timedelta(days=int(days * (rng.random() ** 0.6)))
    return d


def probation_end(hire: date) -> date:
    return hire + timedelta(days=118)  # 119 days including the first day (HR-001 §2)


def build_people() -> tuple[list[Employee], dict, dict]:
    people: list[Employee] = []
    dept_head: dict[str, Employee] = {}
    team_lead: dict[str, Employee] = {}

    def make(persona: str | None = None, **kw) -> Employee:
        base = random_name() if persona is None else {}
        e = Employee(**{**base, **(PERSONAS[persona] if persona else {}), **kw})
        e.persona = persona or ""
        people.append(e)
        return e

    ceo = make("ceo")
    coo = make(dept_id="EXE", team_id="", position="Chief Operating Officer", level="L6",
               app_role="executive", hire_date=date(2015, 1, 5))
    coo.manager_id = "ceo"  # resolved to ids later
    for dept_id, _, _ in DEPARTMENTS[1:]:
        d = make(dept_id=dept_id, team_id="", position=DIRECTOR_TITLE[dept_id], level="L5",
                 app_role="manager", hire_date=random_hire_date(2014))
        d.manager_id = "ceo" if dept_id in ("ENG", "DATA", "IT") else "coo"
        dept_head[dept_id] = d

    for team_id, dept_id, _, _, n, positions in TEAMS:
        lp = LEAD_PERSONA_OF_TEAM.get(team_id)
        if lp:
            lead = make(lp, dept_id=dept_id, team_id=team_id)
        else:
            lead = make(dept_id=dept_id, team_id=team_id, position=f"{TEAMS_BY_ID[team_id][2]} Lead",
                        level="L4", app_role="team_lead", hire_date=random_hire_date(2015))
        lead.manager_id = dept_head[dept_id]
        team_lead[team_id] = lead
        personas_here = [p for p, t in PERSONA_TEAM.items() if t == team_id and p not in LEAD_PERSONA_OF_TEAM.values()]
        for p in personas_here:
            m = make(p, dept_id=dept_id, team_id=team_id)
            m.manager_id = lead
        for _ in range(n - len(personas_here)):
            lvl = rng.choices(["L1", "L2", "L3"], weights=[30, 45, 25])[0]
            pos = rng.choice(positions)
            prefix = {"L1": "Junior ", "L2": "", "L3": "Senior "}[lvl]
            role = {"HR": "hr", "IT": "it_support"}.get(dept_id, "employee")
            if team_id == "IT-INF":
                role = "employee"  # infra engineers don't work the ticket queue
            m = make(dept_id=dept_id, team_id=team_id, position=prefix + pos, level=lvl, app_role=role,
                     hire_date=random_hire_date(2016 if lvl != "L1" else 2024),
                     location="Chiang Mai Office" if rng.random() < 0.12 else "Bangkok HQ")
            m.manager_id = lead

    # IDs by hire date: earlier hire -> smaller number, like a real HRIS
    for i, e in enumerate(sorted(people, key=lambda x: (x.hire_date, x.last_name_en)), start=1):
        e.employee_id = f"NT{i:04d}"
    by_tag = {"ceo": ceo, "coo": coo}
    for e in people:
        if isinstance(e.manager_id, Employee):
            e.manager_id = e.manager_id.employee_id
        elif e.manager_id in by_tag:
            e.manager_id = by_tag[e.manager_id].employee_id

    # emails, probation, status
    seen: set[str] = set()
    for e in sorted(people, key=lambda x: x.employee_id):
        local = f"{e.first_name_en.lower()}.{e.last_name_en[0].lower()}"
        k = 2
        candidate = local
        while candidate in seen:
            candidate = f"{local}{k}"
            k += 1
        seen.add(candidate)
        e.email = f"{candidate}@nawatech.co.th"
        e.probation_end_date = probation_end(e.hire_date)
        e.employment_status = "probation" if e.probation_end_date >= REF_DATE else "active"
    # a few people have left this year (realism; they must not count as headcount)
    leavers = rng.sample([e for e in people if e.level in ("L1", "L2") and not e.persona
                          and e.employment_status == "active"], 4)
    for e in leavers:
        e.employment_status = "resigned"
        e.end_date = date(2026, rng.randint(3, 9), rng.choice([15, 30]) if rng.random() < .5 else 28)
    return people, dept_head, team_lead


TEAMS_BY_ID = {t[0]: t for t in TEAMS}

# --------------------------------------------------------------------------- leave
LEAVE_TYPES = [("VAC", "ลาพักร้อน", "Annual leave", True, True),
               ("SICK", "ลาป่วย", "Sick leave", True, True),
               ("PER", "ลากิจ", "Personal leave", True, True)]


def vac_entitlement(e: Employee) -> float:
    """HR-001 §3.1."""
    pe = e.probation_end_date
    if pe.year > YEAR:
        return 0.0
    if pe.year == YEAR:  # pro-rated in the year probation ends
        months_left = 12 - pe.month  # full months remaining after the probation month
        return round(10 * months_left / 12 * 2) / 2
    years = (date(YEAR, 1, 1) - e.hire_date).days // 365
    return 15.0 if years >= 5 else 12.0 if years >= 3 else 10.0


def random_working_day(lo: date, hi: date) -> date:
    while True:
        d = lo + timedelta(days=rng.randint(0, (hi - lo).days))
        if is_working_day(d, HOLIDAY_SET):
            return d


def build_leave(people: list[Employee]):
    balances, requests = [], []
    seq = 0

    def add_req(e: Employee, typ: str, start: date, end: date, half: str | None, status: str, reason: str):
        nonlocal seq
        seq += 1
        wd = count_working_days(start, end, HOLIDAY_SET, half)
        created = datetime.combine(start - timedelta(days=rng.randint(3, 20)), time(rng.randint(9, 17), rng.randint(0, 59)), BKK)
        requests.append(dict(request_id=f"LV-{YEAR}-{seq:05d}", employee_id=e.employee_id, leave_type=typ,
                             start_date=start, end_date=end, half_day=half or "", working_days=wd, status=status,
                             reason=reason, approver_id=e.manager_id, created_at=created.isoformat()))
        return wd

    vac_reasons = ["พักผ่อนกับครอบครัว", "ท่องเที่ยวต่างจังหวัด", "ธุระส่วนตัว", "กลับบ้านต่างจังหวัด", "พักผ่อน"]
    sick_reasons = ["ไข้หวัด", "ปวดท้อง", "ไปพบแพทย์", "ไมเกรน"]
    per_reasons = ["ติดต่อราชการ", "ทำธุรกรรมธนาคาร", "งานบวชญาติ", "ย้ายบ้าน"]

    for e in people:
        if e.employment_status == "resigned":
            continue
        ent_vac = vac_entitlement(e)
        carried = 0.0
        if e.hire_date < date(YEAR - 1, 1, 1) and ent_vac > 0:
            carried = float(rng.choice([0, 0, 0, 1, 2, 3, 5]))
        used = {"VAC": 0.0, "SICK": 0.0, "PER": 0.0}
        pending = {"VAC": 0.0, "SICK": 0.0, "PER": 0.0}
        work_start = max(e.hire_date, date(YEAR, 1, 1))

        if e.persona == "employee":
            # UC1: Ploy has 1.5 VAC days left (10 entitled, 8.5 used) and no carry-over.
            carried = 0.0
            fixed = [(date(2026, 2, 16), date(2026, 2, 17), None, "กลับบ้านต่างจังหวัด"),
                     (date(2026, 4, 16), date(2026, 4, 17), None, "ต่อวันหยุดสงกรานต์"),
                     (date(2026, 6, 2), date(2026, 6, 2), None, "พักผ่อน"),
                     (date(2026, 8, 13), date(2026, 8, 14), None, "ท่องเที่ยวต่างจังหวัด"),
                     (date(2026, 9, 25), date(2026, 9, 25), "pm", "ธุระส่วนตัว"),
                     (date(2026, 10, 9), date(2026, 10, 9), None, "พักผ่อนกับครอบครัว")]
            for s, en, h, r in fixed:
                used["VAC"] += add_req(e, "VAC", s, en, h, "approved", r)
            used["SICK"] += add_req(e, "SICK", date(2026, 7, 6), date(2026, 7, 6), None, "approved", "ไข้หวัด")
            add_req(e, "VAC", date(2026, 5, 11), date(2026, 5, 11), None, "cancelled", "พักผ่อน")
        elif e.persona == "new_hire" or e.employment_status == "probation" and e.hire_date > date(2026, 9, 1):
            pass  # brand-new: no history yet
        else:
            budget_vac = ent_vac + carried
            # past annual leave (Jan..today)
            for _ in range(rng.randint(0, 5)):
                if work_start >= REF_DATE - timedelta(days=10):
                    break
                lo = max(work_start, e.probation_end_date + timedelta(days=1))
                if not ent_vac or lo >= REF_DATE - timedelta(days=1):
                    break
                start = random_working_day(lo, REF_DATE - timedelta(days=1))
                length = rng.choice([1, 1, 1, 2, 2, 3])
                end = start
                for _ in range(length - 1):
                    nxt = end + timedelta(days=1)
                    while not is_working_day(nxt, HOLIDAY_SET):
                        nxt += timedelta(days=1)
                    end = nxt
                half = rng.choice(["am", "pm"]) if length == 1 and rng.random() < 0.2 else None
                wd = count_working_days(start, end, HOLIDAY_SET, half)
                if used["VAC"] + wd > budget_vac or end >= REF_DATE:
                    continue
                if rng.random() < 0.05:
                    add_req(e, "VAC", start, end, half, "rejected", rng.choice(vac_reasons))
                    continue
                used["VAC"] += add_req(e, "VAC", start, end, half, "approved", rng.choice(vac_reasons))
            # sick / personal
            for _ in range(rng.choices([0, 1, 2, 3], weights=[35, 35, 20, 10])[0]):
                if work_start >= REF_DATE - timedelta(days=5):
                    break
                d = random_working_day(work_start, REF_DATE - timedelta(days=1))
                used["SICK"] += add_req(e, "SICK", d, d, None, "approved", rng.choice(sick_reasons))
            if rng.random() < 0.35 and work_start < REF_DATE - timedelta(days=5):
                d = random_working_day(work_start, REF_DATE - timedelta(days=1))
                half = "am" if rng.random() < 0.4 else None
                used["PER"] += add_req(e, "PER", d, d, half, "approved", rng.choice(per_reasons))
            # upcoming annual leave (Nov–Dec), some still pending
            if ent_vac and rng.random() < 0.4:
                lo = max(REF_DATE + timedelta(days=3), e.probation_end_date + timedelta(days=1))
                s = random_working_day(lo, date(YEAR, 12, 30)) if lo < date(YEAR, 12, 30) else None
                wd = count_working_days(s, s, HOLIDAY_SET) if s else 0
                if s and used["VAC"] + pending["VAC"] + wd <= budget_vac:
                    status = rng.choice(["pending", "approved"])
                    target = pending if status == "pending" else used
                    target["VAC"] += add_req(e, "VAC", s, s, None, status, rng.choice(vac_reasons))

        ents = {"VAC": ent_vac, "SICK": 30.0, "PER": 3.0}
        for code in ("VAC", "SICK", "PER"):
            balances.append(dict(employee_id=e.employee_id, year=YEAR, leave_type=code, entitled=ents[code],
                                 carried_over=carried if code == "VAC" else 0.0,
                                 used=used[code], pending=pending[code]))
    # de-duplicate overlapping random requests per employee (keep the first)
    clean, taken = [], {}
    for r in requests:
        days = set()
        d = r["start_date"]
        while d <= r["end_date"]:
            days.add(d)
            d += timedelta(days=1)
        key = r["employee_id"]
        if r["status"] in ("approved", "pending") and days & taken.get(key, set()):
            bal = next(b for b in balances if b["employee_id"] == key and b["leave_type"] == r["leave_type"])
            bal["used" if r["status"] == "approved" else "pending"] -= r["working_days"]
            continue
        if r["status"] in ("approved", "pending"):
            taken.setdefault(key, set()).update(days)
        clean.append(r)
    return balances, clean


# --------------------------------------------------------------------------- tickets
SLA = [("P1", "ระบบหลักล่ม กระทบหลายคน", 0.25, 4), ("P2", "กระทบการทำงานของคนเดียวอย่างมาก ไม่มีทางเลี่ยง", 1, 24),
       ("P3", "ปัญหาทั่วไป มีทางเลี่ยงได้", 4, 72), ("P4", "คำขอ/สอบถาม", 8, 120)]
SLA_RESOLVE = {p: r for p, _, _, r in SLA}
SLA_RESPONSE = {p: r for p, _, r, _ in SLA}

# subcategory, team, priorities, title variants, description variants, resolution variants
IT_TEMPLATES = [
    ("hardware-notebook", "IT-SD", ["P2", "P3"],
     ["Notebook เปิดไม่ติด", "Notebook ขึ้นจอดำหลังเปิดเครื่อง", "เครื่องค้างที่โลโก้ ไม่เข้า Windows"],
     ["กดปุ่ม power แล้วไฟติดแต่จอดำ ลองชาร์จแล้วก็ไม่ขึ้น", "หลังอัปเดต Windows เมื่อวาน เครื่องค้างที่โลโก้ผู้ผลิต",
      "เครื่องดับไปตอนประชุมแล้วเปิดไม่ติดอีกเลย"],
     ["ทำ hard reset (ถอดอแดปเตอร์ กดปุ่ม power ค้าง 30 วินาที) เครื่องกลับมาใช้งานได้",
      "BIOS เสียหายหลังอัปเดต ทำ BIOS recovery ด้วย USB recovery key แล้วอัปเดต BIOS ใหม่",
      "เข้า Windows Recovery → uninstall latest quality update แล้วเครื่องบูตได้ปกติ",
      "แบตเตอรี่เสื่อม เปลี่ยนเครื่องสำรองให้ระหว่างส่งเคลมกับ vendor (ใช้เวลา 5 วันทำการ)"]),
    ("account-password", "IT-SD", ["P3"],
     ["ลืมรหัสผ่าน", "บัญชีถูกล็อก เข้าระบบไม่ได้", "รหัสผ่านหมดอายุ เปลี่ยนไม่ได้"],
     ["ใส่รหัสผิดหลายครั้งจนบัญชีถูกล็อก", "ลืมรหัสผ่านหลังกลับจากลาพักร้อน", "ระบบให้เปลี่ยนรหัสแต่ขึ้น error"],
     ["ยืนยันตัวตนผ่าน MFA แล้ว reset รหัสผ่านให้ แนะนำให้ใช้ self-service password reset ครั้งต่อไป",
      "ปลดล็อกบัญชีใน Entra ID และให้ผู้ใช้ตั้งรหัสใหม่ตามนโยบาย 14 ตัวอักษร"]),
    ("network-vpn", "IT-INF", ["P2", "P3"],
     ["ต่อ VPN ไม่ได้", "VPN หลุดบ่อยเวลา WFH", "เข้า server ภายในไม่ได้ตอนอยู่นอกออฟฟิศ"],
     ["ขึ้น error authentication failed ตอนต่อ VPN", "ต่อได้ 5 นาทีแล้วหลุด เป็นทุกวัน", "ต่อ VPN สำเร็จแต่เปิดระบบภายในไม่ได้"],
     ["certificate ของ VPN client หมดอายุ ติดตั้ง profile ใหม่ให้", "อัปเดต VPN client เป็นเวอร์ชันล่าสุด ปัญหาหายไป",
      "router ที่บ้านบล็อก UDP แนะนำให้สลับเป็นโหมด TCP 443"]),
    ("email-outlook", "IT-SD", ["P3", "P4"],
     ["Outlook ไม่ sync อีเมล", "ส่งอีเมลไปลูกค้าแล้วเด้งกลับ", "mailbox เต็ม"],
     ["Outlook ค้างที่ Updating inbox มาตั้งแต่เช้า", "อีเมลไปโดเมนลูกค้าเด้งกลับทุกฉบับ", "ได้รับแจ้งว่า mailbox ใกล้เต็ม ส่งเมลไม่ได้"],
     ["ลบ OST profile แล้วสร้างใหม่ sync ได้ปกติ", "โดเมนลูกค้าบล็อกไฟล์แนบ .zip แนะนำให้แชร์ผ่าน OneDrive แทน",
      "เปิด online archive ให้และย้ายเมลเก่ากว่า 1 ปี"]),
    ("software-request", "IT-SD", ["P4"],
     ["ขอติดตั้งโปรแกรม", "ขอ license เพิ่ม", "ขอสิทธิ์ใช้ Power BI Pro"],
     ["ต้องการใช้ DBeaver สำหรับงาน query ข้อมูล", "ขอ license JetBrains สำหรับพนักงานใหม่ในทีม", "ต้องแชร์ dashboard ให้ทีมอื่น"],
     ["ติดตั้งจาก Company Portal ให้แล้ว", "หัวหน้าทีมอนุมัติแล้ว assign license ให้เรียบร้อย"]),
    ("access-request", "IT-INF", ["P3", "P4"],
     ["ขอสิทธิ์เข้า shared drive", "ขอสิทธิ์เข้า database production (read-only)", "ขอเข้า GitHub organization"],
     ["ย้ายมาทีมใหม่ ต้องเข้าโฟลเดอร์ของทีม", "ต้อง query ข้อมูลเพื่อทำรายงาน", "พนักงานใหม่ยังไม่มีสิทธิ์ repo"],
     ["หัวหน้าทีมอนุมัติผ่าน NawaFlow แล้ว เพิ่มเข้า security group ให้",
      "ให้สิทธิ์ read-only ผ่าน role analyst_ro ตามนโยบาย IT-002 ข้อ 5"]),
    ("hardware-peripheral", "IT-SD", ["P4", "P3"],
     ["จอที่สองไม่แสดงผล", "เครื่องพิมพ์ชั้น 5 พิมพ์ไม่ออก", "ขอเมาส์/คีย์บอร์ดใหม่"],
     ["ต่อ dock แล้วจอที่สองไม่ขึ้น", "สั่งพิมพ์แล้วงานค้างในคิว", "เมาส์เสีย คลิกไม่ติด"],
     ["อัปเดต firmware ของ dock แล้วใช้งานได้", "เคลียร์ print queue และ restart spooler", "เบิกอุปกรณ์ใหม่จากสต็อก IT ให้"]),
    ("security-phishing", "IT-INF", ["P2"],
     ["ได้รับอีเมลน่าสงสัย", "เผลอคลิกลิงก์ในอีเมลแปลก ๆ"],
     ["อีเมลอ้างว่ามาจากธนาคาร ให้กรอกรหัสผ่าน", "คลิกลิงก์แล้วมีหน้า login Microsoft ปลอม แต่ยังไม่ได้กรอก"],
     ["ยืนยันว่าเป็น phishing บล็อกโดเมนผู้ส่งและลบเมลออกจากทุก mailbox",
      "บังคับเปลี่ยนรหัสผ่าน ตรวจ sign-in log ไม่พบการเข้าถึงผิดปกติ"]),
]
HR_TEMPLATES = [
    ("payroll", "HR-OPS", ["P3"], ["สอบถามรายการหักในสลิปเงินเดือน", "เงินเดือนเข้าไม่ครบ"],
     ["สลิปเดือนนี้มีรายการหักที่ไม่เข้าใจ", "ยอดเงินโอนน้อยกว่าในสลิป"],
     ["อธิบายรายการหักประกันสังคมและกองทุนสำรองเลี้ยงชีพให้แล้ว", "ตรวจสอบพบโอนตกหล่น โอนเพิ่มในรอบถัดไป"]),
    ("leave-correction", "HR-OPS", ["P4"], ["แก้ไขวันลาในระบบ", "วันลาคงเหลือไม่ถูกต้อง"],
     ["ยื่นลาผิดประเภท ต้องการเปลี่ยนจากลากิจเป็นลาพักร้อน", "ยอดลาพักร้อนคงเหลือไม่ตรงกับที่คำนวณ"],
     ["ยกเลิกใบลาเดิมและบันทึกใหม่ให้แล้ว", "ตรวจสอบแล้วยอดถูกต้อง เนื่องจากนับเฉพาะวันทำงาน"]),
    ("document-request", "HR-OPS", ["P4"], ["ขอหนังสือรับรองเงินเดือน", "ขอหนังสือรับรองการทำงาน"],
     ["ต้องใช้ยื่นกู้ธนาคาร", "ต้องใช้ยื่นวีซ่า"], ["ออกหนังสือรับรองให้แล้ว รับได้ที่ HR ชั้น 3 หรือไฟล์ PDF ทางอีเมล"]),
    ("benefits", "HR-TAL", ["P4"], ["สอบถามสิทธิ์ประกันสุขภาพกลุ่ม", "สอบถามงบอบรมประจำปี"],
     ["ต้องการทราบวงเงิน OPD", "อยากไปอบรมคอร์สภายนอก ต้องทำอย่างไร"],
     ["ส่งเอกสารสรุปสิทธิ์ประกันให้แล้ว", "แนะนำให้ยื่นคำขอผ่าน NawaFlow พร้อมใบเสนอราคา"]),
]

IT_1042 = dict(
    subcategory="hardware-notebook", priority="P2", status="waiting",
    title="Notebook เปิดไม่ติดหลังอัปเดต BIOS",
    description=("เมื่อวานเครื่องแจ้งให้อัปเดต BIOS ตอนเลิกงาน กดอัปเดตแล้วปิดฝาเครื่องไป "
                 "เช้านี้กดเปิดแล้วไฟ power ติด พัดลมหมุน แต่จอดำ ไม่มีโลโก้ขึ้น "
                 "มีงานต้องส่งลูกค้าบ่ายนี้ ไฟล์อยู่ใน OneDrive"),
    resolution="",
)


def business_time(d: date) -> datetime:
    return datetime.combine(d, time(rng.randint(8, 18), rng.randint(0, 59)), BKK)


def build_tickets(people: list[Employee], team_lead: dict[str, Employee]):
    active = [e for e in people if e.employment_status != "resigned" and e.dept_id != "EXE"]
    team_members: dict[str, list[Employee]] = {}
    for e in people:
        if e.team_id and e.employment_status != "resigned":
            team_members.setdefault(e.team_id, []).append(e)
    ref_dt = datetime.combine(REF_DATE, time(14, 0), BKK)
    raw = []
    for category, templates, n in (("it", IT_TEMPLATES, 430), ("hr", HR_TEMPLATES, 110)):
        for _ in range(n):
            sub, team, prios, titles, descs, resolutions = rng.choice(templates)
            requester = rng.choice(active)
            created = business_time(date(2026, 1, 5) + timedelta(days=rng.randint(0, (REF_DATE - date(2026, 1, 5)).days)))
            if created > ref_dt:
                created = ref_dt - timedelta(hours=rng.randint(1, 5))
            prio = rng.choice(prios)
            if category == "it" and rng.random() < 0.03:
                prio = "P1"
            raw.append(dict(category=category, subcategory=sub, assigned_team_id=team, priority=prio,
                            title=rng.choice(titles), description=rng.choice(descs),
                            resolution_choice=rng.choice(resolutions), requester=requester, created=created))
    # Make sure the Data team has some overdue open tickets for UC4
    de_members = team_members["DATA-DE"]
    for days_ago, prio in ((9, "P3"), (6, "P3"), (2, "P2"), (12, "P4")):
        sub, team, _, titles, descs, resolutions = IT_TEMPLATES[5]
        raw.append(dict(category="it", subcategory=sub, assigned_team_id=team, priority=prio,
                        title=rng.choice(titles), description=rng.choice(descs), resolution_choice="",
                        requester=rng.choice(de_members), created=business_time(REF_DATE - timedelta(days=days_ago)),
                        force_open=True))

    tickets = []
    for category, prefix, last_no in (("it", "IT", 1050), ("hr", "HR", 260)):
        rows = sorted([r for r in raw if r["category"] == category], key=lambda r: r["created"])
        first_no = last_no - len(rows) + 1
        for i, r in enumerate(rows):
            tid = f"{prefix}-{first_no + i:04d}"
            if tid == "IT-1042":
                r.update({k: v for k, v in IT_1042.items() if k != "resolution"})
                r["requester"] = next(e for e in people if e.persona == "employee")
                r["resolution_choice"] = ""
                r["assigned_team_id"] = "IT-SD"
                r["force_open"] = True
            created = r["created"]
            age_h = (ref_dt - created).total_seconds() / 3600
            resolve_h = SLA_RESOLVE[r["priority"]]
            breach = rng.random() < 0.15
            if r.get("force_open"):
                status = r.get("status") if r.get("status") in ("waiting",) else rng.choice(["open", "in_progress", "waiting"])
                resolved_at, resolution = None, ""
            elif age_h > resolve_h * 1.5 or rng.random() < 0.6 * min(1, age_h / max(resolve_h, 1)):
                dur = resolve_h * (rng.uniform(1.05, 2.5) if breach else rng.uniform(0.1, 0.95))
                resolved_at = created + timedelta(hours=dur)
                if resolved_at > ref_dt:
                    resolved_at = ref_dt - timedelta(minutes=rng.randint(5, 120))
                status = "closed" if (ref_dt - resolved_at).days > 3 else "resolved"
                resolution = r["resolution_choice"]
            else:
                status, resolved_at, resolution = rng.choice(["open", "in_progress", "waiting"]), None, ""
            first_resp = None if status == "open" else created + timedelta(hours=SLA_RESPONSE[r["priority"]] * rng.uniform(0.2, 1.3))
            if first_resp and resolved_at and first_resp > resolved_at:
                first_resp = created + (resolved_at - created) / 3
            assignee = "" if status == "open" else rng.choice(
                [m for m in team_members[r["assigned_team_id"]]
                 if m.app_role in ("it_support", "hr", "employee", "admin", "team_lead")]).employee_id
            if tid == "IT-1042":
                assignee = next(e for e in people if e.persona == "it_support").employee_id
            tickets.append(dict(
                ticket_id=tid, category=category, subcategory=r["subcategory"], title=r["title"],
                description=r["description"], requester_id=r["requester"].employee_id,
                requester_team_id=r["requester"].team_id, assigned_team_id=r["assigned_team_id"],
                assignee_id=assignee, priority=r["priority"], status=status, created_at=created.isoformat(),
                first_response_at=first_resp.isoformat() if first_resp else "",
                resolved_at=resolved_at.isoformat() if resolved_at else "",
                sla_due_at=(created + timedelta(hours=resolve_h)).isoformat(), resolution=resolution))
    return tickets


# --------------------------------------------------------------------------- compensation
SALARY_BANDS = {"L1": (22000, 35000), "L2": (35000, 60000), "L3": (60000, 95000),
                "L4": (95000, 140000), "L5": (150000, 230000), "L6": (350000, 450000)}


def build_comp(people):
    return [dict(employee_id=e.employee_id, base_salary_thb=round(rng.uniform(*SALARY_BANDS[e.level]), -2),
                 effective_date=max(e.hire_date, date(2026, 4, 1)))
            for e in people]


# --------------------------------------------------------------------------- write
def write_csv(name: str, rows: list[dict], cols: list[str]):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    people, dept_head, team_lead = build_people()
    people.sort(key=lambda e: e.employee_id)
    emp_cols = [f for f in asdict(Employee()) if f != "persona"]
    write_csv("employees.csv", [asdict(e) for e in people], emp_cols)
    write_csv("departments.csv",
              [dict(dept_id=d, name_en=en, name_th=th,
                    head_employee_id=(dept_head[d].employee_id if d in dept_head
                                      else next(e.employee_id for e in people if e.persona == "ceo")))
               for d, en, th in DEPARTMENTS], ["dept_id", "name_en", "name_th", "head_employee_id"])
    write_csv("teams.csv",
              [dict(team_id=t, dept_id=d, name_en=en, name_th=th, lead_employee_id=team_lead[t].employee_id)
               for t, d, en, th, _, _ in TEAMS], ["team_id", "dept_id", "name_en", "name_th", "lead_employee_id"])
    write_csv("holidays.csv", [dict(holiday_date=d, name_th=th, name_en=en, is_substitute=s) for d, th, en, s in HOLIDAYS],
              ["holiday_date", "name_th", "name_en", "is_substitute"])
    write_csv("leave_types.csv", [dict(code=c, name_th=th, name_en=en, paid=p, allow_half_day=h) for c, th, en, p, h in LEAVE_TYPES],
              ["code", "name_th", "name_en", "paid", "allow_half_day"])
    balances, requests = build_leave(people)
    write_csv("leave_balances.csv", balances, ["employee_id", "year", "leave_type", "entitled", "carried_over", "used", "pending"])
    write_csv("leave_requests.csv", requests, ["request_id", "employee_id", "leave_type", "start_date", "end_date", "half_day",
                                               "working_days", "status", "reason", "approver_id", "created_at"])
    write_csv("compensation.csv", build_comp(people), ["employee_id", "base_salary_thb", "effective_date"])
    write_csv("sla_policies.csv", [dict(priority=p, description=d, response_hours=a, resolve_hours=b) for p, d, a, b in SLA],
              ["priority", "description", "response_hours", "resolve_hours"])
    tickets = build_tickets(people, team_lead)
    write_csv("tickets.csv", tickets, ["ticket_id", "category", "subcategory", "title", "description", "requester_id",
                                       "requester_team_id", "assigned_team_id", "assignee_id", "priority", "status",
                                       "created_at", "first_response_at", "resolved_at", "sla_due_at", "resolution"])
    write_personas(people)
    print(f"employees={len(people)} leave_requests={len(requests)} tickets={len(tickets)} -> {OUT}")


def write_personas(people: list[Employee]):
    by_id = {e.employee_id: e for e in people}
    order = [("employee", "UC1, UC2, SEC1, SEC5"), ("new_hire", "UC3"), ("data_lead", "UC4, SEC2"),
             ("it_support", "UC5"), ("admin", "UC6"), ("hr", "HR view"), ("ceo", "Executive view")]
    lines = ["# Demo personas", "",
             "สร้างอัตโนมัติโดย `scripts/generate_seed.py` — อย่าแก้ไฟล์นี้เอง",
             f"วันที่ \"วันนี้\" ในโลกจำลอง: **{REF_DATE.isoformat()}**", "",
             "| Persona | Employee ID | ชื่อ | ตำแหน่ง | ทีม | app_role | หัวหน้า | ใช้ใน |",
             "|---|---|---|---|---|---|---|---|"]
    for p, uc in order:
        e = next(x for x in people if x.persona == p)
        mgr = by_id.get(e.manager_id)
        lines.append(f"| {p} | `{e.employee_id}` | {e.first_name_th} {e.last_name_th} ({e.nickname}) | {e.position} | "
                     f"{e.team_id or '-'} | {e.app_role} | {mgr.employee_id + ' ' + mgr.first_name_en if mgr else '-'} | {uc} |")
    lines += ["", "## ข้อเท็จจริงที่ use case อ้างอิง (ใช้ตรวจคำตอบใน eval)",
              "- **employee (Ploy)**: ลาพักร้อนปี 2026 สิทธิ์ 10 วัน ใช้ไป 8.5 วัน **เหลือ 1.5 วัน**",
              "- UC1: ลาศุกร์ 4 ธ.ค. 2026 + จันทร์ 7 ธ.ค. เป็นวันหยุดชดเชยวันพ่อ → **นับลา 1 วัน** → เหลือพอ",
              "- **new_hire (Ton)**: อยู่ระหว่างทดลองงาน → ยังไม่มีสิทธิ์ลาพักร้อน",
              "- **IT-1042**: notebook ของ Ploy เปิดไม่ติดหลังอัปเดต BIOS (P2, waiting) มอบหมายให้ Fon",
              "- **data_lead (Nat)**: ทีม DATA-DE มี ticket ค้างที่เกิน SLA (ดู `itsm.v_ticket_sla`)", ""]
    (ROOT / "docs" / "demo-personas.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

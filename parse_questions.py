#!/usr/bin/env python3
"""Витягує питання з офіційного PDF -> data/questions.json + img/*.jpg
Запуск: python3 parse_questions.py шлях/до/питання.pdf
"""
import sys, re, json, os
import pymupdf

PDF = sys.argv[1]
OUT = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(OUT, "img")
os.makedirs(IMG_DIR, exist_ok=True)

doc = pymupdf.open(PDF)

HEAD_RE = re.compile(r"^(\d{1,2}(?:\.\d)?)\.\s*(.+)$")
Q_RE = re.compile(r"^(\d{1,3})\.\s*(.*)$")
OPT_RE = re.compile(r"^(\d)\)\s*(.*)$")

def is_upper_heading(text):
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.85

def norm(s):
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ")).strip()

# ---- 1. збираємо потік елементів (рядки + картинки) по сторінках
items = []  # (page, y0, x0, kind, payload)
for pno, page in enumerate(doc):
    d = page.get_text("dict")
    raw = []
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            text = "".join(s["text"] for s in l["spans"])
            if not text.strip():
                continue
            nb = sum(len(sp["text"].strip()) for sp in l["spans"] if sp["flags"] & 16)
            nt = sum(len(sp["text"].strip()) for sp in l["spans"])
            raw.append([l["bbox"][1], l["bbox"][0], text, [nb, nt]])
    raw.sort(key=lambda r: (r[0], r[1]))
    merged = []
    for r in raw:
        # рядки з майже однаковою висотою (напр. "13." окремо від тексту) склеюємо
        if merged and abs(merged[-1][0] - r[0]) < 4:
            merged[-1][2] += " " + r[2].strip()
            merged[-1][3] = [merged[-1][3][0] + r[3][0], merged[-1][3][1] + r[3][1]]
        else:
            merged.append(r)
    for y0, x0, text, (nb, nt) in merged:
        bold = nt > 0 and nb * 2 > nt
        if re.fullmatch(r"\s*\d{1,3}\s*", text) and y0 < 70 and not bold:
            continue
        items.append((pno, y0, x0, "line", (text, bold)))
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        if (x1 - x0) < 8 or (y1 - y0) < 8:
            continue
        items.append((pno, y0, x0, "img", (x0, y0, x1, y1)))

items.sort(key=lambda t: (t[0], round(t[1] / 3), t[2]))

# ---- 2. автомат станів
sections = []     # {id,title}
questions = []
cur_sec = None
cur_q = None
expected = 1
in_heading = False
img_counter = 0

def render_clip(pno, bbox, name):
    page = doc[pno]
    r = pymupdf.Rect(bbox) & page.rect
    pix = page.get_pixmap(clip=r, dpi=150, alpha=False)
    path = os.path.join(IMG_DIR, name)
    pix.save(path, jpg_quality=85)
    return name

for pno, y0, x0, kind, payload in items:
    if kind == "line":
        text, bold = payload
        t = norm(text)
        # заголовок розділу
        m = HEAD_RE.match(t)
        if bold and m and is_upper_heading(m.group(2)) and not (cur_sec and cur_q is None and False):
            # не плутати з питанням: заголовок = ВЕЛИКІ літери
            sec_id = m.group(1)
            cur_sec = {"id": sec_id, "title": m.group(2)}
            sections.append(cur_sec)
            cur_q = None
            expected = 1
            in_heading = True
            continue
        if cur_sec is None:
            continue
        if in_heading and bold and is_upper_heading(t) and not Q_RE.match(t):
            cur_sec["title"] += " " + t   # переніс заголовка на другий рядок
            continue
        mq = Q_RE.match(t)
        if bold and mq and int(mq.group(1)) == expected and mq.group(2):
            in_heading = False
            cur_q = {"id": f"{cur_sec['id']}-{expected}", "section": cur_sec["id"],
                     "num": expected, "page": pno + 1, "text": mq.group(2),
                     "options": [], "images": [], "option_images": []}
            questions.append(cur_q)
            expected += 1
            continue
        in_heading = False
        if cur_q is None:
            continue
        mo = OPT_RE.match(t)
        if mo and int(mo.group(1)) == len(cur_q["options"]) + 1 and not bold:
            cur_q["options"].append(mo.group(2))
        elif cur_q["options"]:
            cur_q["options"][-1] += " " + t
        else:
            cur_q["text"] += " " + t
    else:
        if cur_q is None:
            continue
        img_counter += 1
        name = f"{cur_q['id'].replace('.', '_')}_{len(cur_q['images']) + len(cur_q['option_images']) + 1}.jpg"
        render_clip(pno, payload, name)
        # картинка після початку варіантів — найімовірніше картинка-варіант
        if cur_q["options"]:
            cur_q["option_images"].append({"after_option": len(cur_q["options"]), "file": name})
        else:
            cur_q["images"].append(name)

for q in questions:
    q["text"] = norm(q["text"])
    q["options"] = [norm(o) for o in q["options"]]


# ---- ручні виправлення для кількох питань, де в оригіналі «поїхала» верстка
FIXES = {
 "16.1-34": {"text": "Чи дозволено водію чорного автомобіля повернути праворуч у даному випадку?",
             "options": ["Дозволено.", "Заборонено."]},
 "37-42": {"options": ["Масивної зовнішньої кровотечі.", "Внутрішньої кровотечі."]},
 "37-58": {"text": "За наявності у постраждалого в ДТП ран у ділянці голови необхідно:",
           "options": ["Накласти марлеву пов’язку та зафіксувати її без створення надмірного тиску.",
                       "Обробити рани з використанням антисептиків та накласти тугу марлеву пов’язку.",
                       "Здійснювати тиск на рани до повної зупинки кровотечі."]},
 "45-16": {"text": "Наведений індикатор червоного кольору інформує про:",
           "options": ["Відчинені двері автомобіля.", "Блокування дверей автомобіля.", "Відчинені двері багажника."]},
}
for q in questions:
    q.update(FIXES.get(q["id"], {}))

json.dump({"sections": sections, "questions": questions},
          open(os.path.join(OUT, "data", "questions.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("розділів:", len(sections), "питань:", len(questions), "картинок:", img_counter)

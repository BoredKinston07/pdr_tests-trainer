#!/usr/bin/env python3
"""Склеює data/questions.json + data/answers.json -> data.js (його читає index.html)."""
import json, os
here = os.path.dirname(os.path.abspath(__file__))
q = json.load(open(os.path.join(here, "data/questions.json"), encoding="utf-8"))
ap = os.path.join(here, "data/answers.json")
answers = json.load(open(ap, encoding="utf-8")) if os.path.exists(ap) else {}
ids = {x["id"] for x in q["questions"]}
unknown = [k for k in answers if k not in ids]
bad = [k for k, v in answers.items() if k in ids and not (1 <= v <= len(next(x for x in q["questions"] if x["id"] == k)["options"]))]
open(os.path.join(here, "data.js"), "w", encoding="utf-8").write(
    "window.QDATA=" + json.dumps(q, ensure_ascii=False) + ";window.ANSWERS=" + json.dumps(answers) + ";")
print(f"питань: {len(ids)}, відповідей: {len(answers)}, без відповіді: {len(ids - set(answers))}")
if unknown: print("УВАГА: відповіді до неіснуючих питань:", unknown[:10])
if bad: print("УВАГА: номер відповіді поза діапазоном варіантів:", bad[:10])

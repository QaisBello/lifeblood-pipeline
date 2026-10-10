"""
Generate SYNTHETIC blood-drive form exports that mimic the real ones' structure and mess.
No real people: names are drawn from generic lists and phone numbers use the reserved 0800-000 range.

Run: python samples/generate.py   -> samples/incoming/*.csv
"""
import os, random
import pandas as pd

R = random.Random(7)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "incoming")
os.makedirs(OUT, exist_ok=True)
FIRST = ["Ada", "Tunde", "Ngozi", "Femi", "Zainab", "Kemi", "Ibrahim", "Chidi", "Amaka", "Seyi", "Hauwa", "Tobi", "Bisi", "Emeka", "Funmi", "Yusuf", "Halima", "Dayo", "Ife", "Uche"]
LAST = ["Adeyemi", "Okafor", "Bello", "Balogun", "Eze", "Lawal", "Okon", "Ajayi", "Musa", "Nwosu", "Ogun", "Salami", "Ibe", "Kalu", "Afolabi"]
INST = ["LASUCOM", "Lasucom", "LASUCOM ", "Lagos State University College of Medicine", "Lasu", "LASU", "Lagos state University", "LASU SDG Youth Club", "Unilag", "Civil servant"]
REASONS = ["Low PCV", "low pcv", "Low HB", "My PCV was low", "Low body weight", "Underweight", "Underage", "Not up to 18", "Menstruation", "I was fasting", "Malaria drugs", "Nil"]
GROUPS = ["O+", "O+", "O+", "A+", "B+", "O-", "AB+", "A-", "I don't know", "I don't know"]
people = [dict(first=R.choice(FIRST), last=R.choice(LAST), phone=f"0800000{R.randint(1000, 9999)}", gender=R.choice(["Female", "Male"])) for _ in range(230)]
for p in people: p["email"] = f"{p['first'].lower()}.{p['last'].lower()}{R.randint(1, 99)}@example.com"

def rows(n, date, people_pool, age_text=False):
    out = []
    for p in R.sample(people_pool, n):
        donated = R.random() < (0.55 if p["gender"] == "Female" else 0.9)
        age = R.choice(range(16, 30))
        out.append(dict(p=p, ts=f"{date} {R.randint(11, 16)}:{R.randint(0, 59):02d}:{R.randint(0, 59):02d}", age=f"{age} years" if age_text and R.random() < .05 else str(age),
                        donated="Yes" if donated else "No", reason="I donated" if donated else R.choice(REASONS), inst=R.choice(INST), bg=R.choice(GROUPS),
                        first_time=R.random() < .7, ret="Yes" if R.random() < .92 else "No", rem="Yes" if R.random() < .9 else "No"))
    return out

# Drive 1: Valentine's 2025 — gender question added part-way, some late/misfiled responses
d1 = rows(120, "2025-02-14", people[:150], age_text=True)
df1 = pd.DataFrame([{"Timestamp": r["ts"], "Email address": r["p"]["email"], "First Name": r["p"]["first"] + " ", "Last Name": r["p"]["last"],
                     "Age": r["age"], "Gender": r["p"]["gender"] if i > 70 else None, "Phone number ": "0" + r["p"]["phone"][1:],
                     "Institution / Organisation": r["inst"], "What's your blood group?": r["bg"], "Are you a first time donor?": "Yes" if r["first_time"] else "No",
                     "Will you like to donate at our next donation drive?": r["ret"], "Will you like to be reminded about the next donation drive?": r["rem"],
                     "Were you able to donate?": r["donated"], "If no, why? (If you donated, type I donated)": r["reason"]} for i, r in enumerate(d1)])
df1.loc[3, "Age"] = "99"
df1 = pd.concat([df1, df1.iloc[[10, 11]]])                 # two duplicate submissions
d2 = rows(80, "2025-06-27", people[60:200])
df2 = pd.DataFrame([{"Timestamp": r["ts"], "Email address ": r["p"]["email"], "First Name": r["p"]["first"], "Last Name": r["p"]["last"], "Age": r["age"], "Gender": r["p"]["gender"],
                     "Phone number ": r["p"]["phone"][1:], "Institution / Organisation e.g LASU": r["inst"], "What's your blood group?": r["bg"],
                     "What's your genotype?": R.choice(["AA", "AS", "AC", "I don't know"]), "Were you able to donate?": r["donated"],
                     "If no, why? (If you donated, type I donated)": r["reason"], "Are you a first time donor?": "Yes" if r["first_time"] else "No",
                     "Will you like to donate at our next donation drive?": r["ret"], "Will you like to be reminded about the next donation drive?": r["rem"]} for r in d2])
# three World Blood Donor Day responses landed in the Valentine's form
mis = df2.iloc[:3][[c for c in df2.columns if c in df1.columns or c == "Email address "]].rename(columns={"Email address ": "Email address"})
df1 = pd.concat([df1, mis.reindex(columns=df1.columns)])
d3 = rows(80, "2026-02-13", people[100:230])
df3 = pd.DataFrame([{"Timestamp": r["ts"], "Email address ": r["p"]["email"], "First Name": r["p"]["first"], "Last Name": r["p"]["last"], "Gender": r["p"]["gender"], "Age": r["age"],
                     "Phone Number": "0" + r["p"]["phone"][1:], "Institution ": r["inst"], "Blood Group ": r["bg"],
                     "How many times have you donated in the past?": "Never (First Time Donor)" if r["first_time"] else str(R.randint(1, 4)),
                     "Were you able to donate?": r["donated"], 'If no, why? (If you donated, write "I donated")': r["reason"],
                     "How was the experience?": R.choice(["Good", "Smooth and fast", "A bit scary", "Too stressful", "Nice", "I didn't donate"]),
                     "Would you like to donate at our next drive?": r["ret"], "Would you like to be reminded about our next drive?": r["rem"]} for r in d3])
for name, df in [("ohls_valentines_2025.csv", df1), ("ohls_world_blood_donor_day_2025.csv", df2), ("ohls_valentines_2026.csv", df3)]:
    df.to_csv(os.path.join(OUT, name), index=False); print(name, len(df))

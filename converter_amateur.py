
# converter_amateur.py — server-safe omzetting van het Colab-notebook
import io
import pandas as pd

def to_clean_str(x):
    if pd.isna(x): return ""
    return str(x).strip()

def parse_int_safe(s):
    try:
        if s is None: return None
        s = str(s).strip()
        if s == "": return None
        return int(float(s.replace(",", ".")))
    except Exception:
        return None

def load_all_sheets(filebytes: bytes) -> pd.DataFrame:
    # Lees alle tabbladen en concateneer (bewaar de sheetnaam indien gewenst)
    xls = pd.ExcelFile(io.BytesIO(filebytes))
    frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(io.BytesIO(filebytes), sheet_name=sheet, header=0)
        df["__sheet__"] = sheet
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def find_scorers_column(df: pd.DataFrame):
    # Zoek expliciete kolomnamen
    candidates = [c for c in df.columns if isinstance(c,str) and any(k in c.lower() for k in ["doelpunt","makers","scorer"])]
    if candidates:
        return df[candidates[0]].apply(to_clean_str)
    # Heuristisch: kies de eerste 'vrije tekst' kolom na index 10
    best_i, best_score = None, -1
    for i,c in enumerate(df.columns):
        if i <= 10: 
            continue
        s = df[c]
        cnt = 0
        for val in s.dropna().astype(str).values[:500]:
            try:
                float(val.replace(",", "."))
            except Exception:
                cnt += 1
        if cnt > best_score:
            best_score, best_i = cnt, i
    return (df.iloc[:, best_i] if best_i is not None else pd.Series([""]*len(df))).apply(to_clean_str)

def looks_like_division(text: str) -> bool:
    t = str(text or "").strip().lower()
    return ("divisie" in t) or ("klasse" in t)

def excel_to_txt_amateur(file_bytes: bytes) -> str:
    raw = load_all_sheets(file_bytes)
    if raw.empty:
        raise RuntimeError("Geen data gevonden in het Excelbestand.")

    def get_col(df, idx, fallback):
        return df.iloc[:, idx].apply(to_clean_str) if df.shape[1] > idx else pd.Series([""]*len(df), name=fallback)

    # Kolommen op posities (zoals in notebook): 1=thuis, 3=uit, 5=thuisdoel, 7=uitdoel, 8=rust thuis, 10=rust uit
    home = get_col(raw, 1, "Thuisclub")
    away = get_col(raw, 3, "Uitclub")
    hg   = get_col(raw, 5, "ThuisGoals")
    ag   = get_col(raw, 7, "UitGoals")
    hht  = get_col(raw, 8, "RustThuis")
    aht  = get_col(raw, 10, "RustUit")
    scor = find_scorers_column(raw)

    lines = ["<body>"]
    # Eerste divisie uit kolomkop 2 afleiden indien die op een divisie lijkt
    second_col_header = str(raw.columns[1]) if len(raw.columns) > 1 else ""
    current_div = second_col_header.upper() if looks_like_division(second_col_header) else None
    emitted_div = False

    n = len(raw)
    for i in range(n):
        home_cell = home.iloc[i]
        away_cell = away.iloc[i]
        hg_raw = hg.iloc[i]
        ag_raw = ag.iloc[i]
        hht_raw = hht.iloc[i]
        aht_raw = aht.iloc[i]
        scorers = scor.iloc[i] if i < len(scor) else ""

        # Rij die de divisie aanduidt
        if looks_like_division(home_cell):
            current_div = home_cell.upper()
            emitted_div = False
            continue

        # Sla lege rijen over
        if not (home_cell and home_cell.strip()) or not (away_cell and away_cell.strip()):
            continue

        # Print de subhead_lead voor de huidige divisie één keer
        if current_div and not emitted_div:
            lines.append(f"<subhead_lead>{current_div}</subhead_lead>")
            emitted_div = True

        # Afgelast/gestaakt?
        hg_l = str(hg_raw or "").lower()
        postponed = ("afg" in hg_l) or ("gest" in hg_l)

        hg_num = parse_int_safe(hg_raw)
        ag_num = parse_int_safe(ag_raw)
        # Geen doelpunten → lege makersregel
        if not postponed and (hg_num == 0 and ag_num == 0):
            scorers = " "

        if postponed:
            # Neem de status letterlijk op (bv. 'afgelast' of 'gestaakt')
            subhead = f"<subhead>{home_cell} - {away_cell} {hg_raw}</subhead>"
        else:
            tg = 0 if hg_num is None else int(hg_num)
            ug = 0 if ag_num is None else int(ag_num)
            rth = 0 if parse_int_safe(hht_raw) is None else int(parse_int_safe(hht_raw))
            rut = 0 if parse_int_safe(aht_raw) is None else int(parse_int_safe(aht_raw))
            # scores zonder spatie rond het streepje
            subhead = f"<subhead>{home_cell} - {away_cell} {tg}-{ug} ({rth}-{rut})</subhead>"

        lines.append(subhead)
        lines.append("<howto_facts>")
        lines.append(scorers)
        lines.append("</howto_facts>")

    lines.append("</body>")
    return "\n".join(lines)

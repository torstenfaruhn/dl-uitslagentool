# converter_regiosport.py — server-veilige versie
import io
import re
import unicodedata
import pandas as pd


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _nl_sort_key(sport: str):
    s = (sport or "").strip()
    if not s:
        return (True, "~")
    s_norm = _strip_accents(s).lower()
    if s_norm.startswith("voetbal"):
        return (False, "00_" + s_norm)
    return (False, s_norm)


def iter_sheet2_blocks(sheet2_df):
    current = {
        "sport": None,
        "evenement": None,
        "rows": []
    }
    for _, row in sheet2_df.iterrows():
        sport = (row["sport"] or "").strip()
        evenement = (row["evenement"] or "").strip()
        if sport or evenement:
            if current["sport"] or current["evenement"] or current["rows"]:
                yield current
            current = {
                "sport": sport,
                "evenement": evenement,
                "rows": []
            }
            continue

        home, away = row["thuisclub"], row["uitclub"]
        uitslag = row["uitslag"]
        stand = row["stand"]
        if not home and not away:
            continue
        m = re.match(r"^\s*(\S+)\s*[-–]\s*(\S+)\s*$", uitslag or "")
        if m:
            hs, ascr = m.group(1), m.group(2)
        else:
            hs = uitslag or ""
            ascr = ""

        current["rows"].append((home, away, hs, ascr, stand))

    if current["sport"] or current["evenement"] or current["rows"]:
        yield current


def convert_sheet1_blocks(sheet1_df):
    blocks = []
    for _, row in sheet1_df.iterrows():
        sport = (row["sport"] or "").strip()
        evenement = (row["evenement"] or "").strip()
        uitslag = (row["uitslag"] or "").strip()
        if not sport and not evenement and not uitslag:
            continue
        blocks.append({"sport": sport, "render_lines": [f"<subtitle>{uitslag}</subtitle>"]})
    return blocks


def suppress_redundant_sportheads(blocks):
    last_sport = None
    out = []
    for bl in blocks:
        sport = bl["sport"]
        if last_sport and sport and sport == last_sport:
            new_lines = []
            it = iter(bl["render_lines"])
            for line in it:
                if line.startswith("<sporthead>"):
                    next(it, None)
                    continue
                new_lines.append(line)
            bl = {**bl, "render_lines": new_lines}
        out.append(bl)
        if sport:
            last_sport = sport
    return out


def render_table_block(block):
    sport = block["sport"]
    evenement = block["evenement"]
    rows = block["rows"]

    lines = []
    if sport:
        lines.append(f"<sporthead>{sport}</sporthead>")
    if evenement:
        lines.append(f"<subhead>{evenement}</subhead>")
        lines.append("<EP>")

    lines.append("<TABLE>")
    lines.append("<TBODY>")

    n = len(rows)
    for idx, (home, away, hs, ascr, stand) in enumerate(rows):
        attrs = []
        if idx == 0:
            attrs.append('topgutter="1.5816m"')
        if idx == n - 1:
            attrs.append('bottomgutter="1.5816m"')
        attr_str = f" {' '.join(attrs)}" if attrs else ""
        lines.append(f"<TROW{attr_str}>")

        # --- Uitzonderingsregel: uitslag 'n.n.b.', 'afgelast', 'gestaakt' ---
        hs_norm = hs.strip().lower()
        ascr_norm = ascr.strip().lower()
        speciale_terms = ("n.n.b.", "afgelast", "gestaakt")
        uitzonderings_tekst = next(
            (term for term in speciale_terms if term in hs_norm or term in ascr_norm),
            None
        )

        if uitzonderings_tekst is not None:
            lines += [
                "<TFIELD>", f"{home} - {away}", "</TFIELD>",
                f"<TFIELD colspan='3' align='right'>{uitzonderings_tekst}</TFIELD>"
            ]
        else:
            lines += [
                "<TFIELD>", f"{home} - {away}", "</TFIELD>",
                "<TFIELD>", f"{hs}", "</TFIELD>",
                "<TFIELD>", "-", "</TFIELD>",
                "<TFIELD>", f"{ascr}", "</TFIELD>"
            ]

        lines.append("</TROW>")

    lines.append("</TBODY>")
    lines.append("</TABLE>")

    if block.get("stand"):
        lines.append(f"<howto_facts>{block['stand']}</howto_facts><EP>")

    return lines


def to_render_blocks(sheet1_df, sheet2_df):
    blocks_s1 = convert_sheet1_blocks(sheet1_df)
    blocks_s2 = []
    for b in iter_sheet2_blocks(sheet2_df):
        if not (b['sport'] or b['evenement'] or b['rows']):
            continue
        blocks_s2.append({"sport": b['sport'], "render_lines": render_table_block(b)})
    all_blocks = blocks_s1 + blocks_s2
    return sorted(all_blocks, key=lambda bl: _nl_sort_key(bl.get("sport")))


def convert(sheet1_bytes, sheet2_bytes):
    sheet1_df = pd.read_excel(io.BytesIO(sheet1_bytes), dtype=str).fillna("")
    sheet2_df = pd.read_excel(io.BytesIO(sheet2_bytes), dtype=str).fillna("")

    blocks = to_render_blocks(sheet1_df, sheet2_df)
    blocks = suppress_redundant_sportheads(blocks)

    lines = ["<body>"]
    for bl in blocks:
        lines += bl["render_lines"]
    lines.append("</body>")
    output_text = "\n".join(lines)

    output_text = re.sub(
        r'</howto_facts><EP>\s*<subhead>',
        r'</howto_facts><EP,1>\n<subhead>',
        output_text
    )

    return output_text

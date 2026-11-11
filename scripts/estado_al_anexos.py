"""Alagoas: todos os anexos de ST do Decreto 90.309/2023 (não só materiais de construção).

O Decreto 90.309/2023 tem um anexo por segmento (I autopeças ... XXVII nafta), cada um com uma
"Tabela Única" (o Anexo XII, alimentos, tem uma por capítulo): item, CEST, NCM/SH, descrição, acordo
interestadual, MVA original e as ajustadas para 12%, 7% e 4%. As colunas mudam de posição de um anexo
para outro, então são medidas no cabeçalho de cada tabela (CEST, NCM/SH, DESCRIÇÃO, ACORDO, MVA, 12%,
7%, 4%). As ajustadas "não constam da publicação em DOEAL": são cálculo da SEFAZ-AL.

Anexos sem CEST na tabela (XXV calçados, XXVI contribuinte não inscrito) ficam de fora: não são ST por
CEST do Conv. 142.

Saída (dados/estados/AL/):
    itens_todos_anexos.csv          um item por linha, com anexo, capítulo e segmento
    cruzamento_protocolos.csv       cada linha da matriz com destino AL x o anexo de AL
    anexos.json                     anexos lidos e contagens (vai para metadados.json)

Uso:
    python scripts/estado_al_anexos.py                 baixa da SEFAZ-AL
    python scripts/estado_al_anexos.py --pdf ARQ.pdf   usa o PDF salvo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from estado_al import API, CHAVE, baixar  # noqa: E402
from protocolos import separar_ncms  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
_ITEM = re.compile(r"^\d+(?:\.\d+)+$")
_CEST = re.compile(r"\d{2}\.\d{3}\.\d{2}")
_INICIO_CEST = re.compile(r"^\d{2}\.\d")
_PCT = re.compile(r"^(\*{0,2})(\d+(?:,\d+)?)%?$")
_TABELA = re.compile(r"TABELA [ÚU]NICA DO (?:CAP[ÍI]TULO ([IVXL]+) DO )?ANEXO ([IVXL]+)")
_TITULO_ANEXO = re.compile(r"^ANEXO ([IVXL]+)$")


def _linhas(ws: list[dict]) -> list[tuple[float, str, list[dict]]]:
    """Agrupa palavras em linhas (topo parecido) e devolve (topo, texto, palavras)."""
    saida: list[tuple[float, str, list[dict]]] = []
    for w in sorted(ws, key=lambda w: (round(w["top"]), w["x0"])):
        if saida and abs(saida[-1][0] - w["top"]) < 2.5:
            saida[-1][2].append(w)
        else:
            saida.append((w["top"], "", [w]))
    return [(t, " ".join(x["text"] for x in sorted(p, key=lambda x: x["x0"])), p) for t, _, p in saida]


def colunas_do_cabecalho(ws: list[dict], topo: float) -> dict | None:
    """Fronteiras das colunas a partir das palavras do cabeçalho em volta de 'topo' (linha do CEST)."""
    faixa = [w for w in ws if topo - 60 < w["top"] < topo + 100]
    # o cabeçalho quebra palavras em linhas ("NCM/S" + "H", "MVA-" + "ST", "INTERESTADUA" + "L")
    def x(*prefixos, depois=0.0):
        c = [w["x0"] for w in faixa if w["text"].upper().startswith(prefixos) and w["x0"] > depois]
        return min(c) if c else None
    cest, ncm, desc = x("CEST"), x("NCM"), x("DESCRI")
    if cest is None or ncm is None or desc is None:
        return None
    acordo = x("ACORDO", "INTERESTADU", depois=desc + 20)
    mva = x("MVA", "ORIGINAL", depois=(acordo or desc) + 20)
    a12, a7, a4 = (x(f, depois=(mva or desc) + 20) for f in ("12%", "7%", "4%"))
    col = {"cest": cest - 6, "ncm": ncm - 6, "descricao": desc - 6}
    if acordo:
        col["acordo"] = acordo - 6
    if mva:
        col["mva"] = mva - 6
    # ajustadas: rótulos centralizados sobre a coluna; fronteira no meio entre rótulos, sem passar de 26 pt
    # à esquerda do rótulo (os números são mais largos que "12%")
    if mva and a12:
        col["aj12"] = min((mva + a12) / 2, a12 - 26)
        if a7:
            col["aj7"] = min((a12 + a7) / 2, a7 - 26)
            if a4:
                col["aj4"] = min((a7 + a4) / 2, a4 - 26)
    rotulos = ("CEST", "NCM", "DESCRI", "ACORDO", "INTERESTADU", "MVA", "ORIGINAL", "ITE", "12%", "7%", "4%", "(OBS", "DOEAL")
    col["_fim"] = max(w["top"] for w in faixa if w["text"].upper().startswith(rotulos))
    return col


def _coluna(x0: float, col: dict) -> str:
    nome = "item"
    for k, lim in sorted(((k, v) for k, v in col.items() if not k.startswith("_")), key=lambda kv: kv[1]):
        if x0 >= lim:
            nome = k
    return nome


def ler_pdf(bruto: bytes) -> tuple[list[dict], dict]:
    import pdfplumber

    itens: list[dict] = []
    titulos: dict[str, str] = {}
    anexo = capitulo = None
    col: dict | None = None
    with pdfplumber.open(io.BytesIO(bruto)) as pdf:
        for pg in pdf.pages:
            ws = pg.extract_words()
            linhas = _linhas(ws)
            # eventos da página, de cima para baixo: título de anexo (fecha a tabela), "TABELA ÚNICA" (abre),
            # cabeçalho (mede colunas) e itens
            eventos = []
            for i, (top, txt, _) in enumerate(linhas):
                if (m := _TITULO_ANEXO.match(txt.strip())):
                    seg = " ".join(t for _, t, _ in linhas[i + 1:i + 3])
                    titulos[m.group(1)] = re.sub(r"^DAS? (?:SUBSTITUIÇÃO TRIBUTÁRIA NAS )?(?:OPERAÇÕES|VENDAS) (?:COM |DE )?", "", seg).split(" Art.")[0][:120]
                    eventos.append((top, "anexo", m.group(1)))
                elif (m := _TABELA.search(txt)):
                    eventos.append((top, "tabela", (m.group(2), m.group(1))))
                elif "CEST" in txt.split():
                    eventos.append((top, "cabecalho", None))
            # o número do item; o CEST pode vir quebrado em duas linhas ("04.00" / "1.00"), então só se exige
            # um começo de CEST na coluna do CEST, conferido quando as colunas do anexo já são conhecidas
            for w in ws:
                if _ITEM.match(w["text"]) and w["x0"] < 120:
                    eventos.append((w["top"], "item", w))
            fim_cabecalho = -1.0
            eventos.sort(key=lambda e: (e[0], {"anexo": 0, "tabela": 1, "cabecalho": 2, "item": 3}[e[1]]))
            abertos: list[dict] = []
            for top, tipo, val in eventos:
                if tipo == "anexo":
                    anexo, capitulo, col = None, None, None
                elif tipo == "tabela":
                    anexo, capitulo = val
                elif tipo == "cabecalho" and anexo:
                    nova = colunas_do_cabecalho(ws, top)
                    if nova and "cest" in nova:
                        col = nova
                        fim_cabecalho = nova["_fim"]
                elif tipo == "item" and anexo and col and val["x0"] < col["cest"] and any(
                        _INICIO_CEST.match(v["text"]) and col["cest"] <= v["x0"] < col["ncm"] and -15 < v["top"] - top < 30
                        for v in ws):
                    abertos.append({"top": top, "item": val["text"], "anexo": anexo, "capitulo": capitulo or "", "fim_cab": fim_cabecalho,
                                    "col": col, "partes": {}, "w": val})
            if not abertos:
                continue
            # palavras da página vão para o item mais perto na vertical, dentro da faixa da tabela
            ini, fim = min(a["top"] for a in abertos) - 30, max(a["top"] for a in abertos) + 40
            limites = [e[0] for e in eventos if e[1] in ("anexo", "tabela") and e[0] > min(a["top"] for a in abertos)]
            for w in ws:
                if any(w is a["w"] for a in abertos) or not (ini < w["top"] < fim):
                    continue
                if any(min(a["top"] for a in abertos) < l <= w["top"] for l in limites):
                    # depois de um novo anexo só contam itens desse anexo
                    candidatos = [a for a in abertos if a["top"] >= max(l for l in limites if l <= w["top"])]
                else:
                    candidatos = [a for a in abertos if not any(a["top"] > l for l in limites)] or abertos
                if not candidatos:
                    continue
                alvo = min(candidatos, key=lambda a: abs(a["top"] - w["top"]))
                if w["top"] <= alvo["fim_cab"] + 1:  # palavra do cabeçalho da tabela deste item
                    continue
                c = _coluna(w["x0"], alvo["col"])
                if c != "item":
                    alvo["partes"].setdefault(c, []).append(w)
            for p in abertos:
                junta = lambda c: " ".join(w["text"] for w in sorted(p["partes"].get(c, []), key=lambda w: (round(w["top"]), w["x0"])))
                def pct(c, marca=None):
                    vals = [_PCT.match(w["text"]) for w in sorted(p["partes"].get(c, []), key=lambda w: w["top"])]
                    vals = [m for m in vals if m and m.group(2)]
                    vals = [m for m in vals if (m.group(1) == marca if marca is not None else m.group(1) in ("", "*"))]
                    return vals[0].group(2).replace(",", ".") if vals else ""
                # pedaços do CEST na ordem vertical, colados: "04.00" + "1.00" = "04.001.00"
                cest = _CEST.findall("".join(w["text"] for w in sorted(p["partes"].get("cest", []), key=lambda w: (round(w["top"]), w["x0"]))))
                itens.append({
                    "anexo": p["anexo"], "capitulo": p["capitulo"], "item": p["item"],
                    "cest": cest[0] if cest else "",
                    "ncm_no_pdf": junta("ncm"), "descricao_no_pdf": junta("descricao"), "acordo": junta("acordo"),
                    "mva_original": pct("mva"), "mva_texto": junta("mva") if not pct("mva") else "", "mva_original_sem_frete_na_base": pct("mva", "**"),
                    "mva_ajustada_12": pct("aj12"), "mva_ajustada_7": pct("aj7"), "mva_ajustada_4": pct("aj4"),
                })
    return itens, titulos


def protocolos_do_acordo(acordo: str) -> set[str]:
    """'Protocolos ICMS 41/08 e 97/10' -> {'41/08', '97/10'}.

    A célula do acordo quebra em várias linhas e às vezes só o número cai na faixa do item ("188/09"),
    então vale qualquer número/ano da célula; "Sem Acordo" não tem número."""
    return {f"{int(a)}/{b[-2:]}" for a, b in re.findall(r"(?<![\d/])(\d{1,3})\s*/\s*(\d{4}|\d{2})(?![\d/])", acordo)}


def completar(itens: list[dict], titulos: dict, conv142_csv: Path) -> list[dict]:
    with conv142_csv.open(encoding="utf-8") as f:
        conv = {r["cest"]: r for r in csv.DictReader(f)}
    for i in itens:
        c = conv.get(i["cest"])
        i["segmento"] = titulos.get(i["anexo"], "")
        i["ncm_sh"], i["ncms"], i["descricao"] = ((c["ncm_sh"], c["ncms"], c["descricao"]) if c
                                                  else (i["ncm_no_pdf"], ";".join(separar_ncms(i["ncm_no_pdf"])), ""))
        i["protocolos_citados"] = ";".join(sorted(protocolos_do_acordo(i["acordo"])))
    return itens


def cruzar(itens: list[dict], matriz_csv: Path) -> list[dict]:
    """Cada linha da matriz origem->destino com destino AL x os anexos de AL, pelo CEST provável."""
    por_cest: dict[str, list[dict]] = {}
    for i in itens:
        por_cest.setdefault(i["cest"], []).append(i)
    saida = []
    with matriz_csv.open(encoding="utf-8") as f:
        vistos = set()
        for r in csv.DictReader(f):
            if r["destino"] != "AL" or (r["protocolo"], r["item"]) in vistos:
                continue
            vistos.add((r["protocolo"], r["item"]))
            num = re.search(r"(\d+/\d+)", r["protocolo"]).group(1)
            cests = [c for c in r["cests_provaveis"].split(";") if c]
            al = [i for c in cests for i in por_cest.get(c, [])]
            mvas = sorted({m for i in al for m in (i["mva_original"], i["mva_original_sem_frete_na_base"])} - {""})
            if not cests:
                sit = "sem_cest"
            elif not al:
                sit = "cest_fora_dos_anexos_de_al"
            elif not any(num in i["protocolos_citados"].split(";") for i in al):
                sit = "al_nao_cita_o_protocolo"
            elif r["mva_original"] and mvas and not any(abs(float(m) - float(r["mva_original"])) < 0.005 for m in mvas):
                sit = "mva_diferente"
            else:
                sit = "coerente"
            saida.append({"protocolo": r["protocolo"], "item_protocolo": r["item"], "ncm_sh": r["ncm_sh"],
                          "descricao": r["descricao"][:100], "cests_provaveis": ";".join(cests),
                          "mva_protocolo": r["mva_original"], "mva_al": ";".join(mvas),
                          "anexos_al": ";".join(sorted({i["anexo"] for i in al})),
                          "acordo_al": " | ".join(sorted({i["acordo"] for i in al})), "situacao": sit})
    return saida


def gravar(itens, cruz, titulos, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    campos = ["anexo", "capitulo", "segmento", "item", "cest", "ncm_sh", "ncms", "descricao", "acordo", "protocolos_citados",
              "mva_original", "mva_original_sem_frete_na_base", "mva_texto", "mva_ajustada_12", "mva_ajustada_7", "mva_ajustada_4",
              "ncm_no_pdf", "descricao_no_pdf"]
    with (destino / "itens_todos_anexos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(itens)
    if cruz:
        with (destino / "cruzamento_protocolos.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cruz[0].keys()))
            w.writeheader()
            w.writerows(cruz)
    por_anexo = {}
    for i in itens:
        por_anexo.setdefault(i["anexo"], 0)
        por_anexo[i["anexo"]] += 1
    meta = dict(meta)
    meta["anexos"] = {a: {"segmento": titulos.get(a, ""), "itens": n} for a, n in por_anexo.items()}
    meta["contagens"] = {"itens": len(itens), "com_cest": sum(bool(i["cest"]) for i in itens),
                         "com_mva_original": sum(bool(i["mva_original"]) for i in itens),
                         "cruzamento": {s: sum(c["situacao"] == s for c in cruz) for s in
                                        ("coerente", "mva_diferente", "al_nao_cita_o_protocolo", "cest_fora_dos_anexos_de_al", "sem_cest")}}
    (destino / "anexos.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "AL")
    a = ap.parse_args(argv)
    bruto, nome = (a.pdf.read_bytes(), a.pdf.name) if a.pdf else baixar()
    itens, titulos = ler_pdf(bruto)
    itens = completar(itens, titulos, RAIZ / "dados" / "conv142" / "itens_vigentes.csv")
    cruz = cruzar(itens, RAIZ / "dados" / "protocolos" / "matriz_origem_destino.csv")
    meta = {"fonte": "SEFAZ-AL, Decreto 90.309/2023 consolidado, todos os anexos de ST", "url": f"{API}?acess=1&key={CHAVE}",
            "nome_do_arquivo": nome, "sha256": hashlib.sha256(bruto).hexdigest(),
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": date.today().isoformat()}
    meta = gravar(itens, cruz, titulos, a.saida, meta)
    print(json.dumps({"anexos": meta["anexos"], **meta["contagens"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

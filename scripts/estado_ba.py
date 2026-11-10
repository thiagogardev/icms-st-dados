"""Bahia: bens sujeitos à ST e MVA, do Anexo 1 do RICMS-BA (Decreto 13.780/2012).

A SEFAZ-BA publica o Anexo 1 em um PDF por período ("Redação vigente ano 2026, a
partir de 01/01/2026"). Cada linha tem: item, CEST, NCM/SH, descrição, acordo
interestadual com os estados signatários ("Prot. ICMS 104/09 - BA e SP"), MVA
ajustada por alíquota interestadual e MVA original das operações internas.

As células são centralizadas na vertical: o acordo e as MVAs ajustadas começam
acima da linha do item. A página é dividida pelos pontos médios entre as linhas
de itens consecutivos, e cada palavra vai para o item cuja faixa a contém.

Notas no meio da tabela marcam a história de um item:
    Nota: A redação atual do "item 8.62", foi dada pelo Decreto nº 24.540/26, ..., efeitos a partir de 01/01/26.
    Redação anterior, efeitos até 31/12/25:
    <linhas antigas do item>

Uso:
    python scripts/estado_ba.py               baixa da SEFAZ-BA e grava em dados/estados/BA
    python scripts/estado_ba.py --pdf ARQ.pdf usa um PDF salvo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conv142 import USER_AGENT  # noqa: E402
from protocolos import separar_ncms  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://mbusca.sefaz.ba.gov.br/DITRI/normas_complementares/decretos/decreto_2012_13780_ricms_anexo_1_vigente_2026.pdf"

_CEST = re.compile(r"^\d{2}\.\d{3}\.\d{2}$")
_ITEM = re.compile(r"^\d{1,2}\.\d{1,3}(?:\.\d{1,2})?$")
_PCT = re.compile(r"(\d{1,3}(?:,\d{1,2})?)%")
_DATA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")

# Colunas na página em paisagem (842 pt de largura), medidas no PDF de 2026.
COL_NCM, COL_DESC, COL_ACORDO, COL_AJUSTADA, COL_ORIGINAL = 160, 240, 440, 605, 720


def _sem_aspas(t: str) -> str:
    """As redações anteriores vêm entre aspas tipográficas: “8.33 ... 45%”."""
    return t.strip("“”\"'")


def _datas(s: str) -> list[date]:
    out = []
    for d, m, a in _DATA.findall(s):
        try:
            out.append(date(int(a) + (2000 if len(a) == 2 else 0), int(m), int(d)))
        except ValueError:
            pass
    return out


def _juntar(ws: list[dict]) -> str:
    ws = sorted(ws, key=lambda w: (round(w["top"] / 3), w["x0"]))
    return re.sub(r"\s+", " ", " ".join(w["text"] for w in ws)).strip()


def ler(caminho: Path, ref: date) -> dict:
    import pdfplumber

    itens: list[dict] = []
    notas_soltas: list[str] = []
    vig_arquivo: date | None = None
    nota_atual: dict | None = None      # "A redação atual do item X ... efeitos a partir de D"
    bloco_ant: dict | None = None       # "Redação anterior, efeitos até D:"
    with pdfplumber.open(caminho) as pdf:
        for npag, pg in enumerate(pdf.pages, 1):
            ws = pg.extract_words(keep_blank_chars=False)
            if vig_arquivo is None:
                m = re.search(r"A PARTIR DE (\d{2}/\d{2}/\d{4})", " ".join(w["text"] for w in ws))
                if m:
                    vig_arquivo = _datas(m.group(1))[0]
            # linhas de texto da página
            grupos: dict[int, list[dict]] = {}
            for w in ws:
                w["text"] = _sem_aspas(w["text"])
            ws = [w for w in ws if w["text"]]
            for w in sorted(ws, key=lambda w: w["top"]):
                chave_g = next((k for k in grupos if abs(k - w["top"]) <= 2.5), None)
                grupos.setdefault(chave_g if chave_g is not None else round(w["top"], 1), []).append(w)
            # notas: linha que começa na margem esquerda e não é número de item; linhas seguidas
            # formam uma nota só ("Nota: A redação atual do “item 1.1”, ... / efeitos a partir de 01/01/26.")
            notas: list[tuple[float, float, str]] = []      # (topo, base, texto)
            atual_nota: list | None = None
            ids_nota: set[int] = set()
            for top in sorted(grupos):
                g = sorted(grupos[top], key=lambda w: w["x0"])
                if g[0]["x0"] < 100 and not _ITEM.match(g[0]["text"]) and not any(_CEST.match(w["text"]) for w in g):
                    ids_nota.update(id(w) for w in g)
                    if atual_nota is not None and top - atual_nota[1] < 16:
                        atual_nota[1], atual_nota[2] = top, atual_nota[2] + " " + _juntar(g)
                    else:
                        atual_nota = [top, top, _juntar(g)]
                        notas.append(atual_nota)
                else:
                    atual_nota = None
            ws_tabela = [w for w in ws if id(w) not in ids_nota]
            ceps = [w for w in ws_tabela if _CEST.match(w["text"]) and COL_NCM - 70 <= w["x0"] < COL_NCM]
            eventos = [("item", c["top"], c) for c in ceps] + [("nota", n[0], n) for n in notas]
            eventos.sort(key=lambda e: e[1])
            for k, ev in enumerate(eventos):
                if ev[0] == "nota":
                    txt = ev[2][2]
                    ds = _datas(txt)
                    alvo = {a.rstrip(".") for a in re.findall(r"item ([\d.]+\d)", txt)}
                    if re.match(r"Nota: A reda", txt):
                        nota_atual = {"itens": alvo, "ini": ds[-1] if ds else None, "texto": txt}
                        bloco_ant = None
                    elif re.match(r"Reda[çc][ãa]o (anterior|original)", txt):
                        if "efeitos" in txt.lower():
                            bloco_ant = {"fim": ds[-1] if ds else None, "ini": ds[-2] if len(ds) >= 2 and "de " in txt else None,
                                         "texto": txt, "itens": (alvo or (set(nota_atual["itens"]) if nota_atual else set()))}
                    else:
                        notas_soltas.append(txt[:200])
                    continue
                _, top, cest = ev
                # faixa da linha: até o meio do caminho para o item vizinho, sem atravessar notas
                ant = eventos[k - 1] if k > 0 else None
                prox = eventos[k + 1] if k + 1 < len(eventos) else None
                if ant is None:
                    ini_faixa = top - 20
                elif ant[0] == "nota":
                    ini_faixa = ant[2][1] + 4
                else:
                    ini_faixa = (ant[1] + top) / 2
                if prox is None:
                    fim_faixa = top + 30
                elif prox[0] == "nota":
                    fim_faixa = prox[1] - 1
                else:
                    fim_faixa = (top + prox[1]) / 2
                faixa = [w for w in ws_tabela if ini_faixa <= w["top"] < fim_faixa]
                cand = sorted((w for w in faixa if w["x0"] < cest["x0"] and _ITEM.match(w["text"])),
                              key=lambda w: abs(w["top"] - top))
                item = cand[0]["text"] if cand else ""
                ncm = _juntar([w for w in faixa if COL_NCM <= w["x0"] < COL_DESC and re.match(r"^[\d.,]+$", w["text"])])
                desc = _juntar([w for w in faixa if COL_DESC <= w["x0"] < COL_ACORDO])
                acordo = _juntar([w for w in faixa if COL_ACORDO <= w["x0"] < COL_AJUSTADA])
                ajust = _juntar([w for w in faixa if COL_AJUSTADA <= w["x0"] < COL_ORIGINAL])
                orig_ws = [w for w in faixa if w["x0"] >= COL_ORIGINAL]
                orig = _juntar(orig_ws)
                perto = sorted((w for w in orig_ws if _PCT.search(w["text"])), key=lambda w: abs(w["top"] - top))
                mva = _PCT.search(perto[0]["text"]).group(1).replace(",", ".") if perto else ""
                chave = item.rstrip(".")
                if bloco_ant is not None and (chave in bloco_ant["itens"] or not bloco_ant["itens"]):
                    origem, ini, fim, nota = "anterior_no_texto", bloco_ant["ini"], bloco_ant["fim"], bloco_ant["texto"]
                else:
                    bloco_ant = None
                    origem, fim = "vigente_no_texto", None
                    if nota_atual is not None and chave in nota_atual["itens"]:
                        ini, nota = nota_atual["ini"], nota_atual["texto"]
                    else:
                        ini, nota = vig_arquivo, ""
                itens.append({"item": item, "cest": cest["text"], "ncm_sh": ncm, "ncms": ";".join(separar_ncms(ncm)),
                              "descricao": desc, "acordo": acordo, "mva_ajustada_texto": ajust,
                              "mva_original": mva, "mva_original_texto": orig, "vigencia_inicio": ini,
                              "vigencia_fim": fim, "origem": origem, "nota": nota, "pagina": npag,
                              # "Revogado" na própria linha; "Nota 2: revogada tacitamente" é de outra nota
                              "revogado": bool(re.search(r"\bRevogad[oa]\b(?!\s+t[áa]citamente)",
                                                         f"{desc} {acordo} {orig}"))})
    for r in itens:
        if r["revogado"] and r["origem"] == "vigente_no_texto":
            r["situacao"] = "revogada"
        elif r["vigencia_inicio"] and r["vigencia_inicio"] > ref:
            r["situacao"] = "futura"
        elif r["vigencia_fim"] and r["vigencia_fim"] < ref:
            r["situacao"] = "anterior"
        else:
            r["situacao"] = "vigente"
    return {"itens": itens, "vigencia_arquivo": vig_arquivo, "notas_soltas": notas_soltas}


def ufs_do_acordo_com_sp(acordo: str) -> bool:
    """O acordo lista algum protocolo/convênio em que SP é signatário ('Prot. ICMS 104/09 - BA e SP')?"""
    return bool(re.search(r"\bSP\b", acordo))


def cruzar_com_protocolo(itens: list[dict], matriz: list[dict]) -> list[dict]:
    """Construção (CEST 10.x): o que a BA diz sobre SP x a matriz do Prot. ICMS 104/09 (SP -> BA)."""
    linhas_ba = [m for m in matriz if m["destino"] == "BA"]
    saida = []
    for i in itens:
        if i["situacao"] != "vigente" or not i["cest"].startswith("10."):
            continue
        ncms = [n for n in i["ncms"].split(";") if n]
        achados = [m for m in linhas_ba if any(n.startswith(c) or c.startswith(n)
                                               for n in ncms for c in m["ncms"].split(";") if c)]
        ba_sp = ufs_do_acordo_com_sp(i["acordo"])
        saida.append({"item": i["item"], "cest": i["cest"], "ncm_sh": i["ncm_sh"], "descricao": i["descricao"][:100],
                      "acordo_ba": i["acordo"][:120], "ba_cita_sp": "sim" if ba_sp else "nao",
                      "no_prot_104_09": "sim" if achados else "nao",
                      "itens_do_protocolo": ";".join(m["item"] for m in achados),
                      "situacao": "coerente" if ba_sp == bool(achados) else
                      ("ba_sim_protocolo_nao" if ba_sp else "protocolo_sim_ba_nao")})
    return saida


def gravar(dados: dict, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    campos = ["item", "cest", "ncm_sh", "ncms", "descricao", "acordo", "mva_original", "mva_original_texto",
              "mva_ajustada_texto", "vigencia_inicio", "vigencia_fim", "situacao", "origem", "nota", "pagina"]

    def linha(r):
        d = {k: r.get(k, "") for k in campos}
        for k in ("vigencia_inicio", "vigencia_fim"):
            d[k] = r[k].isoformat() if r[k] else ""
        return d

    for nome, filtro in (("itens_historico.csv", lambda r: True), ("itens_vigentes.csv", lambda r: r["situacao"] == "vigente")):
        with (destino / nome).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(linha(r) for r in dados["itens"] if filtro(r))
    matriz_arq = RAIZ / "dados" / "protocolos" / "matriz_sp_destino.csv"
    cruz = []
    if matriz_arq.exists():
        with matriz_arq.open(encoding="utf-8") as f:
            cruz = cruzar_com_protocolo(dados["itens"], list(csv.DictReader(f)))
        with (destino / "cruzamento_prot_104_09.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cruz[0].keys()))
            w.writeheader()
            w.writerows(cruz)
    vig = [r for r in dados["itens"] if r["situacao"] == "vigente"]
    meta = dict(meta)
    meta["vigencia_do_arquivo"] = dados["vigencia_arquivo"].isoformat() if dados["vigencia_arquivo"] else None
    meta["contagens"] = {
        "redacoes": len(dados["itens"]), "vigentes": len(vig),
        "vigentes_com_mva_original": sum(bool(r["mva_original"]) for r in vig),
        "cruzamento_prot_104_09": {s: sum(c["situacao"] == s for c in cruz)
                                   for s in ("coerente", "ba_sim_protocolo_nao", "protocolo_sim_ba_nao")},
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--ref", type=date.fromisoformat, default=date.today())
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "BA")
    a = ap.parse_args(argv)
    caminho = a.pdf
    if caminho is None:
        import tempfile

        import httpx
        r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=180, follow_redirects=True)
        r.raise_for_status()
        caminho = Path(tempfile.gettempdir()) / "ricms_ba_anexo_1.pdf"
        caminho.write_bytes(r.content)
    bruto = caminho.read_bytes()
    dados = ler(caminho, a.ref)
    meta = {"fonte": "SEFAZ-BA, RICMS-BA (Decreto 13.780/2012), Anexo 1, redação vigente", "url": URL,
            "sha256": hashlib.sha256(bruto).hexdigest(),
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": a.ref.isoformat()}
    meta = gravar(dados, a.saida, meta)
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

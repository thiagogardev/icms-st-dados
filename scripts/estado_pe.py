"""Pernambuco: MVA de materiais de construção (Decreto 44.650/2017, Anexo 37-C).

Desde 01/02/2025 (Decreto 58.019/2025) o PE lista os materiais de construção sujeitos à ST no
Anexo 37-C do Decreto 44.650/2017 por número de item do Anexo XI do Convênio ICMS 142/2018 (há
também um item referido ao Anexo II), com uma MVA única para a operação interna ou de importação.
A tabela não repete CEST, NCM nem descrição: este script junta cada item ao conjunto do Conv. 142
(dados/conv142/itens_vigentes.csv) para ter esses campos.

A SEFAZ-PE publica o decreto consolidado num HTML de cerca de 14 MB; o anexo começa na âncora
"anexo37c".

Uso:
    python scripts/estado_pe.py                 baixa da SEFAZ-PE e grava em dados/estados/PE
    python scripts/estado_pe.py --html ARQ.htm  usa a página salva
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conv142 import USER_AGENT  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://www.sefaz.pe.gov.br/Legislacao/Tributaria/Documents/legislacao/44650/texto/Dec44650_2017.htm"
ANCORA = re.compile(r"name=[\"']?anexo37c[\"' >]", re.I)


def limpar(s: str) -> str:
    return unicodedata.normalize("NFC", re.sub(r"[\s\xa0]+", " ", s or "")).strip()


def recortar_anexo(pagina: str) -> tuple[str, str]:
    """Devolve (texto do cabeçalho do anexo, HTML da primeira tabela depois da âncora)."""
    m = ANCORA.search(pagina)
    if not m:
        raise ValueError("âncora anexo37c não encontrada")
    ini = pagina.find("<table", m.start())
    fim = pagina.find("</table>", ini)
    import html as _html

    trecho = pagina[pagina.find(">", m.start()) + 1:ini]
    cabecalho = limpar(_html.unescape(re.sub(r"<[^>]+>", " ", trecho)))
    return cabecalho, pagina[ini:fim + len("</table>")]


def ler_tabela(tabela_html: str) -> list[dict]:
    from lxml import html

    tb = html.fromstring(tabela_html)
    anexo = "XI"
    linhas = []
    for tr in tb.xpath(".//tr"):
        cel = [limpar(td.text_content()) for td in tr.xpath("./td")]
        if not cel:
            continue
        m = re.search(r"ANEXO ([IVXL]+) DO CONV", cel[0], re.I)
        if m:
            anexo = m.group(1).upper()
            continue
        if len(cel) >= 2 and re.fullmatch(r"\d+\.\d+", cel[0]):
            mva = re.match(r"(\d+(?:,\d+)?)", cel[1])
            linhas.append({"anexo_conv142": anexo, "item_conv142": cel[0],
                           "mva": mva.group(1).replace(",", ".") if mva else "", "mva_texto": cel[1]})
    return linhas


def juntar_conv142(linhas: list[dict], conv142_csv: Path) -> list[dict]:
    with conv142_csv.open(encoding="utf-8") as f:
        conv = {(r["anexo"], r["item"]): r for r in csv.DictReader(f)}
    saida = []
    for l in linhas:
        c = conv.get((l["anexo_conv142"], l["item_conv142"]))
        saida.append({**l, "cest": c["cest"] if c else "", "ncm_sh": c["ncm_sh"] if c else "",
                      "ncms": c["ncms"] if c else "", "descricao": c["descricao"] if c else "",
                      "situacao_conv142": "vigente" if c else "item_nao_vigente_no_conv142"})
    return saida


def cruzar_com_protocolo(itens: list[dict], matriz_csv: Path) -> list[dict]:
    """Prot. ICMS 128/10 (SP-PE): a MVA do protocolo x a do Anexo 37-C, pelo CEST provável."""
    with matriz_csv.open(encoding="utf-8") as f:
        linhas = [r for r in csv.DictReader(f) if r["destino"] == "PE" and r["protocolo"] == "Prot. ICMS 128/10"]
    por_cest = {i["cest"]: i for i in itens if i["cest"]}
    saida = []
    for r in linhas:
        cests = [c for c in r["cests_provaveis"].split(";") if c]
        mvas_pe = sorted({por_cest[c]["mva"] for c in cests if c in por_cest})
        mva_prot = str(float(r["mva_original"])) if r["mva_original"] else ""
        if not cests:
            situacao = "sem_cest"
        elif not mvas_pe:
            situacao = "cest_fora_do_anexo_37c"
        elif not mva_prot:
            situacao = "protocolo_sem_mva"
        elif any(abs(float(m) - float(mva_prot)) < 0.005 for m in mvas_pe):
            situacao = "mva_igual" if len(mvas_pe) == 1 else "mva_igual_em_um_dos_cests"
        else:
            situacao = "mva_diferente"
        saida.append({"item_protocolo": r["item"], "ncm_sh": r["ncm_sh"], "descricao": r["descricao"][:100],
                      "cests_provaveis": ";".join(cests), "mva_protocolo": r["mva_original"],
                      "mva_pe": ";".join(mvas_pe), "situacao": situacao})
    return saida


def gravar(itens, cruz, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, linhas in (("itens.csv", itens), ("cruzamento_prot_128_10.csv", cruz)):
        if linhas:
            with (destino / nome).open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
                w.writeheader()
                w.writerows(linhas)
    meta = dict(meta)
    meta["contagens"] = {
        "itens": len(itens), "itens_com_cest": sum(bool(i["cest"]) for i in itens),
        "cruzamento": {s: sum(c["situacao"] == s for c in cruz) for s in
                       ("mva_igual", "mva_igual_em_um_dos_cests", "mva_diferente", "protocolo_sem_mva",
                        "cest_fora_do_anexo_37c", "sem_cest")},
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "PE")
    a = ap.parse_args(argv)
    if a.html:
        bruto = a.html.read_bytes()
    else:
        import httpx

        r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True)
        r.raise_for_status()
        bruto = r.content
    pagina = bruto.decode("cp1252", errors="replace")  # a página declara windows-1252
    cabecalho, tabela = recortar_anexo(pagina)
    itens = juntar_conv142(ler_tabela(tabela), RAIZ / "dados" / "conv142" / "itens_vigentes.csv")
    matriz = RAIZ / "dados" / "protocolos" / "matriz_sp_destino.csv"
    cruz = cruzar_com_protocolo(itens, matriz) if matriz.exists() else []
    meta = {"fonte": "SEFAZ-PE, Decreto 44.650/2017 consolidado, Anexo 37-C", "url": URL,
            "cabecalho_do_anexo": cabecalho[:600],
            "sha256": hashlib.sha256(bruto).hexdigest(),
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": date.today().isoformat()}
    meta = gravar(itens, cruz, a.saida, meta)
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

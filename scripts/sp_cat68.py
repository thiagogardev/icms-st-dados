"""São Paulo: ST interna pela Portaria CAT 68/2019 (mercadorias sujeitas à ST, por anexo de segmento).

A Portaria CAT 68/2019 lista, em 22 anexos, as mercadorias sujeitas à ST com retenção antecipada em SP
(item, CEST, NCM/SH e descrição), cada anexo ligado a um artigo do RICMS/SP. Desde 2026 a maior parte
foi revogada por Portarias SRE (64/25, 94/25, 09/26, 20/26, 34/26, 52/26), com data de vigência própria;
a revogação aparece numa nota logo abaixo do título do anexo. Itens também têm notas de revogação e
de redação.

A SEFAZ-SP publica o texto consolidado em legislacao.fazenda.sp.gov.br (página SharePoint). Este script
lê a página, monta uma linha por item com a situação do anexo e do item na data de referência e grava:

    dados/sp/cat68_anexos.csv   anexo, segmento, artigo do RICMS, situação, revogado desde, norma
    dados/sp/cat68_itens.csv    um item por linha: anexo, item, CEST, NCM, descrição, situação e notas
    dados/sp/metadados.json     fonte, sha256, contagens

Uso:
    python scripts/sp_cat68.py                 baixa da SEFAZ-SP
    python scripts/sp_cat68.py --html ARQ.htm  usa a página salva
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
from protocolos import separar_ncms  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-CAT-68-de-2019.aspx"
_MESES = {m: i for i, m in enumerate(["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                                      "setembro", "outubro", "novembro", "dezembro"], 1)}
_ANEXO = re.compile(r"^ANEXO ([IVXL]+)\b(.*)$")
_ITEM = re.compile(r"^(\d+(?:\.\d+)?)\s*(?:\((.*)\))?\s*$")
_NORMA = re.compile(r"Portaria (?:CAT|S\s*R\s*E)\s*-?\s*\d+/\d{2,4}", re.I)
_VIGOR = re.compile(r"(?:em vigor|a partir|efeitos? (?:desde|a partir de))\s*(?:em|de|a partir de)?\s*(\d{1,2})[º°o]?\s+de\s+([a-zç]+)\s+de\s+(\d{4})", re.I)
_DOE = re.compile(r"DOE\s+(\d{2})[-/](\d{2})[-/](\d{4})")


def texto_da_pagina(pagina: str) -> str:
    """Uma linha por parágrafo e por linha de tabela (células separadas por " | ")."""
    from lxml import html

    doc = html.fromstring(pagina)
    achados = doc.xpath("//*[@id='DeltaPlaceHolderMain']")
    el = achados[0] if achados else doc
    for lixo in el.xpath(".//script|.//style|.//noscript"):
        lixo.drop_tree()
    for no in el.iter():
        if isinstance(no.tag, str):
            if no.text:
                no.text = no.text.replace("\r", " ").replace("\n", " ")
            if no.tail and no is not el:
                no.tail = no.tail.replace("\r", " ").replace("\n", " ")
    for celula in el.xpath(".//td|.//th"):
        celula.tail = " | " + (celula.tail or "")
        for interno in celula.xpath(".//p|.//div|.//br|.//li"):
            interno.tail = " " + (interno.tail or "")
    for bloco in el.xpath(".//p|.//div|.//tr|.//li|.//br|.//h1|.//h2|.//h3|.//h4|.//table"):
        if not bloco.xpath("ancestor::td|ancestor::th"):
            bloco.tail = "\n" + (bloco.tail or "")
    linhas = []
    for l in re.sub(r"(\s*\|\s*)+\n", "\n", el.text_content()).splitlines():
        l = re.sub(r"[ \t\xa0​]+", " ", unicodedata.normalize("NFC", l)).strip(" |")
        if l:
            linhas.append(l)
    return "\n".join(linhas)


def data_da_nota(nota: str) -> str:
    """Data de vigência citada na nota ("em vigor em 1º de outubro de 2026", "a partir de 1º de janeiro de
    2026", "efeitos desde 1º de março de 2022"); sem ela, a data do DOE."""
    m = _VIGOR.search(nota)
    if m and m.group(2).lower() in _MESES:
        return date(int(m.group(3)), _MESES[m.group(2).lower()], int(m.group(1))).isoformat()
    m = _DOE.search(nota)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat() if m else ""


def _situacao(revogado: bool, desde: str, ref: date) -> str:
    if not revogado:
        return "vigente"
    return "revogacao_futura" if desde and desde > ref.isoformat() else "revogado"


def ler(texto: str, ref: date) -> tuple[list[dict], list[dict]]:
    anexos: dict[str, dict] = {}
    itens: list[dict] = []
    atual = None
    vistos: set[tuple[str, str]] = set()
    for linha in texto.splitlines():
        m = _ANEXO.match(linha)
        if m:
            nome = m.group(1)
            if nome not in anexos:
                anexos[nome] = {"anexo": nome, "segmento": "", "artigo_ricms": "", "nota": "", "_cab": True}
            atual = anexos[nome]
            atual["_cab"] = True
            if m.group(2).strip():
                atual["nota"] += " " + m.group(2).strip(" ()")
            continue
        if atual is None:
            continue
        if atual["_cab"]:
            if linha.startswith("ITEM |"):
                atual["_cab"] = False
            elif re.match(r"^\(artigo", linha, re.I):
                atual["artigo_ricms"] = linha.strip("()").replace("artigo ", "art. ").replace(" do RICMS", "")
            elif linha.startswith("(") and re.search(r"[Rr]evogad|vigor", linha):
                atual["nota"] += " " + linha.strip("()")
            elif not atual["segmento"] and linha.isupper() and not linha.startswith("NOTA"):
                atual["segmento"] = linha
            continue
        cel = [c.strip() for c in linha.split(" | ")]
        mi = _ITEM.match(cel[0]) if cel else None
        if not mi or len(cel) < 3 or not re.match(r"^\d{2}\.\d{3}\.\d{2}", cel[1]):
            continue
        nota = mi.group(2) or ""
        rev = bool(re.search(r"revogad", nota, re.I))
        desde = data_da_nota(nota) if nota else ""
        ncm = cel[2] if len(cel) > 3 else ""
        # A página repete o número do item para as redações anteriores, logo abaixo da atual.
        chave = (atual["anexo"], mi.group(1))
        redacao = "anterior" if chave in vistos else "atual"
        vistos.add(chave)
        itens.append({"anexo": atual["anexo"], "item": mi.group(1), "redacao": redacao, "cest": cel[1][:9], "ncm_sh": ncm,
                      "ncms": ";".join(separar_ncms(ncm)), "descricao": cel[-1] if len(cel) > 3 else "",
                      "item_situacao": _situacao(rev, desde, ref), "item_revogado_desde": desde if rev else "",
                      "item_nota": nota})
    saida_anexos = []
    for a in anexos.values():
        nota = a["nota"].strip()
        rev = bool(re.search(r"revogad", nota, re.I))
        desde = data_da_nota(nota) if rev else ""
        norma = _NORMA.search(nota)
        saida_anexos.append({"anexo": a["anexo"], "segmento": a["segmento"], "artigo_ricms": a["artigo_ricms"],
                             "situacao": _situacao(rev, desde, ref), "revogado_desde": desde,
                             "revogado_por": re.sub(r"\s+", "", norma.group(0)).replace("Portaria", "Portaria ") if (rev and norma) else "",
                             "nota": nota})
    por_anexo = {a["anexo"]: a for a in saida_anexos}
    for i in itens:
        a = por_anexo[i["anexo"]]
        i["segmento"] = a["segmento"]
        i["anexo_situacao"], i["anexo_revogado_desde"] = a["situacao"], a["revogado_desde"]
        if i["redacao"] == "anterior":
            i["situacao"] = "redacao_anterior"
            continue
        i["situacao"] = "vigente" if a["situacao"] == "vigente" and i["item_situacao"] == "vigente" else (
            "revogacao_futura" if "revogacao_futura" in (a["situacao"], i["item_situacao"]) and "revogado" not in (a["situacao"], i["item_situacao"]) else "revogado")
    return saida_anexos, itens


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "sp")
    a = ap.parse_args(argv)
    if a.html:
        bruto = a.html.read_bytes()
    else:
        import httpx

        r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True)
        r.raise_for_status()
        bruto = r.content
    ref = date.today()
    anexos, itens = ler(texto_da_pagina(bruto.decode("utf-8", errors="replace")), ref)
    if len(anexos) < 20 or len(itens) < 300:
        raise SystemExit(f"leitura curta: {len(anexos)} anexos, {len(itens)} itens; a página mudou?")
    a.saida.mkdir(parents=True, exist_ok=True)
    with (a.saida / "cat68_anexos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(anexos[0].keys()))
        w.writeheader()
        w.writerows(anexos)
    campos = ["anexo", "segmento", "item", "redacao", "cest", "ncm_sh", "ncms", "descricao", "situacao", "anexo_situacao",
              "anexo_revogado_desde", "item_situacao", "item_revogado_desde", "item_nota"]
    with (a.saida / "cat68_itens.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(itens)
    meta = {"fonte": "SEFAZ-SP, Portaria CAT 68/2019 consolidada (legislacao.fazenda.sp.gov.br)", "url": URL,
            "sha256": hashlib.sha256(bruto).hexdigest(), "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": ref.isoformat(),
            "contagens": {"anexos": len(anexos), "anexos_vigentes": sum(x["situacao"] == "vigente" for x in anexos),
                          "anexos_com_revogacao_futura": sum(x["situacao"] == "revogacao_futura" for x in anexos),
                          "itens": len(itens), "itens_vigentes": sum(i["situacao"] == "vigente" for i in itens),
                          "itens_com_revogacao_futura": sum(i["situacao"] == "revogacao_futura" for i in itens)}}
    (a.saida / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    for x in anexos:
        print(x["anexo"], x["situacao"], x["revogado_desde"], x["revogado_por"], x["segmento"][:50], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

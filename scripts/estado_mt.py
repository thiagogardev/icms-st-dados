"""Mato Grosso: bens sujeitos à ST (RICMS/MT, Apêndice do Anexo X) e MVA (Portaria 195/2019-SEFAZ).

No MT a regra está em dois atos:

- o Apêndice do Anexo X do RICMS (Decreto 2.212/2014) lista, por segmento, item, CEST, NCM e
  descrição dos bens sujeitos à ST. Não traz MVA. A SEFAZ publica o texto consolidado numa
  página do livro do RICMS (SubIndice.aspx?ID=214);
- a Portaria 195/2019-SEFAZ divulga as MVAs. O Anexo Único tem uma tabela por segmento com a
  MVA de cada item, que vale para quem usa o crédito outorgado do Anexo XVII ou é do Simples
  (art. 1º, § 1º). Para os demais contribuintes o art. 2º-B fixa uma MVA única por segmento,
  por faixa de CEST (materiais de construção: 74,75%). O art. 3º manda aplicar a MVA de qualquer
  origem, sem MVA ajustada. O texto fica na base Lotus Notes da SEFAZ (legislacaotribut.nsf).

Na tabela da portaria as redações anteriores aparecem como linhas extras logo abaixo da vigente:
marcadas com "(Redação original)"/"(Redação anterior ...)", ou só repetindo o número do item.
Item com MVA "excluído" ou "..." está fora.

Uso:
    python scripts/estado_mt.py                                  baixa as duas fontes e grava em dados/estados/MT
    python scripts/estado_mt.py --apendice A.html --portaria P.html  usa páginas salvas
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
URL_APENDICE = "https://www.sefaz.mt.gov.br/legislacao/SubIndice.aspx?ID=214"
URL_PORTARIA = ("https://app1.sefaz.mt.gov.br/Sistema/legislacao/legislacaotribut.nsf/"
                "5edf9c5193c58088032567580038916b/4c7283a0b4318486042584c4004436c1?OpenDocument")
_CEST = re.compile(r"^\d{2}\.\d{3}\.\d{2}$")
_ITEM = re.compile(r"^(\d+(?:\.\d+)?)\.?$")
_ANTERIOR = re.compile(r"\(\s*Reda[çc][ãa]o (?:original|anterior)", re.I)
_ALTERACAO = re.compile(r"\((?:Nova reda[çc][ãa]o|Reda[çc][ãa]o dada|Acrescentad|Revogad|Inclu[íi]d)[^()]*\)", re.I)


def limpar(s: str) -> str:
    return unicodedata.normalize("NFC", re.sub(r"[\s​\xa0]+", " ", s or "")).strip()


def texto(el) -> str:
    return limpar(el.text_content())


def texto_sep(el) -> str:
    """Como texto(), mas separa por espaço os pedaços da célula (NCMs em linhas diferentes)."""
    return limpar(" ".join(el.itertext()))


def _pct(s: str) -> str:
    m = re.match(r"\s*(\d+(?:,\d+)?)\s*%", s or "")
    return m.group(1).replace(",", ".") if m else ""


def _item(s: str) -> str:
    m = _ITEM.match(s.strip())
    return m.group(1) if m else ""


def segmento_do_cest(cest: str) -> str:
    return cest[:2] if _CEST.match(cest or "") else ""


def ler_apendice(pagina: str) -> list[dict]:
    """Linhas das tabelas II em diante do Apêndice do Anexo X (a tabela I é a lista de segmentos)."""
    from lxml import html

    doc = html.fromstring(pagina)
    segmentos: dict[str, str] = {}
    itens: list[dict] = []
    for tabela in doc.xpath('//table[contains(@class,"ms-rteTable")]'):
        for tr in tabela.xpath(".//tr"):
            tds = tr.xpath("./td")
            cel = [texto(td) for td in tds]
            if len(cel) >= 3:
                cel[2] = texto_sep(tds[2])
            if len(cel) == 3 and re.fullmatch(r"\d{2}", cel[2]):
                segmentos[cel[2]] = cel[1]
                continue
            if len(cel) < 4 or not _item(cel[0]):
                continue
            item, cest, ncm, desc = cel[0], cel[1], cel[2], " ".join(cel[3:])
            junto = " ".join(cel)
            revogado = not _CEST.match(cest) and bool(re.search(r"revogad", junto, re.I))
            if not _CEST.match(cest) and not revogado:
                continue
            itens.append({
                "segmento": segmento_do_cest(cest), "item": _item(item), "cest": cest if _CEST.match(cest) else "",
                "ncm_sh": "" if revogado else ncm, "ncms": "" if revogado else ";".join(separar_ncms(ncm)),
                "descricao": "" if revogado else re.sub(r"\s*\((?:cf\.|Nova reda|Reda[çc][ãa]o dada|Acrescentad).*$", "", desc).strip(),
                "situacao": "revogado" if revogado else "vigente",
                "alteracoes": " ".join(re.findall(r"\((?:cf\.|Nova reda|Reda[çc][ãa]o dada|Acrescentad|Revogad)[^()]*\)", junto, re.I))
                              or (junto if revogado else ""),
            })
    # item revogado não tem CEST: herda o segmento da linha anterior
    for i, it in enumerate(itens):
        if not it["segmento"] and i:
            it["segmento"] = itens[i - 1]["segmento"]
        it["nome_segmento"] = segmentos.get(it["segmento"], "")
    return itens


def ler_portaria_tabelas(pagina: str) -> list[dict]:
    """Linhas do Anexo Único da Portaria 195/2019, cada uma marcada como vigente ou anterior."""
    from lxml import html

    doc = html.fromstring(pagina)
    saida: list[dict] = []
    for tabela in doc.xpath("//table"):
        ultimo_item = None
        cest_atual = ""
        for tr in tabela.xpath(".//tr"):
            tds = tr.xpath("./td")
            cel = [texto(td) for td in tds]
            if len(cel) == 5:
                cel[2] = texto_sep(tds[2])
            if len(cel) != 5 or not _item(cel[0]):
                continue
            item, cest, ncm, desc, mva = cel
            if _CEST.match(cest):
                cest_atual = cest
            elif cest not in ("", "...", "....") or _item(item) != ultimo_item:
                cest_atual = cest if _CEST.match(cest) else ""
            repetido = _item(item) == ultimo_item and saida and saida[-1]["cest"] in ("", cest_atual)
            if _ANTERIOR.search(desc) or repetido:
                redacao = "anterior"
            else:
                redacao = "vigente"
            excluido = bool(re.search(r"exclu[íi]d|revogad", mva, re.I)) or (mva.strip(". ") == "" and redacao == "vigente")
            saida.append({
                "segmento": segmento_do_cest(cest_atual), "item": _item(item), "cest": cest_atual,
                "ncm_sh": ncm if ncm.strip(". ") else "", "ncms": ";".join(separar_ncms(ncm)) if ncm.strip(". ") else "",
                "descricao": re.sub(r"\s*\((?:Nova reda|Reda[çc][ãa]o|Acrescentad).*$", "", desc).strip(" ."),
                "mva": "" if excluido else _pct(mva), "redacao": redacao,
                "situacao": "excluido" if excluido and redacao == "vigente" else "",
                "alteracoes": " ".join(_ALTERACAO.findall(desc + " " + mva)) or
                              (re.search(r"\(\s*Reda[çc][ãa]o[^()]*\)", desc).group(0) if _ANTERIOR.search(desc) else ""),
            })
            ultimo_item = _item(item)
    for r in saida:  # linha "..." do item excluído: o segmento vem dos vizinhos
        if not r["segmento"]:
            r["segmento"] = next((x["segmento"] for x in reversed(saida[:saida.index(r)]) if x["segmento"]), "")
    return saida


_FAIXA = re.compile(r"^([IVXL]+(?:-[A-Z])?) - (.+?) - CEST (.+?): (\d+,\d+)%")


def ler_portaria_art_2b(pagina: str) -> list[dict]:
    """MVA por segmento para quem não usa o crédito outorgado (art. 2º-B). Só a redação vigente."""
    from lxml import html

    corpo = html.fromstring(pagina).text_content()
    corpo = unicodedata.normalize("NFC", corpo.replace("\xa0", " "))
    ini = corpo.find("Art. 2°-B")
    fim = corpo.find("Art. 2°-C", ini)
    if ini < 0:
        return []
    saida, vistos = [], set()
    anterior = False
    for linha in corpo[ini:fim].splitlines():
        linha = limpar(linha)
        if re.match(r"Reda[çc][ãa]o (?:original|anterior)", linha):
            anterior = True
            continue
        m = _FAIXA.match(linha)
        if not m:
            continue
        inciso, nome, faixa, mva = m.groups()
        if anterior or inciso in vistos:
            anterior = False
            continue
        vistos.add(inciso)
        anterior = False
        cests = re.findall(r"\d{2}\.\d{3}\.\d{2}", faixa)
        faixas = []
        partes = re.split(r"\s+e\s+", faixa)
        for p in partes:
            cs = re.findall(r"\d{2}\.\d{3}\.\d{2}", p)
            if len(cs) == 2:
                faixas.append(f"{cs[0]}-{cs[1]}")
            elif len(cs) == 1:
                faixas.append(f"{cs[0]}-{cs[0]}")
        saida.append({"inciso": inciso, "segmento": cests[0][:2] if cests else "", "nome": nome, "faixas_cest": ";".join(faixas),
                      "mva": mva.replace(",", ".")})
    return saida


def mva_sem_credito_outorgado(cest: str, faixas: list[dict]) -> str:
    for f in faixas:
        for intervalo in f["faixas_cest"].split(";"):
            a, _, b = intervalo.partition("-")
            if a <= cest <= b:
                return f["mva"]
    return ""


def juntar(itens: list[dict], tabelas: list[dict], faixas: list[dict]) -> list[dict]:
    """Itens vigentes do Apêndice com a MVA da portaria (tabela) e a do art. 2º-B."""
    mva = {}
    for r in tabelas:
        if r["redacao"] == "vigente" and r["cest"]:
            mva.setdefault((r["cest"], r["item"]), r)
            mva.setdefault((r["cest"], ""), r)
    saida = []
    for i in itens:
        if i["situacao"] != "vigente":
            continue
        p = mva.get((i["cest"], i["item"])) or mva.get((i["cest"], ""))
        saida.append({
            "segmento": i["segmento"], "nome_segmento": i["nome_segmento"], "item": i["item"], "cest": i["cest"],
            "ncm_sh": i["ncm_sh"], "ncms": i["ncms"], "descricao": i["descricao"],
            "mva_credito_outorgado_ou_simples": p["mva"] if p else "",
            "mva_demais_contribuintes": mva_sem_credito_outorgado(i["cest"], faixas),
            "situacao_na_portaria": ("sem_linha" if not p else p["situacao"] or "com_mva"),
        })
    return saida


def cruzar_com_protocolo(vigentes: list[dict], matriz_csv: Path) -> list[dict]:
    """Prot. ICMS 11/08 (SP-MT, construção) x Apêndice do Anexo X do MT, pelo CEST provável."""
    with matriz_csv.open(encoding="utf-8") as f:
        linhas = [r for r in csv.DictReader(f) if r["destino"] == "MT" and r["protocolo"] == "Prot. ICMS 11/08"]
    no_mt = {i["cest"]: i for i in vigentes}
    saida, usados = [], set()
    for r in linhas:
        cests = [c for c in r["cests_provaveis"].split(";") if c]
        achados = [c for c in cests if c in no_mt]
        usados.update(achados)
        mvas = sorted({no_mt[c]["mva_credito_outorgado_ou_simples"] for c in achados} - {""})
        saida.append({
            "item_protocolo": r["item"], "ncm_sh": r["ncm_sh"], "descricao": r["descricao"][:100],
            "cests_provaveis": ";".join(cests), "cests_no_mt": ";".join(achados),
            "mva_tabela_mt": ";".join(mvas),
            "situacao": "sem_cest" if not cests else ("coerente" if achados else "cest_fora_do_apendice_mt"),
        })
    for c, i in sorted(no_mt.items()):
        if c.startswith("10.") and c not in usados:
            saida.append({"item_protocolo": "", "ncm_sh": i["ncm_sh"], "descricao": i["descricao"][:100],
                          "cests_provaveis": "", "cests_no_mt": c, "mva_tabela_mt": i["mva_credito_outorgado_ou_simples"],
                          "situacao": "so_no_mt"})
    return saida


def _gravar_csv(caminho: Path, linhas: list[dict]) -> None:
    if not linhas:
        return
    with caminho.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)


def gravar(itens, tabelas, faixas, vigentes, cruz, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    _gravar_csv(destino / "itens.csv", itens)
    _gravar_csv(destino / "mva_portaria_195.csv", tabelas)
    _gravar_csv(destino / "mva_demais_contribuintes.csv", faixas)
    _gravar_csv(destino / "itens_vigentes.csv", vigentes)
    _gravar_csv(destino / "cruzamento_prot_11_08.csv", cruz)
    meta = dict(meta)
    meta["contagens"] = {
        "segmentos": len({i["segmento"] for i in itens}), "itens": len(itens),
        "itens_vigentes": len(vigentes), "itens_revogados": sum(i["situacao"] == "revogado" for i in itens),
        "linhas_portaria": len(tabelas), "redacoes_anteriores_portaria": sum(t["redacao"] == "anterior" for t in tabelas),
        "vigentes_com_mva_da_tabela": sum(bool(v["mva_credito_outorgado_ou_simples"]) for v in vigentes),
        "faixas_art_2b": len(faixas),
        "cruzamento": {s: sum(c["situacao"] == s for c in cruz) for s in
                       ("coerente", "cest_fora_do_apendice_mt", "sem_cest", "so_no_mt")},
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def baixar(url: str) -> bytes:
    import httpx

    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True)
    r.raise_for_status()
    return r.content


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apendice", type=Path)
    ap.add_argument("--portaria", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "MT")
    a = ap.parse_args(argv)
    b_ap = a.apendice.read_bytes() if a.apendice else baixar(URL_APENDICE)
    b_po = a.portaria.read_bytes() if a.portaria else baixar(URL_PORTARIA)
    pag_ap = b_ap.decode("utf-8", errors="replace")
    pag_po = b_po.decode("iso-8859-1")  # a base Notes declara iso-8859-1
    itens = ler_apendice(pag_ap)
    tabelas = ler_portaria_tabelas(pag_po)
    faixas = ler_portaria_art_2b(pag_po)
    vigentes = juntar(itens, tabelas, faixas)
    matriz = RAIZ / "dados" / "protocolos" / "matriz_sp_destino.csv"
    cruz = cruzar_com_protocolo(vigentes, matriz) if matriz.exists() else []
    consolidada = re.search(r"Consolidada at[ée] a Portaria ([\d/]+)", limpar(pag_po))
    meta = {"fonte": "SEFAZ-MT: RICMS/MT (Decreto 2.212/2014), Apêndice do Anexo X; Portaria 195/2019-SEFAZ",
            "urls": {"apendice": URL_APENDICE, "portaria_195_2019": URL_PORTARIA},
            "sha256": {"apendice": hashlib.sha256(b_ap).hexdigest(), "portaria_195_2019": hashlib.sha256(b_po).hexdigest()},
            "portaria_consolidada_ate": consolidada.group(1) if consolidada else "",
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": date.today().isoformat()}
    meta = gravar(itens, tabelas, faixas, vigentes, cruz, a.saida, meta)
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

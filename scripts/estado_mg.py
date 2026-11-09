"""Minas Gerais: bens sujeitos à ST e MVA, do RICMS/2023, Anexo VII, Parte 2.

A Parte 2 tem 28 capítulos (um por segmento) com a mesma tabela: item, CEST,
NBM/SH, descrição, âmbito de aplicação e MVA. O âmbito diz para quais estados a
ST vale nas entradas em MG ("10.1 Interno e nas seguintes unidades da
Federação: ... São Paulo (Protocolo ICMS 32/09)"), e o item pode excluir
estados: "10.1 (Exceção: SP)".

A fonte é a versão consolidada sem histórico ("seco") publicada pela SEF/MG;
ela traz só a redação vigente. As mudanças passam a ser datadas pelo monitor
(cada versão nova da página vira um evento).

Também cruza o resultado com a matriz de protocolos SP -> MG (dados/protocolos):
o item que MG diz valer para SP deveria estar no Prot. ICMS 32/09, e vice-versa.

Uso:
    python scripts/estado_mg.py                 baixa da SEF/MG e grava em dados/estados/MG
    python scripts/estado_mg.py --html-dir DIR  usa HTMLs salvos (anexovii2023_4.html etc.)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conv142 import USER_AGENT  # noqa: E402
from protocolos import consultar, separar_ncms  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
BASE_URL = "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms_2023_seco/"
PAGINAS = ["anexovii2023_4.html", "anexovii2023_5.html", "anexovii2023_6.html"]

UFS = {
    "Acre": "AC", "Alagoas": "AL", "Amapá": "AP", "Amazonas": "AM", "Bahia": "BA", "Ceará": "CE",
    "Distrito Federal": "DF", "Espírito Santo": "ES", "Goiás": "GO", "Maranhão": "MA", "Mato Grosso do Sul": "MS",
    "Mato Grosso": "MT", "Pará": "PA", "Paraíba": "PB", "Paraná": "PR", "Pernambuco": "PE", "Piauí": "PI",
    "Rio de Janeiro": "RJ", "Rio Grande do Norte": "RN", "Rio Grande do Sul": "RS", "Rondônia": "RO",
    "Roraima": "RR", "Santa Catarina": "SC", "São Paulo": "SP", "Sergipe": "SE", "Tocantins": "TO",
}


def texto(el) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", el.text_content()).strip())


def decodificar(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252")


def ler_ambito(txt: str) -> tuple[str, dict[str, str], bool] | None:
    """'10.1 Interno e nas seguintes unidades da Federação: Amapá (Protocolo ICMS 196/09), ...'
    -> ('10.1', {'AP': 'Prot. ICMS 196/09', ...}, aplica_st)."""
    # A primeira linha vem com o rótulo: "Âmbito de Aplicação da Substituição Tributária: 10.1 Interno e ..."
    m = re.search(r"(\d+\.\d+)\s+((?:Interno|Interestadual|Inaplicabilidade).*)", txt, re.I)
    if not m:
        return None
    codigo, resto = m.group(1), m.group(2)
    if re.match(r"(?i)inaplicabilidade", resto):
        return codigo, {}, False
    ufs: dict[str, str] = {}
    # nomes mais longos primeiro: "Mato Grosso do Sul" antes de "Mato Grosso"
    for nome in sorted(UFS, key=len, reverse=True):
        for mm in re.finditer(re.escape(nome) + r"\s*(?:\(([^)]*)\))?", resto):
            antes = resto[max(0, mm.start() - 1):mm.start()]
            if antes and antes.isalpha():
                continue
            if UFS[nome] in ufs:
                continue
            prot = mm.group(1) or ""
            pm = re.search(r"(Protocolo|Convênio)\s+ICMS\s+(\d+/\d+)", prot)
            ufs[UFS[nome]] = f"{'Prot.' if pm and pm.group(1) == 'Protocolo' else 'Conv.'} ICMS {pm.group(2)}" if pm else ""
        resto_sem = resto
    return codigo, ufs, True


def ufs_do_item(ambito_item: str, ambitos: dict) -> tuple[list[str], bool, bool]:
    """'10.1 (Exceção: AP, BA e RS) 10.2' -> (UFs com ST nas entradas em MG, interno, alguma_regra_desconhecida)."""
    ufs: set[str] = set()
    interno = False
    desconhecido = False
    for m in re.finditer(r"(\d+\.\d+)\*?\s*(?:\(\s*Exce[çc][ãa]o:\s*([^)]*)\))?", ambito_item):
        cod, exc = m.group(1), m.group(2)
        if cod not in ambitos:
            desconhecido = True
            continue
        ufs_cod, aplica = ambitos[cod]
        if not aplica:
            continue
        interno = True
        excluir = set(re.findall(r"\b[A-Z]{2}\b", exc or ""))
        ufs.update(set(ufs_cod) - excluir)
    return sorted(ufs), interno, desconhecido


def ler_pagina(pagina: str) -> tuple[list[dict], list[dict]]:
    from lxml import html

    raiz = html.fromstring(pagina)
    itens, ambitos_saida = [], []
    for tabela in raiz.xpath("//table"):
        linhas = tabela.xpath(".//tr")
        if not linhas:
            continue
        titulo = texto(linhas[0])
        cap = re.match(r"(\d+)\.\s*(.+)", titulo)
        if not cap:
            continue
        capitulo, segmento = cap.group(1), cap.group(2)
        ambitos: dict[str, tuple[list[str], bool]] = {}
        col = None
        for tr in linhas[1:]:
            cel = [texto(td) for td in tr.xpath("./td|./th")]
            nao_vazias = [c for c in cel if c]
            if not nao_vazias:
                continue
            if col is None:
                if any(c.upper() == "ITEM" for c in cel):
                    up = [c.upper() for c in cel]
                    col = {"item": up.index("ITEM"), "cest": up.index("CEST"),
                           "ncm": next(i for i, c in enumerate(up) if "NBM" in c or "NCM" in c),
                           "desc": next(i for i, c in enumerate(up) if c.startswith("DESCRI")),
                           "ambito": next(i for i, c in enumerate(up) if "MBITO" in c),
                           "mva": next((i for i, c in enumerate(up) if c.startswith("MVA")), None)}
                    continue
                for c in nao_vazias:
                    a = ler_ambito(c)
                    if a and a[0].startswith(capitulo + "."):
                        ambitos[a[0]] = (sorted(a[1]), a[2])
                        ambitos_saida.append({"capitulo": capitulo, "ambito": a[0],
                                              "aplica_st": "sim" if a[2] else "nao",
                                              "ufs": ";".join(sorted(a[1])),
                                              "normas": ";".join(f"{u}:{p}" for u, p in sorted(a[1].items()) if p),
                                              "texto": c})
                continue
            if len(cel) <= col["ambito"] or not re.match(r"\d+\.\d+", cel[col["item"]]):
                continue
            ufs, interno, desconhecido = ufs_do_item(cel[col["ambito"]], ambitos)
            mva_txt = cel[col["mva"]] if col["mva"] is not None and len(cel) > col["mva"] else ""
            mm = re.fullmatch(r"\s*(\d+(?:,\d+)?)\s*%?\s*", mva_txt)
            itens.append({
                "capitulo": capitulo, "segmento": segmento, "item": cel[col["item"]], "cest": cel[col["cest"]],
                "ncm_sh": cel[col["ncm"]], "ncms": ";".join(separar_ncms(cel[col["ncm"]])),
                "descricao": cel[col["desc"]], "ambito": cel[col["ambito"]],
                "st_interna": "sim" if interno else "nao", "ufs_origem_com_st": ";".join(ufs),
                "mva_original": mm.group(1).replace(",", ".") if mm else "", "mva_texto": mva_txt,
                "ambito_desconhecido": "sim" if desconhecido else "",
            })
    return itens, ambitos_saida


def _palavras(s: str) -> set[str]:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z]{5,}", s)} - {"outros", "outras", "mesmo", "exceto", "inclusive", "construcao"}


def _sobrepoe(a: str, b: str) -> bool:
    return a.startswith(b) or b.startswith(a)


def cruzar_com_protocolo(itens: list[dict], matriz: list[dict]) -> list[dict]:
    """Item a item do capítulo 10: o que MG diz para SP x o que a matriz SP -> MG diz.

    O protocolo não traz CEST, então o casamento é por NCM (códigos que se sobrepõem:
    '3925.90' cobre '3925.90.00'). Quando as descrições não têm palavra em comum,
    o casamento pode ser só de NCM e fica marcado para conferência."""
    linhas_mg = [m for m in matriz if m["destino"] == "MG"]
    saida = []
    for i in itens:
        if i["capitulo"] != "10":
            continue
        mg_sp = "SP" in i["ufs_origem_com_st"].split(";")
        ncms = [n for n in i["ncms"].split(";") if n]
        achados = [m for m in linhas_mg
                   if any(_sobrepoe(n, c) for n in ncms for c in m["ncms"].split(";") if c)]
        parecidos = [m for m in achados if _palavras(m["descricao"]) & _palavras(i["descricao"])]
        no_prot = bool(achados)
        if mg_sp == no_prot:
            situacao = "coerente"
        elif no_prot:
            situacao = "protocolo_sim_mg_nao" if parecidos else "so_ncm_coincide"
        else:
            situacao = "mg_sim_protocolo_nao"
        saida.append({"cest": i["cest"], "item": i["item"], "ncm_sh": i["ncm_sh"], "descricao": i["descricao"][:120],
                      "ambito_mg": i["ambito"], "mg_aplica_para_sp": "sim" if mg_sp else "nao",
                      "no_prot_32_09": "sim" if no_prot else "nao",
                      "itens_do_protocolo": ";".join(m["item"] for m in achados), "situacao": situacao})
    return saida


def gravar(itens, ambitos, cruzamento, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, linhas in (("itens.csv", itens), ("ambitos.csv", ambitos), ("cruzamento_prot_32_09.csv", cruzamento)):
        with (destino / nome).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(linhas)
    meta = dict(meta)
    meta["contagens"] = {
        "capitulos": len({i["capitulo"] for i in itens}), "itens": len(itens),
        "itens_com_mva_numerica": sum(bool(i["mva_original"]) for i in itens),
        "itens_com_ambito_desconhecido": sum(bool(i["ambito_desconhecido"]) for i in itens),
        "cruzamento": {s: sum(c["situacao"] == s for c in cruzamento)
                       for s in ("coerente", "protocolo_sim_mg_nao", "mg_sim_protocolo_nao", "so_ncm_coincide")},
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html-dir", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "MG")
    a = ap.parse_args(argv)
    itens, ambitos, fontes = [], [], []
    for nome in PAGINAS:
        if a.html_dir:
            bruto = (a.html_dir / nome).read_bytes()
        else:
            import httpx
            r = httpx.get(BASE_URL + nome, headers={"User-Agent": USER_AGENT}, timeout=90, follow_redirects=True)
            r.raise_for_status()
            bruto = r.content
            time.sleep(1)
        i, amb = ler_pagina(decodificar(bruto))
        itens += i
        ambitos += amb
        fontes.append({"url": BASE_URL + nome, "sha256": hashlib.sha256(bruto).hexdigest()})
    with (RAIZ / "dados" / "protocolos" / "matriz_sp_destino.csv").open(encoding="utf-8") as f:
        matriz = list(csv.DictReader(f))
    cruz = cruzar_com_protocolo(itens, matriz)
    meta = {"fonte": "SEF/MG, RICMS/2023, Anexo VII, Parte 2 (versão consolidada sem histórico)", "fontes": fontes,
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": date.today().isoformat()}
    meta = gravar(itens, ambitos, cruz, a.saida, meta)
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Pernambuco: todas as tabelas de MVA por item do Conv. 142 no Decreto 44.650/2017 (Anexos 37-A, 37-B e 37-C).

O Anexo 37 do Decreto 44.650/2017 é o regulamento da ST em PE; os segmentos com MVA própria têm uma
tabela em anexo separado, sempre no mesmo formato: o número do item do Anexo do Conv. ICMS 142/2018 e
a MVA da operação interna ou de importação. Este script lê as três:

    37-A  perfumaria, higiene pessoal e cosméticos (itens do Anexo XIX do Conv. 142)
    37-B  materiais elétricos (Anexo XIII, e alguns do Anexo XX)
    37-C  materiais de construção (Anexo XI; é o que scripts/estado_pe.py já lia)

O Anexo 37-D (a partir de 01/01/2027) traz MVA por posição da NCM para o imposto antecipado, não por
item do Conv. 142, e fica de fora.

Saída (dados/estados/PE/):
    itens_todos_anexos.csv       anexo de PE, item e anexo do Conv. 142, CEST, NCM, descrição e MVA
    cruzamento_protocolos.csv    cada linha da matriz com destino PE x as tabelas de PE, pelo CEST provável
    anexos.json                  cabeçalho de cada anexo (com a vigência), fonte, sha256 e contagens

Uso:
    python scripts/estado_pe_anexos.py                 baixa da SEFAZ-PE
    python scripts/estado_pe_anexos.py --html ARQ.htm  usa a página salva
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import estado_pe as pe  # noqa: E402
from conv142 import USER_AGENT  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ANEXOS = {"37-A": "anexo37a", "37-B": "anexo37b", "37-C": "anexo37c"}


def ler_anexos(pagina: str, conv142_csv: Path) -> tuple[list[dict], dict]:
    itens, cabecalhos = [], {}
    for nome, ancora in ANEXOS.items():
        antiga = pe.ANCORA
        try:
            pe.ANCORA = re.compile(r"name=[\"']?%s[\"' >]" % ancora, re.I)
            cab, tabela = pe.recortar_anexo(pagina)
        finally:
            pe.ANCORA = antiga
        cabecalhos[nome] = cab[:600]
        for i in pe.juntar_conv142(pe.ler_tabela(tabela), conv142_csv):
            itens.append({"anexo_pe": nome, **i})
    return itens, cabecalhos


def cruzar(itens: list[dict], matriz_csv: Path) -> list[dict]:
    por_cest: dict[str, list[dict]] = {}
    for i in itens:
        if i["cest"]:
            por_cest.setdefault(i["cest"], []).append(i)
    saida, vistos = [], set()
    with matriz_csv.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["destino"] != "PE" or (r["protocolo"], r["item"]) in vistos:
                continue
            vistos.add((r["protocolo"], r["item"]))
            cests = [c for c in r["cests_provaveis"].split(";") if c]
            pe_ = [i for c in cests for i in por_cest.get(c, [])]
            mvas = sorted({i["mva"] for i in pe_ if i["mva"]})
            if not cests:
                sit = "sem_cest"
            elif not pe_:
                sit = "pe_sem_tabela_propria"
            elif not r["mva_original"]:
                sit = "protocolo_sem_mva"
            elif any(abs(float(m) - float(r["mva_original"])) < 0.005 for m in mvas):
                sit = "mva_igual"
            else:
                sit = "mva_diferente"
            saida.append({"protocolo": r["protocolo"], "item_protocolo": r["item"], "ncm_sh": r["ncm_sh"],
                          "descricao": r["descricao"][:100], "cests_provaveis": ";".join(cests),
                          "mva_protocolo": r["mva_original"], "mva_pe": ";".join(mvas),
                          "anexos_pe": ";".join(sorted({i["anexo_pe"] for i in pe_})), "situacao": sit})
    return saida


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "PE")
    a = ap.parse_args(argv)
    if a.html:
        bruto = a.html.read_bytes()
    else:
        import httpx

        r = httpx.get(pe.URL, headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True)
        r.raise_for_status()
        bruto = r.content
    itens, cabecalhos = ler_anexos(bruto.decode("cp1252", errors="replace"), RAIZ / "dados" / "conv142" / "itens_vigentes.csv")
    cruz = cruzar(itens, RAIZ / "dados" / "protocolos" / "matriz_origem_destino.csv")
    a.saida.mkdir(parents=True, exist_ok=True)
    for nome, linhas in (("itens_todos_anexos.csv", itens), ("cruzamento_protocolos.csv", cruz)):
        with (a.saida / nome).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(linhas)
    meta = {"fonte": "SEFAZ-PE, Decreto 44.650/2017 consolidado, Anexos 37-A, 37-B e 37-C", "url": pe.URL,
            "cabecalhos": cabecalhos, "sha256": hashlib.sha256(bruto).hexdigest(),
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": date.today().isoformat(),
            "contagens": {"itens_por_anexo": {n: sum(i["anexo_pe"] == n for i in itens) for n in ANEXOS},
                          "itens_sem_cest": sum(not i["cest"] for i in itens),
                          "cruzamento": {s: sum(c["situacao"] == s for c in cruz) for s in
                                         ("mva_igual", "mva_diferente", "protocolo_sem_mva", "pe_sem_tabela_propria", "sem_cest")}}}
    (a.saida / "anexos.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

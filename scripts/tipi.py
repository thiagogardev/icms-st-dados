"""TIPI: Tabela de Incidência do IPI (Decreto 11.158/2022 e atualizações), da planilha oficial da Receita.

A Receita Federal publica a TIPI consolidada em Excel, PDF e Word. A planilha tem uma aba ("Tabela
Completa") com quatro colunas: NCM, EX, DESCRIÇÃO e ALÍQUOTA (%). A alíquota pode ser um número
("3.25"), "NT" (não tributado) ou vazia (linha de título: posição ou subposição sem alíquota própria).
O cabeçalho lista os atos que atualizaram a tabela; a vigência de cada redação é a da tabela no dia
em que foi lida, e o histórico fica nas versões deste repositório (o monitor avisa quando o arquivo muda).

Saída (dados/tipi/):
    tipi.csv          todas as linhas, na ordem da tabela, com o nível (posição, subposição, item, subitem)
    tipi_ncm8.csv     só os códigos de 8 dígitos e os EX, com a alíquota aplicável
    metadados.json    fonte, sha256, atos de atualização citados no cabeçalho e contagens

Uso:
    python scripts/tipi.py                  baixa da Receita
    python scripts/tipi.py --xlsx ARQ.xlsx  usa a planilha salva
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
from conv142 import USER_AGENT  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/documentos-e-arquivos/tipi.xlsx"
_ATO = re.compile(r"(Decreto|Ato Declarat[óo]rio Executivo|ADE)[^\n]*?n[ºo°]?\s*([\d.]+)[^\n]*?de\s+(\d{1,2})[ºo°]?\s+de\s+([a-zç]+)\s+de\s+(\d{4})", re.I)


def nivel(ncm: str) -> str:
    d = re.sub(r"\D", "", ncm)
    return {2: "capitulo", 4: "posicao", 5: "subposicao_1", 6: "subposicao", 7: "item", 8: "subitem"}.get(len(d), "outro")


def aliquota(valor) -> tuple[str, str]:
    """('3.25', '3,25') para número; ('', 'NT') para não tributado; ('', '') para linha de título."""
    if valor is None:
        return "", ""
    t = str(valor).strip()
    if not t:
        return "", ""
    if t.upper() == "NT":
        return "", "NT"
    try:
        n = float(t.replace(",", "."))
    except ValueError:
        return "", t
    return f"{n:g}", f"{n:g}".replace(".", ",")


def ler_planilha(bruto: bytes) -> tuple[list[dict], list[str]]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(bruto), read_only=True)
    ws = wb.worksheets[0]
    linhas: list[dict] = []
    cabecalho: list[str] = []
    dentro = False
    for row in ws.iter_rows(values_only=True):
        c = list(row[:4]) + [None] * (4 - len(row[:4]))
        if not dentro:
            if c[0] and str(c[0]).strip().upper().startswith("NCM"):
                dentro = True
            elif c[0]:
                cabecalho.append(str(c[0]))
            continue
        ncm = str(c[0] or "").strip()
        if not re.match(r"^\d{2}(\.\d{1,2}){0,3}$|^\d{4}(\.\d{1,2}){0,2}$", ncm):
            continue
        num, texto = aliquota(c[3])
        linhas.append({
            "ncm": ncm, "ncm_digitos": re.sub(r"\D", "", ncm), "ex": str(c[1] or "").strip(),
            "descricao": re.sub(r"\s+", " ", str(c[2] or "")).strip(), "aliquota": num, "aliquota_texto": texto,
            "nivel": nivel(ncm),
        })
    return linhas, cabecalho


def atos(cabecalho: list[str]) -> list[str]:
    texto = "\n".join(cabecalho)
    bloco = texto[texto.find("Atualiza"):] if "Atualiza" in texto else texto
    return [re.sub(r"\s+", " ", l).strip() for l in bloco.splitlines()[1:] if re.search(r"\d", l)]


def gravar(linhas: list[dict], destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    campos = list(linhas[0].keys())
    with (destino / "tipi.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    oito = [l for l in linhas if len(l["ncm_digitos"]) == 8]
    with (destino / "tipi_ncm8.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ncm", "ex", "aliquota", "aliquota_texto", "descricao"])
        w.writeheader()
        for l in oito:
            w.writerow({"ncm": l["ncm_digitos"], "ex": l["ex"], "aliquota": l["aliquota"],
                        "aliquota_texto": l["aliquota_texto"], "descricao": l["descricao"]})
    meta = dict(meta)
    meta["contagens"] = {
        "linhas": len(linhas), "codigos_8_digitos": sum(1 for l in oito if not l["ex"]), "ex": sum(1 for l in linhas if l["ex"]),
        "nao_tributados": sum(l["aliquota_texto"] == "NT" for l in linhas),
        "aliquota_zero": sum(l["aliquota"] == "0" for l in linhas),
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xlsx", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "tipi")
    a = ap.parse_args(argv)
    if a.xlsx:
        bruto = a.xlsx.read_bytes()
    else:
        import httpx

        r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True)
        r.raise_for_status()
        bruto = r.content
    linhas, cab = ler_planilha(bruto)
    meta = {"fonte": "Receita Federal, TIPI consolidada (Decreto 11.158/2022 e atualizações), planilha oficial", "url": URL,
            "sha256": hashlib.sha256(bruto).hexdigest(), "atualizacoes_citadas": atos(cab),
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": date.today().isoformat()}
    meta = gravar(linhas, a.saida, meta)
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

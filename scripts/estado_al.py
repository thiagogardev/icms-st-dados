"""Alagoas: materiais de construção sujeitos à ST e MVA (Decreto 90.309/2023, Anexo VIII).

O Decreto 90.309/2023 reúne as regras de ST de Alagoas; o Anexo VIII trata dos materiais de
construção e congêneres, com uma Tabela Única: item, CEST, NCM/SH, descrição, acordo
interestadual (por exemplo "Protocolo ICMS 104/08" ou "Sem Acordo"), MVA original e as MVAs
ajustadas para as operações interestaduais a 12%, 7% e 4%. A SEFAZ-AL avisa que as ajustadas
"não constam da publicação em DOEAL": são cálculo dela, não texto legal.

A SEFAZ-AL publica a versão consolidada como PDF no sistema de documentos (gcs2.sefaz.al.gov.br),
pela mesma API que o site usa para mostrar o documento a qualquer visitante. O PDF é lido pela
posição das palavras (pdfplumber); cada palavra vai para o item cuja linha está mais perto na
vertical, porque as células são centralizadas e quebram em várias linhas.

Uso:
    python scripts/estado_al.py                  baixa da SEFAZ-AL e grava em dados/estados/AL
    python scripts/estado_al.py --pdf ARQ.pdf    usa o PDF salvo
"""

from __future__ import annotations

import argparse
import base64
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
from protocolos import separar_ncms  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
API = "https://gcs2.sefaz.al.gov.br/sfz-gcs-api/api/documentos/visualizarDocumento"
CHAVE = "dx9aIL23hOg="  # Decreto 90.309/2023, documento consolidado
_ITEM = re.compile(r"^\d+\.\d+$")
_CEST = re.compile(r"^\d{2}\.\d{3}\.\d{2}$")
_PCT = re.compile(r"^(\*{0,2})(\d+(?:,\d+)?)%?$")

# Colunas da Tabela Única (x inicial, em pontos), medidas no PDF de 03/11/2026.
COL_CEST, COL_NCM, COL_DESC, COL_ACORDO, COL_MVA, COL_12, COL_7, COL_4 = 58, 100, 145, 250, 340, 400, 452, 500


def _coluna(x0: float) -> str:
    if x0 < COL_CEST:
        return "item"
    if x0 < COL_NCM:
        return "cest"
    if x0 < COL_DESC:
        return "ncm"
    if x0 < COL_ACORDO:
        return "descricao"
    if x0 < COL_MVA:
        return "acordo"
    if x0 < COL_12:
        return "mva"
    if x0 < COL_7:
        return "aj12"
    if x0 < COL_4:
        return "aj7"
    return "aj4"


def ler_pdf(bruto: bytes) -> list[dict]:
    import pdfplumber

    itens: list[dict] = []
    with pdfplumber.open(io.BytesIO(bruto)) as pdf:
        dentro = False
        for pg in pdf.pages:
            texto = pg.extract_text() or ""
            ws = pg.extract_words()
            limite = None
            if not dentro:
                ini = next((w for w in ws if w["text"] == "TABELA" and "ANEXO VIII" in texto), None)
                if "TABELA ÚNICA DO ANEXO VIII" not in texto or ini is None:
                    continue
                dentro = True
                topo = ini["top"]
            else:
                topo = 0
            fim = [w["top"] for w in ws if w["text"] == "ANEXO" and abs(w["x0"] - 230) < 120
                   and any(v["text"] == "IX" and abs(v["top"] - w["top"]) < 2 for v in ws)]
            if fim:
                limite = min(fim)
            ws = [w for w in ws if w["top"] > topo and (limite is None or w["top"] < limite)]
            # o CEST pode ficar uma ou duas linhas abaixo do número do item (célula centralizada)
            linhas = [w for w in ws if _ITEM.match(w["text"]) and w["x0"] < COL_CEST
                      and any(_CEST.match(v["text"]) and -3 < v["top"] - w["top"] < 30 for v in ws)]
            if linhas:
                cab = min(l["top"] for l in linhas)
                pagina_itens = [{"top": l["top"], "item": l["text"], "partes": {}} for l in linhas]
                for w in ws:
                    if w in linhas or w["top"] < cab - 30:
                        continue
                    col = _coluna(w["x0"])
                    if col == "item":
                        continue
                    alvo = min(pagina_itens, key=lambda p: abs(p["top"] - w["top"]))
                    alvo["partes"].setdefault(col, []).append(w)
                for p in pagina_itens:
                    junta = lambda c: " ".join(w["text"] for w in sorted(p["partes"].get(c, []), key=lambda w: (round(w["top"]), w["x0"])))
                    def pct(c, marca=None):
                        # "*41%" = com frete na base de cálculo, "**56%" = sem frete; sem marca = única
                        vals = [_PCT.match(w["text"]) for w in sorted(p["partes"].get(c, []), key=lambda w: w["top"])]
                        vals = [m for m in vals if m and m.group(2)]
                        if marca is not None:
                            vals = [m for m in vals if m.group(1) == marca]
                        else:
                            vals = [m for m in vals if m.group(1) in ("", "*")]
                        return vals[0].group(2).replace(",", ".") if vals else ""
                    ncm = junta("ncm")
                    itens.append({
                        "item": p["item"], "cest": junta("cest").split()[0] if junta("cest") else "",
                        "ncm_sh": ncm, "ncms": ";".join(separar_ncms(ncm)), "descricao": junta("descricao"),
                        "acordo": junta("acordo"), "mva_original": pct("mva"),
                        "mva_original_sem_frete_na_base": pct("mva", "**"),
                        "mva_ajustada_12": pct("aj12"), "mva_ajustada_7": pct("aj7"), "mva_ajustada_4": pct("aj4"),
                    })
            if limite is not None:
                break
    return itens


def completar_pelo_conv142(itens: list[dict], conv142_csv: Path) -> list[dict]:
    """O PDF quebra descrição e NCM em várias linhas; o texto de referência vem do Conv. 142 pelo CEST."""
    with conv142_csv.open(encoding="utf-8") as f:
        conv = {r["cest"]: r for r in csv.DictReader(f) if r["anexo"] == "XI"}
    for i in itens:
        c = conv.get(i["cest"])
        i["descricao_no_pdf"] = i.pop("descricao")
        i["ncm_no_pdf"] = i.pop("ncm_sh")
        i.pop("ncms")
        i["ncm_sh"], i["ncms"], i["descricao"] = (c["ncm_sh"], c["ncms"], c["descricao"]) if c else ("", "", "")
    return itens


def cruzar_com_protocolo(itens: list[dict], matriz_csv: Path) -> list[dict]:
    """Matriz SP->AL (Prot. ICMS 104/08): a MVA do protocolo x a do Anexo VIII, pelo CEST provável."""
    with matriz_csv.open(encoding="utf-8") as f:
        linhas = [r for r in csv.DictReader(f) if r["destino"] == "AL"]
    por_cest = {}
    for i in itens:
        por_cest.setdefault(i["cest"], []).append(i)
    saida = []
    for r in linhas:
        cests = [c for c in r["cests_provaveis"].split(";") if c]
        al = [i for c in cests for i in por_cest.get(c, [])]
        mvas = sorted({m for i in al for m in (i["mva_original"], i["mva_original_sem_frete_na_base"])} - {""})
        com_sp = any("104/08" in i["acordo"] for i in al)
        if not cests:
            situacao = "sem_cest"
        elif not al:
            situacao = "cest_fora_do_anexo_viii"
        elif not com_sp:
            situacao = "al_sem_acordo_com_sp"
        elif r["mva_original"] and mvas and not any(abs(float(m) - float(r["mva_original"])) < 0.005 for m in mvas):
            situacao = "mva_diferente"
        else:
            situacao = "coerente"
        saida.append({"protocolo": r["protocolo"], "item_protocolo": r["item"], "ncm_sh": r["ncm_sh"],
                      "descricao": r["descricao"][:100], "cests_provaveis": ";".join(cests),
                      "mva_protocolo": r["mva_original"], "mva_al": ";".join(mvas),
                      "acordo_al": ";".join(sorted({i["acordo"] for i in al})), "situacao": situacao})
    return saida


def gravar(itens, cruz, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, linhas in (("itens.csv", itens), ("cruzamento_prot_104_08.csv", cruz)):
        if linhas:
            with (destino / nome).open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
                w.writeheader()
                w.writerows(linhas)
    meta = dict(meta)
    meta["contagens"] = {
        "itens": len(itens), "com_mva_original": sum(bool(i["mva_original"]) for i in itens),
        "com_acordo_104_08": sum("104/08" in i["acordo"] for i in itens),
        "cruzamento": {s: sum(c["situacao"] == s for c in cruz) for s in
                       ("coerente", "mva_diferente", "al_sem_acordo_com_sp", "cest_fora_do_anexo_viii", "sem_cest")},
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def baixar() -> tuple[bytes, str]:
    import httpx

    r = httpx.get(API, params={"acess": "1", "key": CHAVE}, headers={"User-Agent": USER_AGENT},
                  timeout=300, follow_redirects=True)
    r.raise_for_status()
    arq = r.json()["arquivo"]
    return base64.b64decode(arq["base64"]), arq.get("nomeArquivo", "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "AL")
    a = ap.parse_args(argv)
    bruto, nome = (a.pdf.read_bytes(), a.pdf.name) if a.pdf else baixar()
    itens = completar_pelo_conv142(ler_pdf(bruto), RAIZ / "dados" / "conv142" / "itens_vigentes.csv")
    matriz = RAIZ / "dados" / "protocolos" / "matriz_sp_destino.csv"
    cruz = cruzar_com_protocolo(itens, matriz) if matriz.exists() else []
    meta = {"fonte": "SEFAZ-AL, Decreto 90.309/2023 consolidado, Anexo VIII (Tabela Única)",
            "url": f"{API}?acess=1&key={CHAVE}", "nome_do_arquivo": nome,
            "sha256": hashlib.sha256(bruto).hexdigest(),
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": date.today().isoformat()}
    meta = gravar(itens, cruz, a.saida, meta)
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

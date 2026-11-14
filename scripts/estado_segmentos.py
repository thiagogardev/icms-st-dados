"""Segmentos que cada estado mantém na ST, pelo texto oficial do anexo, e o efeito nos protocolos com destino nele.

Para estados cuja lista de ST vem organizada por segmento do Conv. ICMS 142/2018 (com o código do CEST no
título de cada bloco), basta saber quais segmentos o anexo traz: um protocolo com destino no estado, num
segmento que o anexo não traz, não tem efeito prático lá (o produto não está na ST no destino). Isso vai
para dados/estados/efeito_no_destino.csv, como GO e SC.

Estados configurados:
    PB  RICMS/PB (Decreto 18.930/97), Anexo 05, art. 390. A SEFAZ-PB publica uma versão em PDF a cada
        atualização na mesma página; vale a de maior "ATUALIZADO EM" entre as da redação mais nova.

Saída: dados/estados/<UF>/segmentos.csv, metadados.json; efeito_no_destino.csv (compartilhado).

Uso:
    python scripts/estado_segmentos.py PB                 baixa da SEFAZ
    python scripts/estado_segmentos.py PB --pdf ARQ.pdf   usa o PDF salvo
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
from urllib.parse import quote, urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conv142 import USER_AGENT  # noqa: E402
from estado_go import gravar_efeitos  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

ESTADOS = {
    "PB": {
        # Em 13/11/2026 a SEFAZ-PB tirou do ar a página com a lista de PDFs (artigo 1519); o Anexo 05 passou a
        # sair em planilhas por segmento (página 11601). O último PDF consolidado continua no mesmo endereço.
        "pagina": "https://www.sefaz.pb.gov.br/legislacao/99-regulamentos/anexos-icms/1519",
        "pdf_conhecido": "https://www.sefaz.pb.gov.br/attachments/article/1519/ANEXO%20%2005%20REL.%20MERC.EF.%20SUBST.%20TRIB."
                         "%20E%20RESP.%20TAX.%20VAL.%20%20AGREG.%20NR%20A%20PARTIR%20DE%2001.01.2024%20%20-%20ATUALIZADO%20EM%2009.07.2025.pdf",
        "fonte": "RICMS/PB (Decreto 18.930/97), Anexo 05 (art. 390), PDF atualizado da SEFAZ-PB",
        # título de bloco: "9) CEST 10. Materiais de construção e congêneres"
        "bloco": re.compile(r"^\s*\d+\)\s*CEST\s+(\d{2})\.\s*(.+?)\s*$", re.M),
    },
}

_LINK = re.compile(r'href="([^"]+\.pdf)"', re.I)
_ATUALIZADO = re.compile(r"ATUALIZADO EM (\d{2})\.(\d{2})\.(\d{2,4})", re.I)
_A_PARTIR = re.compile(r"A PARTIR DE (\d{2})\.(\d{2})\.(\d{2,4})", re.I)


def _data(m) -> date | None:
    if not m:
        return None
    a = int(m.group(3))
    try:
        return date(a + 2000 if a < 100 else a, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def escolher_pdf(pagina_html: str, base: str) -> str:
    """O PDF da redação mais nova ("A PARTIR DE" maior) com o "ATUALIZADO EM" mais recente."""
    melhores = []
    for href in dict.fromkeys(_LINK.findall(pagina_html)):
        nome = href.rsplit("/", 1)[-1]
        a_partir, atualizado = _data(_A_PARTIR.search(nome)), _data(_ATUALIZADO.search(nome))
        if a_partir:
            melhores.append((a_partir, atualizado or a_partir, "NOVA VERS" in nome.upper(), href))
    if not melhores:
        raise ValueError("nenhum PDF com data no nome")
    href = max(melhores)[3]
    return urljoin(base, quote(href, safe="/:"))


def texto_do_pdf(bruto: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(bruto)) as pdf:
        return "\n".join(pg.extract_text() or "" for pg in pdf.pages)


def ler_segmentos(texto: str, bloco: re.Pattern) -> list[dict]:
    vistos: dict[str, dict] = {}
    for m in bloco.finditer(texto):
        vistos.setdefault(m.group(1), {"segmento": m.group(1), "titulo": re.sub(r"\s+", " ", m.group(2))})
    cests: dict[str, set] = {}
    for c in re.findall(r"\b(\d{2})\.(\d{3})\.(\d{2})\b", texto):
        cests.setdefault(c[0], set()).add(".".join(c))
    for s, v in vistos.items():
        v["cests_no_texto"] = len(cests.get(s, ()))
    return sorted(vistos.values(), key=lambda v: v["segmento"])


def efeitos(uf: str, segmentos: list[dict], fonte: str, protocolos_csv: Path, matriz_csv: Path) -> list[dict]:
    presentes = {s["segmento"] for s in segmentos}
    with protocolos_csv.open(encoding="utf-8") as f:
        seg = {r["protocolo"]: r["segmento"] for r in csv.DictReader(f)}
    with matriz_csv.open(encoding="utf-8") as f:
        com_uf = sorted({r["protocolo"] for r in csv.DictReader(f) if r["destino"] == uf})
    titulos = ", ".join(s["titulo"].lower() for s in segmentos)
    return [{"uf": uf, "protocolo": p,
             "efeito": f"{uf} não mantém este segmento na ST (a lista do estado traz só: {titulos}); o protocolo segue no "
                       f"Confaz, mas o produto não tem ST em {uf}",
             "desde": "", "fonte": fonte}
            for p in com_uf if seg.get(p) and seg[p] not in presentes]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("uf", choices=sorted(ESTADOS))
    ap.add_argument("--pdf", type=Path)
    a = ap.parse_args(argv)
    cfg = ESTADOS[a.uf]
    if a.pdf:
        bruto, url = a.pdf.read_bytes(), str(a.pdf)
    else:
        import httpx

        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True) as cli:
            r = cli.get(cfg["pagina"])
            try:
                r.raise_for_status()
                url = escolher_pdf(r.text, str(r.url))
            except Exception:
                if not cfg.get("pdf_conhecido"):
                    raise
                url = cfg["pdf_conhecido"]
            r = cli.get(url)
            r.raise_for_status()
            bruto = r.content
    texto = texto_do_pdf(bruto)
    segs = ler_segmentos(texto, cfg["bloco"])
    if len(segs) < 5:
        raise SystemExit(f"{a.uf}: só {len(segs)} segmentos lidos; o formato do anexo mudou?")
    efs = efeitos(a.uf, segs, cfg["fonte"], RAIZ / "dados" / "protocolos" / "protocolos.csv",
                  RAIZ / "dados" / "protocolos" / "matriz_origem_destino.csv")
    destino = RAIZ / "dados" / "estados" / a.uf
    destino.mkdir(parents=True, exist_ok=True)
    with (destino / "segmentos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["segmento", "titulo", "cests_no_texto"])
        w.writeheader()
        w.writerows(segs)
    gravar_efeitos(efs, RAIZ / "dados" / "estados" / "efeito_no_destino.csv")
    cab = texto[:400]
    meta = {"fonte": cfg["fonte"], "pagina": cfg["pagina"], "url": url, "cabecalho": re.sub(r"\s+", " ", cab).strip(),
            "sha256": hashlib.sha256(bruto).hexdigest(), "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": date.today().isoformat(),
            "contagens": {"segmentos": len(segs), "protocolos_sem_efeito": len(efs)},
            "protocolos_sem_efeito": [e["protocolo"] for e in efs]}
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta["contagens"] | {"protocolos": meta["protocolos_sem_efeito"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

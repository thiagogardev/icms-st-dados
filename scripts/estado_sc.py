"""Santa Catarina: segmentos que seguem na ST (RICMS-SC, Anexo 3) e o efeito nos protocolos com destino SC.

O Anexo 3 do RICMS-SC (Decreto 2.870/2001) traz uma Seção por segmento de ST. A maior parte foi revogada:
no texto consolidado da SEF-SC (página "com redação passada") só seguem as seções de cerveja e outras
bebidas frias, veículos, motocicletas, pneumáticos, cigarros, venda porta a porta, combustíveis, energia
elétrica, bebidas quentes e nafta. As seções revogadas aparecem só como "Seção XX – REVOGADA", sem título.

Um protocolo com destino SC num segmento que SC não mantém na ST não tem efeito prático: o produto não está
na ST em SC. Isso vai para dados/estados/efeito_no_destino.csv (compartilhado).

Uso:
    python scripts/estado_sc.py                 baixa da SEF-SC
    python scripts/estado_sc.py --html ARQ.htm  usa a página salva
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_mod
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalogo_protocolos import segmento  # noqa: E402
from conv142 import USER_AGENT  # noqa: E402
from estado_go import gravar_efeitos  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://legislacao.sef.sc.gov.br/html/regulamentos/icms/ricms_01_03.htm"
# "Seção" sem o prefixo "Sub" (as subseções do segmento de combustíveis não contam). O título vai até
# " - REVOGADA", o próximo artigo, nota, subseção ou seção.
_SECAO = re.compile(r"(?<![Ss]ub)Se[çc][ãa]o ([IVXL]+)\s*(?:\(arts?\.[^)]*\))?\s*[–-]?\s*(REVOGADA|Das? Opera[çc][õo]es .{3,160}?)(?=\s*[–-]\s*REVOGADA|\s*(?:\(|Art\.|Nota|Subse|Se[çc][ãa]o|SE[ÇC][ÃA]O))(?P<rev>\s*[–-]\s*REVOGADA)?", re.I)
_NORMA = re.compile(r"(Protocolos?|Conv[êe]nios?) ICMS ([\d/\s,e]+)")

# Títulos de seção que não casam com o padrão de segmento do catálogo.
EXTRA = [("25", r"ve[íi]culos automotores"), ("26", r"motocicletas|ciclomotores"), ("28", r"porta-a-porta|porta a porta"),
         ("06", r"nafta"), ("07", r"energia el[ée]trica")]


def texto_corrido(pagina: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", pagina, flags=re.S)
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", s)))


def seg_do_titulo(titulo: str) -> str:
    for cod, rx in EXTRA:
        if re.search(rx, titulo, re.I):
            return cod
    return segmento(titulo)


def ler_secoes(texto: str) -> list[dict]:
    secoes = []
    for m in _SECAO.finditer(texto):
        revogada = m.group(2).upper().startswith("REVOGADA") or bool(m.group("rev"))
        titulo = "" if revogada else m.group(2).strip()
        normas = []
        for tipo, nums in _NORMA.findall(texto[m.start():m.start() + 400]):
            prefixo = "Conv. ICMS" if tipo.lower().startswith("conv") else "Prot. ICMS"
            normas += [f"{prefixo} {int(a)}/{b[-2:]}" for a, b in re.findall(r"(\d+)\s*/\s*(\d{2,4})", nums)]
        secoes.append({"secao": m.group(1).upper(), "titulo": titulo, "segmento": "" if revogada else seg_do_titulo(titulo),
                       "normas": ";".join(dict.fromkeys(normas)) if not revogada else "",
                       "situacao": "revogada" if revogada else "vigente"})
    return secoes


def efeitos(secoes: list[dict], protocolos_csv: Path, matriz_csv: Path) -> list[dict]:
    """Protocolos com destino SC em segmento sem seção vigente em SC."""
    vigentes = {s["segmento"] for s in secoes if s["situacao"] == "vigente" and s["segmento"]}
    with protocolos_csv.open(encoding="utf-8") as f:
        seg = {r["protocolo"]: r["segmento"] for r in csv.DictReader(f)}
    with matriz_csv.open(encoding="utf-8") as f:
        com_sc = sorted({r["protocolo"] for r in csv.DictReader(f) if r["destino"] == "SC"})
    nomes = ", ".join(sorted({s["titulo"].replace("Das Operações com ", "").split(" (")[0].lower()
                              for s in secoes if s["situacao"] == "vigente" and s["titulo"].startswith("Das Opera")}))
    return [{"uf": "SC", "protocolo": p,
             "efeito": f"SC não mantém este segmento na ST (RICMS-SC, Anexo 3: seguem só {nomes}); o protocolo segue no "
                       f"Confaz, mas o produto não tem ST em SC",
             "desde": "", "fonte": "RICMS-SC (Decreto 2.870/2001), Anexo 3, texto consolidado da SEF-SC"}
            for p in com_sc if seg.get(p) and seg[p] not in vigentes]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "SC")
    a = ap.parse_args(argv)
    if a.html:
        bruto = a.html.read_bytes()
    else:
        import httpx

        r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True)
        r.raise_for_status()
        bruto = r.content
    secoes = ler_secoes(texto_corrido(bruto.decode("cp1252", errors="replace")))
    efs = efeitos(secoes, RAIZ / "dados" / "protocolos" / "protocolos.csv", RAIZ / "dados" / "protocolos" / "matriz_origem_destino.csv")
    a.saida.mkdir(parents=True, exist_ok=True)
    with (a.saida / "secoes.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(secoes[0].keys()))
        w.writeheader()
        w.writerows(secoes)
    gravar_efeitos(efs, RAIZ / "dados" / "estados" / "efeito_no_destino.csv")
    meta = {"fonte": "SEF-SC, RICMS-SC (Decreto 2.870/2001), Anexo 3 consolidado", "url": URL,
            "sha256": hashlib.sha256(bruto).hexdigest(), "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": date.today().isoformat(),
            "contagens": {"secoes": len(secoes), "vigentes": sum(s["situacao"] == "vigente" for s in secoes),
                          "revogadas": sum(s["situacao"] == "revogada" for s in secoes), "protocolos_sem_efeito_em_sc": len(efs)}}
    (a.saida / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Goiás: segmentos de ST por convênio ou protocolo e os que o estado tirou do regime (RCTE, Anexo VIII).

O Regulamento do Código Tributário de Goiás (RCTE, Decreto 4.852/1997) lista no Apêndice II do Anexo
VIII as mercadorias com ST estabelecida por convênio ou protocolo, um inciso por segmento. A SEFAZ-GO
publica o anexo consolidado numa página única (cerca de 57 MB, com todas as redações anteriores). A
redação vigente do Apêndice II é a "conferida pelo Decreto nº 8.819 - vigência: 01.01.17".

Desde 01/03/2018 (Decreto 9.108/2017) Goiás tirou da ST vários segmentos que ainda têm protocolo
vigente no Confaz: autopeças (41/08 e 97/10), ração pet (26/04 e 39/11), materiais de construção
(82/11 e 85/11) e material elétrico (83/11 e 84/11). Na prática, o remetente de outro estado não retém
para GO nesses segmentos, embora o protocolo continue no Confaz sem revogação.

Saída:
    dados/estados/GO/segmentos.csv       um inciso do Apêndice II vigente por linha, com normas e situação
    dados/estados/efeito_no_destino.csv  (compartilhado) protocolos sem efeito num estado de destino

Uso:
    python scripts/estado_go.py                    baixa da SEFAZ-GO
    python scripts/estado_go.py --html ARQ.htm     usa a página salva
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
from conv142 import USER_AGENT  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://appasp.economia.go.gov.br/legislacao/arquivos/Rcte/Anexos/ANEXO_08_Substituicao_Tributaria.htm"
MARCO_VIGENTE = "Redação conferida pelo Decreto nº 8.819 - vigência: 01.01.17"
_INCISO = re.compile(r"\b(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX) - (?=[A-ZÇÃÕÉÍÓÚÂÊ])")
_NORMA = re.compile(r"(Protocolos?|Conv[êe]nios?) IC?MS? ([\d/\s,e]+?)(?=\)|\s[A-Z]|$)")


def texto_corrido(pagina: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", pagina, flags=re.S)
    s = html_mod.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s)


def apendice_ii_vigente(texto: str) -> str:
    ini = texto.find(MARCO_VIGENTE)
    if ini < 0:
        raise SystemExit("redação vigente do Apêndice II não encontrada (a página mudou?)")
    fim = texto.find("APÊNDICE III", ini)
    return texto[ini:fim if fim > 0 else None]


def normas(trecho: str) -> list[str]:
    saida = []
    for tipo, nums in _NORMA.findall(trecho):
        prefixo = "Conv. ICMS" if tipo.lower().startswith("conv") else "Prot. ICMS"
        for n in re.findall(r"(\d+)\s*/\s*(\d{2,4})", nums):
            saida.append(f"{prefixo} {int(n[0])}/{n[1][-2:]}")
    return list(dict.fromkeys(saida))


def ler_segmentos(apendice: str) -> list[dict]:
    """Um inciso por linha. O mesmo número aparece mais de uma vez quando há redações anteriores no
    meio: fica a última ocorrência (a vigente vem depois das anteriores, com a tabela)."""
    achados: dict[str, dict] = {}
    marcas = list(_INCISO.finditer(apendice))
    for k, m in enumerate(marcas):
        fim = marcas[k + 1].start() if k + 1 < len(marcas) else len(apendice)
        bloco = apendice[m.start():fim]
        cab = bloco[:600]
        titulo = re.split(r"\s\(|\.\s|\sNota|\sNOTA|\sItem\s", cab[len(m.group(0)):], maxsplit=1)[0].strip(" .")
        if titulo.lower().startswith("revogad"):
            situacao = "revogado"
        elif re.search(r"exclu[íi]das? da sistem[áa]tica da Substitui", cab, re.I) or re.search(r"Por for[çc]a do art\. 1º do Decreto", cab):
            situacao = "excluido"
        else:
            situacao = "vigente"
        exclusao = re.search(r"exclu[íi]das? da sistem[áa]tica da Substitui[çc][ãa]o Tribut[áa]ria pelo (Decreto n?[°º]? ?[\d./]+) a partir de (\d{2})\.(\d{2})\.(\d{2,4})", cab, re.I)
        achados[m.group(1)] = {
            "inciso": m.group(1), "segmento": titulo[:120], "normas": ";".join(normas(re.split(r"\sItem\s|\sNota|\sNOTA", cab)[0])),
            "situacao": situacao,
            "excluido_por": exclusao.group(1).replace("n° ", "").replace("nº ", "") if exclusao else "",
            "excluido_desde": (f"{2000 + int(exclusao.group(4)) if len(exclusao.group(4)) == 2 else exclusao.group(4)}-"
                               f"{exclusao.group(3)}-{exclusao.group(2)}") if exclusao else "",
        }
    return list(achados.values())


def efeitos(segmentos: list[dict]) -> list[dict]:
    """Protocolos de segmentos que GO tirou da ST: sem efeito nas remessas para GO."""
    saida = []
    for s in segmentos:
        if s["situacao"] != "excluido":
            continue
        for n in s["normas"].split(";"):
            if n.startswith("Prot."):
                saida.append({"uf": "GO", "protocolo": n, "efeito": (
                    f"GO tirou o segmento ({s['segmento'].lower()}) da ST pelo {s['excluido_por'] or 'Decreto 9.108/2017'}"
                    f" desde {s['excluido_desde'] or '2018-03-01'}; o protocolo segue no Confaz, mas o remetente não retém para GO"),
                    "desde": s["excluido_desde"] or "2018-03-01", "fonte": "RCTE-GO, Anexo VIII, Apêndice II (Decreto 8.819, vigente)"})
    return saida


def gravar_efeitos(novos: list[dict], caminho: Path) -> None:
    """Junta ao arquivo compartilhado, trocando só as linhas da UF dos novos."""
    ufs = {n["uf"] for n in novos}
    antigos = []
    if caminho.exists():
        with caminho.open(encoding="utf-8") as f:
            antigos = [r for r in csv.DictReader(f) if r["uf"] not in ufs]
    with caminho.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["uf", "protocolo", "efeito", "desde", "fonte"])
        w.writeheader()
        w.writerows(sorted(antigos + novos, key=lambda r: (r["uf"], r["protocolo"])))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "GO")
    a = ap.parse_args(argv)
    if a.html:
        bruto = a.html.read_bytes()
    else:
        import httpx

        r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=600, follow_redirects=True)
        r.raise_for_status()
        bruto = r.content
    pagina = bruto.decode("cp1252", errors="replace")
    segs = ler_segmentos(apendice_ii_vigente(texto_corrido(pagina)))
    efs = efeitos(segs)
    a.saida.mkdir(parents=True, exist_ok=True)
    with (a.saida / "segmentos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(segs[0].keys()))
        w.writeheader()
        w.writerows(segs)
    gravar_efeitos(efs, RAIZ / "dados" / "estados" / "efeito_no_destino.csv")
    meta = {"fonte": "SEFAZ-GO, RCTE (Decreto 4.852/1997), Anexo VIII, Apêndice II vigente (Decreto 8.819)", "url": URL,
            "sha256": hashlib.sha256(bruto).hexdigest(), "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": date.today().isoformat(),
            "contagens": {"incisos": len(segs), "vigentes": sum(s["situacao"] == "vigente" for s in segs),
                          "excluidos": sum(s["situacao"] == "excluido" for s in segs),
                          "protocolos_sem_efeito_em_go": len(efs)}}
    (a.saida / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

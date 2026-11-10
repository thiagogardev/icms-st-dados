"""Rio Grande do Sul: bens sujeitos à ST e MVA, do RICMS/RS, Apêndice II, Seção III.

O RICMS/RS (Decreto 37.699/1997) é publicado pela Receita Estadual numa página
única de cerca de 10 MB. O Apêndice II, Seção III, tem uma tabela por segmento
("ITEM XXVI - MATERIAIS DE CONSTRUÇÃO E CONGÊNERES") com: número, mercadoria,
NCM, CEST e três MVAs: a da operação interna (a original) e as ajustadas das
operações interestaduais a 12% e a 4%.

Cada número pode trazer notas na própria célula da mercadoria, como
"NOTA - Este número não se aplica às operações originárias do Estado de SP."
e notas de alteração "(Redação dada pelo art. 1º (Alteração 6847) do Decreto
58.901, ... - Efeitos a partir de 01/08/26.)", de onde sai o início de vigência.

Uso:
    python scripts/estado_rs.py                 baixa da Receita Estadual e grava em dados/estados/RS
    python scripts/estado_rs.py --html ARQ.html usa a página salva
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
URL = ("https://legislacao.sefaz.rs.gov.br/Site/DocumentView.aspx?inpKey=109362&inpCodDispositive=0"
       "&inpStToValidateDoc=&inpForceEdit=&inpDtTimeTunnel=&inpDsKeywords=&Debug=")
_CEST = re.compile(r"^\d{2}\.\d{3}\.\d{2}$")
_EFEITOS = re.compile(r"Efeitos (?:a partir de|retroativos a) (\d{1,2})/(\d{1,2})/(\d{2,4})", re.I)

UFS = {"AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI",
       "PR", "RJ", "RN", "RO", "RR", "SC", "SE", "SP", "TO"}


def texto(el) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", el.text_content()).strip())


def decodificar(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252")


def _numero(s: str) -> str:
    m = re.match(r"\s*(\d+(?:,\d+)?)", s or "")
    return m.group(1).replace(",", ".") if m else ""


def _efeitos(s: str) -> date | None:
    ds = []
    for d, m, a in _EFEITOS.findall(s):
        ano = int(a) + (2000 if len(a) == 2 else 0)
        try:
            ds.append(date(ano, int(m), int(d)))
        except ValueError:
            pass
    return max(ds) if ds else None


def ufs_excluidas(nota: str) -> list[str]:
    """'Este número não se aplica às operações originárias do Estado de SP' -> ['SP']."""
    saida = set()
    for m in re.finditer(r"n[ãa]o se aplica [àa]s opera[çc][õo]es origin[áa]rias d[oa]s? (?:Estados? (?:de |do |da )?)?([^.;]+)", nota, re.I):
        saida.update(u for u in re.findall(r"\b[A-Z]{2}\b", m.group(1)) if u in UFS)
    return sorted(saida)


def ler_html(pagina: str) -> list[dict]:
    from lxml import html

    itens = []
    for tabela in html.fromstring(pagina).xpath("//table"):
        linhas = tabela.xpath(".//tr")
        if not linhas:
            continue
        titulo = texto(linhas[0])
        m = re.match(r"ITEM ([IVXL]+) - (.+)", titulo)
        if not m or "CEST" not in tabela.text_content() and "ESPECIFICADOR" not in tabela.text_content().upper():
            continue
        item_ap, segmento = m.group(1), m.group(2)
        # Notas de alteração ficam em parágrafos logo depois da tabela:
        # "(Redação dada ao número 60 pelo art. 1º (Alteração 6847) do Decreto 58.901, ...
        #  - Efeitos retroativos a 01/08/26 - Prots. ICMS 92/09 e 54/26.)"
        notas_numero: dict[str, list[str]] = {}
        irmao = tabela.getnext()
        for _ in range(40):
            if irmao is None or irmao.tag == "table" or irmao.xpath(".//table"):
                break
            t = texto(irmao)
            for alvo in re.finditer(r"n[úu]meros? ([\d\s,e-]+?)(?= (?:pelo|do|da|ao)\b)", t):
                for n in re.findall(r"\d+", alvo.group(1)):
                    notas_numero.setdefault(n, []).append(t)
            irmao = irmao.getnext()
        for tr in linhas[1:]:
            cel = [texto(td) for td in tr.xpath("./td|./th")]
            pos = next((i for i, c in enumerate(cel) if _CEST.match(c)), None)
            if pos is None or pos < 3:
                continue
            numero, mercadoria, ncm = cel[0], cel[1], cel[pos - 1]
            mvas = cel[pos + 1:pos + 4] + [""] * (3 - len(cel[pos + 1:pos + 4]))
            notas = " ".join(re.findall(r"NOTA\s*\d*\s*-[^()]*", mercadoria))
            # a nota tem parênteses dentro: "(Redação dada ... (DOE 04/08/26) - Efeitos a partir de 01/08/26.)"
            alteracoes = " ".join(re.findall(r"\((?:Reda[çc][ãa]o dada|Acrescentad|Inclu[íi]d)[^()]*(?:\([^()]*\)[^()]*)*\)",
                                             " ".join(cel)))
            alteracoes = " ".join([alteracoes] + notas_numero.get(numero.strip(), [])).strip()
            descricao = re.sub(r"\s*NOTA\s*\d*\s*-.*$", "", mercadoria).strip()
            itens.append({
                "item_apendice": item_ap, "segmento": segmento, "numero": numero, "cest": cel[pos],
                "ncm_sh": ncm, "ncms": ";".join(separar_ncms(ncm)), "descricao": descricao,
                "mva_interna": _numero(mvas[0]), "mva_inter_12": _numero(mvas[1]), "mva_inter_4": _numero(mvas[2]),
                "mva_texto": " | ".join(mvas), "nao_se_aplica_origem": ";".join(ufs_excluidas(notas)),
                "notas": notas, "vigencia_inicio": (_efeitos(alteracoes) or "") and _efeitos(alteracoes).isoformat(),
                "alteracoes": alteracoes,
            })
    return itens


def cruzar_com_protocolo(itens: list[dict], protocolos_csv: Path) -> list[dict]:
    """Construção (item XXVI): os CESTs que o RS diz não valer para SP x os que o Prot. 92/09 exclui."""
    with protocolos_csv.open(encoding="utf-8") as f:
        p = next(r for r in csv.DictReader(f) if r["protocolo"] == "Prot. ICMS 92/09")
    excluidos = set(p["cests_excluidos"].split(";")) - {""}
    saida = []
    for i in itens:
        if i["item_apendice"] != "XXVI":
            continue
        rs_exclui_sp = "SP" in i["nao_se_aplica_origem"].split(";")
        prot_exclui = i["cest"] in excluidos
        saida.append({"cest": i["cest"], "numero": i["numero"], "descricao": i["descricao"][:100],
                      "rs_exclui_sp": "sim" if rs_exclui_sp else "nao", "prot_92_09_exclui": "sim" if prot_exclui else "nao",
                      "situacao": "coerente" if rs_exclui_sp == prot_exclui else
                      ("so_rs_exclui" if rs_exclui_sp else "so_protocolo_exclui")})
    for c in sorted(excluidos - {i["cest"] for i in itens if i["item_apendice"] == "XXVI"}):
        saida.append({"cest": c, "numero": "", "descricao": "", "rs_exclui_sp": "", "prot_92_09_exclui": "sim",
                      "situacao": "excluido_no_protocolo_ausente_no_rs"})
    return saida


def gravar(itens, cruz, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, linhas in (("itens.csv", itens), ("cruzamento_prot_92_09.csv", cruz)):
        if not linhas:
            continue
        with (destino / nome).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(linhas)
    meta = dict(meta)
    meta["contagens"] = {
        "segmentos": len({i["item_apendice"] for i in itens}), "itens": len(itens),
        "itens_com_mva_interna": sum(bool(i["mva_interna"]) for i in itens),
        "itens_com_excecao_de_origem": sum(bool(i["nao_se_aplica_origem"]) for i in itens),
        "cruzamento": {s: sum(c["situacao"] == s for c in cruz) for s in
                       ("coerente", "so_rs_exclui", "so_protocolo_exclui", "excluido_no_protocolo_ausente_no_rs")},
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "RS")
    a = ap.parse_args(argv)
    if a.html:
        bruto = a.html.read_bytes()
    else:
        import ssl

        import certifi
        import httpx
        # O servidor da Receita do RS não envia o certificado intermediário (GoDaddy DV R1v1).
        # Ele está em certs/, baixado do endereço que o próprio certificado indica; a verificação continua ligada.
        ctx = ssl.create_default_context(cafile=certifi.where())
        for pem in sorted((RAIZ / "certs").glob("*.pem")):
            ctx.load_verify_locations(cafile=str(pem))
        r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True, verify=ctx)
        r.raise_for_status()
        bruto = r.content
    itens = ler_html(decodificar(bruto))
    prot = RAIZ / "dados" / "protocolos" / "protocolos.csv"
    cruz = cruzar_com_protocolo(itens, prot) if prot.exists() else []
    meta = {"fonte": "Receita Estadual RS, RICMS (Decreto 37.699/1997), Apêndice II, Seção III", "url": URL,
            "sha256": hashlib.sha256(bruto).hexdigest(),
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": date.today().isoformat()}
    meta = gravar(itens, cruz, a.saida, meta)
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

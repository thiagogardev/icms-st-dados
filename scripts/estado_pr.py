"""Paraná: MVA original da ST, da Resolução SEFA 571/2019 (texto consolidado).

A resolução tem uma tabela por segmento (item, CEST, NCM/SH, descrição, MVA)
e marca a história em notas de texto entre as linhas:

    Tabela com redação dada pelo art. 1º, inciso II, da Resolução SEFA n. 1245, ...
    produzindo efeitos a partir de 1º.4.2026
    ... tabela vigente ...
    Redação original da tabela de que trata o caput do art. 16 que produziu efeitos de
    4.7.2019 até 31.3.2026 ...
    ... tabela antiga, com notas por item:
    Nova redação do item dada pelo ..., produzindo efeitos a partir de 1º.3.2020.
    <linha do item>
    Redação original que produziu efeitos de 4.7.2019 até 29.2.2020:
    <linha antiga do item>

A fonte é um PDF de quase 600 páginas. O texto corrido embaralha as colunas (a
MVA fica centralizada na célula), por isso a leitura usa a posição de cada
palavra: item, CEST e MVA ficam na mesma altura. A descrição vem do Convênio
142, pelo CEST.

Uso:
    python scripts/estado_pr.py               baixa do SEFANET e grava em dados/estados/PR
    python scripts/estado_pr.py --pdf ARQ.pdf usa um PDF salvo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conv142 import USER_AGENT  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
URL = "https://www.sefanet.pr.gov.br/dados/SEFADOCUMENTOS/101201900571.pdf"
INICIO_RESOLUCAO = date(2019, 7, 4)

_CEST = re.compile(r"^\d{2}\.\d{3}\.\d{2}$")
_NCM = re.compile(r"^\d{2}(?:\.\d{1,2}){0,3}$|^\d{4}(?:\.\d{1,2}){0,2}$|^\d{8}$")
_MVA = re.compile(r"^\d{1,3}(?:,\d{1,2})?$")
_DATA = re.compile(r"(\d{1,2})º?\.(\d{1,2})\.(\d{4})")


def _datas(s: str) -> list[date]:
    out = []
    for d, m, a in _DATA.findall(s):
        try:
            out.append(date(int(a), int(m), int(d)))
        except ValueError:
            pass
    return out


def linhas_do_pdf(caminho: Path):
    """Linhas de texto na ordem da página, cada uma com as palavras e suas posições."""
    import pdfplumber

    with pdfplumber.open(caminho) as pdf:
        for n, pg in enumerate(pdf.pages, 1):
            palavras = pg.extract_words(keep_blank_chars=False, use_text_flow=False)
            grupos: list[list[dict]] = []
            for w in sorted(palavras, key=lambda w: (round(w["top"]), w["x0"])):
                if grupos and abs(grupos[-1][0]["top"] - w["top"]) <= 2.5:
                    grupos[-1].append(w)
                else:
                    grupos.append([w])
            for g in grupos:
                g.sort(key=lambda w: w["x0"])
                yield n, g


def ler(caminho: Path, ref: date) -> dict:
    itens: list[dict] = []
    secao, titulo, artigo = "", "", ""
    tabela_ini: date | None = None
    tabela_fim: date | None = None
    nota_item: dict | None = None
    esperando_titulo = False
    buffer_nota = ""
    ultimo: dict | None = None

    def fechar_nota() -> None:
        nonlocal buffer_nota, tabela_ini, tabela_fim, nota_item
        n, buffer_nota = buffer_nota, ""
        if not n:
            return
        # "Nova redação da tabela ... a partir de 1º.4.2026. Redação original da tabela ...
        # que produziu efeitos de 4.7.2019 até 31.3.2026": o que vem depois é a redação antiga.
        m_ant = re.search(r"Redação (?:original|anterior)", n)
        if m_ant and m_ant.start() > 0:
            n = n[m_ant.start():]
        ds = _datas(n)
        baixo = n.lower()
        if baixo.startswith("tabela com reda"):
            tabela_ini, tabela_fim, nota_item = (ds[-1] if ds else None), None, None
        elif "da tabela" in baixo and baixo.startswith(("redação original", "redação anterior")):
            tabela_ini = ds[0] if len(ds) >= 2 else INICIO_RESOLUCAO
            tabela_fim = ds[1] if len(ds) >= 2 else (ds[0] if ds else None)
            nota_item = None
        elif baixo.startswith(("redação original", "redação anterior")):
            nota_item = {"tipo": "anterior", "ini": ds[0] if len(ds) >= 2 else None,
                         "fim": ds[1] if len(ds) >= 2 else (ds[0] if ds else None), "texto": n}
        elif baixo.startswith("revogado"):
            nota_item = {"tipo": "revogacao", "ini": ds[-1] if ds else None, "texto": n}
        elif "tabela" in baixo and baixo.startswith("nova reda"):
            nota_item = None  # a tabela vigente já veio antes; a redação antiga vem na próxima nota
        else:
            nota_item = {"tipo": "nova", "ini": ds[-1] if ds else None, "texto": n}

    for pagina, g in linhas_do_pdf(caminho):
        txt = " ".join(w["text"] for w in g)
        cest = next((w for w in g if _CEST.match(w["text"])), None)
        if cest is None and ultimo is not None and not buffer_nota:
            # NCM que continua nas linhas de baixo, na mesma coluna ("7217.10.90" / "7312")
            extra = [w["text"] for w in g if ultimo["_x_ncm"][0] - 15 <= w["x0"] <= ultimo["_x_ncm"][1]
                     and _NCM.match(w["text"])]
            if extra and len(extra) == len([w for w in g if w["x0"] <= ultimo["_x_ncm"][1]]):
                ultimo["ncm_sh"] = (ultimo["ncm_sh"] + " " + " ".join(extra)).strip()
                continue
        if cest is None:
            # --- texto fora da tabela: seções, artigos e notas de vigência
            if re.match(r"^SEÇÃO [IVXL]+$", txt):
                fechar_nota()
                secao, titulo, esperando_titulo = txt.split()[1], "", True
                tabela_ini = tabela_fim = None
                continue
            if esperando_titulo and txt.isupper() and not re.search(r"\d", txt):
                titulo = (titulo + " " + txt).strip()
                continue
            esperando_titulo = False
            m = re.match(r"^Art\. (\d+)", txt)
            if m:
                fechar_nota()
                artigo = m.group(1)
                tabela_ini = tabela_fim = None
                nota_item = None
                continue
            # notas podem quebrar em várias linhas: acumula até a próxima nota ou a próxima linha de item
            if re.match(r"^(Tabela com reda|Redação original|Redação anterior|Nova redação|Acres[ce]*ntado|Revogad)", txt):
                fechar_nota()
                buffer_nota = txt
            elif buffer_nota and not re.match(r"^(ITEM|Estado do Paraná|Secretaria de Estado|Receita Estadual|Coordenação)", txt):
                buffer_nota += " " + txt
            continue

        # --- linha de item
        fechar_nota()
        antes = [w for w in g if w["x0"] < cest["x0"]]
        item = antes[-1]["text"] if antes and re.fullmatch(r"\d+(?:\.\d+)?", antes[-1]["text"]) else ""
        direita = [w for w in g if w["x0"] > cest["x1"]]
        mvas = [w["text"] for w in direita if w["x0"] >= 400 and _MVA.match(w["text"])]
        ncms = [w["text"] for w in direita if w["x0"] < cest["x1"] + 120 and _NCM.match(w["text"])]
        ini, fim, origem, nota = tabela_ini, tabela_fim, "tabela", None
        if nota_item is not None:
            if nota_item["tipo"] == "anterior":
                ini = nota_item["ini"] or ini
                fim = nota_item["fim"]
                origem = "item_anterior"
            elif nota_item["tipo"] == "nova":
                ini = nota_item["ini"]
                origem = "item_alterado"
            nota = nota_item["texto"]
            nota_item = None
        reg = {"secao": secao, "segmento": titulo, "artigo": artigo, "item": item, "cest": cest["text"],
               "ncm_sh": " ".join(ncms), "mva_original": mvas[0].replace(",", ".") if mvas else "",
               "mva_texto": " ".join(mvas), "vigencia_inicio": ini, "vigencia_fim": fim, "origem": origem,
               "nota": nota or "", "pagina": pagina, "_x_ncm": (cest["x1"] + 5, cest["x1"] + 120)}
        chave = ("artigo", "cest", "ncm_sh", "mva_texto", "vigencia_inicio", "vigencia_fim", "origem")
        if ultimo is not None and all(ultimo[k] == reg[k] for k in chave):
            continue  # a mesma linha repetida na quebra de página
        itens.append(reg)
        ultimo = reg
    # fim das redações alteradas por item: véspera da redação seguinte do mesmo item e artigo
    for r in itens:
        if r["origem"] == "item_anterior" and r["vigencia_fim"] is None:
            prox = [x for x in itens if x["artigo"] == r["artigo"] and x["cest"] == r["cest"]
                    and x is not r and x["vigencia_inicio"] and (r["vigencia_inicio"] or INICIO_RESOLUCAO) < x["vigencia_inicio"]]
            if prox:
                r["vigencia_fim"] = min(x["vigencia_inicio"] for x in prox) - timedelta(days=1)
    for r in itens:
        if r["vigencia_inicio"] and r["vigencia_inicio"] > ref:
            r["situacao"] = "futura"
        elif r["vigencia_fim"] and r["vigencia_fim"] < ref:
            r["situacao"] = "anterior"
        else:
            r["situacao"] = "vigente"
    return {"itens": itens}


def descricoes_conv142() -> dict[str, str]:
    caminho = RAIZ / "dados" / "conv142" / "itens_vigentes.csv"
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8") as f:
        return {r["cest"]: r["descricao"] for r in csv.DictReader(f)}


def validar(itens: list[dict]) -> list[str]:
    avisos = []
    vig = [r for r in itens if r["situacao"] == "vigente"]
    vistos: dict[tuple, int] = {}
    for r in vig:
        k = (r["artigo"], r["cest"], r["ncm_sh"])
        vistos[k] = vistos.get(k, 0) + 1
    for k, n in vistos.items():
        if n > 1:
            avisos.append(f"art. {k[0]}, CEST {k[1]}: {n} redações vigentes ao mesmo tempo")
    for r in vig:
        if not r["mva_original"]:
            avisos.append(f"art. {r['artigo']}, CEST {r['cest']} (p. {r['pagina']}): sem MVA numérica")
    return avisos


def _sobrepoe(a: str, b: str) -> bool:
    return a.startswith(b) or b.startswith(a)


def cruzar_com_protocolo(itens: list[dict], matriz: list[dict]) -> list[dict]:
    """Cada item do Prot. ICMS 71/11 (SP -> PR) e a MVA que o PR fixa para ele (art. 16, construção)."""
    from protocolos import separar_ncms
    pr = [r for r in itens if r["situacao"] == "vigente" and r["artigo"] == "16"]
    saida = []
    for m in matriz:
        if m["destino"] != "PR":
            continue
        ncms = [c for c in m["ncms"].split(";") if c]
        achados = [r for r in pr if any(_sobrepoe(n, c) for n in ncms for c in separar_ncms(r["ncm_sh"]))]
        mvas = sorted({r["mva_texto"] for r in achados})
        saida.append({"item_protocolo": m["item"], "ncm_sh": m["ncm_sh"], "descricao": m["descricao"][:100],
                      "cests_pr": ";".join(r["cest"] for r in achados), "mva_pr": ";".join(mvas),
                      "situacao": "sem_mva_no_pr" if not achados else ("mva_unica" if len(mvas) == 1 else "varias_mvas")})
    return saida


def gravar(dados: dict, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    desc = descricoes_conv142()
    campos = ["secao", "segmento", "artigo", "item", "cest", "descricao_conv142", "ncm_sh", "mva_original",
              "mva_texto", "vigencia_inicio", "vigencia_fim", "situacao", "origem", "nota", "pagina"]

    def linha(r):
        d = {k: r.get(k, "") for k in campos}
        d["descricao_conv142"] = desc.get(r["cest"], "")
        for k in ("vigencia_inicio", "vigencia_fim"):
            d[k] = r[k].isoformat() if r[k] else ""
        return d

    for nome, filtro in (("mva_historico.csv", lambda r: True), ("mva_vigente.csv", lambda r: r["situacao"] == "vigente")):
        with (destino / nome).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(linha(r) for r in dados["itens"] if filtro(r))
    matriz_arq = RAIZ / "dados" / "protocolos" / "matriz_sp_destino.csv"
    cruz = []
    if matriz_arq.exists():
        with matriz_arq.open(encoding="utf-8") as f:
            cruz = cruzar_com_protocolo(dados["itens"], list(csv.DictReader(f)))
        with (destino / "cruzamento_prot_71_11.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["item_protocolo", "ncm_sh", "descricao", "cests_pr", "mva_pr", "situacao"])
            w.writeheader()
            w.writerows(cruz)
    avisos = validar(dados["itens"])
    (destino / "avisos.txt").write_text("\n".join(avisos) + ("\n" if avisos else ""), encoding="utf-8")
    meta = dict(meta)
    itens = dados["itens"]
    meta["contagens"] = {
        "redacoes": len(itens), "vigentes": sum(r["situacao"] == "vigente" for r in itens),
        "segmentos": len({r["artigo"] for r in itens}), "avisos": len(avisos),
        "cruzamento_prot_71_11": {s: sum(c["situacao"] == s for c in cruz)
                                  for s in ("mva_unica", "varias_mvas", "sem_mva_no_pr")},
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--ref", type=date.fromisoformat, default=date.today())
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "estados" / "PR")
    a = ap.parse_args(argv)
    caminho = a.pdf
    if caminho is None:
        import httpx
        import tempfile
        r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=180, follow_redirects=True)
        r.raise_for_status()
        caminho = Path(tempfile.gettempdir()) / "res_sefa_571_2019.pdf"
        caminho.write_bytes(r.content)
    bruto = caminho.read_bytes()
    dados = ler(caminho, a.ref)
    meta = {"fonte": "SEFA/PR, Resolução SEFA 571/2019, texto consolidado (SEFANET)", "url": URL,
            "sha256": hashlib.sha256(bruto).hexdigest(),
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": a.ref.isoformat()}
    meta = gravar(dados, a.saida, meta)
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""TEC com vigência por data: alíquota do II de cada NCM desde 01/09/2022, montada das versões publicadas dos Anexos.

Para conferir o II de uma DI antiga é preciso a alíquota da data do registro, não a de hoje. O MDIC/Camex
não publica um histórico pronto, mas guarda no próprio site as planilhas que já publicou (o nome traz a
data: "14-03-2025-anexos-i-a-ix-resolucao-gecex-272-21.xlsx"). Este script lê as versões abaixo, cada uma
valendo da sua data até a véspera da seguinte, e aplica a mesma regra do tec.py:

    exceção vigente para o NCM inteiro (sem Ex e sem quota) > Anexo II (aplicada) > Anexo I (TEC)

Versões usadas (dados/tec/historico_fontes.json traz URL e sha256 de cada uma):
    Anexo II  01/09/2022  "Anexo_II_Res_272_2021.xlsx"; o MDIC não serve mais este arquivo, a cópia é a
                          guardada no web.archive.org em 08/10/2022 (fica em dados/tec/fontes/)
    Anexo I   07/01/2023 e 02/04/2023  PDFs do Anexo I vigente
    Anexo II  20/02/2024
    Exceções  29/05/2024 (VI e IX) e 13/06/2024 (IV e V)
    Anexos I a X/XI  14/03/2025, 04/06/2025, 13/02/2026, 01/06/2026, 05/10/2026 e a vigente

O art. 7º da Res. Gecex 272/2021 (redação da Res. Gecex 353/2022) reduziu temporariamente a alíquota de
6.181 NCMs até 31/12/2023 (12,6% para 11,2% na maioria). Na versão de 01/09/2022 essas linhas têm
"Art. 7º" na fundamentação; de 01/01/2024 até a versão seguinte vale a TEC da própria linha.

Exceções: valem do início ao término informados; sem datas na planilha (Anexo IV), do primeiro arquivo em
que aparecem até a véspera do primeiro em que somem. Exceções que começaram e acabaram entre duas versões
lidas não aparecem (limite registrado no README).

Saída: dados/tec/tec_historico.csv
    ncm, aliquota_ii, vigencia_inicio, vigencia_fim (vazio = vigente), origem, ato, observacao

Uso:
    python scripts/tec_historico.py --dir PASTA   lê os arquivos já baixados na PASTA (nome = final da URL)
    python scripts/tec_historico.py               baixa tudo (do MDIC; o de 2022 do web.archive.org)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tec  # noqa: E402
from conv142 import USER_AGENT  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
INICIO = date(2022, 9, 1)
FIM_ART7 = date(2023, 12, 31)
MDIC = "https://www.gov.br/mdic/pt-br/assuntos/camex/estrategia-comercial/arquivos-listas/"
ARQUIVO_2022 = ("https://web.archive.org/web/20221008080332id_/https://www.gov.br/produtividade-e-comercio-exterior/"
                "pt-br/assuntos/camex/estrategia-comercial/arquivos-listas/Anexo_II_Res_272_2021.xlsx")

# (nome do arquivo, data de referência, tipo, URL)
VERSOES = [
    ("Anexo_II_Res_272_2021.xlsx", date(2022, 9, 1), "anexo_ii_2022", ARQUIVO_2022),
    ("anexo_i_20230107_vigente_res_412_e_413.pdf", date(2023, 1, 7), "anexo_i_pdf", MDIC + "anexo_i_20230107_vigente_res_412_e_413.pdf"),
    ("anexo_i_20230402_vigente_res-_440_2022.pdf", date(2023, 4, 2), "anexo_i_pdf", MDIC + "anexo_i_20230402_vigente_res-_440_2022.pdf"),
    ("2024-02-20-anexo-ii.xlsx", date(2024, 2, 20), "anexo_ii", MDIC + "2024-02-20-anexo-ii.xlsx"),
    ("2024-05-29-anexo-ix-dcc-1.xlsx", date(2024, 5, 29), "excecao:Anexo IX (DCC)", MDIC + "2024-05-29-anexo-ix-dcc-1.xlsx"),
    ("2024-05-29-anexo_vi_lebit_bk.xlsx", date(2024, 5, 29), "excecao:Anexo VI (LEBIT/BK)", MDIC + "2024-05-29-anexo_vi_lebit_bk.xlsx"),
    ("13-06-2024-anexo-iv-desabastecimento.xlsx", date(2024, 6, 13), "excecao:Anexo IV (desabastecimento)", MDIC + "13-06-2024-anexo-iv-desabastecimento.xlsx"),
    ("13-06-2024-anexo-v-letec.xlsx", date(2024, 6, 13), "excecao:Anexo V (LETEC)", MDIC + "13-06-2024-anexo-v-letec.xlsx"),
    ("14-03-2025-anexos-i-a-ix-resolucao-gecex-272-21.xlsx", date(2025, 3, 14), "completa", None),
    ("04-06-2025-anexos-i-a-ix-resolucao-gecex-272-21.xlsx", date(2025, 6, 4), "completa", None),
    ("13-02-2026-anexos-i-a-x-resolucao-gecex-272-21.xlsx", date(2026, 2, 13), "completa", None),
    ("01-06-2026-anexos-i-a-x-resolucao-gecex-272-21-1.xlsx", date(2026, 6, 1), "completa", None),
    ("05-10-2026-anexos-i-a-x-resolucao-gecex-272-21.xlsx", date(2026, 10, 5), "completa", None),
    ("11-11-2026-anexos-i-a-x-resolucao-gecex-272-21.xlsx", date(2026, 11, 11), "completa", None),
]
_PDF_LINHA = re.compile(r"^(\d{4}\.\d{2}\.\d{2})\s+(.*?)\s+(\d+(?:,\d+)?)\s*(BIT|BK)?$")
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


# ---------------------------------------------------------------- leitura de cada tipo de arquivo

def ler_xlsx_cru(bruto: bytes) -> list[list]:
    """Primeira aba pelo XML (o arquivo de 2022 tem um desenho quebrado que o openpyxl não abre)."""
    z = zipfile.ZipFile(io.BytesIO(bruto))
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss = ["".join(t.text or "" for t in si.iter(_NS + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_NS + "si")]
    folha = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))[0]
    linhas = []
    for row in ET.fromstring(z.read(folha)).iter(_NS + "row"):
        cel: dict[int, object] = {}
        for c in row.findall(_NS + "c"):
            col = 0
            for ch in re.match(r"[A-Z]+", c.get("r")).group(0):
                col = col * 26 + ord(ch) - 64
            v = c.find(_NS + "v")
            cel[col - 1] = None if v is None else (ss[int(v.text)] if c.get("t") == "s" else v.text)
        linhas.append([cel.get(i) for i in range(max(cel) + 1)] if cel else [])
    return linhas


def _ncm(v) -> str | None:
    d = re.sub(r"\D", "", str(v or ""))
    return d if len(d) == 8 and re.match(r"^\d{4}\.?\d{2}\.?\d{2}$", str(v).strip()) else None


def anexo_ii_de_linhas(linhas: list[list], ref: date, art7: bool) -> dict[str, dict]:
    """{ncm: {aliquota, tec, ato, art7}} da tabela do Anexo II (aplicada, senão TEC)."""
    i = next((k for k, l in enumerate(linhas) if l and str(l[0] or "").strip().upper() == "NCM"), None)
    if i is None:
        return {}
    cab = [str(c or "").strip().upper() for c in linhas[i]]
    col = lambda rx: next((k for k, c in enumerate(cab) if re.search(rx, c)), -1)
    i_apl, i_tec, i_fund, i_ato = col(r"APLICADA"), col(r"^TEC"), col(r"FUNDAMENTA"), col(r"^ATOS")
    out = {}
    for l in linhas[i + 1:]:
        n = _ncm(l[0] if l else None)
        if not n:
            continue
        g = lambda k: l[k] if 0 <= k < len(l) else None
        apl, tecv = tec.ler_aliquota(g(i_apl))[0], tec.ler_aliquota(g(i_tec))[0]
        if apl is None and tecv is None:
            continue
        fund = str(g(i_fund) or "").strip()
        ato = str(g(i_ato) or "").strip()
        out[n] = {"aliquota": apl if apl is not None else tecv, "tec": tecv, "art7": art7 and fund.startswith("Art. 7"),
                  "ato": ("Res. Gecex " + ato.replace(";", ",") if ato else "") + (f" ({fund})" if fund else "")}
    return out


def anexo_i_do_pdf(bruto: bytes) -> dict[str, float]:
    import pdfplumber

    out = {}
    with pdfplumber.open(io.BytesIO(bruto)) as pdf:
        for pg in pdf.pages:
            for l in (pg.extract_text() or "").splitlines():
                m = _PDF_LINHA.match(l.strip())
                if m:
                    out[m.group(1).replace(".", "")] = float(m.group(3).replace(",", "."))
    return out


def excecoes_da_aba(ws_linhas: list[tuple], rotulo: str) -> list[dict]:
    i = next((k for k, l in enumerate(ws_linhas) if l and str(l[0] or "").strip().upper() == "NCM"), None)
    if i is None:
        return []
    cab = [str(c or "").strip().upper() for c in ws_linhas[i]]
    col = lambda rx: next((k for k, c in enumerate(cab) if re.search(rx, c)), -1)
    i_ex, i_al, i_q = col(r"^N[ºO°] ?EX"), col(r"^AL[ÍI]QUOTA"), col(r"^QUOTA")
    i_ini, i_fim, i_ato = col(r"^IN[ÍI]CIO"), col(r"^T[ÉE]RMINO"), col(r"^ATO")
    out = []
    for l in ws_linhas[i + 1:]:
        n = _ncm(l[0] if l else None)
        if not n:
            continue
        g = lambda k: l[k] if 0 <= k < len(l) else None
        v = tec.ler_aliquota(g(i_al))[0]
        ex = "" if tec._vazio(g(i_ex)) else str(g(i_ex)).strip()
        out.append({"ncm": n, "rotulo": rotulo, "aliquota": v, "ex": ex, "quota": not tec._vazio(g(i_q)) if i_q >= 0 else False,
                    "ini": tec._data(g(i_ini)) if i_ini >= 0 else None, "fim": tec._data(g(i_fim)) if i_fim >= 0 else None,
                    "ato": "" if tec._vazio(g(i_ato)) else str(g(i_ato)).strip()})
    return out


def ler_completa(bruto: bytes) -> tuple[dict[str, float], dict[str, dict], list[dict]]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(bruto), read_only=True)
    aba = lambda p: next((ws for ws in wb.worksheets if ws.title.upper().startswith(p.upper())), None)
    a1 = {}
    for l in aba("Anexo I -").iter_rows(values_only=True):
        n = _ncm(l[0] if l else None)
        if n and len(l) > 2:
            v = tec.ler_aliquota(l[2])[0]
            if v is not None:
                a1[n] = v
    a2 = anexo_ii_de_linhas([list(r) for r in aba("Anexo II").iter_rows(values_only=True)], date.min, False)
    exc = []
    for prefixo, rotulo in tec.EXCECOES:
        ws = aba(prefixo)
        if ws is not None:
            exc += excecoes_da_aba(list(ws.iter_rows(values_only=True)), rotulo)
    return a1, a2, exc


# ---------------------------------------------------------------- linha do tempo

def montar(versoes: list[tuple[date, str, bytes]], hoje: date) -> list[dict]:
    """versoes: (data de referência, tipo, conteúdo), em ordem de data."""
    anexo_i: list[tuple[date, dict]] = []      # (desde, {ncm: aliquota})
    anexo_ii: list[tuple[date, dict]] = []     # (desde, {ncm: {...}})
    exc_por_versao: dict[str, list[tuple[date, list[dict]]]] = {}
    for ref, tipo, bruto in versoes:
        if tipo == "anexo_ii_2022":
            a2 = anexo_ii_de_linhas(ler_xlsx_cru(bruto), ref, True)
            anexo_ii.append((ref, a2))
            # fim do art. 7º: de 01/01/2024 vale a TEC da própria linha
            depois = {n: ({**x, "aliquota": x["tec"], "ato": "TEC da linha, após o fim do art. 7º em 31/12/2023"} if x["art7"] else x)
                      for n, x in a2.items()}
            anexo_ii.append((FIM_ART7 + timedelta(days=1), depois))
        elif tipo == "anexo_i_pdf":
            anexo_i.append((ref, anexo_i_do_pdf(bruto)))
        elif tipo == "anexo_ii":
            anexo_ii.append((ref, anexo_ii_de_linhas(ler_xlsx_cru(bruto), ref, False)))
        elif tipo.startswith("excecao:"):
            import openpyxl

            ws = openpyxl.load_workbook(io.BytesIO(bruto), read_only=True).worksheets[0]
            rotulo = tipo.split(":", 1)[1]
            exc_por_versao.setdefault(rotulo, []).append((ref, excecoes_da_aba(list(ws.iter_rows(values_only=True)), rotulo)))
        elif tipo == "completa":
            a1, a2, exc = ler_completa(bruto)
            anexo_i.append((ref, a1))
            anexo_ii.append((ref, a2))
            for rotulo in {e["rotulo"] for e in exc} | {r for _, r in tec.EXCECOES}:
                exc_por_versao.setdefault(rotulo, []).append((ref, [e for e in exc if e["rotulo"] == rotulo]))
    anexo_i.sort(key=lambda t: t[0])
    anexo_ii.sort(key=lambda t: t[0])

    # exceções: intervalo pelas datas da planilha ou pela presença nas versões
    excecoes: dict[str, list[dict]] = {}
    for rotulo, lista in exc_por_versao.items():
        lista.sort(key=lambda t: t[0])
        refs = [r for r, _ in lista]
        vistos: dict[tuple, dict] = {}
        for k, (ref, itens) in enumerate(lista):
            presentes = set()
            for e in itens:
                # a mesma exceção (NCM, Ex, quota, início) pode voltar corrigida numa versão seguinte
                # (39031120: 18% em 05/10/2026, 20% em 11/11/2026): vale o que a versão mais nova diz
                chave = (e["ncm"], e["ex"], e["quota"], e["ini"])
                presentes.add(chave)
                primeira = vistos[chave]["primeira"] if chave in vistos else ref
                vistos[chave] = {**e, "primeira": primeira, "ultima_k": k}
        for chave, e in vistos.items():
            ini = e["ini"] or e["primeira"]
            if e["fim"]:
                fim = e["fim"]
            elif e["ultima_k"] == len(lista) - 1:
                fim = None
            else:
                fim = refs[e["ultima_k"] + 1] - timedelta(days=1)
            excecoes.setdefault(e["ncm"], []).append({**e, "ini": ini, "fim": fim})

    def vigente_em(tabela, d):
        atual = None
        for desde, t in tabela:
            if desde <= d:
                atual = (desde, t)
        return atual

    ncms = set()
    for _, t in anexo_i:
        ncms |= set(t)
    for _, t in anexo_ii:
        ncms |= set(t)
    marcos_globais = sorted({INICIO} | {d for d, _ in anexo_i} | {d for d, _ in anexo_ii})
    saida = []
    for n in sorted(ncms):
        exs = excecoes.get(n, [])
        marcos = set(marcos_globais)
        for e in exs:
            marcos.add(max(e["ini"], INICIO))
            if e["fim"]:
                marcos.add(e["fim"] + timedelta(days=1))
        # datas futuras entram: exceção já publicada com término ou início marcado (vigência programada)
        marcos = sorted(m for m in marcos if INICIO <= m)
        segs = []
        for k, ini in enumerate(marcos):
            fim = marcos[k + 1] - timedelta(days=1) if k + 1 < len(marcos) else None
            a2 = vigente_em(anexo_ii, ini)
            a1 = vigente_em(anexo_i, ini)
            if a2 and n in a2[1]:
                x = a2[1][n]
                al, origem, ato = x["aliquota"], "Anexo II (aplicada)", x["ato"]
            elif a1 and n in a1[1]:
                al, origem, ato = a1[1][n], "Anexo I (TEC)", "Res. Gecex 272/2021, Anexo I"
            else:
                continue
            ativas = [e for e in exs if e["ini"] <= ini and (e["fim"] is None or e["fim"] >= ini)]
            inteiras = [e for e in ativas if not e["ex"] and not e["quota"] and e["aliquota"] is not None]
            if inteiras:
                e = max(inteiras, key=lambda e: e["ini"])
                al, origem, ato = e["aliquota"], e["rotulo"], e["ato"]
            obs = " | ".join(sorted({f"{e['rotulo']}: {'Ex ' + e['ex'] if e['ex'] else 'NCM'}{' com quota' if e['quota'] else ''} a "
                                     f"{tec._fmt(e['aliquota']).replace('.', ',') + '%' if e['aliquota'] is not None else '?'}"
                                     + (f" ({e['ato']})" if e["ato"] else "")
                                     for e in ativas if e not in inteiras}))
            seg = {"ncm": n, "aliquota_ii": tec._fmt(al), "vigencia_inicio": ini, "vigencia_fim": fim,
                   "origem": origem, "ato": ato, "observacao": obs}
            if segs and all(segs[-1][c] == seg[c] for c in ("aliquota_ii", "origem", "ato", "observacao")) \
                    and segs[-1]["vigencia_fim"] == ini - timedelta(days=1):
                segs[-1]["vigencia_fim"] = fim
            else:
                segs.append(seg)
        for s in segs:
            s["vigencia_inicio"] = s["vigencia_inicio"].isoformat()
            s["vigencia_fim"] = s["vigencia_fim"].isoformat() if s["vigencia_fim"] else ""
        saida += segs
    return saida


def aliquota_em(linhas: list[dict], ncm: str, d: str) -> dict | None:
    """Linha que vale para o NCM na data (AAAA-MM-DD)."""
    for l in linhas:
        if l["ncm"] == ncm and l["vigencia_inicio"] <= d and (not l["vigencia_fim"] or l["vigencia_fim"] >= d):
            return l
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, help="pasta com os arquivos já baixados")
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "tec")
    a = ap.parse_args(argv)
    import httpx

    hoje = date.today()
    cli = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True)
    fontes, versoes = [], []
    guardado_2022 = a.saida / "fontes" / VERSOES[0][0]
    for nome, ref, tipo, url in VERSOES:
        url = url or MDIC + nome
        arq = (a.dir / nome) if a.dir else None
        if arq and arq.exists():
            bruto = arq.read_bytes()
        elif tipo == "anexo_ii_2022" and guardado_2022.exists():
            bruto = guardado_2022.read_bytes()
        else:
            r = cli.get(url)
            r.raise_for_status()
            bruto = r.content
        if tipo == "anexo_ii_2022":
            guardado_2022.parent.mkdir(parents=True, exist_ok=True)
            guardado_2022.write_bytes(bruto)
        versoes.append((ref, tipo, bruto))
        fontes.append({"arquivo": nome, "referencia": ref.isoformat(), "tipo": tipo, "url": url, "sha256": hashlib.sha256(bruto).hexdigest()})
    # a versão vigente: a mesma planilha que o tec.py lê
    url_atual = tec.url_da_planilha(cli)
    nome_atual = url_atual.rsplit("/", 1)[-1]
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", nome_atual)
    ref_atual = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else hoje
    if not any(f["arquivo"] == nome_atual for f in fontes):
        arq = (a.dir / nome_atual) if a.dir else None
        bruto = arq.read_bytes() if arq and arq.exists() else cli.get(url_atual).content
        versoes.append((ref_atual, "completa", bruto))
        fontes.append({"arquivo": nome_atual, "referencia": ref_atual.isoformat(), "tipo": "completa", "url": url_atual,
                       "sha256": hashlib.sha256(bruto).hexdigest()})
    versoes.sort(key=lambda v: v[0])
    linhas = montar(versoes, hoje)
    a.saida.mkdir(parents=True, exist_ok=True)
    campos = ["ncm", "aliquota_ii", "vigencia_inicio", "vigencia_fim", "origem", "ato", "observacao"]
    with (a.saida / "tec_historico.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    meta = {"fonte": "MDIC/Camex, versões publicadas dos Anexos da Res. Gecex 272/2021", "inicio_da_cobertura": INICIO.isoformat(),
            "regra": "exceção vigente para o NCM inteiro > Anexo II (aplicada) > Anexo I (TEC); cada versão vale da sua data até a véspera da seguinte",
            "versoes": fontes, "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": hoje.isoformat(),
            "contagens": {"linhas": len(linhas), "ncms": len({l["ncm"] for l in linhas})}}
    (a.saida / "historico_fontes.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

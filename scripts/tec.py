"""TEC: alíquota do Imposto de Importação por NCM (Resolução Gecex 272/2021, Anexos I a XI), da planilha oficial.

O MDIC/Camex publica na página "Tarifas Vigentes" uma planilha com os anexos da Resolução Gecex 272/2021:

    Anexo I     TEC do Mercosul (alíquota de cada NCM; marca BIT ou BK)
    Anexo II    tarifas brasileiras diferentes da TEC (alíquota aplicada no Brasil)
    Anexo IV    reduções por desabastecimento        Anexo V    LETEC
    Anexo VI    LEBIT/BK                              Anexo VIII concessões OMC
    Anexo IX    elevações (DCC)                       Anexo X    automotivos ACE-14
    Anexo XI    LETEC temporária

A nota do Anexo X diz que as exceções temporárias prevalecem. Este script monta, para cada NCM de 8 dígitos,
a alíquota que vale hoje: exceção vigente que vale para o NCM inteiro (sem Ex e sem quota) > Anexo II >
Anexo I. As exceções com Ex ou com quota não mudam a alíquota do NCM (dependem do produto ou do saldo da
quota) e vão em texto, só como aviso. Mesma regra do leitor em custo-importacao-br/src/aliquotas.ts.

Saída (dados/tec/):
    tec.csv          um NCM por linha: ncm, descricao, ii_tec, ii_aplicada, ii_vigente, fonte_ii_vigente,
                     bit_bk, excecoes, vigencia_planilha
    metadados.json   fonte, URL da planilha, sha256, "atualizado até" de cada anexo, contagens

Uso:
    python scripts/tec.py                  acha a planilha na página do MDIC e baixa
    python scripts/tec.py --xlsx ARQ.xlsx  usa a planilha salva
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
PAGINA = "https://www.gov.br/mdic/pt-br/assuntos/camex/se-camex/strat/tarifas/vigentes"
_LINK = re.compile(r'href="([^"]*anexos-i-a-x[^"]*resolucao-gecex-272[^"]*\.xlsx)"', re.I)
_NCM8 = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")
_ATUALIZADO = re.compile(r"Atualizad[oa] at[ée] (?:a )?Resolu[çc][ãa]o Gecex n[ºo°]\s*(\d+)(?:,? de ([^*]+?\d{4}))?", re.I)

EXCECOES = [  # (início do nome da aba, rótulo)
    ("Anexo IV -", "Anexo IV (desabastecimento)"),
    ("Anexo V -", "Anexo V (LETEC)"),
    ("Anexo VI -", "Anexo VI (LEBIT/BK)"),
    ("Anexo VIII -", "Anexo VIII (OMC)"),
    ("Anexo IX -", "Anexo IX (DCC)"),
    ("Anexo X -", "Anexo X (automotivos ACE-14)"),
    ("Anexo XI -", "Anexo XI (LETEC temporária)"),
]


def ler_aliquota(valor) -> tuple[float | None, str]:
    """'12.6' -> (12.6, ''); '12,6BK' -> (12.6, 'BK'); '0BIT' -> (0.0, 'BIT'); número do Excel também vale."""
    if valor is None:
        return None, ""
    if isinstance(valor, (int, float)):
        return float(valor), ""
    t = str(valor).strip().upper()
    marca = "BIT" if "BIT" in t else "BK" if "BK" in t else ""
    n = re.sub(r"[A-Z\s%]", "", t).replace(",", ".")
    try:
        return (float(n), marca) if n else (None, marca)
    except ValueError:
        return None, marca


def _fmt(v: float | None) -> str:
    return "" if v is None else f"{v:g}"


def _data(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", t) or None
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", t)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _vazio(v) -> bool:
    return v is None or str(v).strip() in ("", "-")


def _tabela(ws) -> tuple[list[str], list[tuple]]:
    """Cabeçalho (linha que começa com 'NCM') e as linhas seguintes."""
    linhas = list(ws.iter_rows(values_only=True))
    for i, l in enumerate(linhas):
        if l and str(l[0] or "").strip().upper() == "NCM":
            return [str(c or "").strip().upper() for c in l], linhas[i + 1:]
    return [], []


def _col(cab: list[str], padrao: str) -> int:
    return next((i for i, c in enumerate(cab) if re.search(padrao, c)), -1)


def ler_planilha(bruto: bytes, hoje: date) -> tuple[dict[str, dict], dict[str, str]]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(bruto), read_only=True)
    aba = lambda prefixo: next((ws for ws in wb.worksheets if ws.title.upper().startswith(prefixo.upper())), None)
    atualizado = {}
    for ws in wb.worksheets:
        for l in ws.iter_rows(values_only=True, max_row=3):
            m = _ATUALIZADO.search(str(l[0] or "")) if l else None
            if m:
                atualizado[ws.title] = f"Res. Gecex nº {m.group(1)}" + (f", de {m.group(2).strip()}" if m.group(2) else "")
                break

    ncms: dict[str, dict] = {}
    for l in aba("Anexo I -").iter_rows(values_only=True):
        if not l or not _NCM8.match(str(l[0] or "").strip()):
            continue
        v, marca = ler_aliquota(l[2] if len(l) > 2 else None)
        n = str(l[0]).strip().replace(".", "")
        ncms[n] = {"ncm": n, "descricao": re.sub(r"\s+", " ", str(l[1] or "")).strip(), "ii_tec": v, "ii_aplicada": None,
                   "ii_vigente": v, "fonte_ii_vigente": "Anexo I (TEC)", "bit_bk": marca, "excecoes": []}

    cab, linhas = _tabela(aba("Anexo II"))
    i_apl, i_tec = _col(cab, r"APLICADA"), _col(cab, r"^TEC")
    for l in linhas:
        if not l or not _NCM8.match(str(l[0] or "").strip()):
            continue
        v = ler_aliquota(l[i_apl])[0] if i_apl >= 0 else None
        if v is None and i_tec >= 0:
            v = ler_aliquota(l[i_tec])[0]
        if v is None:
            continue
        n = str(l[0]).strip().replace(".", "")
        x = ncms.setdefault(n, {"ncm": n, "descricao": str(l[1] or "").strip(), "ii_tec": None, "ii_aplicada": None,
                                "ii_vigente": None, "fonte_ii_vigente": "", "bit_bk": "", "excecoes": []})
        x["ii_aplicada"], x["ii_vigente"], x["fonte_ii_vigente"] = v, v, "Anexo II (aplicada)"

    for prefixo, rotulo in EXCECOES:
        ws = aba(prefixo)
        if ws is None:
            continue
        cab, linhas = _tabela(ws)
        i_ex, i_al, i_q = _col(cab, r"^N[ºO°] ?EX"), _col(cab, r"^AL[ÍI]QUOTA"), _col(cab, r"^QUOTA")
        i_ini, i_fim, i_ato = _col(cab, r"^IN[ÍI]CIO"), _col(cab, r"^T[ÉE]RMINO"), _col(cab, r"^ATO")
        for l in linhas:
            if not l or not _NCM8.match(str(l[0] or "").strip()):
                continue
            ini = _data(l[i_ini]) if i_ini >= 0 else None
            fim = _data(l[i_fim]) if i_fim >= 0 else None
            if (ini and ini > hoje) or (fim and fim < hoje):
                continue
            v = ler_aliquota(l[i_al])[0] if i_al >= 0 else None
            ex = "" if i_ex < 0 or _vazio(l[i_ex]) else str(l[i_ex]).strip()
            quota = i_q >= 0 and not _vazio(l[i_q])
            ato = str(l[i_ato]).strip() if i_ato >= 0 and not _vazio(l[i_ato]) else ""
            n = str(l[0]).strip().replace(".", "")
            x = ncms.get(n)
            if x is None:
                continue
            if not ex and not quota and v is not None:
                x["ii_vigente"] = v
                x["fonte_ii_vigente"] = rotulo + (f", {ato}" if ato else "") + (f", até {fim.isoformat()}" if fim else "")
            else:
                aviso = (f"{rotulo}: {'Ex ' + ex if ex else 'NCM'}{' com quota' if quota else ''} a "
                         f"{_fmt(v).replace('.', ',') + '%' if v is not None else '?'}" + (f" ({ato})" if ato else ""))
                if aviso not in x["excecoes"]:
                    x["excecoes"].append(aviso)
    return ncms, atualizado


def url_da_planilha(cliente) -> str:
    r = cliente.get(PAGINA)
    r.raise_for_status()
    m = _LINK.search(r.text)
    if not m:
        raise SystemExit(f"planilha dos Anexos da Res. Gecex 272/2021 não encontrada em {PAGINA}")
    return m.group(1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xlsx", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "tec")
    a = ap.parse_args(argv)
    if a.xlsx:
        bruto, url = a.xlsx.read_bytes(), a.xlsx.name
    else:
        import httpx

        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True) as cli:
            url = url_da_planilha(cli)
            r = cli.get(url)
            r.raise_for_status()
            bruto = r.content
    hoje = date.today()
    ncms, atualizado = ler_planilha(bruto, hoje)
    if len(ncms) < 9000:
        raise SystemExit(f"leitura curta: {len(ncms)} NCMs; a planilha mudou?")
    vig = "; ".join(f"{k.split(' -')[0]}: {v}" for k, v in atualizado.items() if k.upper().startswith(("ANEXO I -", "ANEXO II -")))
    a.saida.mkdir(parents=True, exist_ok=True)
    campos = ["ncm", "descricao", "ii_tec", "ii_aplicada", "ii_vigente", "fonte_ii_vigente", "bit_bk", "excecoes", "vigencia_planilha"]
    with (a.saida / "tec.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for n in sorted(ncms):
            x = ncms[n]
            w.writerow({**x, "ii_tec": _fmt(x["ii_tec"]), "ii_aplicada": _fmt(x["ii_aplicada"]), "ii_vigente": _fmt(x["ii_vigente"]),
                        "excecoes": " | ".join(x["excecoes"]), "vigencia_planilha": vig})
    meta = {"fonte": "MDIC/Camex, Anexos I a XI da Resolução Gecex 272/2021 (página Tarifas Vigentes)", "pagina": PAGINA,
            "url": url, "sha256": hashlib.sha256(bruto).hexdigest(), "atualizado_ate": atualizado,
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_referencia": hoje.isoformat(),
            "regra": "ii_vigente = exceção vigente para o NCM inteiro (sem Ex e sem quota) > Anexo II > Anexo I",
            "contagens": {"ncms": len(ncms), "com_anexo_ii": sum(x["ii_aplicada"] is not None for x in ncms.values()),
                          "com_excecao_no_ncm_inteiro": sum(not x["fonte_ii_vigente"].startswith(("Anexo I ", "Anexo II ")) for x in ncms.values()),
                          "com_aviso_de_ex_ou_quota": sum(bool(x["excecoes"]) for x in ncms.values()),
                          "bk": sum(x["bit_bk"] == "BK" for x in ncms.values()), "bit": sum(x["bit_bk"] == "BIT" for x in ncms.values())}}
    (a.saida / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

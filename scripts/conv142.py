"""Convênio ICMS 142/2018 em dados estruturados, com vigência por redação.

Lê a página consolidada do Confaz e devolve uma linha por redação de cada
item dos Anexos II a XXVI (bens sujeitos à ST, com CEST, NCM/SH e descrição),
além dos segmentos (Anexo I) e da lista do Anexo XXVII (escala industrial não
relevante).

Como a página marca a história de cada item:

    <nota>  Nova redação dada ao item 42.0 do Anexo II pelo Conv. ICMS 66/22,
            efeitos a partir de 02.05.22.
    <linha> 42.0 | 01.042.00 | 8421.32.00 | Depuradores ...        (vigente)
    <nota>  Redação original, efeitos até 01.05.22.
    <linha> 42.0 | 01.042.00 | 8421.39.20 | Depuradores ...        (verde: anterior)

As notas são texto livre, com erros de digitação ("sem feitos", "item14"),
por isso as regras abaixo são tolerantes e tudo o que não puder ser associado
vai para a lista de notas não associadas, que é conferida a cada versão.

Uso:
    python scripts/conv142.py                    baixa do Confaz e grava em dados/conv142
    python scripts/conv142.py --html pagina.html usa um HTML salvo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

URL = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
RAIZ = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- utilidades

_DATA = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
_NORMA = re.compile(r"Conv(?:[êe]nio)?\.?\s*ICMS\s*(\d+)\s*/\s*(\d{2,4})", re.I)
_CEST = re.compile(r"^\d{2}\.\d{3}\.\d{2}$")
_ROMANOS = {"I": 1, "V": 5, "X": 10, "L": 50}


def texto(el) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", el.text_content()).strip())


def romano(s: str) -> int:
    total = 0
    for i, ch in enumerate(s):
        v = _ROMANOS[ch]
        total += -v if i + 1 < len(s) and _ROMANOS[s[i + 1]] > v else v
    return total


def datas(s: str) -> list[date]:
    saida = []
    for d, m, a in _DATA.findall(s):
        ano = int(a) + (2000 if len(a) == 2 else 0)
        try:
            saida.append(date(ano, int(m), int(d)))
        except ValueError:
            pass
    return saida


def norma(s: str) -> str | None:
    m = _NORMA.search(s)
    if not m:
        return None
    ano = m.group(2)
    return f"Conv. ICMS {int(m.group(1))}/{ano[-2:]}"


def chave_item(item: str) -> str:
    """'42.0' e '42' são o mesmo item; '1.1' não é '11'."""
    item = item.strip().rstrip(".")
    return item[:-2] if item.endswith(".0") else item


def itens_citados(nota: str) -> set[str]:
    """Números de item citados numa nota: 'itens 21.1, 21.2 e 21.4', 'itens 5.2 a 5.5'."""
    m = re.search(r"\bite(?:m|ns)\s*([\d.,\se a]+?)(?=\s*(?:do|ao|em|pelo|no|da|,\s*efeitos)\b|$)", nota, re.I)
    if not m:
        return set()
    trecho = m.group(1)
    achados: set[str] = set()
    for ini, fim in re.findall(r"(\d+(?:\.\d+)?)\s+a\s+(\d+(?:\.\d+)?)", trecho):
        a, b = ini.split("."), fim.split(".")
        if len(a) == 2 and len(b) == 2 and a[0] == b[0]:
            for k in range(int(a[1]), int(b[1]) + 1):
                achados.add(chave_item(f"{a[0]}.{k}"))
        else:
            achados.update({chave_item(ini), chave_item(fim)})
    for n in re.findall(r"\d+(?:\.\d+)?", trecho):
        achados.add(chave_item(n))
    return achados


# ---------------------------------------------------------------- modelo

@dataclass
class Nota:
    texto: str
    tipo: str                 # nova_redacao | acrescimo | revogacao | anterior | outra
    inicio: date | None = None
    fim: date | None = None
    sem_efeitos: bool = False
    norma: str | None = None
    itens: set[str] = field(default_factory=set)
    usada: bool = False


@dataclass
class Redacao:
    anexo: str
    anexo_num: int
    segmento_codigo: str
    segmento: str
    item: str
    cest: str
    ncm_sh: str
    descricao: str
    origem: str               # vigente_no_texto | anterior_no_texto
    vigencia_inicio: date | None
    vigencia_fim: date | None
    sem_efeitos: bool
    revogado_em: date | None
    norma_alteradora: str | None
    nota_alteracao: str | None
    nota_vigencia: str | None
    situacao: str = ""

    def calcular_situacao(self, ref: date) -> None:
        if self.sem_efeitos:
            self.situacao = "sem_efeitos"
        elif self.vigencia_inicio and self.vigencia_inicio > ref:
            self.situacao = "futura"
        elif self.vigencia_fim and self.vigencia_fim < ref:
            self.situacao = "revogada" if self.revogado_em else "anterior"
        else:
            self.situacao = "vigente"


def ler_nota(txt: str, classe: str) -> Nota:
    t = txt.strip().lstrip("x")
    baixo = t.lower()
    ds = datas(t)
    n = Nota(texto=txt, tipo="outra", norma=norma(t), itens=itens_citados(t))
    anterior = classe.startswith("A8-2") or baixo.startswith(("redação original", "redação anterior"))
    if "sem efeito" in baixo or "sem feito" in baixo:
        n.tipo, n.sem_efeitos = "anterior", True
        return n
    if anterior or ("a partir" not in baixo and ("até" in baixo or len(ds) >= 2)):
        n.tipo = "anterior"
        if len(ds) >= 2:
            n.inicio, n.fim = ds[0], ds[-1]
        elif ds:
            if "até" in baixo:
                n.fim = ds[0]
            else:
                n.inicio = ds[0]
        return n
    if baixo.startswith("revogad"):
        n.tipo = "revogacao"
    elif "acrescid" in baixo:
        n.tipo = "acrescimo"
    elif "redação" in baixo:
        n.tipo = "nova_redacao"
    if ds:
        n.inicio = ds[0]
    return n


# ---------------------------------------------------------------- leitura

def _classe_linha(tr) -> str:
    classes = " ".join(tr.xpath(".//p/@class"))
    if "A8-1" in classes or "A8-2" in classes or "A8-3" in classes:
        return "nota"
    if "A9-" in classes:
        return "anterior"
    if "Subtitulo" in classes:
        return "titulo"
    return "vigente"


def ler_html(pagina: str, ref: date) -> dict:
    from lxml import html

    conteudo = html.fromstring(pagina).xpath("//*[@id='content']")
    if not conteudo:
        raise SystemExit("estrutura da página mudou: #content não encontrado")
    raiz = conteudo[0]

    segmentos: dict[int, dict] = {}
    redacoes: list[Redacao] = []
    escala: list[dict] = []
    notas_soltas: list[dict] = []
    repetidas: list[dict] = []
    divergencias: list[dict] = []

    anexo, titulo_anexo = None, []
    for el in raiz.iter("p", "table"):
        if el.tag == "p":
            if el.xpath("ancestor::table"):
                continue
            if "A6-1Subtitulo" in (el.get("class") or ""):
                t = texto(el)
                m = re.match(r"^ANEXO ([IVXL]+)\b", t)
                if m:
                    anexo, titulo_anexo = m.group(1), []
                else:
                    titulo_anexo.append(t)
            continue
        if anexo is None:
            continue
        num = romano(anexo)
        if num == 1:
            for tr in el.xpath(".//tr")[1:]:
                cel = [texto(td) for td in tr.xpath("./td|./th")]
                if len(cel) == 3 and cel[2].isdigit():
                    segmentos[int(cel[2])] = {"item": cel[0], "segmento": cel[1], "codigo": cel[2].zfill(2)}
            continue
        if 2 <= num <= 27:
            _ler_tabela(el, anexo, num, " ".join(titulo_anexo), segmentos, redacoes, escala, notas_soltas, repetidas,
                        divergencias)

    for r in redacoes:
        r.calcular_situacao(ref)
    return {"segmentos": segmentos, "redacoes": redacoes, "escala": escala, "notas_soltas": notas_soltas,
            "repetidas": repetidas, "divergencias": divergencias}


def _segmento(segmentos: dict, cest: str, titulo: str) -> dict:
    # Os dois primeiros dígitos do CEST são o código do segmento do Anexo I
    # (os códigos têm lacunas, então não dá para deduzir pelo número do anexo).
    return segmentos.get(int(cest[:2]), {"codigo": cest[:2], "segmento": titulo})


def _ler_tabela(tabela, anexo, num, titulo, segmentos, redacoes, escala, notas_soltas, repetidas, divergencias) -> None:
    nota_atual: Nota | None = None      # nota que precede linhas vigentes
    bloco_ant: set[str] = set()         # itens cujas próximas linhas são redações anteriores
    ultimo_vigente: str | None = None
    nota_colada = False                 # a linha anterior foi uma nota de nova redação/acréscimo
    nota_ant: Nota | None = None        # nota que precede linhas anteriores (verdes)
    revogacao: Nota | None = None
    subgrupo = ""

    def descartar(n: Nota | None):
        if n is not None and not n.usada and num != 27:
            notas_soltas.append({"anexo": anexo, "nota": n.texto})

    anterior_txt = None
    for tr in tabela.xpath(".//tr"):
        tipo = _classe_linha(tr)
        cel = [texto(td) for td in tr.xpath("./td|./th")]
        while cel and cel[-1] == "":
            cel.pop()
        # A página repete algumas linhas (itens e notas) duas vezes seguidas.
        assinatura = (tipo, tuple(cel))
        if assinatura == anterior_txt:
            repetidas.append({"anexo": anexo, "linha": " | ".join(cel)})
            continue
        anterior_txt = assinatura
        if cel and cel[0].upper() == "ITEM":
            continue
        dado = len(cel) >= 2 and (_CEST.match(cel[1]) or cel[1].upper() == "REVOGADO")
        if tipo == "titulo" and not dado:
            if num == 27 and len(cel) == 1:
                subgrupo = cel[0]
            continue
        if tipo == "titulo":
            tipo = "vigente"  # linha de item com a classe de título por descuido de formatação
        if tipo == "nota":
            n = ler_nota(" ".join(cel), " ".join(tr.xpath(".//p/@class")))
            nota_colada = n.tipo in ("nova_redacao", "acrescimo")
            if n.tipo == "anterior":
                nota_ant = n
                # As linhas seguintes do mesmo item são redações anteriores,
                # mesmo que a página as tenha formatado como vigentes.
                bloco_ant = n.itens or ({ultimo_vigente} if ultimo_vigente else set())
                if revogacao is not None:
                    revogacao.usada = True  # a nota de vigência vem logo depois da revogação
            elif n.tipo == "revogacao":
                descartar(nota_atual)
                nota_atual, revogacao, nota_ant = None, n, None
            elif n.tipo == "outra" and num != 27:
                notas_soltas.append({"anexo": anexo, "nota": n.texto})
            else:
                descartar(nota_atual)
                nota_atual, revogacao, nota_ant = n, None, None
            continue
        # Item revogado: a página mantém uma linha "REVOGADO" no lugar do item.
        # É só um marcador; a redação que valia vem depois, em verde.
        if tipo == "vigente" and len(cel) >= 2 and "REVOGADO" in (c.upper() for c in cel[1:]):
            if revogacao is not None:
                revogacao.itens.add(chave_item(cel[0]))
            else:
                notas_soltas.append({"anexo": anexo, "nota": "linha REVOGADO sem nota de revogação: " + " | ".join(cel)})
            continue
        if len(cel) < 4 or not _CEST.match(cel[1]):
            if num == 27 and len(cel) == 1 and cel[0]:
                subgrupo = cel[0]
            continue

        item, cest, ncm, desc = cel[0], cel[1], cel[2], " ".join(cel[3:])
        if num == 27:
            if tipo == "vigente":
                escala.append({"subgrupo": subgrupo, "item": item, "cest": cest, "ncm_sh": ncm, "descricao": desc})
            continue

        k = chave_item(item)
        seg = _segmento(segmentos, cest, titulo)
        colada, nota_colada = nota_colada, False
        if tipo == "vigente" and k in bloco_ant:
            tipo = "anterior"
            divergencias.append({"anexo": anexo, "item": item, "cest": cest,
                                 "problema": "redação anterior formatada como vigente na página; tratada como anterior"})
        elif tipo == "vigente":
            bloco_ant = set()
        if tipo == "vigente":
            n = None
            if nota_atual is not None and (k in nota_atual.itens or (not nota_atual.itens and not nota_atual.usada)):
                n = nota_atual
                n.usada = True
            elif nota_atual is not None and not nota_atual.usada and colada:
                # Nota imediatamente antes da linha, mas citando outro item (erro de cópia na página).
                n = nota_atual
                n.usada = True
                divergencias.append({"anexo": anexo, "item": item, "cest": cest,
                                     "problema": f"nota colada na linha cita outro item: {n.texto}"})
            elif nota_atual is not None and nota_atual.usada:
                nota_atual = None
            revogacao, nota_ant = None, None
            ultimo_vigente = k
            redacoes.append(Redacao(
                anexo=anexo, anexo_num=num, segmento_codigo=seg["codigo"], segmento=seg["segmento"],
                item=item, cest=cest, ncm_sh=ncm, descricao=desc, origem="vigente_no_texto",
                vigencia_inicio=n.inicio if n else None, vigencia_fim=None, sem_efeitos=False,
                revogado_em=None, norma_alteradora=n.norma if n else None,
                nota_alteracao=n.texto if n else None, nota_vigencia=None))
        else:  # anterior
            ini = nota_ant.inicio if nota_ant else None
            fim = nota_ant.fim if nota_ant else None
            sem = nota_ant.sem_efeitos if nota_ant else False
            if nota_ant:
                nota_ant.usada = True
            revog = None
            if revogacao is not None and (not revogacao.itens or k in revogacao.itens):
                revog = revogacao.inicio
                revogacao.usada = True
                if fim is None and revog:
                    fim = revog - timedelta(days=1)
            if fim is None and not sem:
                # redação anterior sem data final: termina na véspera da redação vigente do mesmo item
                atual = next((r for r in reversed(redacoes)
                              if r.anexo == anexo and chave_item(r.item) == k and r.origem == "vigente_no_texto"), None)
                if atual and atual.vigencia_inicio:
                    fim = atual.vigencia_inicio - timedelta(days=1)
            redacoes.append(Redacao(
                anexo=anexo, anexo_num=num, segmento_codigo=seg["codigo"], segmento=seg["segmento"],
                item=item, cest=cest, ncm_sh=ncm, descricao=desc, origem="anterior_no_texto",
                vigencia_inicio=ini, vigencia_fim=fim, sem_efeitos=sem, revogado_em=revog,
                norma_alteradora=revogacao.norma if revog else None,
                nota_alteracao=revogacao.texto if revog else None,
                nota_vigencia=nota_ant.texto if nota_ant else None))
    descartar(nota_atual)
    if revogacao is not None and not revogacao.usada and num != 27:
        notas_soltas.append({"anexo": anexo, "nota": revogacao.texto})


# ---------------------------------------------------------------- validação

def validar(dados: dict) -> list[str]:
    avisos = []
    reds = dados["redacoes"]
    prefixos: dict[str, set[str]] = {}
    for r in reds:
        prefixos.setdefault(r.anexo, set()).add(r.cest[:2])
        if int(r.cest[:2]) not in dados["segmentos"]:
            avisos.append(f"CEST {r.cest} (Anexo {r.anexo}) sem segmento correspondente no Anexo I")
    for anexo, ps in prefixos.items():
        if len(ps) > 1:
            avisos.append(f"Anexo {anexo} mistura segmentos: {sorted(ps)}")
    for r in reds:
        if r.vigencia_inicio and r.vigencia_fim and r.vigencia_fim < r.vigencia_inicio:
            avisos.append(f"vigência invertida: Anexo {r.anexo} item {r.item} ({r.vigencia_inicio} a {r.vigencia_fim})")
    vigentes: dict[str, list[Redacao]] = {}
    for r in reds:
        if r.situacao == "vigente":
            vigentes.setdefault(r.cest, []).append(r)
    for cest, rs in vigentes.items():
        if len(rs) > 1:
            avisos.append(f"CEST {cest} com {len(rs)} redações vigentes ao mesmo tempo (Anexo {rs[0].anexo}, itens "
                          + ", ".join(r.item for r in rs) + ")")
    return avisos


# ---------------------------------------------------------------- gravação

def _iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def gravar(dados: dict, destino: Path, meta: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    cols = ["anexo", "segmento_codigo", "segmento", "item", "cest", "ncm_sh", "ncms", "descricao", "situacao",
            "vigencia_inicio", "vigencia_fim", "revogado_em", "norma_alteradora", "origem",
            "nota_alteracao", "nota_vigencia"]
    ordenadas = sorted(dados["redacoes"], key=lambda r: (r.anexo_num, r.cest, r.vigencia_inicio or date.min))

    def linha(r: Redacao) -> dict:
        d = asdict(r)
        d.update(vigencia_inicio=_iso(r.vigencia_inicio), vigencia_fim=_iso(r.vigencia_fim),
                 revogado_em=_iso(r.revogado_em), ncms=";".join(r.ncm_sh.split()))
        return {c: d.get(c) or "" for c in cols}

    with open(destino / "itens_historico.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(linha(r) for r in ordenadas)
    vig = [r for r in ordenadas if r.situacao == "vigente"]
    cols_vig = ["anexo", "segmento_codigo", "segmento", "item", "cest", "ncm_sh", "ncms", "descricao",
                "vigencia_inicio", "norma_alteradora"]
    with open(destino / "itens_vigentes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols_vig, extrasaction="ignore")
        w.writeheader()
        w.writerows(linha(r) for r in vig)
    with open(destino / "segmentos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["codigo", "segmento", "anexo"])
        w.writeheader()
        anexo_de = {r.segmento_codigo: r.anexo for r in dados["redacoes"]}
        for cod, s in sorted(dados["segmentos"].items()):
            w.writerow({"codigo": s["codigo"], "segmento": s["segmento"], "anexo": anexo_de.get(s["codigo"], "")})
    with open(destino / "escala_nao_relevante_anexo_xxvii.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["subgrupo", "item", "cest", "ncm_sh", "descricao"])
        w.writeheader()
        w.writerows(dados["escala"])
    with open(destino / "divergencias_da_fonte.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["anexo", "item", "cest", "problema"])
        w.writeheader()
        w.writerows(dados["divergencias"])
    with open(destino / "notas_nao_associadas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["anexo", "nota"])
        w.writeheader()
        w.writerows(dados["notas_soltas"])

    contagem = {}
    for r in ordenadas:
        contagem[r.situacao] = contagem.get(r.situacao, 0) + 1
    resumo = {
        **meta,
        "redacoes": len(ordenadas),
        "por_situacao": contagem,
        "cests_vigentes": len({r.cest for r in vig}),
        "segmentos": len(dados["segmentos"]),
        "itens_anexo_xxvii": len(dados["escala"]),
        "notas_nao_associadas": len(dados["notas_soltas"]),
        "linhas_repetidas_na_pagina": len(dados["repetidas"]),
        "divergencias_da_fonte": len(dados["divergencias"]),
        "avisos_validacao": validar(dados),
    }
    with open(destino / "itens_historico.json", "w", encoding="utf-8") as f:
        json.dump([linha(r) for r in ordenadas], f, ensure_ascii=False, indent=1)
    with open(destino / "metadados.json", "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    return resumo


def _romano_de(n: int) -> str:
    saida = ""
    for v, s in [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]:
        while n >= v:
            saida, n = saida + s, n - v
    return saida


def baixar() -> bytes:
    import httpx
    r = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True)
    r.raise_for_status()
    return r.content


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--html", type=Path, help="HTML salvo da página do Confaz")
    p.add_argument("--ref", help="data de referência para a situação (AAAA-MM-DD); padrão: hoje")
    p.add_argument("--saida", type=Path, default=RAIZ / "dados" / "conv142")
    a = p.parse_args(argv)
    bruto = a.html.read_bytes() if a.html else baixar()
    ref = date.fromisoformat(a.ref) if a.ref else date.today()
    dados = ler_html(bruto.decode("utf-8", errors="replace"), ref)
    meta = {
        "fonte": URL,
        "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256_pagina": hashlib.sha256(bruto).hexdigest(),
        "data_referencia_situacao": ref.isoformat(),
    }
    resumo = gravar(dados, a.saida, meta)
    print(json.dumps({k: v for k, v in resumo.items() if k != "avisos_validacao"}, ensure_ascii=False, indent=2))
    for av in resumo["avisos_validacao"]:
        print("AVISO:", av)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

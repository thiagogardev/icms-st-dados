"""Protocolos ICMS de substituição tributária em dados estruturados, com vigência.

Primeiro conjunto: os 11 protocolos de materiais de construção, acabamento,
bricolagem ou adorno de que São Paulo é signatário. Para cada protocolo, lê a
página consolidada do Confaz e devolve uma linha por redação de cada item do
anexo (NCM/SH, descrição e MVA original, quando o protocolo a fixa), com início
e fim de vigência. Depois monta a matriz "remetente em SP -> destino": quais
itens têm retenção na origem, para qual estado, por qual protocolo.

A página de cada protocolo segue o mesmo desenho do Convênio 142:

    <nota Remissão>        Item 62 revogado pelo Prot. ICMS 76/26, efeitos a partir de 01.08.26.
    <linha>                62 | REVOGADO
    <nota Remissão ant.>   Redação original, efeitos até 31.07.26.
    <linha verde>          62 | 7411.10.10 | Tubos de cobre ... | 35

e as redações antigas do anexo inteiro ficam em tabelas próprias, precedidas
de uma nota como "Redação original, efeitos até 31.12.25".

Uso:
    python scripts/protocolos.py                 baixa do Confaz e grava em dados/protocolos
    python scripts/protocolos.py --html-dir DIR  usa HTMLs salvos (pt011_08.html etc.)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conv142 import USER_AGENT, Nota, chave_item, datas, itens_citados, texto  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
BASE_URL = "https://www.confaz.fazenda.gov.br/legislacao/protocolos/"

# Protocolos de materiais de construção com SP. "destinos_de_sp": estados para os
# quais o remetente paulista retém a ST. Em vários deles a aplicação nas entradas em
# SP depende de ato do Secretário da Fazenda que nunca foi editado (Comunicado CAT
# 36/2009), por isso a matriz_sp_destino só tem o sentido SP -> destino. A matriz
# origem -> destino lista todos os sentidos que a cláusula primeira cita, e marca as
# linhas com destino SP em "efeito_no_destino".
EFEITO_SP = "depende de ato do Secretário da Fazenda de SP não editado (Comunicado CAT 36/2009)"
PROTOCOLOS = [
    {"protocolo": "11/08", "pagina": "2008/pt011_08", "signatarios": ["MT", "SP"], "destinos_de_sp": ["MT"]},
    {"protocolo": "20/13", "pagina": "2013/pt020_13", "signatarios": ["ES", "SP"], "destinos_de_sp": ["ES"]},
    {"protocolo": "25/11", "pagina": "2011/pt025_11", "signatarios": ["DF", "SP"], "destinos_de_sp": ["DF"]},
    {"protocolo": "32/09", "pagina": "2009/pt032_09", "signatarios": ["MG", "SP"], "destinos_de_sp": ["MG"]},
    {"protocolo": "32/14", "pagina": "2014/pt032_14", "signatarios": ["RJ", "SP"], "destinos_de_sp": ["RJ"]},
    {"protocolo": "60/11", "pagina": "2011/pt060_11", "signatarios": ["AP", "PA", "SP"], "destinos_de_sp": ["AP", "PA"]},
    {"protocolo": "71/11", "pagina": "2011/pt071_11", "signatarios": ["PR", "SP"], "destinos_de_sp": ["PR"]},
    {"protocolo": "92/09", "pagina": "2009/pt092_09", "signatarios": ["RS", "SP"], "destinos_de_sp": ["RS"]},
    {"protocolo": "104/08", "pagina": "2008/pt104_08", "signatarios": ["AL", "SP"], "destinos_de_sp": ["AL"]},
    {"protocolo": "104/09", "pagina": "2009/pt104_09", "signatarios": ["BA", "SP"], "destinos_de_sp": ["BA"]},
    {"protocolo": "128/10", "pagina": "2010/pt128_10", "signatarios": ["PE", "SP"], "destinos_de_sp": ["PE"]},
    # Autopeças (segmento 01). Multilateral: SP assina e a cláusula primeira lista os destinos.
    {"protocolo": "41/08", "pagina": "2008/pt041_08", "segmento": "01",
     "signatarios": ["AP", "AM", "BA", "MA", "MT", "MG", "PA", "PR", "PI", "RS", "SC", "SP", "DF"],
     "destinos_de_sp": ["AC", "AL", "AM", "AP", "BA", "DF", "MA", "MG", "MT", "PA", "PB", "PI", "PR", "RJ", "RR"]},
    # Bilaterais SP-RJ de outros segmentos (destino de SP: RJ).
    {"protocolo": "29/14", "pagina": "2014/pt029_14", "segmento": "02", "signatarios": ["RJ", "SP"], "destinos_de_sp": ["RJ"]},
    {"protocolo": "34/14", "pagina": "2014/pt034_14", "segmento": "11", "signatarios": ["RJ", "SP"], "destinos_de_sp": ["RJ"]},
    {"protocolo": "76/14", "pagina": "2014/pt076_14", "segmento": "13", "signatarios": ["RJ", "SP"], "destinos_de_sp": ["RJ"]},
    {"protocolo": "77/14", "pagina": "2014/pt077_14", "segmento": "08", "signatarios": ["RJ", "SP"], "destinos_de_sp": ["RJ"]},
    {"protocolo": "104/12", "pagina": "2012/pt104_12", "segmento": "20", "signatarios": ["RJ", "SP"], "destinos_de_sp": ["RJ"]},
    {"protocolo": "136/13", "pagina": "2013/pt136_13", "segmento": "21", "signatarios": ["RJ", "SP"], "destinos_de_sp": ["RJ"]},
]
SEGMENTO = {p["protocolo"]: p.get("segmento", "10") for p in PROTOCOLOS}

_PROT = re.compile(r"Prot(?:ocolo)?\.?\s*ICMS\s*(?:n[ºo°]\s*)?(\d+)\s*/\s*(\d{2,4})", re.I)
_NCM_CEL = re.compile(r"\d{2}\.?\d{2}")


def norma_prot(s: str) -> str | None:
    m = _PROT.search(s)
    return f"Prot. ICMS {int(m.group(1))}/{m.group(2)[-2:]}" if m else None


def separar_ncms(s: str) -> list[str]:
    """'2514.00.00, 6802, 6803' e '3214.90.00 3816.00.1 3824.50.00' -> lista de códigos sem pontos."""
    s = re.sub(r"\b(?:e|ex)\b", " ", s, flags=re.I)
    # códigos grudados na fonte: "72.137214.20.00" (Prot. 32/09, item 48) = "72.13" e "7214.20.00"
    s = re.sub(r"(\d{2}\.\d{2})(?=\d{4}\.)", r"\1 ", s)
    return [c.replace(".", "") for c in re.findall(r"\d{2}(?:\.?\d{1,2}){0,3}", s)]


def mva(s: str) -> float | None:
    m = re.search(r"\d+(?:,\d+)?", s or "")
    return float(m.group(0).replace(",", ".")) if m else None


# ---------------------------------------------------------------- modelo

@dataclass
class Item:
    protocolo: str
    item: str
    ncm_sh: str
    descricao: str
    mva_original: float | None
    origem: str               # vigente_no_texto | anterior_no_texto | anexo_anterior
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
        elif self.origem == "anexo_anterior" and self.vigencia_fim is None:
            # redação antiga do anexo inteiro cuja nota não traz data final
            # ("até a data prevista em decreto"): já foi substituída
            self.situacao = "anterior"
        elif self.vigencia_fim and self.vigencia_fim < ref:
            self.situacao = "revogada" if self.revogado_em else "anterior"
        else:
            self.situacao = "vigente"


def ler_nota(txt: str, anterior: bool) -> Nota:
    """Mesma leitura do Convênio 142, com a norma no formato de protocolo."""
    from conv142 import ler_nota as ler_nota_conv
    # Algumas notas escrevem a data com barra ("até 31/10/12").
    txt = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", r"\1.\2.\3", txt)
    n = ler_nota_conv(txt, "A8-2" if anterior else "A8-1")
    n.norma = norma_prot(txt)
    # "Item 62 revogado pelo Prot. ICMS 76/26" começa por "Item", não por "Revogado".
    if not anterior and n.tipo != "anterior" and re.search(r"\brevogad", txt, re.I):
        n.tipo = "revogacao"
    elif n.tipo == "outra" and re.search(r"\bacrescentad", txt, re.I):
        n.tipo = "acrescimo"
    if not n.itens:
        m = re.match(r"\s*Ite(?:m|ns)\s+(\d+(?:\.\d+)?)", txt, re.I)
        if m:
            n.itens = {chave_item(m.group(1))}
    return n


def _classe(tr) -> str:
    c = " ".join(tr.xpath(".//p/@class"))
    if "RemissoAnt" in c or "RedaoAnt" in c or "A8-2" in c:
        return "nota_anterior"
    if "Remisso" in c or "A8-1" in c:
        return "nota"
    if "verde" in c:
        return "anterior"
    return "vigente"


def _colunas(cabecalho: list[str]) -> dict | None:
    col: dict[str, int] = {}
    for i, c in enumerate(cabecalho):
        u = c.upper()
        if "ITEM" in u and "item" not in col:
            col["item"] = i
        elif ("NCM" in u or "NBM" in u) and "ncm" not in col:
            col["ncm"] = i
        elif "DESCRI" in u and "desc" not in col:
            col["desc"] = i
        elif "MVA" in u and "ORIGINAL" in u and "mva" not in col:
            col["mva"] = i
        elif u == "CEST":
            col["cest"] = i
    return col if "ncm" in col and "desc" in col else None


def _nota_da_tabela(tabela) -> tuple[str, Nota | None]:
    """Vigência do anexo inteiro: a nota de remissão mais próxima antes da tabela."""
    for p in tabela.xpath("preceding::p[not(ancestor::table)][position()<=4]")[::-1]:
        t = texto(p)
        if not re.search(r"[A-Za-zÀ-ú]{3}", t) or t.upper().startswith("ANEXO"):
            continue
        classe = p.get("class") or ""
        baixo = t.lower()
        if "Remiss" in classe or "Remisso" in classe or "efeitos" in baixo:
            ant = "Ant" in classe or baixo.startswith(("redação original", "redação anterior", "redação dada"))
            if baixo.startswith("revogad") and "anexo" in baixo:
                return "revogada", ler_nota(t, False)
            return ("anterior" if ant else "atual"), ler_nota(t, ant)
        break
    return "atual", None


_CEST_TXT = r"\d{2}\.\d{3}\.\d{2}"


def cests_excluidos(clausula: str) -> list[str]:
    """'com exceção aos CEST 10.011.00, 10.025.00 a 10.028.00 e 10.080.00, destinadas' -> lista expandida."""
    m = re.search(r"exce[çc][ãa]o.*?(?=,?\s*destinad)", clausula, re.I)
    trecho = m.group(0) if m else ""
    saida: set[str] = set()
    for a, b in re.findall(rf"({_CEST_TXT})\s+a\s+({_CEST_TXT})", trecho):
        pa, pb = a.split("."), b.split(".")
        for k in range(int(pa[1]), int(pb[1]) + 1):
            saida.add(f"{pa[0]}.{k:03d}.{pa[2]}")
    saida.update(re.findall(_CEST_TXT, trecho))
    return sorted(saida)


def ler_clausula_primeira(raiz) -> dict:
    """Redação vigente da cláusula primeira (a primeira que aparece na página) e a nota que a precede.

    RS (Prot. 92/09) e AP/PA (Prot. 60/11) trocaram a lista própria pela referência ao
    Anexo XI do Convênio 142, menos os CESTs citados na própria cláusula."""
    ps = raiz.xpath(".//p[not(ancestor::table)]")
    for i, p in enumerate(ps):
        t = texto(p)
        if re.match(r"Cl.usula primeira", t, re.I):
            nota = None
            for q in ps[max(0, i - 3):i][::-1]:
                tq = texto(q)
                if re.search(r"(?i)cl.usula primeira", tq) and "efeitos" in tq.lower():
                    nota = ler_nota(tq, False)
                    break
            ref = re.search(r"Anexo ([IVXL]+) do Conv[eê]nio ICMS n?.?\s*142", t, re.I)
            modelo = f"conv142_anexo_{ref.group(1).lower()}" if ref else "lista_propria"
            return {"texto": t, "modelo": modelo, "desde": nota.inicio if nota else None,
                    "norma": nota.norma if nota else None,
                    "cests_excluidos": cests_excluidos(t) if modelo != "lista_propria" else [],
                    "destinos_na_clausula": ufs_destino(t)}
    return {"texto": "", "modelo": "lista_propria", "desde": None, "norma": None, "cests_excluidos": [],
            "destinos_na_clausula": []}


_UF_NOME = {"Acre": "AC", "Alagoas": "AL", "Amapá": "AP", "Amazonas": "AM", "Bahia": "BA", "Ceará": "CE",
            "Distrito Federal": "DF", "Espírito Santo": "ES", "Goiás": "GO", "Maranhão": "MA", "Mato Grosso do Sul": "MS",
            "Mato Grosso": "MT", "Minas Gerais": "MG", "Pará": "PA", "Paraíba": "PB", "Paraná": "PR", "Pernambuco": "PE",
            "Piauí": "PI", "Rio de Janeiro": "RJ", "Rio Grande do Norte": "RN", "Rio Grande do Sul": "RS",
            "Rondônia": "RO", "Roraima": "RR", "Santa Catarina": "SC", "São Paulo": "SP", "Sergipe": "SE",
            "Tocantins": "TO"}


def ufs_destino(clausula: str) -> list[str]:
    """'destinadas aos Estados do Acre, ..., Roraima e o Distrito Federal, fica' -> ['AC', ..., 'DF']."""
    m = re.search(r"destinad[ao]s? (?:aos?|às?) (?:Estados?|Distrito|unidades).*?(?=, fica|\. |$)", clausula, re.I)
    if not m:
        return []
    trecho, achados = m.group(0), []
    for nome in sorted(_UF_NOME, key=len, reverse=True):
        if nome in trecho:
            achados.append(_UF_NOME[nome])
            trecho = trecho.replace(nome, "")
    return sorted(achados)


_REVOGACAO = re.compile(r"Revogad[oa] pel[oa] Prot(?:ocolo)?\.?\s*ICMS\s*(?:n[ºo°]\s*)?(\d+\s*/\s*\d{2,4})\s*,?\s*"
                        r"efeitos? a partir de\s*(\d{1,2})[./](\d{1,2})[./](\d{2,4})", re.I)


def revogacao_total(cabecalho: str) -> tuple[date, str] | None:
    """Nota do cabeçalho 'Revogado pelo Prot. ICMS 112/26, efeitos a partir de 01.10.26' -> (2026-10-01, 'Prot. ICMS 112/26')."""
    m = _REVOGACAO.search(cabecalho)
    if not m:
        return None
    d, mes, a = int(m.group(2)), int(m.group(3)), int(m.group(4))
    numero = re.sub(r"\s", "", m.group(1))
    return date(a + 2000 if a < 100 else a, mes, d), f"Prot. ICMS {numero}"


def ler_protocolo(pagina: str, prot: str, ref: date) -> dict:
    from lxml import html

    conteudo = html.fromstring(pagina).xpath("//*[@id='content']")
    if not conteudo:
        raise SystemExit(f"Prot. {prot}: estrutura da página mudou (#content não encontrado)")
    clausula = ler_clausula_primeira(conteudo[0])
    # Revogação do protocolo inteiro: fica no cabeçalho, antes da cláusula primeira
    for lixo in conteudo[0].xpath(".//script"):
        lixo.drop_tree()
    corpo = re.sub(r"\s+", " ", conteudo[0].text_content())
    fim_cab = corpo.find("Cláusula primeira")
    fim_cab = fim_cab if fim_cab >= 0 else 3000
    rev = revogacao_total(corpo[:fim_cab])
    clausula["revogado_desde"], clausula["revogado_por"] = (rev if rev else (None, None))
    revogacao_anexo = None
    if clausula["modelo"] != "lista_propria":
        for p in conteudo[0].xpath(".//p[not(ancestor::table)]"):
            t = texto(p)
            if re.search(r"(?i)anexo [úu]nico revogado|revogado o anexo [úu]nico", t):
                revogacao_anexo = ler_nota(t, False)
    itens: list[Item] = []
    notas_soltas: list[dict] = []
    divergencias: list[dict] = []
    tabelas_atuais = 0
    for tabela in conteudo[0].xpath(".//table"):
        estado, nota_tab = _nota_da_tabela(tabela)
        if clausula["modelo"] != "lista_propria":
            estado = "anterior"  # a lista própria foi substituída pela referência ao Conv. 142
            if revogacao_anexo and revogacao_anexo.inicio and nota_tab and nota_tab.fim is None:
                nota_tab.fim = revogacao_anexo.inicio - timedelta(days=1)
        linhas = tabela.xpath(".//tr")
        col = None
        for tr in linhas[:3]:
            col = _colunas([texto(td) for td in tr.xpath("./td|./th")])
            if col:
                break
        if not col:
            continue
        if estado == "atual":
            tabelas_atuais += 1
            _ler_atual(linhas, col, prot, itens, notas_soltas, divergencias)
        else:
            _ler_anexo_anterior(linhas, col, prot, nota_tab, estado, itens)
    esperado = 1 if clausula["modelo"] == "lista_propria" else 0
    if tabelas_atuais != esperado:
        divergencias.append({"protocolo": prot, "item": "", "problema": f"{tabelas_atuais} tabelas tratadas como anexo vigente"})
    if rev:
        for i in itens:
            if i.vigencia_fim is None or i.vigencia_fim >= rev[0]:
                i.vigencia_fim = rev[0] - timedelta(days=1)
                i.revogado_em = i.revogado_em or rev[0]
                i.norma_alteradora = i.norma_alteradora or rev[1]
    for i in itens:
        i.calcular_situacao(ref)
    return {"itens": itens, "notas_soltas": notas_soltas, "divergencias": divergencias, "clausula": clausula}


def _celulas(tr) -> list[str]:
    cel = [texto(td) for td in tr.xpath("./td|./th")]
    while cel and cel[-1] in ("", "-"):
        cel.pop()
    return cel


def _ler_anexo_anterior(linhas, col, prot, nota, estado, itens) -> None:
    ini = nota.inicio if nota else None
    fim = nota.fim if nota else None
    if estado == "revogada" and nota and nota.inicio:
        ini, fim = None, nota.inicio - timedelta(days=1)
    for tr in linhas:
        cel = _celulas(tr)
        if len(cel) <= max(col["ncm"], col["desc"]) or not _NCM_CEL.search(cel[col["ncm"]]):
            continue
        itens.append(Item(
            protocolo=prot, item=cel[col["item"]].rstrip(".") if "item" in col else "",
            ncm_sh=cel[col["ncm"]], descricao=cel[col["desc"]],
            mva_original=mva(cel[col["mva"]]) if "mva" in col and len(cel) > col["mva"] else None,
            origem="anexo_anterior", vigencia_inicio=ini, vigencia_fim=fim, sem_efeitos=bool(nota and nota.sem_efeitos),
            revogado_em=None, norma_alteradora=None, nota_alteracao=None,
            nota_vigencia=nota.texto if nota else None))


def _ler_atual(linhas, col, prot, itens, notas_soltas, divergencias) -> None:
    nota_atual: Nota | None = None
    nota_ant: Nota | None = None
    revogacao: Nota | None = None
    ultimo_vigente: str | None = None
    em_bloco_ant = False

    def montar(cel, origem, ini, fim, sem, revog, norma_alt, nota_alt, nota_vig):
        itens.append(Item(
            protocolo=prot, item=cel[col["item"]].rstrip(".") if "item" in col else "",
            ncm_sh=cel[col["ncm"]], descricao=cel[col["desc"]],
            mva_original=mva(cel[col["mva"]]) if "mva" in col and len(cel) > col["mva"] else None,
            origem=origem, vigencia_inicio=ini, vigencia_fim=fim, sem_efeitos=sem, revogado_em=revog,
            norma_alteradora=norma_alt, nota_alteracao=nota_alt, nota_vigencia=nota_vig))

    for tr in linhas:
        tipo = _classe(tr)
        cel = _celulas(tr)
        if not cel:
            continue
        if tipo in ("nota", "nota_anterior") or (len(cel) == 1 and re.search(r"(?i)efeitos|revogad|acrescid|reda[çc][ãa]o", cel[0])):
            n = ler_nota(" ".join(cel), tipo == "nota_anterior")
            if n.tipo == "anterior":
                nota_ant, em_bloco_ant = n, True
                if revogacao is not None:
                    revogacao.usada = True
            elif n.tipo == "revogacao":
                nota_atual, revogacao, nota_ant = None, n, None
            elif n.tipo == "outra":
                notas_soltas.append({"protocolo": prot, "nota": n.texto})
            else:
                nota_atual, revogacao, nota_ant = n, None, None
            continue
        # Linha só com códigos: continuação da célula de NCM da linha anterior
        # (Prot. 104/08, item 52: "7217.10.90," numa linha e "7312" na seguinte).
        if len(cel) == 1 and re.fullmatch(r"[\d.,;\s]+", cel[0]) and itens and itens[-1].protocolo == prot:
            itens[-1].ncm_sh = f"{itens[-1].ncm_sh} {cel[0]}".replace(", ", ",").replace(",", ", ")
            continue
        k = chave_item(cel[col["item"]]) if "item" in col else ""
        if k.upper() == "ITEM":
            continue
        if any("REVOGADO" in c.upper() for c in cel[1:]):
            if revogacao is None:
                notas_soltas.append({"protocolo": prot, "nota": "linha REVOGADO sem nota: " + " | ".join(cel)})
            elif revogacao.itens and k not in revogacao.itens:
                divergencias.append({"protocolo": prot, "item": k,
                                     "problema": f"linha REVOGADO do item {k} logo após a nota: {revogacao.texto}"})
                revogacao.itens.add(k)
            else:
                revogacao.itens.add(k)
            continue
        if len(cel) <= max(col["ncm"], col["desc"]) or not _NCM_CEL.search(cel[col["ncm"]]):
            continue
        if tipo == "vigente" and em_bloco_ant and (nota_ant is not None) and k == ultimo_vigente:
            tipo = "anterior"
            divergencias.append({"protocolo": prot, "item": k,
                                 "problema": "redação anterior formatada como vigente; tratada como anterior"})
        if tipo == "vigente":
            em_bloco_ant = False
            n = None
            if nota_atual is not None and (k in nota_atual.itens or not nota_atual.itens) and not nota_atual.usada:
                n, n.usada = nota_atual, True
            revogacao, nota_ant = None, None
            ultimo_vigente = k
            montar(cel, "vigente_no_texto", n.inicio if n else None, None, False, None,
                   n.norma if n else None, n.texto if n else None, None)
        else:
            ini = nota_ant.inicio if nota_ant else None
            fim = nota_ant.fim if nota_ant else None
            sem = nota_ant.sem_efeitos if nota_ant else False
            revog = None
            if revogacao is not None and (not revogacao.itens or k in revogacao.itens):
                revog = revogacao.inicio
                revogacao.usada = True
                if fim is None and revog:
                    fim = revog - timedelta(days=1)
                elif fim and revog and fim != revog - timedelta(days=1) and not any(
                        r.protocolo == prot and chave_item(r.item) == k and r.revogado_em for r in itens):
                    # só a redação imediatamente anterior à revogação precisa terminar na véspera dela
                    divergencias.append({"protocolo": prot, "item": k, "problema":
                                         f"revogação a partir de {revog:%d/%m/%Y}, mas a redação anterior "
                                         f"vale só até {fim:%d/%m/%Y}: {revogacao.texto}"})
            if fim is None and not sem:
                atual = next((r for r in reversed(itens) if r.protocolo == prot and chave_item(r.item) == k
                              and r.origem == "vigente_no_texto"), None)
                if atual and atual.vigencia_inicio:
                    fim = atual.vigencia_inicio - timedelta(days=1)
            montar(cel, "anterior_no_texto", ini, fim, sem, revog,
                   revogacao.norma if revog else None, revogacao.texto if revog else None,
                   nota_ant.texto if nota_ant else None)


# ---------------------------------------------------------------- matriz

def carregar_conv142() -> list[dict]:
    caminho = RAIZ / "dados" / "conv142" / "itens_vigentes.csv"
    if not caminho.exists():
        return []
    with caminho.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cests_provaveis(ncms: list[str], conv: list[dict], segmento: str = "10") -> list[str]:
    """CESTs do segmento do protocolo (10 = construção) cujo NCM cobre o do item, ou é coberto por ele."""
    achados = []
    for r in conv:
        if not r["cest"].startswith(segmento + "."):
            continue
        for c in r["ncms"].split(";"):
            c = c.replace(".", "").strip()
            if c and any(n.startswith(c) or c.startswith(n) for n in ncms):
                achados.append(r["cest"])
                break
    return sorted(set(achados))


def pares(prot: str, cl: dict | None) -> list[tuple[str, str]]:
    """(origem, destino) que o protocolo cobre: cada signatário vendendo para os estados que a
    cláusula primeira cita ("destinadas ao Estado de MG ou ao Estado de SP" vale nos dois sentidos;
    "destinadas ao Estado do ES" só de SP para o ES). Sem destinos legíveis, usa a configuração."""
    conf = next(p for p in PROTOCOLOS if p["protocolo"] == prot)
    destinos = (cl or {}).get("destinos_na_clausula") or conf["destinos_de_sp"]
    return [(o, d) for o in conf["signatarios"] for d in destinos if d != o]


def matriz_geral(itens: list[Item], conv: list[dict], clausulas: dict | None = None) -> list[dict]:
    clausulas = clausulas or {}
    linhas = []
    for prot, cl in clausulas.items():
        if not cl["modelo"].startswith("conv142_anexo_"):
            continue
        if cl.get("revogado_desde") and cl["revogado_desde"] <= date.today():
            continue
        anexo = cl["modelo"].rsplit("_", 1)[1].upper()
        for r in conv:
            if r["anexo"] != anexo or r["cest"] in cl["cests_excluidos"]:
                continue
            for o, d in pares(prot, cl):
                linhas.append({
                    "origem": o, "destino": d, "protocolo": f"Prot. ICMS {prot}", "item": f"CEST {r['cest']}",
                    "ncm_sh": r["ncm_sh"], "ncms": ";".join(c.replace(".", "") for c in r["ncms"].split(";") if c),
                    "descricao": r["descricao"], "mva_original": "", "cests_provaveis": r["cest"],
                    "vigencia_inicio": _iso(cl["desde"]),
                    "efeito_no_destino": EFEITO_SP if d == "SP" else "",
                })
    for i in itens:
        if i.situacao != "vigente":
            continue
        ncms = separar_ncms(i.ncm_sh)
        cests = ";".join(cests_provaveis(ncms, conv, SEGMENTO[i.protocolo]))
        for o, d in pares(i.protocolo, clausulas.get(i.protocolo)):
            linhas.append({
                "origem": o, "destino": d, "protocolo": f"Prot. ICMS {i.protocolo}", "item": i.item,
                "ncm_sh": i.ncm_sh, "ncms": ";".join(ncms), "descricao": i.descricao,
                "mva_original": "" if i.mva_original is None else f"{i.mva_original:g}",
                "cests_provaveis": cests, "vigencia_inicio": _iso(i.vigencia_inicio),
                "efeito_no_destino": EFEITO_SP if d == "SP" else "",
            })
    return linhas


def matriz_sp(itens: list[Item], conv: list[dict], clausulas: dict | None = None) -> list[dict]:
    return [r for r in matriz_geral(itens, conv, clausulas) if r["origem"] == "SP"]


def consultar(matriz: list[dict], ncm: str, uf: str, origem: str = "SP") -> list[dict]:
    """Itens da matriz que cobrem o NCM (código completo ou posição) da origem para o destino."""
    n = ncm.replace(".", "")
    return [m for m in matriz if m["destino"] == uf and m.get("origem", "SP") == origem and any(n.startswith(c) for c in m["ncms"].split(";") if c)]


# ---------------------------------------------------------------- gravação

def _iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def gravar(resultados: dict, destino: Path, meta: dict, conv: list[dict]) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    todos = [i for r in resultados.values() for i in r["itens"]]
    campos = list(asdict(todos[0]).keys())

    def linha(i: Item) -> dict:
        d = asdict(i)
        for k in ("vigencia_inicio", "vigencia_fim", "revogado_em"):
            d[k] = _iso(d[k])
        d["mva_original"] = "" if i.mva_original is None else f"{i.mva_original:g}"
        d["ncms"] = ";".join(separar_ncms(i.ncm_sh))
        return d

    campos.insert(campos.index("ncm_sh") + 1, "ncms")
    for nome, filtro in (("itens_historico.csv", lambda i: True), ("itens_vigentes.csv", lambda i: i.situacao == "vigente")):
        with (destino / nome).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            for i in todos:
                if filtro(i):
                    w.writerow(linha(i))
    geral = matriz_geral(todos, conv, {k: r["clausula"] for k, r in resultados.items()})
    for nome, linhas in (("matriz_origem_destino.csv", geral),
                         ("matriz_sp_destino.csv", [r for r in geral if r["origem"] == "SP"])):
        with (destino / nome).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(geral[0].keys()))
            w.writeheader()
            w.writerows(linhas)
    for nome, chave in (("divergencias_da_fonte.csv", "divergencias"), ("notas_nao_associadas.csv", "notas_soltas")):
        linhas = [x for r in resultados.values() for x in r[chave]]
        with (destino / nome).open("w", encoding="utf-8", newline="") as f:
            cab = ["protocolo", "item", "problema"] if chave == "divergencias" else ["protocolo", "nota"]
            w = csv.DictWriter(f, fieldnames=cab)
            w.writeheader()
            w.writerows(linhas)
    with (destino / "protocolos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["protocolo", "signatarios", "destinos_de_sp", "modelo", "clausula_desde",
                                          "cests_excluidos", "destinos_na_clausula", "revogado_desde", "revogado_por", "url", "itens_vigentes",
                                          "com_mva_no_protocolo"])
        w.writeheader()
        for p in PROTOCOLOS:
            vig = [i for i in resultados[p["protocolo"]]["itens"] if i.situacao == "vigente"]
            cl = resultados[p["protocolo"]]["clausula"]
            w.writerow({"protocolo": f"Prot. ICMS {p['protocolo']}", "signatarios": ";".join(p["signatarios"]),
                        "destinos_de_sp": ";".join(p["destinos_de_sp"]), "modelo": cl["modelo"],
                        "clausula_desde": _iso(cl["desde"]), "cests_excluidos": ";".join(cl["cests_excluidos"]),
                        "destinos_na_clausula": ";".join(cl.get("destinos_na_clausula", [])),
                        "revogado_desde": _iso(cl.get("revogado_desde")), "revogado_por": cl.get("revogado_por") or "",
                        "url": BASE_URL + p["pagina"],
                        "itens_vigentes": len(vig), "com_mva_no_protocolo": sum(i.mva_original is not None for i in vig)})
    meta = dict(meta)
    meta["contagens"] = {
        "protocolos": len(PROTOCOLOS),
        "redacoes": len(todos),
        "itens_vigentes": sum(i.situacao == "vigente" for i in todos),
        "linhas_matriz": len([r for r in geral if r["origem"] == "SP"]), "linhas_matriz_origem_destino": len(geral),
        "divergencias_da_fonte": sum(len(r["divergencias"]) for r in resultados.values()),
        "notas_nao_associadas": sum(len(r["notas_soltas"]) for r in resultados.values()),
    }
    (destino / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def baixar(pagina: str) -> bytes:
    import httpx
    r = httpx.get(BASE_URL + pagina, headers={"User-Agent": USER_AGENT}, timeout=90, follow_redirects=True)
    r.raise_for_status()
    return r.content


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html-dir", type=Path, help="pasta com os HTMLs salvos (nome = final da URL + .html)")
    ap.add_argument("--ref", type=date.fromisoformat, default=date.today(), help="data de referência (AAAA-MM-DD)")
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "protocolos")
    a = ap.parse_args(argv)

    resultados, fontes = {}, []
    for p in PROTOCOLOS:
        nome = p["pagina"].split("/")[1]
        if a.html_dir:
            bruto = (a.html_dir / f"{nome}.html").read_bytes()
        else:
            bruto = baixar(p["pagina"])
            time.sleep(1)
        resultados[p["protocolo"]] = ler_protocolo(bruto.decode("utf-8", "ignore"), p["protocolo"], a.ref)
        fontes.append({"protocolo": f"Prot. ICMS {p['protocolo']}", "url": BASE_URL + p["pagina"],
                       "sha256": hashlib.sha256(bruto).hexdigest()})
    meta = {"fonte": "Confaz, textos consolidados dos protocolos ICMS", "fontes": fontes,
            "obtido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_referencia": a.ref.isoformat(),
            "escopo": "protocolos de que SP é signatário (construção, autopeças e bilaterais SP-RJ); matriz SP -> destino e matriz origem -> destino de todos os signatários"}
    meta = gravar(resultados, a.saida, meta, carregar_conv142())
    print(json.dumps(meta["contagens"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Catálogo dos protocolos ICMS de substituição tributária publicados pelo Confaz.

Percorre os índices anuais de protocolos (um por ano), separa pelos títulos os protocolos-base
("Dispõe sobre a substituição tributária nas operações com ...") e abre cada um para registrar:
signatários (preâmbulo), destinos citados na cláusula primeira, modelo da lista (própria ou
referência a um anexo do Convênio 142, com os CESTs excluídos), segmento provável e a revogação
do protocolo inteiro, quando houver.

O catálogo é o mapa para estender a matriz origem -> destino além dos protocolos de que SP é
signatário. Ele não lê os itens; isso continua em scripts/protocolos.py.

Uso:
    python scripts/catalogo_protocolos.py              baixa do Confaz e grava dados/protocolos/catalogo.csv
    python scripts/catalogo_protocolos.py --de 2008 --ate 2012
"""

from __future__ import annotations

import argparse
import csv
import html as html_mod
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protocolos as p  # noqa: E402
from conv142 import USER_AGENT  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
INDICE = "https://www.confaz.fazenda.gov.br/legislacao/protocolos/{ano}"
_LINK = re.compile(r'<a[^>]*href="[^"]*/protocolos/(\d{4})/(pt\d+_\d+)"[^>]*title="([^"]*)"', re.I)
# Protocolo-base: o título COMEÇA com "Dispõe sobre a substituição tributária nas operações". "Revoga o Protocolo
# ICMS nº X, que dispõe sobre a substituição tributária" é um revogador, lido à parte.
_BASE = re.compile(r"^\s*Disp[õo]e sobre a (?:sobre a )?substitui[çc][ãa]o tribut[áa]ria nas opera[çc][õo]es", re.I)
_REVOGADOR = re.compile(r"^\s*Revoga (?:o|os) Protocolos? ICMS.*substitui[çc][ãa]o tribut[áa]ria", re.I)
_ALVO = re.compile(r"Protocolos? ICMS\s*(?:n[ºo°]s?\.?\s*)?(\d+)\s*(?:/\s*(\d{2,4})|,\s*de\s*\d{1,2}[ºo°]?\s*de\s*[a-zç]+\s*de\s*(\d{4}))", re.I)

# Palavras do título -> segmento do Convênio 142 (código de dois dígitos do CEST). A ordem importa:
# "papelaria" antes de "papel", "sorvetes" antes do resto; os padrões usam limite de palavra para
# "rações" não casar dentro de "operações" nem "água" dentro de "aguardente".
SEGMENTOS = [
    ("01", r"autope[çc]as"), ("19", r"\bpapelaria"), ("23", r"\bsorvetes?"),
    ("02", r"bebidas? (?:alco[óo]licas?|quentes)|\bvinhos?\b|\bsidras?\b|\baguardentes?\b"),
    ("03", r"\bcervejas?|\brefrigerantes?|\b[áa]guas? mine"), ("04", r"\bcigarros?|\bfumo"), ("05", r"\bcimentos?\b"),
    ("06", r"combust[íi]veis|lubrificantes"), ("07", r"energia el[ée]trica"), ("08", r"\bferramentas"),
    ("09", r"\bl[âa]mpadas|\breatores"), ("10", r"materia(?:l|is) de constru[çc][ãa]o|bricolagem"),
    ("11", r"(?:material|materiais) de limpeza"), ("12", r"materia(?:l|is) el[ée]tricos?"),
    ("13", r"\bmedicamentos|farmac[êe]uticos"), ("14", r"artefatos de uso dom[ée]stico|\bpap[ée]is|pl[áa]sticos|\bvidros|cer[âa]mic"),
    ("15", r"\bpilhas|\bbaterias"), ("16", r"pneum[áa]ticos|c[âa]maras de ar"), ("17", r"aliment[íi]cios"),
    ("20", r"cosm[ée]ticos|perfumaria|higiene"), ("21", r"eletr[ôo]nicos|eletrodom[ée]sticos|m[áa]quinas e aparelhos"),
    ("22", r"\bra[çc][õo]es\b"), ("24", r"\btintas|\bvernizes"), ("25", r"ve[íi]culos automotores|ve[íi]culos novos"),
    ("26", r"duas e tr[êe]s rodas|motocicletas"), ("28", r"porta a porta|porta-a-porta"), ("29", r"\bbicicletas"),
]

# Anexo do Convênio 142 -> segmento, para os protocolos que remetem a um anexo.
ANEXO_SEGMENTO = {"II": "01", "III": "02", "IV": "03", "V": "04", "VI": "05", "VII": "06", "VIII": "07", "IX": "08",
                  "X": "09", "XI": "10", "XII": "11", "XIII": "12", "XIV": "13", "XV": "14", "XVI": "16", "XVII": "17",
                  "XVIII": "19", "XIX": "20", "XX": "21", "XXI": "22", "XXII": "23", "XXIII": "24", "XXIV": "25", "XXV": "26"}


def segmento(titulo: str) -> str:
    for cod, rx in SEGMENTOS:
        if re.search(rx, titulo, re.I):
            return cod
    return ""


def signatarios(conteudo_texto: str) -> list[str]:
    """Preâmbulo vigente: 'Os Estados do Acre, ... e o Distrito Federal, neste ato representados' ou
    'O Distrito Federal e o Estado de São Paulo, neste ato representados'."""
    m = re.search(r"((?:Os Estados?|O Estado|O Distrito Federal) .{0,900}?)(?:,\s*)?neste ato", conteudo_texto)
    if not m:
        return []
    trecho, achados = m.group(1), []
    for nome in sorted(p._UF_NOME, key=len, reverse=True):
        if nome in trecho:
            achados.append(p._UF_NOME[nome])
            trecho = trecho.replace(nome, "")
    return sorted(achados)


def indice(ano: int, cliente) -> list[tuple[str, str, str, str]]:
    import httpx

    for tentativa in range(3):
        try:
            r = cliente.get(INDICE.format(ano=ano))
            break
        except httpx.TimeoutException:
            if tentativa == 2:
                raise
            time.sleep(5)
    if r.status_code != 200:
        return []
    vistos, saida = set(), []
    for a, pagina, titulo in _LINK.findall(r.text):
        if pagina in vistos:
            continue
        vistos.add(pagina)
        titulo = html_mod.unescape(titulo)
        if _BASE.search(titulo):
            saida.append((f"{a}/{pagina}", pagina, titulo, "base"))
        elif _REVOGADOR.search(titulo):
            saida.append((f"{a}/{pagina}", pagina, titulo, "revogador"))
    return saida


def alvos_do_revogador(texto: str) -> list[str]:
    """'Revoga o Protocolo ICMS nº 14, de 11 de abril de 2008' / 'Protocolo ICMS 14/08' -> ['Prot. ICMS 14/08']."""
    saida = []
    for n, aa, ano in _ALVO.findall(texto):
        sufixo = (aa or ano)[-2:]
        saida.append(f"Prot. ICMS {int(n)}/{sufixo}")
    return list(dict.fromkeys(saida))


def efeitos_do_revogador(corpo: str) -> str:
    """Data de efeitos da revogação: 'efeitos a partir de 01.01.20' na cláusula, senão a publicação no DOU."""
    m = re.search(r"(?:efeitos?|produzindo efeitos)\s+a partir de\s*(\d{1,2})[º°]?[./ ](?:de\s+)?(\d{1,2}|[a-zç]+)[./ ](?:de\s+)?(\d{2,4})", corpo, re.I)
    meses = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
             "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
    if m:
        mes = int(m.group(2)) if m.group(2).isdigit() else meses.get(m.group(2).lower())
        if mes:
            ano = int(m.group(3))
            return date(ano + 2000 if ano < 100 else ano, mes, int(m.group(1))).isoformat()
    return p.cabecalho_publicacao(corpo)["publicado_dou"]


def ler(pagina_html: str, ref: date) -> dict:
    from lxml import html

    conteudo = html.fromstring(pagina_html).xpath("//*[@id='content']")
    if not conteudo:
        return {"erro": "sem #content"}
    for lixo in conteudo[0].xpath(".//script"):
        lixo.drop_tree()
    corpo = re.sub(r"\s+", " ", conteudo[0].text_content())
    cl = p.ler_clausula_primeira(conteudo[0])
    fim = corpo.find("Cláusula primeira")
    rev = p.revogacao_total(corpo[:fim if fim >= 0 else 3000])
    preambulo = signatarios(corpo)
    destinos = cl["destinos_na_clausula"]
    # "realizadas entre contribuintes situados nas unidades federadas signatárias": o destino são os signatários.
    # "entre contribuintes situados nas unidades federadas signatárias / nos seus territórios", "entre estabelecimentos
    # localizados em seus territórios", "destinadas aos Estados signatários": o destino são os signatários.
    entre = bool(re.search(r"entre (?:contribuintes|estabelecimentos) (?:situados|localizados) (?:n(?:as|os)|em) (?:seus territ[óo]rios|unidades federadas signat|Estados signat)|destinad[ao]s aos [Ee]stados signat[áa]rios", cl["texto"], re.I))
    # Sem nenhuma menção ao destino, o protocolo só obriga quem assina: destino implícito = signatários.
    implicito = not entre and not destinos and not re.search(r"destinad", cl["texto"], re.I)
    # Retenção só pelo industrial ou importador (atacadista que revende não retém por este protocolo).
    restrito = bool(re.search(r"fica atribu[íi]da ao (?:estabelecimento |contribuinte )?(?:industrial|importador)", cl["texto"], re.I))
    # Quem aderiu depois aparece na lista de destinos da cláusula sem estar no preâmbulo.
    sig = sorted(set(preambulo) | set(destinos))
    if (entre or implicito) and not destinos:
        destinos = sig
    return {
        "signatarios": sig, "destinos_na_clausula": destinos, "regra_destino": ("entre_signatarios" if entre else "implicito_signatarios" if implicito else "lista_na_clausula" if cl["destinos_na_clausula"] else "nao_identificada"),
        "remetente": "industrial_ou_importador" if restrito else "qualquer",
        "modelo": cl["modelo"], "cests_excluidos": cl["cests_excluidos"], "clausula_desde": cl["desde"],
        "revogado_desde": rev[0] if rev else None, "revogado_por": rev[1] if rev else "",
        "situacao": ("revogado" if rev[0] is None or rev[0] <= ref else "revogacao_futura") if rev else "vigente",
        "sp_signatario": "SP" in sig,
    }


def main(argv: list[str] | None = None) -> int:
    import httpx

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--de", type=int, default=2004)
    ap.add_argument("--ate", type=int, default=date.today().year)
    ap.add_argument("--cache", type=Path, help="pasta para guardar as páginas baixadas")
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados" / "protocolos" / "catalogo.csv")
    a = ap.parse_args(argv)
    ref = date.today()
    linhas = []
    revogadores: list[dict] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True) as cli:
        for ano in range(a.de, a.ate + 1):
            for caminho, pagina, titulo, tipo in indice(ano, cli):
                cache = a.cache / f"{pagina.lower()}.html" if a.cache else None
                if cache and cache.exists():
                    texto, status = cache.read_text(encoding="utf-8"), 200
                else:
                    for tentativa in range(3):  # o Confaz às vezes demora a responder
                        try:
                            r = cli.get(p.BASE_URL + caminho)
                            break
                        except httpx.TimeoutException:
                            if tentativa == 2:
                                raise
                            time.sleep(5)
                    texto, status = r.text, r.status_code
                    if cache and status == 200:
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        cache.write_text(texto, encoding="utf-8")
                    time.sleep(0.3)
                num = re.match(r"pt(\d+)_(\d+)", pagina, re.I)
                if tipo == "revogador":
                    if status == 200:
                        from lxml import html as _h
                        cont = _h.fromstring(texto).xpath("//*[@id='content']")
                        corpo = re.sub(r"\s+", " ", cont[0].text_content()) if cont else ""
                        revogadores.append({"revogador": f"Prot. ICMS {int(num.group(1))}/{num.group(2)}",
                                            "alvos": alvos_do_revogador(titulo + " " + corpo[corpo.find("Cláusula"):][:1500]),
                                            "efeitos": efeitos_do_revogador(corpo)})
                    continue
                info = ler(texto, ref) if status == 200 else {"erro": f"HTTP {status}"}
                linhas.append({
                    "protocolo": f"Prot. ICMS {int(num.group(1))}/{num.group(2)}", "pagina": caminho,
                    "titulo": titulo,
                    "segmento": ANEXO_SEGMENTO.get(info.get("modelo", "").rsplit("_", 1)[-1].upper(), "") if info.get("modelo", "").startswith("conv142") else segmento(titulo),
                    "signatarios": ";".join(info.get("signatarios", [])),
                    "destinos_na_clausula": ";".join(info.get("destinos_na_clausula", [])),
                    "regra_destino": info.get("regra_destino", ""),
                    "remetente": info.get("remetente", ""),
                    "modelo": info.get("modelo", ""), "cests_excluidos": ";".join(info.get("cests_excluidos", [])),
                    "clausula_desde": p._iso(info.get("clausula_desde")),
                    "situacao": info.get("situacao", info.get("erro", "")),
                    "revogado_desde": p._iso(info.get("revogado_desde")), "revogado_por": info.get("revogado_por", ""),
                    "sp_signatario": "sim" if info.get("sp_signatario") else "nao",
                })
            print(ano, sum(1 for l in linhas if l["pagina"].startswith(str(ano))), file=sys.stderr)
    # Segunda conferência: protocolo citado por um revogador e ainda marcado como vigente.
    por_nome = {l["protocolo"]: l for l in linhas}
    for rv in revogadores:
        for alvo in rv["alvos"]:
            l = por_nome.get(alvo)
            if not l or l["situacao"] not in ("vigente", "revogacao_futura"):
                continue
            quando = rv["efeitos"]
            l["situacao"] = "revogado" if not quando or quando <= ref.isoformat() else "revogacao_futura"
            l["revogado_desde"], l["revogado_por"] = quando, rv["revogador"] + " (pelo revogador)"
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    with a.saida.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    vig = [l for l in linhas if l["situacao"] == "vigente"]
    print({"protocolos_de_st": len(linhas), "revogadores_lidos": len(revogadores), "vigentes": len(vig),
           "revogados": sum(l["situacao"] == "revogado" for l in linhas),
           "revogacao_futura": sum(l["situacao"] == "revogacao_futura" for l in linhas),
           "vigentes_sem_sp": sum(l["sp_signatario"] == "nao" for l in vig)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

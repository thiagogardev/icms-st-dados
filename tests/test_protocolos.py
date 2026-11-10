"""Cada teste reproduz um padrão real das páginas dos protocolos no Confaz (09/11/2026)."""

import csv
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import protocolos as p  # noqa: E402

REF = date(2026, 11, 9)


def linha(*cels, classe="Tabelajustificado"):
    return "<tr>" + "".join(f'<td><p class="{classe}">{x}</p></td>' for x in cels) + "</tr>"


def nota(txt, classe="Remisso"):
    return f'<tr><td colspan="4"><p class="{classe}">{txt}</p></td></tr>'


def anterior(*cels):
    return linha(*cels, classe="Tabelajustificadoverde")


CAB = linha("ITEM", "NCM/SH", "DESCRIÇÃO DAS MERCADORIAS", "MVA (%) ORIGINAL", classe="TabelaSubtitulo")
CLAUSULA_LISTA = ('<p class="TextoAcordo">Cláusula primeira Nas operações interestaduais com as mercadorias '
                  'listadas no Anexo Único, destinadas ao Estado de Alagoas, fica atribuída ao remetente...</p>')


def pagina(*linhas, clausula=CLAUSULA_LISTA, extra=""):
    return f"""<html><body><div id="content">{clausula}
<p class="Subtitulo">ANEXO ÚNICO</p><table>{CAB}{"".join(linhas)}</table>{extra}</div></body></html>"""


def ler(*linhas, **kw):
    return p.ler_protocolo(pagina(*linhas, **kw), "104/08", REF)


def test_item_revogado_comeca_por_item():
    r = ler(linha("67", "73.25", "Outras obras moldadas", "86"),
            nota("Item 81 revogado pelo Prot. ICMS 57/26, efeitos a partir de 01.08.26."),
            linha("81", "REVOGADO"),
            nota("Redação original, efeitos até 31.07.26.", classe="RemissoAnt"),
            anterior("81", "7411.10.10", "Tubos de cobre", "35"))
    velho = [i for i in r["itens"] if i.item == "81"][0]
    assert velho.situacao == "revogada"
    assert velho.revogado_em == date(2026, 8, 1) and velho.vigencia_fim == date(2026, 7, 31)
    assert velho.norma_alteradora == "Prot. ICMS 57/26"
    assert not r["divergencias"] and not r["notas_soltas"]


def test_linha_revogado_de_outro_item_vira_divergencia():
    # Prot. 32/09: a nota revoga o item 69 e a linha seguinte diz "80. REVOGADO".
    r = ler(nota("Item 69 revogado pelo Prot. ICMS 75/26, efeitos a partir de 01.08.26."),
            linha("80.", "REVOGADO"),
            nota("Redação original, efeitos até 31.07.26.", classe="RemissoAnt"),
            anterior("69.", "74.12", "Acessórios para tubos de cobre", "35"))
    assert any("item 80" in d["problema"] for d in r["divergencias"])


def test_ncm_continuado_na_linha_seguinte():
    # Prot. 104/08, item 52: "7217.10.90," numa linha e "7312" sozinho na seguinte.
    r = ler(linha("52", "7217.10.90,", "Fios de ferro ou aço, cordas, cabos", "44"), linha("7312"))
    item = r["itens"][0]
    assert p.separar_ncms(item.ncm_sh) == ["72171090", "7312"]
    assert item.mva_original == 44


def test_coluna_descricao_antes_do_ncm():
    cab = linha("Item", "Descrição das mercadorias", "NCM/SH", "MVA-ST original (%)", classe="TabelaSubtitulo")
    html = pagina().replace(CAB, cab).replace("</table>", linha("68", "Abraçadeiras", "73.26", "80") + "</table>")
    item = p.ler_protocolo(html, "104/08", REF)["itens"][0]
    assert (item.ncm_sh, item.descricao, item.mva_original) == ("73.26", "Abraçadeiras", 80)


def test_data_com_barra_e_anexo_antigo_sem_data_final():
    extra = ('<p class="RemissoAnt">Redação original, efeitos até 31/10/12:</p>'
             f'<table>{CAB}{linha("1", "84.81", "torneiras", "30,18")}</table>'
             '<p class="RemissoAnt">Redação original, efeitos até a data prevista em decreto.</p>'
             f'<table>{CAB}{linha("1", "73.07", "acessórios", "33")}</table>')
    r = ler(linha("85", "84.81", "Torneiras, válvulas", "47"), extra=extra)
    antigos = {i.ncm_sh: i for i in r["itens"] if i.origem == "anexo_anterior"}
    assert antigos["84.81"].vigencia_fim == date(2012, 10, 31)
    assert antigos["84.81"].situacao == "anterior"
    assert antigos["73.07"].situacao == "anterior"   # sem data final, mas já substituído
    assert [i.mva_original for i in r["itens"] if i.situacao == "vigente"] == [47]


def test_modelo_por_referencia_ao_conv142():
    clausula = ('<p class="Remisso">Nova redação dada à cláusula primeira pelo Prot. ICMS 54/26, '
                'efeitos a partir de 01.08.26.</p>'
                '<p class="TextoAcordo">Cláusula primeira Nas operações interestaduais com bens e mercadorias '
                'relacionadas no Anexo XI do Convênio ICMS nº 142, de 14 de dezembro de 2018, com exceção aos '
                'Códigos Especificadores da Substituição Tributária, 10.011.00, 10.025.00 a 10.028.00 e '
                '10.080.00, destinadas ao Estado de São Paulo ou ao Estado do Rio Grande do Sul, fica...</p>')
    extra = '<p class="Remisso">Anexo Único revogado pelo Prot. ICMS 67/25, efeitos a partir de 01.01.26.</p>'
    r = p.ler_protocolo(pagina(linha("1", "73.26", "Abraçadeiras", "103"), clausula=clausula, extra=extra),
                        "92/09", REF)
    cl = r["clausula"]
    assert cl["modelo"] == "conv142_anexo_xi" and cl["desde"] == date(2026, 8, 1)
    assert cl["cests_excluidos"] == ["10.011.00", "10.025.00", "10.026.00", "10.027.00", "10.028.00", "10.080.00"]
    assert all(i.situacao != "vigente" for i in r["itens"])   # a lista própria deixou de valer
    conv = [{"anexo": "XI", "cest": "10.062.00", "ncm_sh": "7326", "ncms": "7326", "descricao": "Abraçadeiras"},
            {"anexo": "XI", "cest": "10.080.00", "ncm_sh": "9406", "ncms": "9406", "descricao": "Construções pré"}]
    m = p.matriz_sp([], conv, {"92/09": cl})
    assert [(x["destino"], x["cests_provaveis"]) for x in m] == [("RS", "10.062.00")]
    assert p.consultar(m, "7326.19.00", "RS") and not p.consultar(m, "9406.10.00", "RS")


def test_consulta_por_posicao_e_codigo_completo():
    m = [{"destino": "MT", "ncms": "73071910;73071920"}, {"destino": "MG", "ncms": "7307"}]
    assert p.consultar(m, "7307.19.20", "MT") and not p.consultar(m, "7307.19.90", "MT")
    assert p.consultar(m, "7307.19.90", "MG")


# ---------------------------------------------------------------- dados publicados

MATRIZ = RAIZ / "dados" / "protocolos" / "matriz_sp_destino.csv"


@pytest.mark.skipif(not MATRIZ.exists(), reason="dados ainda não gerados")
def test_gabarito_conferido_na_norma_e_na_econet():
    """Casos NCM x destino conferidos à mão em 09/11/2026 (texto do protocolo e Lista ST da Econet)."""
    with MATRIZ.open(encoding="utf-8") as f:
        matriz = list(csv.DictReader(f))
    with (RAIZ / "tests" / "gabarito_protocolos.csv").open(encoding="utf-8") as f:
        casos = list(csv.DictReader(f))
    erros = []
    for c in casos:
        achados = p.consultar(matriz, c["ncm"], c["destino"])
        mvas = {a["mva_original"] for a in achados if a["mva_original"]}
        if ("sim" if achados else "nao") != c["tem_st"] or (c["mva_original"] and c["mva_original"] not in mvas):
            erros.append(f"{c['ncm']} {c['destino']}: esperado {c['tem_st']} {c['mva_original']}, obtido {mvas}")
    assert not erros, erros


def test_destinos_lidos_da_clausula_do_41_08():
    cl = ("Nas operações interestaduais com bens e mercadorias relacionadas no Anexo II do Convênio ICMS nº 142, "
          "de 14 de dezembro de 2018, com exceção aos Códigos Especificadores da Substituição Tributária – CEST - "
          "01.019.00, 01.062.01 e 01.999.00, destinadas aos Estados do Acre, Mato Grosso, Minas Gerais, Paraná, "
          "Rio de Janeiro, Roraima e o Distrito Federal, fica atribuída ao estabelecimento remetente")
    assert p.ufs_destino(cl) == ["AC", "DF", "MG", "MT", "PR", "RJ", "RR"]
    assert p.cests_excluidos(cl) == ["01.019.00", "01.062.01", "01.999.00"]


@pytest.mark.skipif(not (RAIZ / "dados" / "protocolos" / "protocolos.csv").exists(), reason="dados ainda não gerados")
def test_destinos_configurados_batem_com_a_clausula_nos_multilaterais():
    with (RAIZ / "dados" / "protocolos" / "protocolos.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["destinos_na_clausula"] and r["protocolo"] == "Prot. ICMS 41/08":
                assert r["destinos_na_clausula"] == r["destinos_de_sp"], r


def test_revogacao_do_protocolo_inteiro():
    cab = ("PROTOCOLO ICMS 77/14 Publicado no DOU de 11.12.14. Alterado pelos Prots. ICMS 20/15 e 67/26. "
           "Revogado pelo Prot. ICMS 112/26, efeitos a partir de 01.10.26. Dispõe sobre a substituição tributária")
    assert p.revogacao_total(cab) == (date(2026, 10, 1), "Prot. ICMS 112/26")
    assert p.revogacao_total("Alterado pelo Prot. ICMS 31/14. Dispõe sobre") is None


@pytest.mark.skipif(not (RAIZ / "dados" / "protocolos" / "protocolos.csv").exists(), reason="dados ainda não gerados")
def test_protocolos_sp_rj_revogados_em_2025_e_2026():
    with (RAIZ / "dados" / "protocolos" / "protocolos.csv").open(encoding="utf-8") as f:
        rev = {r["protocolo"]: r["revogado_desde"] for r in csv.DictReader(f)}
    assert {k: rev[k] for k in ("Prot. ICMS 29/14", "Prot. ICMS 34/14", "Prot. ICMS 76/14", "Prot. ICMS 77/14",
                                 "Prot. ICMS 104/12", "Prot. ICMS 136/13")} == {
        "Prot. ICMS 29/14": "2026-01-01", "Prot. ICMS 34/14": "2026-08-01", "Prot. ICMS 76/14": "2026-01-01",
        "Prot. ICMS 77/14": "2026-10-01", "Prot. ICMS 104/12": "2026-04-01", "Prot. ICMS 136/13": ""}

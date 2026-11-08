"""Cada teste reproduz um padrão real da página do Confaz (08/11/2026)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import conv142 as c  # noqa: E402

REF = date(2026, 11, 8)


def linha(*cels, classe="A7-2Tabelajustificado"):
    return "<tr>" + "".join(f'<td><p class="{classe}">{x}</p></td>' for x in cels) + "</tr>"


def nota(txt, classe="A8-1Remissao"):
    return f'<tr><td colspan="4"><p class="{classe}">{txt}</p></td></tr>'


def anterior(*cels):
    return linha(*cels, classe="A9-2Tabelajustificadoverde")


CAB = linha("ITEM", "CEST", "NCM/SH", "DESCRIÇÃO", classe="A7-1TabelaSubtitulo")


def pagina(*linhas_anexo_ii):
    segs = "".join(linha(str(i), n, cod) for i, (n, cod) in enumerate([("Autopeças", "01"), ("Bebidas", "02")], 1))
    return f"""<html><body><div id="content">
<p class="A6-1Subtitulo">ANEXO I</p><p class="A6-1Subtitulo">SEGMENTOS</p>
<table>{linha("ITEM", "NOME DO SEGMENTO", "CÓDIGO DO SEGMENTO", classe="A7-1TabelaSubtitulo")}{segs}</table>
<p class="A6-1Subtitulo">ANEXO II</p><p class="A6-1Subtitulo">AUTOPEÇAS</p>
<table>{CAB}{"".join(linhas_anexo_ii)}</table>
</div></body></html>"""


def ler(*linhas_anexo_ii):
    return c.ler_html(pagina(*linhas_anexo_ii), REF)


def por_item(dados, item):
    return [r for r in dados["redacoes"] if r.item == item]


def test_nova_redacao_fecha_a_anterior_na_vespera():
    d = ler(
        nota("Nova redação dada ao item 42.0 do Anexo II pelo Conv. ICMS 66/22, efeitos a partir de 02.05.22."),
        linha("42.0", "01.042.00", "8421.32.00", "Depuradores"),
        nota("Redação original, efeitos até 01.05.22.", "A8-2RemissaoAnt"),
        anterior("42.0", "01.042.00", "8421.39.20", "Depuradores"),
    )
    atual, antiga = por_item(d, "42.0")
    assert (atual.situacao, atual.vigencia_inicio, atual.norma_alteradora) == ("vigente", date(2022, 5, 2), "Conv. ICMS 66/22")
    assert (antiga.situacao, antiga.vigencia_fim, antiga.ncm_sh) == ("anterior", date(2022, 5, 1), "8421.39.20")
    assert d["segmentos"][1]["segmento"] == "Autopeças" and atual.segmento == "Autopeças"


def test_linha_revogado_nao_vira_item_vigente():
    d = ler(
        nota("Revogado o item 110.0 do Anexo II pelo Conv. ICMS 165/19, efeitos a partir de 01.01.20."),
        linha("110.0", "01.110.00", "7314.50.00", "REVOGADO"),
        nota("Redação original, efeitos até 31.12.19.", "A8-2RemissaoAnt"),
        anterior("110.0", "01.110.00", "7314.50.00", "Corrente de transmissão"),
    )
    (r,) = por_item(d, "110.0")
    assert r.descricao == "Corrente de transmissão"
    assert (r.situacao, r.revogado_em, r.vigencia_fim) == ("revogada", date(2020, 1, 1), date(2019, 12, 31))
    assert not d["notas_soltas"]


def test_revogacao_de_varios_itens_com_cest_revogado():
    d = ler(
        nota("Revogado os itens 49.8 a 49.9 do Anexo II pelo Conv. ICMS 72/20, efeitos a partir de 01.10.20."),
        linha("49.8", "REVOGADO", "", ""),
        linha("49.9", "REVOGADO", "", ""),
        nota("Redação anterior acrescida os itens 49.8 a 49.9 pelo Conv. ICMS 240/19, efeitos de 01.03.20 a 30.09.20.",
             "A8-2RemissaoAnt"),
        anterior("49.8", "01.049.08", "1905", "Biscoitos"),
        anterior("49.9", "01.049.09", "1905", "Wafers"),
    )
    assert {r.situacao for r in d["redacoes"]} == {"revogada"}
    assert all(r.vigencia_inicio == date(2020, 3, 1) and r.vigencia_fim == date(2020, 9, 30) for r in d["redacoes"])


def test_redacao_sem_efeitos():
    d = ler(
        nota("Redação acrescida do item 2.1 ao Anexo II pelo Conv. ICMS 53/23, efeitos a partir de 01.05.23."),
        linha("2.1", "01.002.01", "1806.31.10", "Chocolates novos"),
        nota("Redação anterior acrescida do item 2.1 ao Anexo II pelo Conv. ICMS 202/22, sem feitos.", "A8-2RemissaoAnt"),
        anterior("2.1", "01.002.01", "1806.31.10", "Chocolates antigos"),
    )
    atual, antiga = por_item(d, "2.1")
    assert atual.situacao == "vigente" and antiga.situacao == "sem_efeitos"


def test_redacao_anterior_formatada_como_vigente_e_corrigida():
    # Água de coco: a redação antiga está em preto na página.
    d = ler(
        nota("Nova redação do item 11.0 do ANEXO II pelo Conv. ICMS 51/24, efeitos a partir de 01.06.24."),
        linha("11.0", "01.011.00", "2009.89.2", "Água de coco"),
        nota("Redação original, efeitos até 31.05.24", "A8-2RemissaoAnt"),
        linha("11.0", "01.011.00", "2009.8", "Água de coco"),
        linha("12.0", "01.012.00", "0402.1", "Leite em pó"),
    )
    atual, antiga, leite = d["redacoes"]
    assert (atual.situacao, antiga.situacao, antiga.ncm_sh) == ("vigente", "anterior", "2009.8")
    assert leite.situacao == "vigente"  # o bloco de redações anteriores termina no item seguinte
    assert d["divergencias"][0]["item"] == "11.0"


def test_item_com_classe_de_titulo_continua_sendo_item():
    d = ler(
        nota("Acrescido o item 65.0 ao Anexo II pelo Conv. ICMS 108/22, efeitos a partir de 01.09.22."),
        linha("65.0", "01.065.00", "5601.21.10", "Algodão hidrófilo", classe="A7-1TabelaSubtitulo"),
    )
    (r,) = por_item(d, "65.0")
    assert (r.situacao, r.vigencia_inicio) == ("vigente", date(2022, 9, 1))


def test_nota_que_cita_outro_item_e_associada_e_registrada():
    # A página repete a nota do item 63.0 na frente do item 85.0.
    d = ler(
        linha("84.0", "01.084.00", "9104.00.00", "Relógios"),
        nota("Nova redação dada ao item 63.0 do Anexo II pelo Conv. ICMS 66/22, efeitos a partir de 02.05.22."),
        linha("85.0", "01.085.00", "9401.99.00", "Assentos"),
    )
    (r,) = por_item(d, "85.0")
    assert r.vigencia_inicio == date(2022, 5, 2)
    assert "63.0" in d["divergencias"][0]["problema"] and not d["notas_soltas"]


def test_redacao_futura():
    d = ler(
        nota("Acrescido o item 46.1 do Anexo II pelo Convênio ICMS 107/26, efeitos a partir de 01.12.26."),
        linha("46.1", "01.046.01", "8516.60.00", "Fogões"),
    )
    (r,) = por_item(d, "46.1")
    assert (r.situacao, r.norma_alteradora) == ("futura", "Conv. ICMS 107/26")


def test_itens_citados_listas_e_intervalos():
    assert c.itens_citados("Acrescidos os itens 21.1, 21.2, 21.3 e 21.4 ao Anexo IV") == {"21.1", "21.2", "21.3", "21.4"}
    assert c.itens_citados("Acrescidos os itens 5.2 a 5.5 ao Anexo XIV") == {"5.2", "5.3", "5.4", "5.5"}
    assert c.itens_citados("Revogado o item14 do Anexo IV") == {"14"}
    assert c.chave_item("42.0") == c.chave_item("42") and c.chave_item("1.1") != c.chave_item("11")


def test_validacao_aponta_cest_vigente_duplicado():
    d = ler(linha("1.0", "01.001.00", "3815", "A"), linha("1.1", "01.001.00", "3815", "B"))
    assert any("01.001.00" in a for a in c.validar(d))

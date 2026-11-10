"""Rio Grande do Sul: RICMS, Apêndice II, Seção III (Receita Estadual, 09/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import estado_rs as rs  # noqa: E402


def test_nota_de_excecao_de_origem():
    assert rs.ufs_excluidas("NOTA - Este número não se aplica às operações originárias do Estado de SP.") == ["SP"]
    assert rs.ufs_excluidas("NOTA - Este número não se aplica às operações originárias dos Estados de MG e SP.") == ["MG", "SP"]
    assert rs.ufs_excluidas("NOTA - Ver Nota 04 desta Seção.") == []


def test_linha_da_tabela():
    html = """<table><tr><td>ITEM XXVI - MATERIAIS DE CONSTRUÇÃO E CONGÊNERES</td></tr>
    <tr><td>NÚMERO</td><td>MERCADORIA</td><td>NCM</td><td>CÓDIGO ESPECIFICADOR DA SUBSTITUIÇÃO TRIBUTÁRIA - CEST</td><td>MVA</td></tr>
    <tr><td>54</td><td>Parafusos NOTA - Este número não se aplica às operações originárias do Estado de SP.</td>
        <td>7318</td><td>10.058.00</td><td>69,00</td><td>79,18</td><td>95,46</td></tr>
    <tr><td>58</td><td>Abraçadeiras (Redação dada pelo art. 1º (Alteração 6847) do Decreto 58.901, de 03/08/26.
        (DOE 04/08/26) - Efeitos a partir de 01/08/26.)</td><td>7326</td><td>10.062.00</td><td>103,00</td><td>115,22</td><td>134,79</td></tr>
    </table>"""
    itens = {i["cest"]: i for i in rs.ler_html(html)}
    assert itens["10.058.00"]["nao_se_aplica_origem"] == "SP"
    assert itens["10.058.00"]["descricao"] == "Parafusos"
    a = itens["10.062.00"]
    assert (a["mva_interna"], a["mva_inter_12"], a["mva_inter_4"]) == ("103.00", "115.22", "134.79")
    assert a["vigencia_inicio"] == "2026-08-01"


ITENS = RAIZ / "dados" / "estados" / "RS" / "itens.csv"


@pytest.mark.skipif(not ITENS.exists(), reason="dados ainda não gerados")
def test_mva_do_rs_conferida_na_econet_e_no_erp():
    with ITENS.open(encoding="utf-8") as f:
        por_cest = {r["cest"]: r for r in csv.DictReader(f) if r["item_apendice"] == "XXVI"}
    for cest, mva in {"10.062.00": "103.00", "10.079.00": "71.00", "10.046.00": "73.00", "10.044.00": "64.00"}.items():
        assert por_cest[cest]["mva_interna"] == mva, cest
        assert "SP" not in por_cest[cest]["nao_se_aplica_origem"].split(";"), cest


@pytest.mark.skipif(not (RAIZ / "dados" / "estados" / "RS" / "cruzamento_prot_92_09.csv").exists(),
                    reason="dados ainda não gerados")
def test_rs_e_protocolo_92_09_concordam_nas_excecoes_de_sp():
    with (RAIZ / "dados" / "estados" / "RS" / "cruzamento_prot_92_09.csv").open(encoding="utf-8") as f:
        divergentes = [r for r in csv.DictReader(f) if r["situacao"] in ("so_rs_exclui", "so_protocolo_exclui")]
    assert not divergentes, divergentes

"""Pernambuco: Decreto 44.650/2017, Anexo 37-C (SEFAZ-PE, 10/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import estado_pe as pe  # noqa: E402

PAGINA = """<p><a name=anexo37c></a>ANEXO 37-C<br>(Dec. 58.019/2025 &#8211; efeitos a partir de 1&deg;.02.2025)</p>
<table><tr><td>ITEM DO ANEXO XI DO CONVÊNIO ICMS 142/2018</td><td>MVA (%)</td></tr>
<tr><td>46.0</td><td>37</td></tr><tr><td>62.0</td><td>80</td></tr>
<tr><td>ITEM DO ANEXO II DO CONVÊNIO ICMS 142/2018</td><td>MVA (%)</td></tr>
<tr><td>87.0</td><td>70</td></tr></table><table><tr><td>99.0</td><td>1</td></tr></table>"""


def test_recorta_e_le_a_tabela_com_troca_de_anexo():
    cab, tabela = pe.recortar_anexo(PAGINA)
    assert cab.startswith("ANEXO 37-C (Dec. 58.019/2025")
    linhas = pe.ler_tabela(tabela)
    assert [(l["anexo_conv142"], l["item_conv142"], l["mva"]) for l in linhas] == [
        ("XI", "46.0", "37"), ("XI", "62.0", "80"), ("II", "87.0", "70")]


ITENS = RAIZ / "dados" / "estados" / "PE" / "itens.csv"


@pytest.mark.skipif(not ITENS.exists(), reason="dados ainda não gerados")
def test_mva_do_pe_nos_produtos_conferidos():
    with ITENS.open(encoding="utf-8") as f:
        por_cest = {r["cest"]: r["mva"] for r in csv.DictReader(f)}
    assert {c: por_cest[c] for c in ("10.046.00", "10.062.00", "10.079.00")} == {
        "10.046.00": "37", "10.062.00": "80", "10.079.00": "47"}


@pytest.mark.skipif(not (RAIZ / "dados" / "estados" / "PE" / "cruzamento_prot_128_10.csv").exists(),
                    reason="dados ainda não gerados")
def test_unica_divergencia_com_o_prot_128_10_e_o_fibrocimento():
    with (RAIZ / "dados" / "estados" / "PE" / "cruzamento_prot_128_10.csv").open(encoding="utf-8") as f:
        dif = [r for r in csv.DictReader(f) if r["situacao"] in ("mva_diferente", "cest_fora_do_anexo_37c")]
    assert [(r["item_protocolo"], r["mva_protocolo"], r["mva_pe"]) for r in dif] == [("38.1", "56", "41")]

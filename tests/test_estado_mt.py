"""Mato Grosso: Apêndice do Anexo X do RICMS e Portaria 195/2019-SEFAZ (09/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import estado_mt as mt  # noqa: E402

PORTARIA = """<html><body>
<p>Art. 2°-B Ficam divulgados os percentuais de MVA:</p>
<p>X - materiais de construção e congêneres - CEST 10.001.00 a 10.080.00: 74,75%;</p>
<p>XV - produtos alimentícios - CEST 17.001.00 a 17.117.00: 59,75%; (Nova redação dada pela Port. 212/2022)</p>
<p>Redação original.</p>
<p>XV - produtos alimentícios - CEST 17.001.00 a 17.115.00: 59,75%;</p>
<p>V - ferramentas - CEST 08.001.00 a 08.019.00 e 08.020.00 a 08.023.00: 55,61%;</p>
<p>Art. 2°-C Nas operações com bens de informática...</p>
<table>
<tr><td>Item</td><td>CEST</td><td>NCM/SH</td><td>Descrição</td><td>MVA</td></tr>
<tr><td>23.0</td><td>...</td><td>...</td><td>... (Nova redação dada à coluna MVA pela Port. 099/2020)</td><td>excluído</td></tr>
<tr><td>23.0</td><td></td><td></td><td>... (Redação original)</td><td>52,14%</td></tr>
<tr><td>43.0</td><td>10.043.00</td><td>7213</td><td>Outros vergalhões (Nova redação dada pela Port. 127/2021)</td><td>30,41%</td></tr>
<tr><td>43.0</td><td>10.043.00</td><td>7213<br>7308.90.10</td><td>Outros vergalhões (Redação original)</td><td>30,41%</td></tr>
<tr><td>58.0</td><td>10.058.00</td><td>7318</td><td>Parafusos (Nova redação dada pela Port. 161/2022)</td><td>52,14%</td></tr>
<tr><td>58.0</td><td>10.058.00</td><td>7318</td><td>Parafusos, pinos ou pernos</td><td>52,14%</td></tr>
<tr><td>62.0</td><td>10.062.00</td><td>7326</td><td>Abraçadeiras</td><td>52,14%</td></tr>
</table></body></html>"""


def test_redacoes_anteriores_da_portaria():
    linhas = mt.ler_portaria_tabelas(PORTARIA)
    vig = [(r["cest"], r["item"], r["mva"], r["situacao"]) for r in linhas if r["redacao"] == "vigente"]
    assert vig == [("", "23.0", "", "excluido"), ("10.043.00", "43.0", "30.41", ""),
                   ("10.058.00", "58.0", "52.14", ""), ("10.062.00", "62.0", "52.14", "")]
    anteriores = [r for r in linhas if r["redacao"] == "anterior"]
    assert len(anteriores) == 3
    assert next(r for r in anteriores if r["item"] == "43.0")["ncms"] == "7213;73089010"


def test_mva_do_art_2b_so_redacao_vigente():
    faixas = {f["inciso"]: f for f in mt.ler_portaria_art_2b(PORTARIA)}
    assert faixas["X"]["mva"] == "74.75"
    assert faixas["XV"]["faixas_cest"] == "17.001.00-17.117.00"
    assert faixas["V"]["faixas_cest"] == "08.001.00-08.019.00;08.020.00-08.023.00"
    assert mt.mva_sem_credito_outorgado("10.062.00", list(faixas.values())) == "74.75"
    assert mt.mva_sem_credito_outorgado("08.019.50", list(faixas.values())) == ""


DADOS = RAIZ / "dados" / "estados" / "MT"


@pytest.mark.skipif(not (DADOS / "itens_vigentes.csv").exists(), reason="dados ainda não gerados")
def test_mva_do_mt_nos_produtos_conferidos():
    with (DADOS / "itens_vigentes.csv").open(encoding="utf-8") as f:
        por_cest = {r["cest"]: r for r in csv.DictReader(f)}
    # conexões de aço, abraçadeiras e válvulas: 52,14% (crédito outorgado ou Simples) e 74,75% (demais)
    for cest in ("10.046.00", "10.062.00", "10.079.00"):
        assert por_cest[cest]["mva_credito_outorgado_ou_simples"] == "52.14", cest
        assert por_cest[cest]["mva_demais_contribuintes"] == "74.75", cest
    assert por_cest["10.044.00"]["mva_credito_outorgado_ou_simples"] == "30.41"
    assert por_cest["10.024.00"]["ncms"] == "6811"


@pytest.mark.skipif(not (DADOS / "cruzamento_prot_11_08.csv").exists(), reason="dados ainda não gerados")
def test_todo_cest_do_prot_11_08_existe_no_apendice_do_mt():
    with (DADOS / "cruzamento_prot_11_08.csv").open(encoding="utf-8") as f:
        fora = [r for r in csv.DictReader(f) if r["situacao"] == "cest_fora_do_apendice_mt"]
    assert not fora, fora

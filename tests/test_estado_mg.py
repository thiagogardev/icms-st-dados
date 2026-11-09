"""Padrões reais do RICMS/MG, Anexo VII, Parte 2 (SEF/MG, 09/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import estado_mg as mg  # noqa: E402


def test_ambito_com_rotulo_e_protocolos():
    cod, ufs, aplica = mg.ler_ambito(
        "Âmbito de Aplicação da Substituição Tributária: 10.1 Interno e nas seguintes unidades da Federação: "
        "Amapá (Protocolo ICMS 196/09), Bahia (Protocolo ICMS 26/10), Mato Grosso do Sul, Mato Grosso "
        "e São Paulo (Protocolo ICMS 32/09)")
    assert cod == "10.1" and aplica
    assert sorted(ufs) == ["AP", "BA", "MS", "MT", "SP"]
    assert ufs["SP"] == "Prot. ICMS 32/09" and ufs["AP"] == "Prot. ICMS 196/09"


def test_ambito_so_interno_e_inaplicabilidade():
    assert mg.ler_ambito("10.3 Interno") == ("10.3", {}, True)
    assert mg.ler_ambito("10.4 Inaplicabilidade do regime de Substituição Tributária") == ("10.4", {}, False)


def test_excecao_por_item():
    ambitos = {"10.1": (["AP", "BA", "ES", "PA", "PR", "RJ", "RS", "SP"], True), "10.2": (["DF"], True)}
    assert mg.ufs_do_item("10.1 (Exceção: SP)", ambitos)[0] == ["AP", "BA", "ES", "PA", "PR", "RJ", "RS"]
    ufs, interno, _ = mg.ufs_do_item("10.1 (Exceção: AP, BA, ES, PA, PR, RJ e RS) 10.2", ambitos)
    assert ufs == ["DF", "SP"] and interno
    assert mg.ufs_do_item("10.1 10.2*", ambitos)[0] == ["AP", "BA", "DF", "ES", "PA", "PR", "RJ", "RS", "SP"]


ITENS = RAIZ / "dados" / "estados" / "MG" / "itens.csv"


@pytest.mark.skipif(not ITENS.exists(), reason="dados ainda não gerados")
def test_mva_de_mg_conferida_na_econet():
    """MVA original e ST a partir de SP, conferidas na Lista ST da Econet em 09/11/2026."""
    with ITENS.open(encoding="utf-8") as f:
        por_cest = {r["cest"]: r for r in csv.DictReader(f)}
    esperado = {"10.062.00": "75", "10.079.00": "40", "10.046.00": "35", "10.044.00": "45"}
    for cest, mva in esperado.items():
        assert por_cest[cest]["mva_original"] == mva, cest
        assert "SP" in por_cest[cest]["ufs_origem_com_st"].split(";"), cest
    assert "SP" not in por_cest["10.064.00"]["ufs_origem_com_st"].split(";")   # "10.1 (Exceção: SP)"

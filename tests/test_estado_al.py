"""Alagoas: Decreto 90.309/2023, Anexo VIII (SEFAZ-AL, consolidado de 03/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import estado_al as al  # noqa: E402

DADOS = RAIZ / "dados" / "estados" / "AL"


def test_colunas_da_tabela():
    assert [al._coluna(x) for x in (35, 61, 106, 151, 260, 347, 412, 458, 505)] == [
        "item", "cest", "ncm", "descricao", "acordo", "mva", "aj12", "aj7", "aj4"]
    assert al._PCT.match("**56%").groups() == ("**", "56")
    assert al._PCT.match("*58,06%").groups() == ("*", "58,06")


@pytest.mark.skipif(not (DADOS / "itens.csv").exists(), reason="dados ainda não gerados")
def test_mva_de_al_nos_produtos_conferidos():
    with (DADOS / "itens.csv").open(encoding="utf-8") as f:
        por_cest = {r["cest"]: r for r in csv.DictReader(f)}
    esperado = {"10.046.00": ("37", "53.58", "67.54"), "10.062.00": ("80", "101.78", "120.13"),
                "10.079.00": ("47", "64.79", "79.77")}
    for cest, (orig, aj12, aj4) in esperado.items():
        r = por_cest[cest]
        assert (r["mva_original"], r["mva_ajustada_12"], r["mva_ajustada_4"]) == (orig, aj12, aj4), cest
        assert "104/08" in r["acordo"], cest
    # fibrocimento: 41% com frete na base, 56% sem frete
    assert (por_cest["10.024.00"]["mva_original"], por_cest["10.024.00"]["mva_original_sem_frete_na_base"]) == ("41", "56")


@pytest.mark.skipif(not (DADOS / "cruzamento_prot_104_08.csv").exists(), reason="dados ainda não gerados")
def test_al_e_prot_104_08_sem_divergencia():
    with (DADOS / "cruzamento_prot_104_08.csv").open(encoding="utf-8") as f:
        ruins = [r for r in csv.DictReader(f) if r["situacao"] not in ("coerente", "sem_cest")]
    assert not ruins, ruins

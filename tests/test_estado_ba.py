"""Bahia: Anexo 1 do RICMS-BA, redação vigente 2026 (SEFAZ-BA, 09/11/2026)."""

import csv
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
HIST = RAIZ / "dados" / "estados" / "BA" / "itens_historico.csv"
CRUZ = RAIZ / "dados" / "estados" / "BA" / "cruzamento_prot_104_09.csv"


def _linhas():
    with HIST.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.skipif(not HIST.exists(), reason="dados ainda não gerados")
def test_mva_da_ba_conferida_no_erp_e_na_econet():
    vig = {(r["cest"], r["ncm_sh"]): r for r in _linhas() if r["situacao"] == "vigente"}
    for (cest, ncm), mva in {("10.062.00", "7326"): "85", ("10.079.00", "8481"): "45",
                             ("10.046.00", "7307"): "35", ("10.044.00", "7312"): "45"}.items():
        r = vig[(cest, ncm)]
        assert r["mva_original"] == mva, cest
        assert "SP" in r["acordo"], cest


@pytest.mark.skipif(not HIST.exists(), reason="dados ainda não gerados")
def test_redacao_anterior_entre_aspas():
    """Vidros (8.33): até 31/12/2025 o acordo incluía o Prot. 104/09 (SP); a redação de 2026 não."""
    linhas = [r for r in _linhas() if r["cest"] == "10.033.00"]
    ant = [r for r in linhas if r["situacao"] == "anterior"]
    vig = [r for r in linhas if r["situacao"] == "vigente"]
    assert len(ant) == 1 and len(vig) == 1
    assert ant[0]["vigencia_fim"] == "2025-12-31" and "SP" in ant[0]["acordo"]
    assert vig[0]["vigencia_inicio"] == "2026-01-01" and "SP" not in vig[0]["acordo"]


@pytest.mark.skipif(not CRUZ.exists(), reason="dados ainda não gerados")
def test_cruzamento_com_prot_104_09_sem_surpresas():
    with CRUZ.open(encoding="utf-8") as f:
        divergentes = {r["cest"] for r in csv.DictReader(f) if r["situacao"] != "coerente"}
    # 4 casam só por NCM (como em MG) e 2 são conflitos reais registrados no README
    assert divergentes <= {"10.017.00", "10.029.00", "10.030.01", "10.050.00", "10.043.00", "10.064.00"}, divergentes

"""Paraná: Resolução SEFA 571/2019 consolidada (SEFANET, 09/11/2026)."""

import csv
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
HIST = RAIZ / "dados" / "estados" / "PR" / "mva_historico.csv"


@pytest.mark.skipif(not HIST.exists(), reason="dados ainda não gerados")
def test_mva_do_pr_conferida_na_norma_e_na_econet():
    """Art. 16 (construção): MVA de 01/04/2026 (Res. SEFA 1.245/2025) e a anterior, conferidas em 09/11/2026."""
    with HIST.open(encoding="utf-8") as f:
        linhas = [r for r in csv.DictReader(f) if r["artigo"] == "16"]

    def achar(cest, situacao):
        rs = [r for r in linhas if r["cest"] == cest and r["situacao"] == situacao]
        assert len(rs) == 1, (cest, situacao, rs)
        return rs[0]

    for cest, atual, antiga in [("10.062.00", "89.91", "75"), ("10.079.00", "68.05", "50"),
                                ("10.046.00", "53.59", "39"), ("10.044.00", "60.29", "45")]:
        v, a = achar(cest, "vigente"), achar(cest, "anterior")
        assert (v["mva_original"], v["vigencia_inicio"]) == (atual, "2026-04-01")
        assert (a["mva_original"], a["vigencia_fim"]) == (antiga, "2026-03-31")
    # o cabo: "7217.10.90" numa linha e "73.12" na seguinte, na mesma célula
    assert achar("10.044.00", "vigente")["ncm_sh"] == "7217.10.90 73.12"


@pytest.mark.skipif(not HIST.exists(), reason="dados ainda não gerados")
def test_construcao_sem_redacao_vigente_duplicada():
    with HIST.open(encoding="utf-8") as f:
        vig = [(r["cest"], r["ncm_sh"]) for r in csv.DictReader(f) if r["artigo"] == "16" and r["situacao"] == "vigente"]
    assert len(vig) == len(set(vig))

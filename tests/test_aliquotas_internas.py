"""Alíquotas internas e FCP dos 27 estados (leitura de 10/11/2026)."""

import csv
from pathlib import Path

ARQ = Path(__file__).resolve().parent.parent / "dados" / "estados" / "aliquotas_internas.csv"
UFS = set("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split())


def _linhas():
    with ARQ.open(encoding="utf-8") as f:
        return {r["uf"]: r for r in csv.DictReader(f)}


def test_todas_as_ufs_uma_vez_com_base_legal():
    t = _linhas()
    assert set(t) == UFS
    for uf, r in t.items():
        assert r["base_legal"], uf
        assert r["fonte_oficial_conferida"] in ("sim", "parcial", "nao"), uf
        assert r["confianca"] in ("alta", "media", "baixa"), uf
        assert abs(float(r["aliquota_interna"]) + float(r["fcp_geral"]) - float(r["carga_geral"])) < 1e-9, uf
        assert 17 <= float(r["aliquota_interna"]) <= 23, uf
        if r["fonte_oficial_conferida"] != "nao":
            assert r["url_oficial"].startswith("http"), uf


def test_valores_conferidos():
    t = _linhas()
    # as 12 UFs que a Consulta de ICMS ST do Escrituro já usava, mais SP e o FCP geral de RJ, AL e SE
    esperado = {"AL": (20.5, 1), "AP": (18, 0), "BA": (20.5, 0), "DF": (20, 0), "ES": (17, 0), "MG": (18, 0),
                "MT": (17, 0), "PA": (19, 0), "PE": (20.5, 0), "PR": (19.5, 0), "RJ": (20, 2), "RS": (17, 0),
                "SP": (18, 0), "SE": (19, 1), "MA": (23, 0), "PI": (22.5, 0)}
    for uf, (aliq, fcp) in esperado.items():
        assert (float(t[uf]["aliquota_interna"]), float(t[uf]["fcp_geral"])) == (aliq, fcp), uf
    assert {uf for uf, r in t.items() if r["fcp_em_construcao"] == "sim"} == {"AL", "RJ", "SE"}

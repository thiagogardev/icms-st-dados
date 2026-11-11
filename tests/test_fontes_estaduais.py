"""Registro das fontes estaduais de ST (10/11/2026)."""

import csv
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
UFS = set("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split())


def test_todas_as_ufs_com_situacao():
    with (RAIZ / "dados" / "estados" / "fontes_estaduais.csv").open(encoding="utf-8") as f:
        t = {r["uf"]: r for r in csv.DictReader(f)}
    assert set(t) == UFS
    for uf, r in t.items():
        assert r["situacao_leitura"] in ("lido", "levantado", "bloqueado", "sem_fonte"), uf
        if r["situacao_leitura"] == "lido":
            pasta = r["conjunto"].split(" ")[0]
            assert (RAIZ / pasta).exists(), (uf, pasta)
        if r["situacao_leitura"] == "bloqueado":
            assert r["observacao"], uf
    assert {uf for uf, r in t.items() if r["situacao_leitura"] == "bloqueado"} >= {"RJ", "DF", "PA"}

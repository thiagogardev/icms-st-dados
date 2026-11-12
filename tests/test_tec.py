"""TEC: Anexos da Resolução Gecex 272/2021 (planilha do MDIC lida em 12/11/2026)."""

import csv
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import tec  # noqa: E402

DADOS = RAIZ / "dados" / "tec"


def test_ler_aliquota():
    assert tec.ler_aliquota("12.6") == (12.6, "")
    assert tec.ler_aliquota("12,6BK") == (12.6, "BK")
    assert tec.ler_aliquota("0BIT") == (0.0, "BIT")
    assert tec.ler_aliquota(18) == (18.0, "")
    assert tec.ler_aliquota(None) == (None, "")


def test_datas():
    assert tec._data("05/05/2022") == date(2022, 5, 5)
    assert tec._data("2026-12-04 00:00:00") == date(2026, 12, 4)
    assert tec._data("-") is None


@pytest.mark.skipif(not (DADOS / "tec.csv").exists(), reason="dados ainda não gerados")
def test_gabarito():
    with (DADOS / "tec.csv").open(encoding="utf-8") as f:
        t = {r["ncm"]: r for r in csv.DictReader(f)}
    assert len(t) > 10000
    # mangueira de borracha: 12,6% pelo Anexo II (conferido na TECnet em 09/11/2026)
    r = t["40093100"]
    assert (r["ii_tec"], r["ii_aplicada"], r["ii_vigente"]) == ("12.6", "12.6", "12.6")
    assert r["fonte_ii_vigente"] == "Anexo II (aplicada)"
    # válvula esfera: BK no Anexo I
    assert t["84818095"]["bit_bk"] == "BK"
    for n, r in t.items():
        assert len(n) == 8 and n.isdigit(), n
        assert r["ii_vigente"] != "" or r["ii_tec"] == "", n

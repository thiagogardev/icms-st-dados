"""TIPI (Receita Federal, planilha oficial consolidada, lida em 10/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import tipi  # noqa: E402


def test_aliquota_e_nivel():
    assert tipi.aliquota("3.25") == ("3.25", "3,25")
    assert tipi.aliquota("NT") == ("", "NT")
    assert tipi.aliquota(None) == ("", "")
    assert tipi.aliquota(0) == ("0", "0")
    assert [tipi.nivel(n) for n in ("73.07", "7307.1", "7307.19", "7307.19.1", "7307.19.10")] == [
        "posicao", "subposicao_1", "subposicao", "item", "subitem"]


NCM8 = RAIZ / "dados" / "tipi" / "tipi_ncm8.csv"


@pytest.mark.skipif(not NCM8.exists(), reason="dados ainda não gerados")
def test_aliquotas_conferidas_na_tabela_oficial():
    with NCM8.open(encoding="utf-8") as f:
        t = {(r["ncm"], r["ex"]): r["aliquota_texto"] for r in csv.DictReader(f)}
    assert t[("73071910", "")] == "3,25"
    assert t[("73261900", "")] == "6,5"
    assert t[("84818095", "")] == "0"
    assert t[("84818029", "1")] == "3,25"  # Ex 01: gaveta ou esfera, de ferro ou aço ou de cobre
    assert t[("73121090", "")] == "9,75" and t[("73121090", "1")] == "3,25"
    assert len({n for n, ex in t if not ex}) > 10000

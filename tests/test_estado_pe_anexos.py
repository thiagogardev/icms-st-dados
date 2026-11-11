"""Pernambuco: Anexos 37-A, 37-B e 37-C do Decreto 44.650/2017 (SEFAZ-PE, leitura de 10/11/2026)."""

import csv
import json
from pathlib import Path

import pytest

DADOS = Path(__file__).resolve().parent.parent / "dados" / "estados" / "PE"


@pytest.mark.skipif(not (DADOS / "itens_todos_anexos.csv").exists(), reason="dados ainda não gerados")
def test_tres_anexos_e_mvas_conferidas():
    with (DADOS / "itens_todos_anexos.csv").open(encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    por = {(r["anexo_pe"], r["cest"]): r for r in linhas}
    assert {r["anexo_pe"] for r in linhas} == {"37-A", "37-B", "37-C"}
    assert por[("37-A", "20.001.00")]["mva"] == "76.45"   # perfumaria, item 1.0 do Anexo XIX
    assert por[("37-B", "12.001.00")]["mva"] == "50"      # transformadores, item 1.0 do Anexo XIII
    assert por[("37-C", "10.024.00")]["mva"] == "41"      # construção, igual ao itens.csv
    with (DADOS / "itens.csv").open(encoding="utf-8") as f:
        velho = {(r["anexo_conv142"], r["item_conv142"]): r["mva"] for r in csv.DictReader(f)}
    novo = {(r["anexo_conv142"], r["item_conv142"]): r["mva"] for r in linhas if r["anexo_pe"] == "37-C"}
    assert velho == novo


@pytest.mark.skipif(not (DADOS / "anexos.json").exists(), reason="dados ainda não gerados")
def test_cabecalhos_com_vigencia():
    meta = json.loads((DADOS / "anexos.json").read_text(encoding="utf-8"))
    for nome in ("37-A", "37-B", "37-C"):
        assert "efeitos a partir de" in meta["cabecalhos"][nome], nome

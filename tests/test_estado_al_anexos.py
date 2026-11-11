"""Alagoas: todos os anexos de ST do Decreto 90.309/2023 (SEFAZ-AL, consolidado de 03/11/2026)."""

import csv
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import estado_al_anexos as al  # noqa: E402

DADOS = RAIZ / "dados" / "estados" / "AL"


def test_protocolos_do_acordo():
    assert al.protocolos_do_acordo("Protocolos ICMS 41/08 e 97/10") == {"41/08", "97/10"}
    assert al.protocolos_do_acordo("Protocolo ICMS 15/2007") == {"15/07"}
    assert al.protocolos_do_acordo("188/09 Prot. ICMS") == {"188/09"}
    assert al.protocolos_do_acordo("Sem Acordo") == set()


def test_coluna_ignora_chaves_internas():
    col = {"cest": 60, "ncm": 100, "descricao": 145, "_fim": 400}
    assert [al._coluna(x, col) for x in (30, 70, 120, 300, 500)] == ["item", "cest", "ncm", "descricao", "descricao"]


@pytest.mark.skipif(not (DADOS / "itens_todos_anexos.csv").exists(), reason="dados ainda não gerados")
def test_anexo_viii_igual_ao_leitor_de_construcao():
    with (DADOS / "itens.csv").open(encoding="utf-8") as f:
        velho = {r["item"]: r for r in csv.DictReader(f)}
    with (DADOS / "itens_todos_anexos.csv").open(encoding="utf-8") as f:
        novo = {r["item"]: r for r in csv.DictReader(f) if r["anexo"] == "VIII"}
    assert set(velho) == set(novo)
    for k, v in velho.items():
        for c in ("cest", "mva_original", "mva_original_sem_frete_na_base", "mva_ajustada_12", "mva_ajustada_7", "mva_ajustada_4"):
            assert v[c] == novo[k][c], (k, c)


@pytest.mark.skipif(not (DADOS / "itens_todos_anexos.csv").exists(), reason="dados ainda não gerados")
def test_itens_conferidos_em_outros_anexos():
    with (DADOS / "itens_todos_anexos.csv").open(encoding="utf-8") as f:
        por_cest = {r["cest"]: r for r in csv.DictReader(f)}
    # furadeiras (eletrônicos, Prot. 15/07) e chocolate branco (alimentos, cap. I)
    assert (por_cest["21.100.00"]["anexo"], por_cest["21.100.00"]["mva_original"], por_cest["21.100.00"]["mva_ajustada_4"]) == ("XV", "72.15", "110.53")
    assert "15/07" in por_cest["21.100.00"]["protocolos_citados"]
    assert (por_cest["17.001.00"]["anexo"], por_cest["17.001.00"]["capitulo"], por_cest["17.001.00"]["mva_original"]) == ("XII", "I", "61.26")
    # autopeças: Protocolos 41/08 e 97/10
    assert por_cest["01.002.00"]["protocolos_citados"] == "41/08;97/10"


@pytest.mark.skipif(not (DADOS / "anexos.json").exists(), reason="dados ainda não gerados")
def test_contagens_e_sem_mva_diferente():
    meta = json.loads((DADOS / "anexos.json").read_text(encoding="utf-8"))
    assert len(meta["anexos"]) >= 20 and meta["contagens"]["itens"] >= 900
    assert meta["contagens"]["cruzamento"]["mva_diferente"] == 0

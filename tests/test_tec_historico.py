"""TEC com vigência por data (versões dos Anexos da Res. Gecex 272/2021, leitura de 12/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import tec_historico as h  # noqa: E402

ARQ = RAIZ / "dados" / "tec" / "tec_historico.csv"


@pytest.fixture(scope="module")
def linhas():
    if not ARQ.exists():
        pytest.skip("dados ainda não gerados")
    with ARQ.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_nf_13_de_2023_da_garoflex(linhas):
    # DI de 10/10/2023, mangueira 4009.31.00: 11,2% pelo art. 7º (redução temporária até 31/12/2023)
    l = h.aliquota_em(linhas, "40093100", "2023-10-10")
    assert (l["aliquota_ii"], l["origem"]) == ("11.2", "Anexo II (aplicada)") and "Art. 7" in l["ato"]
    assert h.aliquota_em(linhas, "40093100", "2024-01-01")["aliquota_ii"] == "12.6"
    assert h.aliquota_em(linhas, "40093100", "2026-11-12")["aliquota_ii"] == "12.6"


def test_excecao_temporaria_com_correcao(linhas):
    # poliestireno 3903.11.20: elevação do Anexo IX; a versão de 11/11/2026 corrigiu 18% para 20% (Res. 963)
    assert h.aliquota_em(linhas, "39031120", "2025-01-10")["origem"] == "Anexo IX (DCC)"
    l = h.aliquota_em(linhas, "39031120", "2026-11-12")
    assert (l["aliquota_ii"], l["ato"]) == ("20", "Resolução Gecex nº 963")


def test_intervalos_sem_sobreposicao_e_igual_ao_tec_de_hoje(linhas):
    por = {}
    for l in linhas:
        por.setdefault(l["ncm"], []).append(l)
    for n, ls in por.items():
        ls.sort(key=lambda l: l["vigencia_inicio"])
        for a, b in zip(ls, ls[1:]):
            assert a["vigencia_fim"] and a["vigencia_fim"] < b["vigencia_inicio"], n
    assert min(l["vigencia_inicio"] for l in linhas) == "2022-09-01"
    with (RAIZ / "dados" / "tec" / "tec.csv").open(encoding="utf-8") as f:
        hoje = {r["ncm"]: r["ii_vigente"] for r in csv.DictReader(f)}
    data = (RAIZ / "dados" / "tec" / "metadados.json").read_text(encoding="utf-8").split('"data_referencia": "')[1][:10]
    dif = [n for n in hoje if (l := h.aliquota_em(por.get(n, []), n, data)) and l["aliquota_ii"] != hoje[n]]
    assert not dif, dif[:5]

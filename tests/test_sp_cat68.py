"""SP: Portaria CAT 68/2019 consolidada (leitura de 10/11/2026)."""

import csv
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import sp_cat68 as sp  # noqa: E402

DADOS = RAIZ / "dados" / "sp"


def test_data_da_nota():
    assert sp.data_da_nota("Anexo revogado pela Portaria SRE-34/26 , de 29-06-2026; DOE 30-06 -2026 ; em vigor em 1º de outubro de 2026") == "2026-10-01"
    assert sp.data_da_nota("Revogado, a partir de 1º de janeiro de 2026, pela Portaria SRE-64/25") == "2026-01-01"
    assert sp.data_da_nota("Item revogado pela Portaria CAT-57/21, de 06-08-2021; DOE 07-08-2021") == "2021-08-07"


def test_leitura_de_um_trecho():
    texto = "\n".join([
        "ANEXO XVII", "(Anexo revogado pela Portaria SRE-52/26, de 28-10-2026; DOE 29-10-2026; em vigor em 1º de fevereiro de 2027)",
        "MATERIAIS DE CONSTRUÇÃO E CONGÊNERES", "(artigo 313-Y do RICMS)", "ITEM | CEST | NCM/SH | DESCRIÇÃO",
        "1 | 10.001.00 | 2522 | Cal",
        "2 (Item revogado pela Portaria SRE-09/26, de 17-03-2026; DOE 18-03-2026; em vigor em 1º de julho de 2026 ) | 10.002.00 | 3816.00.1 | Argamassas",
        "2 | 10.002.00 | 3816.00.1 | Argamassas (redação antiga)",
    ])
    anexos, itens = sp.ler(texto, date(2026, 11, 10))
    assert anexos[0]["situacao"] == "revogacao_futura" and anexos[0]["revogado_desde"] == "2027-02-01"
    assert anexos[0]["revogado_por"] == "Portaria SRE-52/26" and anexos[0]["artigo_ricms"] == "art. 313-Y"
    assert [(i["item"], i["redacao"], i["situacao"]) for i in itens] == [
        ("1", "atual", "revogacao_futura"), ("2", "atual", "revogado"), ("2", "anterior", "redacao_anterior")]


@pytest.mark.skipif(not (DADOS / "cat68_anexos.csv").exists(), reason="dados ainda não gerados")
def test_anexos_conferidos():
    with (DADOS / "cat68_anexos.csv").open(encoding="utf-8") as f:
        a = {r["anexo"]: r for r in csv.DictReader(f)}
    assert len(a) == 22
    # saídas de 2026 conferidas no texto: autopeças, ferramentas, elétricos, pneus e tintas em 01/10/2026 (SRE 34/26),
    # limpeza e ração em 01/08/2026 (SRE 20/26), construção em 01/02/2027 (SRE 52/26)
    for anexo in ("VII", "VIII", "XIV", "XVIII", "XXI"):
        assert (a[anexo]["revogado_desde"], a[anexo]["revogado_por"]) == ("2026-10-01", "Portaria SRE-34/26"), anexo
    for anexo in ("XII", "XIII"):
        assert a[anexo]["revogado_desde"] == "2026-08-01", anexo
    assert (a["XVII"]["revogado_desde"], a["XVII"]["revogado_por"]) == ("2027-02-01", "Portaria SRE-52/26")
    assert {k for k, v in a.items() if v["situacao"] == "vigente"} == {"I", "II", "III", "V", "VI", "XVI", "XXII"}

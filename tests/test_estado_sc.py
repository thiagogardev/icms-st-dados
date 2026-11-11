"""Santa Catarina: RICMS-SC, Anexo 3 (SEF-SC, 10/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import estado_sc as sc  # noqa: E402

TEXTO = ("Seção I Das Operações com Cerveja, Chope, Refrigerante e Outras Bebidas Art. 9 Seção II Das Operações com "
         "Sorvete - REVOGADA Seção III Das Operações com Cimento (Protocolo ICMS 30/97) Art. 13 Seção XII – REVOGADA "
         "( arts. 71 a 76-B ) Seção XXVIII Das Operações com Combustíveis e Lubrificantes (Convênio ICMS 110/07 ) "
         "Subseção V Das Operações Realizadas por Importador - REVOGADA Art. 200")


def test_secoes_vigentes_e_revogadas():
    s = {x["secao"]: x for x in sc.ler_secoes(TEXTO)}
    assert s["I"]["situacao"] == "vigente" and s["I"]["segmento"] == "03"
    assert s["II"]["situacao"] == "revogada"
    assert s["III"]["situacao"] == "vigente" and s["III"]["segmento"] == "05"
    assert s["XII"]["situacao"] == "revogada"
    assert "V" not in s  # subseção do segmento de combustíveis não é seção


EFEITOS = RAIZ / "dados" / "estados" / "efeito_no_destino.csv"


@pytest.mark.skipif(not EFEITOS.exists(), reason="dados ainda não gerados")
def test_protocolos_sem_efeito_em_sc():
    with EFEITOS.open(encoding="utf-8") as f:
        sc_ = {r["protocolo"] for r in csv.DictReader(f) if r["uf"] == "SC"}
    # 193/09 e 91/07 saíram da lista: SC foi excluída desses protocolos (Prots. ICMS 10/19 e 83/19), então SC já
    # não é destino na matriz e o efeito não precisa ser marcado.
    assert {"Prot. ICMS 20/05", "Prot. ICMS 203/09"} <= sc_
    assert not sc_ & {"Prot. ICMS 193/09", "Prot. ICMS 91/07"}
    assert "Prot. ICMS 103/12" not in sc_  # bebidas quentes seguem na ST em SC (Seção XLIV)

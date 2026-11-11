"""Goiás: RCTE, Anexo VIII, Apêndice II vigente (SEFAZ-GO, 10/11/2026)."""

import csv
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import estado_go as go  # noqa: E402
import protocolos as p  # noqa: E402

TRECHO = ("Redação conferida pelo Decreto nº 8.819 - vigência: 01.01.17 SUBSTITUIÇÃO TRIBUTÁRIA I - BEBIDA (Protocolos ICMS "
          "11/91 e 19/97 ) Notas: 1. O Índice XV - MATERIAL DE CONSTRUÇÃO, ACABAMENTO, BRICOLAGEM OU ADORNO . (Mercadorias "
          "excluídas da sistemática da Substituição Tributária pelo Decreto n° 9.108 a partir de 01.03.18 – vigência: 24.02.16 a "
          "28.02.18) (Protocolos ICMS 82/11 e 85/11 ) NOTAS: 1. Vide Item Descrição CEST NCM APÊNDICE III")


def test_segmentos_e_exclusao():
    segs = {s["inciso"]: s for s in go.ler_segmentos(go.apendice_ii_vigente(TRECHO))}
    assert segs["I"]["situacao"] == "vigente" and segs["I"]["normas"] == "Prot. ICMS 11/91;Prot. ICMS 19/97"
    xv = segs["XV"]
    assert (xv["situacao"], xv["excluido_por"], xv["excluido_desde"]) == ("excluido", "Decreto 9.108", "2018-03-01")
    assert {e["protocolo"] for e in go.efeitos(list(segs.values()))} == {"Prot. ICMS 82/11", "Prot. ICMS 85/11"}


MATRIZ = RAIZ / "dados" / "protocolos" / "matriz_origem_destino.csv"


@pytest.mark.skipif(not MATRIZ.exists(), reason="dados ainda não gerados")
def test_sp_para_go_construcao_sem_efeito():
    """Prot. 82/11 segue vigente no Confaz, mas GO tirou construção da ST em 01/03/2018 (Decreto 9.108/2017)."""
    with MATRIZ.open(encoding="utf-8") as f:
        m = list(csv.DictReader(f))
    linhas = p.consultar(m, "73071910", "GO", origem="SP")
    assert linhas and all(r["protocolo"] == "Prot. ICMS 82/11" for r in linhas)
    assert all("9.108" in r["efeito_no_destino"] for r in linhas)

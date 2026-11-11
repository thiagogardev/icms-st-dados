"""Exclusões, denúncias e adesões nas notas do cabeçalho dos protocolos (Confaz)."""

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import catalogo_protocolos as c  # noqa: E402

# Trecho das notas do Prot. ICMS 85/11 como estão no Confaz (10/11/2026).
NOTAS_85_11 = ("Adesão do RJ pelo Protocolo 170/12 , efeitos a partir da data prevista na legislação do Estado do Rio de "
               "Janeiro. Exclusão do RN pelo Protocolo 170/12 , efeitos a partir de 14.12.12. Alterado pelos Prots. ICMS "
               "221/12 , 161/13 . Adesão da PB pelo Protocolo ICMS 221/12 , efeitos na data prevista em ato do Poder "
               "Executivo do Estado da Paraíba. Exclusão do MA pelo Prot. ICMS 161/13 , efeitos a partir de 01.01.14 "
               "Denunciado por GO, conforme Despacho 182/17 . Adesão do PA pelo Prot. ICMS 62/21 , efeitos a partir de "
               "data prevista em ato do Poder Executivo. Exclusão de SE e outras alterações, pelo Prot. ICMS 12/23 , "
               "efeitos a partir de 01.07.23.")


def test_saidas_do_85_11():
    ev = c.mudancas_de_signatarios(NOTAS_85_11, date(2026, 11, 10))
    saidas = {e["uf"]: (e["norma"], e["desde"]) for e in ev if e["tipo"] == "saida"}
    assert saidas == {"RN": ("Protocolo 170/12", "2012-12-14"), "MA": ("Prot. ICMS 161/13", "2014-01-01"),
                      "GO": ("Despacho 182/17", ""), "SE": ("Prot. ICMS 12/23", "2023-07-01")}
    assert {e["uf"] for e in ev if e["tipo"] == "adesao"} == {"RJ", "PB", "PA"}


def test_saida_futura_nao_vale_ainda():
    ev = c.mudancas_de_signatarios("Exclusão do Estado de Minas Gerais pelo Prot. ICMS 9/27, efeitos a partir de 01.03.27.",
                                   date(2026, 11, 10))
    assert [(e["uf"], e["valendo"]) for e in ev] == [("MG", False)]


def test_nome_por_extenso_e_varios_estados():
    ev = c.mudancas_de_signatarios("Exclusão dos Estados de Alagoas e Sergipe pelo Protocolo ICMS 40/15.", date(2026, 1, 1))
    assert sorted(e["uf"] for e in ev) == ["AL", "SE"]


def test_datas_antes_e_depois_da_norma():
    ev = c.mudancas_de_signatarios(
        "Exclusão de SP pelo Prot. ICMS 93/26 e outras alterações, efeitos a partir de 01.10.26. "
        "Exclusão do PA, a partir de 21.02.18, pelo Prot. ICMS 07/18 . Denunciado pelo DF, conforme Despacho 88/08 .",
        date(2026, 11, 10))
    assert [(e["uf"], e["norma"], e["desde"]) for e in ev] == [
        ("SP", "Prot. ICMS 93/26", "2026-10-01"), ("PA", "Prot. ICMS 07/18", "2018-02-21"), ("DF", "Despacho 88/08", "")]

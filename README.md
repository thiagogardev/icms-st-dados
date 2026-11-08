# ICMS ST: dados abertos do Convênio ICMS 142/2018

A lista nacional de bens sujeitos à substituição tributária do ICMS (CEST,
NCM/SH, descrição e segmento), extraída do texto consolidado do Confaz e
organizada **com a vigência de cada redação**: o que vale hoje, o que valia
antes, desde quando e por qual convênio.

O Confaz publica o Convênio 142/2018 só como uma página HTML de cerca de 930 KB,
com as redações antigas misturadas às atuais e marcadas apenas por cor e por
notas de texto livre. Não existe planilha nem API oficial. Este repositório
transforma essa página em tabelas e mantém o código que faz isso, para que
qualquer pessoa possa refazer e conferir.

> Situação em 08/11/2026: **1.043 CESTs vigentes** em 25 segmentos, 1.220
> redações no histórico (136 anteriores, 12 revogadas, 29 que nunca tiveram
> efeito) e 222 itens do Anexo XXVII.

## Arquivos

Todos em `dados/conv142/`, UTF-8, separador vírgula.

| Arquivo | Conteúdo |
| --- | --- |
| `itens_vigentes.csv` | Um item por CEST vigente na data de referência. É o arquivo para a maioria dos usos |
| `itens_historico.csv` (e `.json`) | Todas as redações de todos os itens, com início e fim de vigência e situação |
| `segmentos.csv` | Os 25 segmentos do Anexo I, com o código (dois primeiros dígitos do CEST) e o anexo correspondente |
| `escala_nao_relevante_anexo_xxvii.csv` | Anexo XXVII: bens que podem ficar fora da ST quando o fabricante tem escala industrial não relevante (só a redação atual) |
| `divergencias_da_fonte.csv` | Inconsistências encontradas na própria página do Confaz e como foram tratadas |
| `notas_nao_associadas.csv` | Notas de alteração que o leitor não conseguiu ligar a nenhum item (deve ficar vazio) |
| `metadados.json` | Fonte, data de obtenção, hash SHA-256 da página lida, data de referência e contagens |

### Colunas de `itens_historico.csv`

| Coluna | Significado |
| --- | --- |
| `anexo` | Anexo do Convênio 142 (II a XXVI) |
| `segmento_codigo`, `segmento` | Segmento do Anexo I |
| `item` | Número do item no anexo, como está na norma |
| `cest` | Código Especificador da Substituição Tributária |
| `ncm_sh` | NCM/SH como está na norma (pode ter vários códigos e códigos parciais, que valem para todas as subposições) |
| `ncms` | Os mesmos códigos separados por `;` |
| `descricao` | Descrição legal do bem. Ela faz parte do enquadramento: um NCM só está sujeito à ST se o bem corresponder à descrição |
| `situacao` | `vigente`, `futura`, `anterior`, `revogada` ou `sem_efeitos`, calculada para a data de referência |
| `vigencia_inicio` | Início dos efeitos desta redação. Vazio = redação original do convênio |
| `vigencia_fim` | Fim dos efeitos. Vazio = sem fim previsto |
| `revogado_em` | Data em que o item foi revogado, quando for o caso |
| `norma_alteradora` | Convênio que deu esta redação ou que revogou o item |
| `origem` | `vigente_no_texto` (redação atual da página) ou `anterior_no_texto` (redação antiga, mantida pelo Confaz em verde) |
| `nota_alteracao`, `nota_vigencia` | As notas originais do Confaz das quais as datas foram tiradas, para conferência |

## Como as datas são obtidas

A página do Confaz marca a história de cada item assim:

```
Nova redação dada ao item 42.0 do Anexo II pelo Conv. ICMS 66/22, efeitos a partir de 02.05.22.
42.0 | 01.042.00 | 8421.32.00 | Depuradores por conversão catalítica ...     <- redação atual
Redação original, efeitos até 01.05.22.
42.0 | 01.042.00 | 8421.39.20 | Depuradores por conversão catalítica ...     <- redação anterior (verde)
```

O script `scripts/conv142.py` lê essas notas e as associa às linhas. As notas
são texto livre, com erros de digitação, então o leitor é tolerante, e toda
nota que não pode ser associada vai para `notas_nao_associadas.csv`. Quando
uma redação anterior não traz data final, ela termina na véspera da redação
seguinte do mesmo item.

### Inconsistências da fonte

Em 08/11/2026 a página tinha cinco, registradas em `divergencias_da_fonte.csv`:

- no Anexo II, a nota da nova redação do item 85.0 repete o texto da nota do
  item 63.0 (mesmo convênio e mesma data, item errado). A data foi associada ao
  item 85.0, que é a linha que a nota precede;
- no Anexo XVII, quatro redações anteriores (itens 2.1, 2.3, 11.0 e 24.0) estão
  formatadas como vigentes. Foram tratadas como anteriores pela nota que as
  precede.

### Validação

- Cada CEST vigente aparece uma única vez.
- Os dois primeiros dígitos de todo CEST correspondem a um segmento do Anexo I,
  e cada anexo tem um único segmento.
- Cruzamento com a Portaria CAT 68/2019 de São Paulo (lista paulista de bens
  sujeitos à ST, baseada no mesmo convênio): dos 762 CESTs que ela cita, todos
  existem aqui; 756 estão vigentes e os 6 restantes são itens que o próprio
  Convênio 142 revogou.
- Testes automáticos em `tests/` reproduzem cada padrão encontrado na página.

## Como refazer

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # no Linux: .venv/bin/...
.venv/Scripts/python scripts/conv142.py                   # baixa do Confaz e grava em dados/conv142
.venv/Scripts/python scripts/conv142.py --ref 2025-01-01  # situação em outra data
.venv/Scripts/python -m pytest -q
```

## Limites

- **Não é orientação tributária.** O Convênio 142 diz quais bens *podem* ter
  ST. Se um bem está de fato sujeito à ST numa operação depende da legislação
  de cada estado e dos protocolos e convênios entre a origem e o destino.
  Confira sempre a norma original antes de aplicar.
- MVA não está aqui: ela é definida por cada estado.
- O enquadramento exige NCM **e** descrição. Um NCM pode aparecer em vários
  CEST.
- A data de referência da coluna `situacao` está em `metadados.json`; para
  outra data, rode o script com `--ref`.

## Próximos conjuntos

Este é o primeiro conjunto de um projeto maior de monitoramento da legislação
de ICMS ST. Os próximos são a matriz de protocolos e convênios entre estados
(quais pares de UF têm ST em cada segmento) e as listas e MVAs estaduais.

## Licença

Os textos de atos oficiais não têm proteção de direito autoral (Lei 9.610/98,
art. 8º, IV). A organização dos dados neste repositório é distribuída sob
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.pt_BR) e o código
sob a licença MIT (arquivo `LICENSE`).

---

## English summary

Open data for Brazil's ICMS tax substitution (ST) national goods list,
Convênio ICMS 142/2018, parsed from the official Confaz consolidated HTML page
(the only format published). Each row is one wording of an item (CEST code,
NCM/HS codes, legal description) with its effective dates, so you can tell what
applies today, what applied before, and which agreement changed it. As of
2026-11-08: 1,043 valid CEST codes across 25 segments and 1,220 wordings in
the history. The parser is tolerant to the free-text notes, logs every
inconsistency found in the source, and is validated against São Paulo's state
list. Data under CC BY 4.0, code under MIT.

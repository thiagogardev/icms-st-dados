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

## Protocolos de materiais de construção com SP

O segundo conjunto, em `dados/protocolos/`, responde a uma pergunta prática:
**vendendo de São Paulo para outro estado, o remetente retém a ST deste
produto?** Ele lê os 11 protocolos de materiais de construção, acabamento,
bricolagem ou adorno de que SP é signatário (Prot. ICMS 11/08, 20/13, 25/11,
32/09, 32/14, 60/11, 71/11, 92/09, 104/08, 104/09 e 128/10), com a vigência de
cada item, e monta a matriz SP -> destino.

> Situação em 09/11/2026: 11 protocolos, 2.290 redações no histórico,
> 486 itens vigentes e 672 linhas na matriz (12 destinos: AL, AP, BA, DF, ES,
> MG, MT, PA, PE, PR, RJ, RS).

| Arquivo | Conteúdo |
| --- | --- |
| `matriz_sp_destino.csv` | Uma linha por item vigente e estado de destino: protocolo, item, NCM/SH, descrição, MVA original (quando o protocolo a fixa) e os CESTs prováveis do Convênio 142 |
| `itens_historico.csv` / `itens_vigentes.csv` | Todas as redações dos anexos, com início e fim de vigência, ou só as vigentes |
| `protocolos.csv` | Cada protocolo: signatários, destinos a partir de SP, modelo de lista, CESTs excluídos e quantos itens trazem MVA |
| `divergencias_da_fonte.csv` | Inconsistências das próprias páginas do Confaz |
| `metadados.json` | URL e hash SHA-256 de cada página lida, data de referência e contagens |

O que este levantamento mostrou:

- **Dois modelos de lista.** Nove protocolos têm lista própria de NCMs. RS
  (Prot. 92/09, desde 01/01/2026) e AP/PA (Prot. 60/11) passaram a valer para
  todo o Anexo XI do Convênio 142, menos os CESTs que a cláusula primeira
  exclui. Quem procura o item na lista antiga do protocolo do RS não acha nada,
  e quem lê só "Anexo Único revogado" conclui, errado, que a ST acabou.
- **A MVA nem sempre está no protocolo.** Em 6 dos 11 (MT, MG, AP/PA, PR, RS e
  BA) ela vem da legislação do estado de destino. A matriz deixa a coluna vazia
  nesses casos; o valor tem de vir da norma estadual.
- **A limpeza de 2025/2026.** Em 01/01/2026 os protocolos perderam dezenas de
  itens (Prot. ICMS 61/25 a 70/25 e 86/25), e em 01/08/2026 outros (Prot. 44/26 a
  78/26). Exemplo: a abraçadeira (NCM 7326.19.00) saiu do protocolo SP-MT, e
  uma base comercial consultada em 09/11/2026 ainda o listava.
- **Três erros nas páginas**, registrados em `divergencias_da_fonte.csv`: no
  Prot. 32/09, a nota que revoga o item 69 está seguida da linha
  "80. REVOGADO"; em dois itens (32/09 item 69 e 20/13 item 41), a data final
  da redação anterior não fecha com a data da revogação.

Validação: `tests/gabarito_protocolos.csv` tem 34 casos de NCM x destino
conferidos à mão no texto do protocolo e numa base comercial de referência;
o teste exige acerto em todos (presença do protocolo e, quando fixada, a MVA).

Limites próprios deste conjunto: o enquadramento é por NCM **e** descrição (o
Prot. 11/08 traz "8481 metais hidrossanitários", que não alcança uma válvula
industrial de mesmo NCM); a matriz só cobre o sentido SP -> destino, porque a
aplicação nas entradas em SP de vários desses protocolos depende de ato que
nunca foi editado; e SP tira os materiais de construção da sua ST interna em
01/02/2027 (Portaria SRE 52/2026), o que não muda os protocolos.

```bash
.venv/Scripts/python scripts/protocolos.py                  # baixa os 11 protocolos e grava em dados/protocolos
.venv/Scripts/python scripts/protocolos.py --ref 2027-01-01 # situação em outra data
```

## Minas Gerais: lista estadual e MVA

O terceiro conjunto, em `dados/estados/MG/`, lê o RICMS/MG 2023, Anexo VII,
Parte 2: os 25 capítulos com tabela (um por segmento), **1.032 itens**, com
CEST, NCM/SH, descrição, MVA original e o âmbito de cada um, ou seja, de
quais estados a mercadoria chega a MG com a ST já retida.

| Arquivo | Conteúdo |
| --- | --- |
| `itens.csv` | Um item por linha: capítulo, CEST, NCM/SH, descrição, âmbito como está na norma, `st_interna`, `ufs_origem_com_st` (já com as exceções do item aplicadas) e `mva_original` |
| `ambitos.csv` | Os âmbitos de cada capítulo ("10.1 Interno e nas seguintes unidades da Federação: ...") com os estados e protocolos lidos |
| `cruzamento_prot_32_09.csv` | Capítulo 10 (materiais de construção) comparado, item a item, com a matriz do Prot. ICMS 32/09 (SP -> MG) |
| `metadados.json` | URLs, hashes e contagens |

Em 09/11/2026 o cruzamento deu 69 itens coerentes e 7 para conferência. Quatro
são conflitos reais entre a lei de MG e o protocolo:

- **telhas de concreto (CEST 10.022.00) e acessórios de cobre (10.065.00):** o
  Prot. ICMS 32/09 deixou de listá-los (Prot. 63/25 e 75/26), mas o RICMS/MG
  ainda diz que a ST vale para mercadoria vinda de SP;
- **ladrilhos de cerâmica (10.030.00) e tubos de cobre (10.064.00):** o
  protocolo ainda os lista, mas MG os trata só na operação interna ou com
  "Exceção: SP".

Os outros três (10.017.00, 10.030.01 e 10.050.00) casam com o protocolo só
pelo NCM, porque o protocolo não traz CEST, e precisam de leitura da
descrição.

A fonte é a versão consolidada sem histórico publicada pela SEF/MG, que traz
só a redação vigente; as datas das mudanças passam a vir do monitor, que guarda
cada versão da página.

```bash
.venv/Scripts/python scripts/estado_mg.py   # baixa da SEF/MG e grava em dados/estados/MG
```

## Paraná: MVA original com vigência

O quarto conjunto, em `dados/estados/PR/`, lê a Resolução SEFA 571/2019
consolidada (PDF de cerca de 590 páginas no SEFANET), que fixa a MVA original de
23 segmentos: **817 redações, 592 vigentes**, cada uma com início e fim de
vigência. Exemplo do segmento de construção (art. 16): a Resolução SEFA
1.245/2025 trocou a tabela inteira em 01/04/2026, e a abraçadeira passou de 75%
para 89,91%; os dois valores estão no histórico, com as datas.

| Arquivo | Conteúdo |
| --- | --- |
| `mva_historico.csv` / `mva_vigente.csv` | Seção, segmento, artigo, item, CEST, descrição (do Convênio 142, pelo CEST), NCM/SH, MVA, vigência e a nota de alteração |
| `cruzamento_prot_71_11.csv` | Cada item do Prot. ICMS 71/11 (SP -> PR) com a MVA que o PR fixa para ele |
| `avisos.txt` | O que o leitor não conseguiu resolver sozinho |

No PDF a MVA fica centralizada na célula e o texto corrido embaralha as
colunas; a leitura usa a posição de cada palavra na página (item, CEST e MVA
ficam na mesma altura). Em 09/11/2026: dos 54 itens do Prot. 71/11, 43 têm MVA
única no PR, 9 casam com mais de um CEST (a descrição decide) e 2 (juntas de
borracha e tapetes) não têm MVA no artigo de construção. Os avisos se
concentram em bebidas e alimentos, onde um mesmo CEST aparece com MVAs por
condição; o segmento de construção sai sem aviso.

```bash
.venv/Scripts/python scripts/estado_pr.py   # baixa do SEFANET e grava em dados/estados/PR
```

## Rio Grande do Sul: lista estadual e MVA

O quinto conjunto, em `dados/estados/RS/`, lê o RICMS/RS (Decreto 37.699/1997),
Apêndice II, Seção III: 13 segmentos vigentes, **288 itens**, cada um com CEST,
NCM, a MVA da operação interna (a original) e as já ajustadas para as operações
interestaduais a 12% e a 4%, além das notas por item, como "Este número não se
aplica às operações originárias do Estado de SP".

| Arquivo | Conteúdo |
| --- | --- |
| `itens.csv` | Segmento, número, CEST, NCM/SH, descrição, `mva_interna`, `mva_inter_12`, `mva_inter_4`, `nao_se_aplica_origem` (estados excluídos pela nota do item) e as notas de alteração |
| `cruzamento_prot_92_09.csv` | Construção (item XXVI): os CESTs que o RS diz não valer para SP x os que o Prot. ICMS 92/09 exclui |

O cruzamento deu **coerência total** em 09/11/2026: os 77 itens de construção
do RS concordam com o protocolo, e os 6 CESTs que o protocolo exclui nem
constam da lista do RS. A Receita publica o regulamento inteiro numa página de
cerca de 10 MB; o servidor não envia o certificado intermediário no TLS, que
fica em `certs/` (baixado do endereço que o próprio certificado indica) para a
verificação continuar ligada. A página só anota as alterações feitas número a
número; as datas das próximas mudanças vêm do monitor.

```bash
.venv/Scripts/python scripts/estado_rs.py   # baixa da Receita Estadual e grava em dados/estados/RS
```

## Próximos conjuntos

Este é o começo de um projeto maior de monitoramento da legislação de ICMS ST.
Os próximos são os protocolos dos demais segmentos e origens e as listas e
MVAs de BA e AP/PA, que completam as MVAs que os protocolos com SP não fixam.

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

A second dataset covers the 11 ICMS protocols on construction materials signed
by São Paulo: every item with its effective dates and a São Paulo -> destination
matrix (12 states) telling whether the seller in SP must withhold the tax. It
handles both list models (own NCM list, or a reference to Annex XI of Convênio
142 minus excluded CEST codes) and is checked against 34 hand-verified cases.

A third dataset reads Minas Gerais' own ST list (RICMS/2023, Annex VII, Part 2:
1,032 items with MVA and the states each item applies to) and cross-checks the
construction chapter against the SP -> MG protocol, flagging four real conflicts
between the state law and the protocol.

A fourth dataset extracts Paraná's original MVA table (SEFA Resolution 571/2019,
a ~590-page PDF) with effective dates for every wording, reading words by their
position on the page because the plain text scrambles the columns.

A fifth dataset reads Rio Grande do Sul's ST list (RICMS, Appendix II, Section
III: 288 items with original and adjusted MVA) and matches the SP -> RS
protocol exclusions exactly.

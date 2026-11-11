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

**Autopeças (10/11/2026).** A matriz passou a incluir o Prot. ICMS 41/08, o
protocolo multilateral de autopeças de que SP é signatário. Ele usa o modelo
de referência: vale para o Anexo II do Conv. 142, menos 6 CESTs (01.019.00,
01.062.01, 01.112.00, 01.127.00, 01.128.00 e 01.999.00), nas remessas para os
15 destinos listados na cláusula primeira (AC, AL, AM, AP, BA, DF, MA, MG, MT,
PA, PB, PI, PR, RJ e RR), redação em vigor desde 01/10/2024. São 125 CESTs e
1.875 linhas novas na matriz, que agora tem 2.547 linhas e uma coluna de
segmento implícita no CEST (01 = autopeças, 10 = construção). RS e SC assinam o
protocolo, mas não estão entre os destinos: de SP para lá, autopeças não têm
retenção pelo 41/08. O Prot. 97/10, o outro de autopeças, não tem SP entre os
signatários. Os destinos lidos da cláusula são conferidos contra a configuração
em teste, e o gabarito ganhou 7 casos de autopeças.

**Outros segmentos com SP (10/11/2026).** Fora de construção e autopeças, SP
assinava seis protocolos bilaterais com o RJ. O leitor agora lê a revogação do
protocolo inteiro no cabeçalho da página ("Revogado pelo Prot. ICMS 112/26,
efeitos a partir de 01.10.26") e tira da matriz o que foi revogado. Cinco dos
seis caíram em 2026:

| Protocolo | Segmento | Situação |
| --- | --- | --- |
| 29/14 | Bebidas alcoólicas, exceto cerveja | revogado desde 01/01/2026 (Prot. 58/25) |
| 76/14 | Produtos farmacêuticos, soros e vacinas | revogado desde 01/01/2026 (Prot. 77/25) |
| 104/12 | Cosméticos, perfumaria e higiene | revogado desde 01/04/2026 (Prot. 21/26) |
| 34/14 | Materiais de limpeza (Anexo XII do Conv. 142) | revogado desde 01/08/2026 (Prot. 74/26) |
| 77/14 | Ferramentas | revogado desde 01/10/2026 (Prot. 112/26) |
| 136/13 | Eletrônicos, eletroeletrônicos e eletrodomésticos | **vigente**, 101 itens; refrigeradores (itens 2 a 10) saíram em 01/10/2026 e secadoras (item 11) em 31/07/2026 |

Na matriz isso dá, por exemplo: vendendo de SP para o RJ, uma furadeira
elétrica (8467.21.00) continua com retenção pelo 136/13, mas um alicate (8203)
não tem mais, porque o protocolo de ferramentas caiu. A matriz tem 2.648 linhas,
e o gabarito tem 44 casos.

**Matriz origem -> destino (10/11/2026).** `matriz_origem_destino.csv` responde a
mesma pergunta para qualquer remetente signatário, não só para SP. O sentido
vem da cláusula primeira de cada protocolo:

- "destinadas ao Estado de Minas Gerais **ou** ao Estado de São Paulo" vale nos
  dois sentidos (11/08, 32/09, 32/14, 92/09, 104/08, 104/09, 128/10 e 136/13);
- "destinadas ao Estado do Espírito Santo" vale só de SP para lá (20/13, 25/11,
  60/11 e 71/11);
- no 41/08 (autopeças), cada um dos 13 signatários vende com retenção para os
  15 destinos listados, menos ele mesmo: de MG para a BA sim, de SC para o RS
  não, porque o RS assina mas não está entre os destinos.

São 24.512 linhas. As 488 com destino SP ficam marcadas em `efeito_no_destino`:
o texto do protocolo cita SP, mas a aplicação nas entradas em SP depende de ato
do Secretário da Fazenda que não foi editado (Comunicado CAT 36/2009). A
`matriz_sp_destino.csv` continua igual, só com a origem SP.

**Todos os protocolos de ST do Confaz (10/11/2026).** `scripts/catalogo_protocolos.py`
percorre os índices anuais do Confaz (2004 a 2026) e grava `catalogo.csv`: são
**156 protocolos-base de ST** (título que começa com "Dispõe sobre a substituição
tributária nas operações"; os que só alteram ou revogam outro ficam de fora), dos
quais **54 vigentes e 102 revogados**. A situação sai de duas conferências:

1. a nota de revogação no cabeçalho da página, em todas as formas encontradas
   ("Revogado pelo Prot. ICMS 52/19, com efeitos a partir de 01.01.20", "efeitos a
   partir de 2026", "Revogado, a partir de 01.01.18, pelo Prot. ICMS 54/17",
   "Revogado tacitamente pelo Convênio ICMS 155/15");
2. os 110 protocolos revogadores ("Revoga o Protocolo ICMS nº X..."), que marcam
   o protocolo citado com a data de efeitos do revogador.

Conferido contra os 18 protocolos lidos à mão: 18 de 18. Para cada protocolo o
catálogo registra signatários (preâmbulo mais as adesões que aparecem na lista
de destinos), destinos, `regra_destino` (lista na cláusula, "entre signatários"
ou implícita), segmento (pelo anexo do Convênio 142 ou pelo título) e
`remetente`: 7 protocolos só atribuem a retenção ao **industrial ou importador**
(sorvetes, vinhos, bebidas quentes, aguardente, materiais elétricos e os
Prots. 82/11 e 83/11); nesses, o atacadista que revende não retém.

O leitor de protocolos lê agora os 54 vigentes mais os revogados já
configurados: **59 protocolos, 7.330 redações, 1.529 itens vigentes**, matriz
SP -> destino com 3.702 linhas e matriz origem -> destino com **102.456 linhas**
(17,8 MB), com a coluna nova `remetente`. Protocolos sem tabela de itens que
descrevem o produto na própria cláusula ("vinhos, sidras ... classificados nas
posições 2204 e subposições 2206.00.10 e 2206.00.90") viram um item
"cláusula 1ª"; o Prot. 20/05 (sorvetes), sem tabela e sem NCM, usa o Anexo
XXII do Convênio 142 e fica registrado em `divergencias_da_fonte.csv`.

**Publicação e alterações (10/11/2026).** `protocolos.csv` traz, lidos do cabeçalho
de cada página do Confaz: `publicado_dou` (data da publicação no DOU), `despacho`,
`retificacoes_dou`, `alterado_por` (os protocolos que mudaram o texto, em ordem) e
`notas_do_cabecalho`, as remissões "Vide" e "Ver" que o Confaz registra, como
"Ver Despacho 30/08, quanto à aplicação no AP e DF" ou a inclusão de um estado
por outro protocolo.

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

## Bahia: lista estadual e MVA

O sexto conjunto, em `dados/estados/BA/`, lê o Anexo 1 do RICMS-BA (Decreto
13.780/2012), que a SEFAZ-BA publica em um PDF por período ("redação vigente
ano 2026, a partir de 01/01/2026"): **311 redações, 284 vigentes**, cada uma
com CEST, NCM, o acordo interestadual com os estados signatários ("Prot. ICMS
104/09 - BA e SP"), as MVAs ajustadas por alíquota e a MVA original.

| Arquivo | Conteúdo |
| --- | --- |
| `itens_historico.csv` / `itens_vigentes.csv` | Item, CEST, NCM/SH, descrição, acordo, MVA original, MVAs ajustadas, vigência e situação (`vigente`, `anterior` ou `revogada`) |
| `cruzamento_prot_104_09.csv` | Construção (CEST 10.x): o acordo da BA com SP x a matriz do Prot. ICMS 104/09 |

As células são centralizadas na vertical e as redações anteriores vêm entre
aspas no meio da tabela; a leitura usa a posição das palavras e as notas
"A redação atual do item ... efeitos a partir de" e "Redação anterior, efeitos
até". Exemplo: os vidros (CEST 10.033.00 a 10.038.00) tinham o Prot. 104/09
(SP) no acordo até 31/12/2025 e deixaram de ter em 2026, junto com o
protocolo.

Cruzamento com o Prot. 104/09 em 09/11/2026: 77 coerentes, 4 que casam só pelo
NCM (os mesmos de MG) e **2 conflitos reais**: a BA ainda cita SP para tubos de
cobre (10.064.00), que o protocolo revogou em 01/08/2026 (Prot. 60/26), e para
outros vergalhões (10.043.00, NCM 7213), que o protocolo não lista. Em bebidas,
combustíveis e medicamentos ficam casos para revisão (linhas sem número de
item, MVAs por condição e marcas de "Revogado" que caem na faixa do item
vizinho); o segmento de construção sai limpo.

```bash
.venv/Scripts/python scripts/estado_ba.py   # baixa da SEFAZ-BA e grava em dados/estados/BA
```

## Mato Grosso: lista estadual e MVA

O sétimo conjunto, em `dados/estados/MT/`, junta dois atos da SEFAZ-MT. O
Apêndice do Anexo X do RICMS/MT (Decreto 2.212/2014) diz o que está na ST: 25
segmentos, **1.046 itens (1.006 vigentes)**, com CEST, NCM e descrição, sem
MVA. A Portaria 195/2019-SEFAZ divulga as MVAs, e de dois jeitos:

- a tabela do Anexo Único, item a item, vale para quem usa o crédito outorgado
  do Anexo XVII ou é do Simples (art. 1º, § 1º);
- para os demais contribuintes, o art. 2º-B fixa uma MVA por segmento, por
  faixa de CEST (materiais de construção, 10.001.00 a 10.080.00: 74,75%).

O MT não usa MVA ajustada: a mesma MVA vale para qualquer origem (art. 3º).

| Arquivo | Conteúdo |
| --- | --- |
| `itens.csv` | Apêndice: segmento, item, CEST, NCM/SH, descrição, situação (`vigente` ou `revogado`) e notas de alteração |
| `mva_portaria_195.csv` | Anexo Único da portaria: cada linha com a MVA e a redação (`vigente` ou `anterior`); item com MVA "excluído" fica marcado |
| `mva_demais_contribuintes.csv` | Art. 2º-B: MVA por segmento e faixa de CEST, só a redação vigente |
| `itens_vigentes.csv` | Itens vigentes do Apêndice com `mva_credito_outorgado_ou_simples` (tabela) e `mva_demais_contribuintes` (art. 2º-B) |
| `cruzamento_prot_11_08.csv` | Construção: as linhas do Prot. ICMS 11/08 (SP-MT) na matriz x o Apêndice do MT, pelo CEST provável |

Na tabela da portaria as redações anteriores aparecem logo abaixo da vigente,
marcadas com "(Redação original)" ou só repetindo o número do item: são 266.
Combustíveis, energia e veículos não têm MVA na portaria (a base vem do PMPF e
de outros artigos do RICMS). O texto da portaria na base da SEFAZ está
consolidado até a Portaria 212/2022, e atos de 2026 ainda a citam como vigente.

Cruzamento com o Prot. 11/08 em 09/11/2026: **39 coerentes e nenhum CEST do
protocolo fora do Apêndice do MT**; 3 linhas do protocolo (tubos de aço e de
cobre) não têm CEST provável, e 46 itens de construção estão só na lista do
MT. Nesses 46, a ST não vem do protocolo: quem retém não é o remetente de SP,
é o destinatário mato-grossense que antecipa o imposto.

```bash
.venv/Scripts/python scripts/estado_mt.py   # baixa da SEFAZ-MT e grava em dados/estados/MT
```

## Pernambuco: MVA de materiais de construção

O oitavo conjunto, em `dados/estados/PE/`, lê o Anexo 37-C do Decreto
44.650/2017 (criado pelo Decreto 58.019/2025, efeitos desde 01/02/2025), no
texto consolidado da SEFAZ-PE. A tabela só traz o número do item do Anexo XI do
Convênio 142 e uma MVA única, para operação interna ou importação: **73 itens**.
O script junta cada item ao conjunto do Conv. 142 para ter CEST, NCM e
descrição.

| Arquivo | Conteúdo |
| --- | --- |
| `itens.csv` | Anexo e item do Conv. 142, MVA, CEST, NCM/SH e descrição |
| `cruzamento_prot_128_10.csv` | A MVA do Prot. ICMS 128/10 (SP-PE) x a do Anexo 37-C, pelo CEST provável |

Cruzamento em 10/11/2026: 47 MVAs iguais, 7 iguais em um dos CESTs prováveis e
**1 diferença real**: caixas d'água, telhas e calhas de fibrocimento (NCM 6811,
CEST 10.024.00). O protocolo traz duas MVAs, 41% com o frete na base de cálculo
e 56% sem o frete, e o anexo do PE só tem os 41%. Duas linhas do
protocolo (juntas de borracha e tapetes) não têm CEST provável.

## Alagoas: lista estadual e MVA

O nono conjunto, em `dados/estados/AL/`, lê o Anexo VIII do Decreto 90.309/2023,
que reúne as regras de ST de Alagoas. A SEFAZ-AL publica a versão consolidada
como PDF no seu sistema de documentos (gcs2.sefaz.al.gov.br), pela mesma API
que o site usa para mostrar o documento. São **83 itens**, cada um com CEST, o
acordo interestadual (Prot. ICMS 104/08 ou "Sem Acordo"), a MVA original e as
ajustadas para 12%, 7% e 4%. Em três itens (fibrocimento, tijolos e telhas
cerâmicas) a MVA muda conforme o frete esteja ou não na base de cálculo.

| Arquivo | Conteúdo |
| --- | --- |
| `itens.csv` | Item, CEST, acordo, `mva_original`, `mva_original_sem_frete_na_base`, ajustadas a 12/7/4%, descrição e NCM do Conv. 142 e o texto como saiu do PDF |
| `cruzamento_prot_104_08.csv` | A MVA do Prot. ICMS 104/08 (SP-AL) x a do Anexo VIII, pelo CEST provável |

O PDF é lido pela posição das palavras: as células são centralizadas e quebram
em várias linhas, então descrição e NCM vêm do Conv. 142 pelo CEST. A SEFAZ-AL
avisa que as ajustadas não constam da publicação no Diário Oficial: são cálculo
dela, feito com a alíquota interna de 20,5% mais 1% de FCP (21,5%). O RJ, por
exemplo, calcula sem o FCP.

Cruzamento em 10/11/2026: **52 coerentes e nenhuma diferença de MVA**; duas
linhas do protocolo (juntas de borracha e tapetes) não têm CEST provável.

## Goiás: segmentos fora da ST e efeito no destino

O décimo conjunto, em `dados/estados/GO/`, lê o Apêndice II do Anexo VIII do
RCTE de Goiás (Decreto 4.852/1997) na redação vigente (Decreto 8.819, desde
01/01/2017), na página consolidada da SEFAZ-GO (cerca de 57 MB, com todo o
histórico). `segmentos.csv` traz um inciso por linha, com as normas e a
situação: 12 segmentos seguem na ST e 4 foram **tirados da ST desde 01/03/2018
pelo Decreto 9.108/2017**: autopeças (Prots. 41/08 e 97/10), ração pet (26/04 e
39/11), materiais de construção (82/11 e 85/11) e material elétrico (83/11 e
84/11). Esses protocolos continuam vigentes no Confaz, sem nota de revogação:
é um conflito entre a lei estadual e o protocolo.

`dados/estados/efeito_no_destino.csv` é compartilhado entre os estados: cada
linha diz que um protocolo não tem efeito num destino, com o motivo, a data e a
fonte. O leitor de protocolos usa o arquivo para preencher `efeito_no_destino`
na matriz (além da regra de SP do Comunicado CAT 36/2009). Exemplo: de SP para
GO, as conexões 7307 aparecem pelo Prot. 82/11, com a observação de que GO tirou
o segmento da ST; na matriz, são 557 linhas com destino GO marcadas assim.

### Estados sem fonte automática

- **RJ:** o portal de legislação da SEFAZ-RJ só responde a navegadores, e o
  Anexo I do Livro II do RICMS (lista e MVAs) é um arquivo .doc. Fica fora da
  coleta automática; a cobertura SP-RJ vem do Prot. 32/14, que traz MVA.
- **ES:** a Portaria 16-R/2019, que divulga as MVAs, está numa base de
  legislação (www2.sefaz.es.gov.br) que não resolve mais no DNS. A cobertura
  SP-ES vem do Prot. 20/13.
- **DF:** o SINJ-DF, onde está o RICMS (Decreto 18.955/1997, Anexo IV, Caderno
  I, item 41), responde com bloqueio de firewall a qualquer acesso que não seja
  de navegador. A cobertura SP-DF vem do protocolo.
- **AP e PA:** ver a seção dos protocolos (PA só atende navegadores; AP não
  tem texto consolidado oficial).

## Próximos conjuntos

Este é o começo de um projeto maior de monitoramento da legislação de ICMS ST.
Os próximos são os protocolos dos demais segmentos e origens e as listas e
MVAs de AP e PA, que completam as MVAs que os protocolos com SP não fixam.

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

A sixth dataset reads Bahia's Annex 1 (311 wordings, with the interstate
agreements and original MVA per item) and finds two real conflicts with the
SP -> BA protocol.

A seventh dataset joins Mato Grosso's two acts: the RICMS Annex X appendix
(1,006 valid items, no MVA) and SEFAZ Ordinance 195/2019, which sets one MVA
per item for taxpayers using the granted-credit regime or Simples, and a single
MVA per segment for everyone else (construction: 74.75%). Every CEST of the
SP -> MT protocol is on Mato Grosso's list.

An eighth dataset reads Pernambuco's Annex 37-C (73 items keyed to Convênio 142
Annex XI, one MVA each) and finds one real MVA difference from the SP -> PE
protocol (fiber-cement products, 56% vs 41%). Rio de Janeiro and Espírito Santo
have no source that can be collected automatically.

A ninth dataset reads Alagoas' Annex VIII (83 items, original and adjusted MVA,
with and without freight in the tax base) with no MVA differences from the
SP -> AL protocol. The Federal District has no source that can be collected
automatically.

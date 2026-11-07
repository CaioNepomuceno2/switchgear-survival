# Decisões de dados da Energisa MS (EMS)

Este documento foi escrito e commitado **antes** de qualquer estimativa de vida, validação ou projeção de MS. Cada
decisão sai de um diagnóstico dos dados abertos de MS, e não de um resultado do modelo. Os diagnósticos são
reproduzíveis com `scripts/diagnostico_bdgd.py` (e `scripts/00_baixar_bdgd.py` para montar o cache) e as saídas ficam em
[`reports/ems/diagnostico/`](../reports/ems/diagnostico/). Cada tabela abaixo cita o arquivo de onde sai. Execução de
06 e 07/11/2026.

O pipeline foi escrito e validado com a Energisa MT (EMT). Aqui cada suposição herdada de MT foi medida em MS antes de
ser mantida ou trocada. As decisões, os caminhos e os resultados de MT **não mudam**.

> Projeto independente, sem vínculo com a Energisa ou com a ANEEL. Só dados abertos (BDGD da ANEEL).

## Resumo das decisões

| # | Tema | O que os dados de MS mostram | Decisão |
|---|---|---|---|
| 1 | Fonte | 8 snapshots de 31/12 (2018 a 2025), versão mais recente de cada ano, já baixados no cache compartilhado | Ler direto dos zips, só nas 4 camadas necessárias; nada é baixado de novo nem alterado |
| 2 | Linhas repetidas | 0 linhas repetidas e 0 `COD_ID` repetido nas 4 camadas dos 8 snapshots | Nada a tratar; a conferência fica no diagnóstico |
| 3 | `anos_com_data` | `DAT_IMO` é `01/01/1920` em 100% dos equipamentos das 4 classes em 2018 e 2019; de 2020 em diante é uma data válida em 88,9% a 100% | **2020 a 2025**, como em MT |
| 4 | Classes por TUC | Os 4 códigos e as camadas EQSE/EQRE existem nos 8 snapshots e significam o mesmo; 69% dos TUC 210 estão em alta tensão | Mesmos códigos de MT; só o rótulo do 210 muda para "Disjuntor (alta e média tensão)" |
| 5 | Limiares de qualidade | Nenhuma classe passa nos limites de MT (0,25 e 0,10) em nenhuma janela candidata | **Mantidos**; resultado esperado: diagnóstico do cadastro, sem estimativa de vida |
| 6 | Janelas | A transição 2020→2021 coincide com o preenchimento das datas (disjuntores datados: 343 → 396) | Principal 2021→2025, sensibilidade com 2020, validações como em MT |
| 7 | Pontos de religador | `TIP_UNID` 32 confere; 100% dos pontos têm coordenada, compatível com a extensão de MS; latitude mediana -20,5 a -20,7 | Latitude de referência -20,6 (MT usa -13) |
| 8 | Vida útil regulatória | O PDF da Tabela XVI do MCPSE continua inacessível (HTTP 403 em 06/11/2026) | Em branco, como em MT |

## 1. Fonte e cache

A BDGD vem do ArcGIS Hub da ANEEL, um File Geodatabase por ano em 31/12. Os 8 itens e seus títulos foram conferidos
pelo agente que baixou os zips (`MANIFESTO.json` e `DOWNLOAD_DONE.txt` do cache compartilhado, com tamanho e SHA-256):

| Ano | Item | Título |
|---|---|---|
| 2018 | `5382c59d7cc7494a9a1f8cd865187457` | Energisa_MS_404_2018-12-31_M10_20191023-2327 |
| 2019 | `b83ad867a35b43189f41b68988f7f0b6` | Energisa_MS_404_2019-12-31_M10_20200323-1921 |
| 2020 | `fe56dce0714f4b6795d3b23130f5898a` | Energisa_MS_404_2020-12-31_M10_20210628-1527 |
| 2021 | `933af69c57dd41ea8f6048118b8d07e7` | Energisa_MS_404_2021-12-31_V10_20230315-1800 |
| 2022 | `ff5242147c86428e88971941a35c7cd1` | Energisa_MS_404_2022-12-31_V11_20240422-2036 |
| 2023 | `975f18dfdb0c479cb237893c5b296ca9` | Energisa_MS_404_2023-12-31_V11_20250923-1616 |
| 2024 | `b7fad4cd388845a08a01643599ec747b` | Energisa_MS_404_2024-12-31_V11_20250730-1637 |
| 2025 | `9a1ce360865f4358b31e9fb2d016aac9` | Energisa_MS_404_2025-12-31_V11_20260830-0339 |

Ficam de fora o item avulso `c3585ae516f340b596617827d60da5ef` (`EMS_404_2022-10-31_V10`) e a versão de 17/12/2024 do
snapshot de 2023 (`b8c585ae35224ac8aa0648587ec61bcb`), substituída pela de 23/09/2025. Em MT a política é a mesma
(versão mais recente de cada ano).

`scripts/00_baixar_bdgd.py --config configs/premissas_ems.yaml --zips <pasta dos zips>` lê cada zip pelo GDAL
(`/vsizip/`), abre só as camadas `UNSEMT`, `EQSE`, `UNREMT` e `EQRE` e grava um Parquet por camada e ano em
`data/cache/ems/<ano>/` (fora do git). O zip não é alterado, nada é extraído, e um ano já convertido é pulado.

**Modelo de dados.** Os snapshots de 2018 a 2020 são M10 e os de 2021 em diante, V10/V11
([`esquema_camadas.csv`](../reports/ems/diagnostico/esquema_camadas.csv)). Na troca de modelo, `EQSE` perde `PAC_1` e
`PAC_2` e ganha `UN_SE` (vínculo com a unidade), `TIP_INST`, `UAR` e `GRU_TEN`; `EQRE` ganha `UN_RE` e perde `TIP_REGU` e
as 12 colunas `ENE_xx`. As colunas que o pipeline usa (`COD_ID`, `TUC`, `DAT_IMO`, `MEI_ISO`, `COR_NOM`, e `TIP_UNID`,
`lon` e `lat` da `UNSEMT`) existem nos 8 anos. Só `UN_SE`/`UN_RE` faltam até 2020; elas entram apenas no diagnóstico de
rastreamento (`mesma_unidade` fica vazia na transição 2020→2021, o mesmo que acontece em MT).

## 2. Linhas repetidas

`count(*)` contra `count(distinct *)` em **toda** camada lida, por snapshot
([`repetidas_camadas.csv`](../reports/ems/diagnostico/repetidas_camadas.csv)):

| Camada | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| EQSE | 300.570 | 295.589 | 235.440 | 243.239 | 252.361 | 262.937 | 295.256 | 346.980 |
| EQRE | 544 | 572 | 602 | 664 | 726 | 789 | 879 | 946 |
| UNSEMT | 137.052 | 136.158 | 113.217 | 116.909 | 121.063 | 125.633 | 137.493 | 161.148 |
| UNREMT | 182 | 191 | 200 | 222 | 243 | 264 | 294 | 316 |

Em todas as 32 combinações de camada e ano, as linhas distintas são iguais às linhas (0 repetidas), o número de
`COD_ID` distintos é igual ao de linhas e a coluna `DIST` vale 404 (código ANEEL da EMS) em todas as 3.288.679 linhas,
sem nenhuma vazia. Não há o que remover. A conferência de `DIST` virou uma guarda do pipeline: `ler_classe` para com erro se o cache for de outra
distribuidora (por exemplo, `SWSURV_CACHE` apontando para o cache de MT, que tem `DIST` 405). Este repositório não lê os
arquivos de interrupções e de continuidade da ANEEL, então não há outra tabela a conferir.

## 3. Anos com data de imobilização válida (`anos_com_data`)

"Válida" é a data que `swsurv.cadastro.safra` aceita: não vazia, diferente de `0`, entre 1950 e o ano do cadastro.
Percentual de equipamentos com data válida por classe e snapshot
([`dat_imo_qualidade.csv`](../reports/ems/diagnostico/dat_imo_qualidade.csv)):

| Classe | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| Religador (TUC 345) | 0 | 0 | 99,8 | 100 | 100 | 100 | 100 | 100 |
| Disjuntor (TUC 210) | 0 | 0 | 88,9 | 98,3 | 97,9 | 100 | 100 | 100 |
| Chave (TUC 160) | 0 | 0 | 90,9 | 100 | 100 | 100 | 100 | 100 |
| Regulador (TUC 340) | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 |

* Em **2018 e 2019** a data é `01/01/1920` em 100% dos equipamentos das 4 classes (o valor-padrão do modelo M10, o mesmo
  problema de MT, onde a data-padrão é a mesma). Esses dois cadastros não têm safra e ficam de fora.
* De **2020** em diante todas as classes têm data válida em pelo menos 88,9% dos equipamentos. A data-padrão some, e as
  datas aparecem espalhadas por 16 a 49 safras distintas por classe e cadastro.
* Decisão: `anos_com_data = [2020, 2021, 2022, 2023, 2024, 2025]`, igual a MT. Os snapshots de 2018 e 2019 continuam
  entrando no rastreamento dos pontos de religador (seção 7), que não usa data.
* Fora das 4 classes, os 245.126 equipamentos de `EQSE` com `TUC` 000 de 2025 (71% da camada) quase não têm data: de
  2020 a 2025, 99,8% a 100% dos equipamentos fora das classes têm `DAT_IMO` vazia ou `0`. Eles não entram em nenhuma
  classe.

## 4. Classes por TUC

Os mesmos códigos de MT: religador 345, disjuntor 210, chave 160 (todos na `EQSE`) e regulador 340 (`EQRE`).
Contagem de equipamentos por TUC e cadastro ([`tuc_por_ano.csv`](../reports/ems/diagnostico/tuc_por_ano.csv)):

| Camada | TUC | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| EQSE | 345 | 1.766 | 1.839 | 1.898 | 1.959 | 2.100 | 2.174 | 2.254 | 2.654 |
| EQSE | 210 | 419 | 409 | 386 | 403 | 435 | 422 | 445 | 455 |
| EQSE | 160 | 298.385 | 293.341 | 70.855 | 74.124 | 77.199 | 83.061 | 86.598 | 98.745 |
| EQSE | 000 | 0 | 0 | 162.301 | 166.753 | 172.627 | 177.280 | 205.564 | 245.126 |
| EQSE | 00 | 0 | 0 | 0 | 0 | 0 | 0 | 395 | 0 |
| EQRE | 340 | 544 | 572 | 596 | 658 | 720 | 783 | 873 | 946 |
| EQRE | 000 | 0 | 0 | 6 | 6 | 6 | 6 | 6 | 0 |

O que cada código significa em MS, medido contra o tipo da unidade a que o equipamento pertence (`TIP_UNID` da
`UNSEMT`/`UNREMT`; [`tuc_x_tip_unid.csv`](../reports/ems/diagnostico/tuc_x_tip_unid.csv)) e o nível de tensão
(`GRU_TEN`; [`tuc_x_tensao.csv`](../reports/ems/diagnostico/tuc_x_tensao.csv)):

* **Religador (345).** De 2022 a 2025, 100% dos equipamentos TUC 345 pertencem a unidades `TIP_UNID` 32 (religador);
  em 2021, 1.954 de 1.959 (99,7%). Todos são de média tensão (2.654 de 2.654 em 2025). Nos snapshots M10 o vínculo é por
  `PAC_1`, que casa menos (2019: 1.306 de 1.839), então a prova vale a partir de 2021. O código 345 e o tipo 32 se
  identificam um ao outro: em 2025 as unidades 32 têm 2.654 equipamentos TUC 345 e 50 TUC 000.
* **Regulador (340).** 100% dos equipamentos TUC 340 pertencem a unidades `TIP_UNID` 14 da `UNREMT` (946 de 946 em
  2025); 6 equipamentos TUC 000 de 2020 a 2024 ficam fora.
* **Disjuntor (210).** Só 139 dos 455 equipamentos (2025) pertencem a unidades de média tensão da `UNSEMT` (`TIP_UNID`
  29, todos `GRU_TEN` MT). Os outros 316 têm `GRU_TEN` = AT e a unidade não está na `UNSEMT` (aparecem como "sem
  unidade"): são disjuntores de alta tensão, de unidades de outra camada. Isso vale em todos os anos com `GRU_TEN`
  (2021 a 2025: 125 a 140 MT e 278 a 316 AT). O código 210 significa "disjuntor" em qualquer tensão, e o rótulo
  "Disjuntor de média tensão", herdado da configuração de MT, não vale para a classe inteira. **Decisão:** manter o 210
  e chamar a classe de "Disjuntor (alta e média tensão)" nos arquivos de MS. (Nenhum número de MT deste documento vem de
  releitura dos dados de MT; o rótulo do README de MT não foi alterado.)
* **Chave (160).** O código existe nos 8 anos, em unidades de vários tipos (em 2025, `TIP_UNID` 19 e 22 somam
  90.685 dos 98.745 equipamentos), mas a **composição muda**. Entre 2019 e 2020 a maior parte das chaves fusíveis (`TIP_UNID` 22: 234.541 em 2019)
  passa do TUC 160 para o TUC 000 (160.926 em 2020), e o TUC 000 só cresce depois (245.126 em 2025). Dentro do TUC 160,
  o `TIP_UNID` 49 vai de 0 a 2.706 em 2023, 511 em 2024 e 1.246 em 2025, e o 26 cai de 1.593 em 2023 para 15 em 2024.
  Os códigos continuam valendo; o conjunto de equipamentos que eles cobrem não é estável. O código fica como em MT.

## 5. Limiares de qualidade

O teste de consistência de MT reprova uma classe se os acréscimos em safras antigas passam de 25% das baixas
(`limite_reversoes`) ou se mais de 10% das safras com 10 equipamentos ou mais voltam a subir depois de cair
(`limite_nao_monotonas`). Indicadores nas janelas candidatas, calculados só com as contagens por safra, sem ajustar curva
alguma ([`janelas_candidatas.csv`](../reports/ems/diagnostico/janelas_candidatas.csv)):

| Classe | Janela | Baixas | Acréscimos | Acréscimos / baixas | Safras que voltam a subir | Passa nos limites de MT |
|---|---|---|---|---|---|---|
| Religador | 2021→2025 | 790 | 550 | 0,696 | 22 de 29 (0,759) | não |
| Disjuntor | 2021→2025 | 49 | 6 | 0,122 | 2 de 16 (0,125) | não |
| Chave | 2021→2025 | 59.660 | 53.018 | 0,889 | 42 de 45 (0,933) | não |
| Regulador | 2021→2025 | 368 | 241 | 0,655 | 10 de 19 (0,526) | não |
| Religador | 2022→2025 | 602 | 526 | 0,874 | 10 de 29 (0,345) | não |
| Disjuntor | 2022→2025 | 39 | 6 | 0,154 | 2 de 15 (0,133) | não |
| Religador | 2023→2025 | 306 | 283 | 0,925 | 4 de 29 (0,138) | não |
| Disjuntor | 2023→2025 | 23 | 6 | 0,261 | 0 de 14 (0) | não |

(O arquivo traz as 4 classes nas 6 janelas candidatas, de 2018→2025 a 2023→2025. As janelas que começam em 2018, 2019 e
2020 dão os mesmos totais, porque 2018 e 2019 não têm safra.) **Nenhuma classe passa em nenhuma janela.** A conclusão
não depende de qual janela se escolhe.

* **Religador, chave e regulador** reprovam por larga margem na janela principal: 0,655 a 0,889 de acréscimos por baixa
  (limite 0,25) e 0,526 a 0,933 das safras voltando a subir (limite 0,10). Nenhum limiar razoável os aprovaria.
* **Disjuntor** passa no primeiro critério (0,12) e reprova no segundo: 2 de 16 safras voltam a subir (12,5%), uma a mais
  do que os 10% toleram (1 de 16 daria 6,3%). As duas safras são 2013 (25, 24, 22, 23, 23 equipamentos de 2021 a 2025) e
  2014 (17, 17, 16, 17, 17), isto é, oscilam em **um** equipamento
  ([`safras_que_voltam_a_subir.csv`](../reports/ems/diagnostico/safras_que_voltam_a_subir.csv)). O critério é sensível
  a oscilações pequenas em safras pequenas, e essa é uma limitação do teste. Mesmo assim, **o limiar não foi movido**:
  os limites de MT foram fixados antes de qualquer dado de MS, e afrouxá-los depois de ver estes números seria ajustar o
  teste ao resultado. Se um refinamento do teste (por exemplo, uma tolerância em número de equipamentos) for
  considerado, ele deve ser fixado antes de reaplicá-lo a MS e testado também em MT.
* Janelas de uma transição só (como 2024→2025) não estão na lista: o teste de não monotonicidade precisa de 3 ou mais
  cadastros, e o disjuntor tem 5 baixas nessa. A única transição do religador abaixo do limite de acréscimos é 2021→2022
  (188 baixas, 24 acréscimos, 0,128), e uma transição só não sustenta uma curva de vida.

**Por que a contagem por safra não é estável em MS.** O método de MT supõe que a contagem por safra só cai
(`cadastro.py`). Em MS ela sobe e desce. Dois sinais, ambos nos arquivos de diagnóstico:

* Nas safras maiores do religador a contagem tem quedas de um ano que voltam no seguinte
  ([`safras_principais.csv`](../reports/ems/diagnostico/safras_principais.csv)): safra 2015 com 377, 372, 384, **190**,
  378 e 378 equipamentos de 2020 a 2025; safra 2017 com 212, 212, 196, 182, **80** e 82.
* O mesmo equipamento (mesmo `COD_ID`) com a mesma safra no cadastro anterior e no seguinte tem outra safra no cadastro
  do meio em 57% dos casos no religador em 2023 (212 de 372), 38% em 2024, e em 54% a 73% das chaves
  ([`vai_e_volta_das_datas.csv`](../reports/ems/diagnostico/vai_e_volta_das_datas.csv)). Nos disjuntores é de 3% a 14%
  (2022 a 2024). As datas de imobilização do cadastro de MS não acompanham o equipamento de um ano para o outro.

Por transição ([`transicoes.csv`](../reports/ems/diagnostico/transicoes.csv)), só ficam abaixo de 0,25 acréscimos por
baixa a transição 2021→2022 do religador (0,128) e três do disjuntor (2021→2022, 2022→2023 e 2024→2025, todas com
0 acréscimos). As chaves (mínimo 0,544) e os reguladores (mínimo 0,366) ficam acima em todas as transições.

## 6. Janelas de ajuste e de validação

* **Principal:** transições 2021→2022 a 2024→2025 (`transicoes_principal = [2021, 2022, 2023, 2024]`).
* **Sensibilidade:** inclui 2020→2021 (`com_2020_2021`).
* **Por que 2020→2021 fica fora da principal.** É a transição em que as datas passam a ser preenchidas, não em que a
  frota envelhece: os disjuntores datados vão de 343 (de 386, 88,9%) para 396 em 2021 e as chaves de 64.439 (de 70.855)
  para 74.124, e a transição soma 40 acréscimos contra 3 baixas nos disjuntores
  ([`transicoes.csv`](../reports/ems/diagnostico/transicoes.csv)). Todas as classes ficam acima do limite de acréscimos
  nela. É o mesmo motivo de MT (recadastramento), e a janela fica igual.
* **Validação:** ajuste com as transições de 2021 e 2022 e teste de 2023 e 2024 (cadastros 2024 e 2025), e ajuste até
  2023 com teste em 2024, iguais a MT. Os anos com data válida de MS (2020 a 2025) são os mesmos de MT, então a mesma
  estrutura cabe. Como nenhuma classe passa no teste de consistência (seção 5), a validação roda, mas fica marcada
  `confiavel = False` e não é um resultado de destaque.
* **Idade-limite do baseline:** 25 anos, **bootstrap:** 500 reamostragens por safra e **semente:** 7, como em MT.

## 7. Pontos de religador e coordenadas

[`pontos_religador.csv`](../reports/ems/diagnostico/pontos_religador.csv): os pontos de religador (`UNSEMT`,
`TIP_UNID` 32) vão de 1.730 (2018) a 2.646 (2025), e 100% têm coordenada. O 1º e o 99º percentil da longitude ficam
entre -57,7 e -51,1 e os da latitude entre -23,9 e -17,9 (2019 a 2025), compatíveis com a extensão de MS. A latitude mediana é -20,5 a
-20,7 de 2019 a 2025 (-22,2 em 2018). Este repositório usa longitude e latitude em graus (convertidas para WGS84),
não a coordenada UTM codificada no `PAC`; a questão dos fusos 21S e 22S de MS não se aplica aqui. A conversão de graus
em metros do rastreamento usa a latitude de referência, que em MT é fixa (-13°). **Decisão:** parâmetro
`pontos.lat_ref_graus`, -13 como padrão (MT) e **-20,6** em MS.

## 8. Vida útil regulatória

`vida_util_regulatoria_anos` fica em branco em MS, como em MT, pelo mesmo motivo documentado: a Tabela XVI do Manual de
Controle Patrimonial (anexo da REN ANEEL 674/2015) não pôde ser lida (o site da ANEEL respondeu HTTP 403 ao acesso
automatizado) e cópias de terceiros não foram usadas. Nenhum código lê esse parâmetro.

## 9. Suposições de MT que foram achadas e como foram tratadas

Busca ampla em `src/`, `scripts/`, `configs/`, `tests/`, `README.md` e `docs/` por nome da distribuidora, UF, código
ANEEL, anos fixos, TUC, `TIP_UNID`, coordenadas e caminhos fixos:

| Suposição de MT | Onde estava | Em MS | Tratamento |
|---|---|---|---|
| Caminhos `reports/` e `data/processed` fixos nos scripts | `scripts/01` a `05` | Gravaria por cima dos resultados de MT | `paths.reports` na configuração (padrão `reports`); MS em `reports/ems/` e `data/ems/processed/` |
| Uma só configuração (`premissas.yaml`) | `Config.load()` | | `--config` ou `SWSURV_CONFIG`; padrão = MT; `SWSURV_CACHE` continua valendo |
| Cache de outra distribuidora lido sem aviso | `SWSURV_CACHE` | Com a variável apontando para MT, o pipeline de MS rodaria com dados de MT | Guarda por `DIST` / `cod_aneel` em `ler_classe` |
| Anos fixos: 2018 a 2025, `2025`, `2021`, `2020` | `01_painel`, `02_vida`, `04_projecao`, `05_figuras` | Coincidem com MS hoje, mas ficariam errados em outro recorte | Derivados da configuração (`ano_base`, `anos_snapshots`, `anos_com_data`); em MT dão os mesmos nomes de colunas e arquivos |
| Latitude fixa de -13° | `cadastro.pontos_religador` | Erra a distância leste-oeste em cerca de 4% (cos 20,6° contra cos 13°) | `pontos.lat_ref_graus` (seção 7) |
| `TIP_UNID` 32 fixo para religador | `cadastro.pontos_religador` | Confere (seção 4) | Parâmetro `pontos.tip_unid_religador` |
| TUC 160, 210, 345, 340 | `configs/premissas.yaml` | Conferem; o 210 inclui alta tensão (seção 4) | Mesmos códigos; rótulo do 210 próprio de MS |
| `anos_com_data` = 2020 a 2025 | `configs/premissas.yaml` | Confere (seção 3) | Mesmo valor, agora justificado com dados de MS |
| Limiares 0,25 e 0,10; janelas 2021 a 2024 | `configs/premissas.yaml` | Mantidos (seções 5 e 6) | Mesmos valores |
| "A contagem por safra é estável e só cai" | docstring de `cadastro.py` | **Não vale em MS** (seção 5) | Docstring ajustada; o teste de consistência a verifica; o pipeline roda sem nenhuma classe confiável |
| Rótulos "Energisa MT", "Mato Grosso" | README, `docs/metodologia.md` | Texto de MT não se aplica | O texto de MT não foi reescrito; MS tem seção e documentos próprios; as figuras de MS levam o nome da distribuidora no título |
| Conclusão "o risco cresce com a idade" no título da figura 02 | `05_figuras.py` | Sem estimativa em MS, a conclusão não se sustenta | `figuras.complemento_taxa`, vazio em MS (a figura só sai se alguma classe passar no teste) |
| Nome do arquivo de interrupções (`interrupcoes_emt.parquet`), malha do IBGE de MT, UF do INMET, PAC em UTM | | **Não existem neste repositório** | Nada a fazer; conferido por busca |

## 10. Reproduzir

```bash
python scripts/00_baixar_bdgd.py --config configs/premissas_ems.yaml --zips <pasta dos zips>
python scripts/diagnostico_bdgd.py --config configs/premissas_ems.yaml
```

A pasta de zips também pode vir da variável `SWSURV_BDGD_ZIPS`. Sem pasta, o `00_baixar_bdgd.py` baixa do ArcGIS, como em
MT.

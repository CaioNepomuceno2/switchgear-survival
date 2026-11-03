# Metodologia

## 1. Pergunta e escopo

Quanto tempo os equipamentos de manobra e proteção da média tensão duram na rede da Energisa Mato Grosso (EMT),
quantos precisarão ser substituídos por ano e quanto isso custa.

| Classe | Fonte na BDGD | Identificação |
|---|---|---|
| Religador | camada EQSE (equipamento de seccionamento) | TUC 345 |
| Disjuntor de média tensão | EQSE | TUC 210 |
| Chave (seccionadora e fusível) | EQSE | TUC 160 |
| Regulador de tensão | EQRE (equipamento regulador) | TUC 340 |

O TUC (Tipo de Unidade de Cadastro) é a classificação patrimonial do setor elétrico. Os códigos 160 e 210 aparecem
com esses nomes no Banco de Preços de Referência da ANEEL (campo NumUC). Os códigos 345 e 340 foram confirmados pela
ligação na própria BDGD: os equipamentos instalados nas unidades com TIP_UNID = 32 (religador) têm TUC 345, e a
camada de reguladores tem TUC 340.

## 2. Dados

* Oito cadastros anuais da BDGD da EMT (31/12 de 2018 a 2025), baixados do ArcGIS Hub da ANEEL
  (`scripts/00_baixar_bdgd.py`).
* Campo de idade: DAT_IMO, a data de imobilização contábil do equipamento.
* Os cadastros de 2018 e 2019 (modelo antigo M10) trazem DAT_IMO = 01/01/1920 em 100% dos equipamentos: ficam de
  fora. Datas vazias, "0", anteriores a 1950 ou posteriores ao ano do cadastro viram "sem data".

## 3. Por que a análise é por safra e não por equipamento

O caminho natural seria seguir cada equipamento pelo código (COD_ID) e registrar quando ele some. Testei e não
funciona:

* Os códigos são renumerados em massa em alguns anos: só 28% dos códigos de religador de 2022 reaparecem em 2023.
* Entre os códigos que reaparecem, a DAT_IMO do mesmo equipamento muda em 50% a 95% dos casos, ano a ano.
* O meio de isolação também é reclassificado (código SE de 205 para 6 religadores entre 2023 e 2025).

Já a contagem de equipamentos por ano de imobilização (a safra) é estável: nos religadores, nenhuma safra volta a
crescer depois de cair na janela 2021-2025. Isso é o que os estudos de depreciação de concessionárias chamam de
dados por safra (*aged data*): o registro contábil sabe quantos ativos de cada ano de compra ainda existem, mesmo
sem acompanhar cada unidade. O método adequado é o atuarial de taxas de retirada.

Como checagem independente, segui os **pontos** de religador no mapa (camada UNSEMT): por código e, quando o código
não reaparece, pelo vizinho mais próximo a até 30 m. Os pontos que somem sem par têm a mesma ordem de grandeza das
baixas por safra (`reports/qualidade_pontos_religador.csv`).

## 4. Movimentos por safra

Para cada safra *v* e cada par de cadastros consecutivos (*t*, *t*+1), com *v* ≤ *t*:

* expostos = N(*v*, *t*)
* baixas = max(N(*v*, *t*) − N(*v*, *t*+1), 0)
* acréscimos = max(N(*v*, *t*+1) − N(*v*, *t*), 0): uma safra antiga que ganha equipamentos só pode ser correção
  cadastral (o equipamento novo entra com a safra do ano em que foi imobilizado).
* idade no início do ano *t*+1 = *t* − *v*

**Teste de consistência por classe.** Uma classe entra na estimativa se acréscimos / baixas ≤ 25% e se no máximo
10% das safras (com pelo menos 10 equipamentos) voltam a crescer depois de cair. Religadores e disjuntores passam
(0% e 0%); chaves (37% e 16%) e reguladores (21% e 59%) não.

## 5. Truncamento e censura, de forma didática

Imagine que você começa a observar a frota em 31/12/2021 e para em 31/12/2025.

* **Truncamento à esquerda.** Um religador comprado em 2006 já tinha 15 anos quando a observação começou. Os
  religadores de 2006 que saíram da rede antes de 2021 nunca aparecem. Se você calcular "idade média na baixa" só
  com quem você viu, as baixas de equipamentos jovens daquela safra ficam de fora e a vida parece maior do que é.
* **Censura à direita.** A maior parte da frota ainda está em operação em 2025. Não sabemos quando esses
  equipamentos vão sair, só que duraram pelo menos até a idade atual. Ignorá-los (ou tratá-los como se tivessem
  saído) distorce a curva.

A tábua de vida resolve os dois problemas ao trabalhar **idade por idade**: para cada idade *a*, só conta quem
estava em operação naquela idade durante a janela observada (os expostos) e quantos desses saíram (as baixas).
O religador de 2006 contribui para as idades 15 a 19, e não para as idades 0 a 14, que ele viveu antes da
observação. O religador que segue em operação contribui como exposto em todas as idades que viveu dentro da janela,
sem nunca ser contado como baixa. É o mesmo princípio do estimador de Kaplan-Meier com entrada tardia, aplicado a
dados agrupados por safra.

## 6. Tábua de vida e curva de Weibull

**Taxa de baixa por idade:** q(*a*) = baixas(*a*) / expostos(*a*), somando safras e anos da janela.

**Sobrevivência empírica:** S(*x*) = ∏ (1 − q(*a*)) para *a* < *x*. Intervalo de confiança de Greenwood em
escala log: Var[log S(*x*)] ≈ Σ q(*a*) / (expostos(*a*) · (1 − q(*a*))).

**Weibull.** S(*x*) = exp(−(*x*/η)^β). A idade do equipamento é contada a partir do meio do ano de imobilização
(*x*₀ = *a* + 0,5), então

q(*a*) = 1 − exp(−[((*x*₀+1)/η)^β − (*x*₀/η)^β])

Os parâmetros saem por máxima verossimilhança binomial agrupada: baixas(*a*) ~ Binomial(expostos(*a*), q(*a*)).

* β > 1: o risco cresce com a idade (desgaste). β = 1: risco constante. β < 1: falhas precoces dominam.
* Vida mediana = η · (ln 2)^(1/β).

**Intervalos de confiança.** Bootstrap por safra: reamostra safras inteiras com reposição (500 vezes) e reajusta.
Reamostrar a safra, e não cada célula, preserva a correlação entre os anos de uma mesma safra.

## 7. Janelas

* **Principal:** transições 2021→2022, 2022→2023, 2023→2024 e 2024→2025.
* **Sensibilidade:** inclui 2020→2021. Nos religadores, essa transição tem 60 acréscimos em safras antigas para 56
  baixas (recadastramento). Com ela, a vida mediana dos religadores vai de 28 para 31 anos e a dos disjuntores de
  39 para 24 anos (79 baixas de disjuntores concentradas em 2021).

## 8. Validação

Dois desenhos fora da amostra: ajuste com 2022-2023 e teste em 2024-2025; ajuste com 2022-2024 e teste em 2025.

| Método | Como prevê as baixas do ano *t*+1 |
|---|---|
| Weibull | Σ N(*v*, *t*) · q(*t* − *v*) com os parâmetros ajustados |
| Taxa constante | frota em *t* × (baixas / expostos da janela de ajuste) |
| Idade-limite | todos os equipamentos que completam 25 anos no ano |
| Persistência | as baixas do último ano de ajuste |

**Acerto por safra:** Σ min(previsto, observado) por safra e ano, dividido pelas baixas observadas. Mede quanto das
baixas reais caiu nas safras em que o método esperava baixas. A idade-limite é um baseline, não a vida regulatória.

## 9. Projeção

A frota datada de 2025 é envelhecida ano a ano: baixas esperadas no ano *t*+1 = Σ N(*v*, *t*) · q(*t* − *v*). Cada
baixa é reposta por um equipamento novo (safra *t*+1), que também passa a envelhecer. Os equipamentos sem data
válida entram por reescala, supondo a mesma distribuição de idade. O IC 90% vem de rodar a projeção com cada par
(β, η) do bootstrap. A projeção não inclui expansão (equipamentos em pontos novos).

CAPEX = substituições × custo unitário. O custo do religador (R$ 160 mil) é **ilustrativo** e configurável; as
demais classes ficam sem custo.

## 10. Premissas

| Premissa | Valor | Fonte |
|---|---|---|
| Classes por TUC | 345, 210, 160, 340 | BDGD e Banco de Preços de Referência da ANEEL |
| Anos com data válida | 2020-2025 | Diagnóstico do cadastro |
| Janela principal | transições 2021-2024 | Diagnóstico do cadastro |
| Limiares de consistência | 25% de acréscimos; 10% de safras não monótonas | Escolha do projeto |
| Idade-limite do baseline | 25 anos | Parâmetro de comparação |
| Custo de substituição do religador | R$ 160 mil | Ilustrativo |
| Vida útil regulatória | não preenchida | Preencher com a tabela oficial da ANEEL |

## 11. Como interpretar

* **Taxa anual de 1,0% (religadores):** de cada 100 religadores em operação no início do ano, 1 sai da rede.
* **Vida mediana de 28 anos:** metade de uma safra nova terá saído da rede aos 28 anos, segundo a curva. Como a
  observação densa vai até 24 anos, é parcialmente extrapolação.
* **β = 2,6:** o risco de um religador de 25 anos sair da rede no ano é várias vezes o de um de 10 anos.
* **Substituições 2026-2035:** é o volume para manter a frota atual, sem contar crescimento da rede.
* **Classe "não confiável":** o cadastro não sustenta a estimativa. Corrija o cadastro ou use dados patrimoniais
  antes de estimar.

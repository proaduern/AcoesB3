# AcoesB3 — Especificação v1

Documento de decisões consolidado a partir de 32 perguntas respondidas pelo usuário (03/10/2026).

**Status: aprovada pelo usuário em 03/10/2026, incluindo as suposições da seção 13.** Segredo `NEON_DATABASE_URL` já cadastrado no GitHub Actions.
Todo parâmetro numérico abaixo é **configurável** no sistema; os valores são os padrões iniciais.

## 1. Objetivo

Sistema pessoal para ações da B3 que:
- **(a)** indica se uma ação está para compra ou não (preço teto);
- **(b)** sugere a alocação do aporte mensal;
- **(c)** alerta venda/rebalanceamento.

## 2. Fontes de dados

| Dado | Fonte | Observação |
|---|---|---|
| Demonstrações financeiras | CVM Dados Abertos (DFP/ITR/FCA) | Fonte única dos números. Sem leitura de PDF para números. |
| Release de resultados | CVM (comunicados) → Google Drive | Só para leitura. Empresas que não entregarem à CVM: link manual para o RI. |
| Cotações históricas | B3 COTAHIST (oficial) | Base para cálculos e backtest. |
| Cotação intradiária | brapi / Yahoo (atraso de ~15 min) | Só exibição. Se falhar: fechamento anterior + aviso. |
| Classificação setorial | B3 (setor/subsetor/segmento) | Com reclassificação manual por empresa. |
| Operações do usuário | Lançamento manual + extrato da Área do Investidor B3 (upload) | Reconciliação entre os dois. Sem histórico inicial. |

Duas séries de preço:
- ajustada só por desdobramentos/grupamentos (para múltiplos);
- ajustada também por proventos, de retorno total (para backtest e rentabilidade).

## 3. Universo

- **Filtro**: B3 inteira, menos os segmentos excluídos pelo usuário.
- **Acompanhamento detalhado** (DCF, release, alertas): lista do usuário.
- **Classes**: uma linha por empresa no filtro e preço teto por classe. Units calculadas pela composição (ex.: TAEE11 = 1 ON + 2 PN).
- **Liquidez**: volume médio diário ≥ R$ 1 mi e presença em ≥ 90% dos pregões (últimos 3 meses).

## 4. Filtro

**Lucratividade**
- lucro líquido positivo em ≥ 8 dos últimos 10 anos;
- ROE médio de 5 anos > 10%.

**Proventos** (dividendos + JCP)
- pagos em 10 de 10 anos;
- DY médio líquido de 5 anos > 5%;
- payout entre 25% e 100%;
- dividendo por ação caiu em no máximo 3 dos últimos 10 anos.

**DY líquido**: alíquotas configuráveis (JCP 15%, dividendo 0%).

**Outliers**: provento > 2× a mediana de 5 anos é marcado como suspeito.
- Fica fora do histórico por padrão.
- Aparece em destaque na tela.
- O usuário revisa e decide incluir ou não.

**Limitação de histórico**: os dados estruturados da CVM começam por volta de 2010.

## 5. Preço teto

| Método | Aplicação | Parâmetros | Exclusões |
|---|---|---|---|
| Bazin | Todas | dividendo médio líquido de 5 anos (sem outliers) ÷ 6% | — |
| Graham | Todas | √(22,5 × LPA médio de 3 anos × VPA) | LPA ≤ 0, VPA ≤ 0, bancos e seguradoras |
| Gordon | Todas | D1 ÷ (k − g); k = 12% nominal; g = crescimento histórico de 5 anos limitado a [0%, 5%]; D1 = dividendo médio líquido de 5 anos × (1+g) | k − g < 3 p.p. |
| Múltiplos | Todas | P/L mediano de 10 anos × LPA médio de 3 anos (não financeiras); P/VP mediano de 10 anos × VPA (bancos e seguradoras). Conta como 1 método. | Anos de lucro negativo fora do P/L |
| DCF (FCFE) | Só lista do usuário | Desconto a 12%; 5 anos projetados (crescimento histórico, sobrescrevível por empresa) + perpetuidade de 4% | Bancos e seguradoras |

**Consolidação**: preço teto = **mediana** dos métodos aplicáveis.

**"Compra"** exige preço < mediana **e** preço < teto em pelo menos K métodos:
- 5 métodos → K = 3
- 4 métodos → K = 3
- 3 métodos → K = 2
- menos de 3 → "dados insuficientes": visível, mas fora do aporte automático.

**Faixas** (preço ÷ teto):

| Faixa | Situação |
|---|---|
| < 80% | Compra forte |
| 80–100% | Compra |
| 100–120% | Manter |
| > 120% | Cara, avaliar venda |

## 6. Alocação do aporte

- **Elegíveis**: ações com peso abaixo do alvo e na faixa de compra. O desconto define o quanto cada uma recebe.
- **Peso-alvo**: igual para todas, ajustável por ação.
- **Limites**: máximo de 10% por ação e 30% por setor; no máximo 3 ações por aporte.
- **Lote**: mercado fracionário (ações inteiras).

## 7. Venda e rebalanceamento

- **Alertas**: preço > 120% do teto; ação deixou de passar no filtro (sempre "avaliar venda"); concentração acima do limite; dívida líquida/EBITDA > 3× (não se aplica a financeiras); 2 trimestres seguidos de queda de lucro.
- **Rebalanceamento** só via aportes. O sistema não sugere venda por concentração.

## 8. Backtest

- **Ponto no tempo**: um balanço só entra a partir da data de entrega à CVM **da versão cujos números estão guardados** (decisão de 03/10/2026; view `filing_available`). Documento reapresentado só entra na data da reapresentação, mesmo que a 1ª versão seja anterior. Empresas canceladas incluídas (sem viés de sobrevivência).
- **Período**: 2012 em diante. Ajuste até 3 anos atrás; os **3 últimos anos ficam reservados para validação**.
- **Comparação**: Ibovespa, IDIV e CDI, mais variações de parâmetros (DY desejado, K etc.).
- **Critério de morte**: aviso se o retorno total perder do IDIV em mais de 50% das janelas móveis de 5 anos, **ou** se a queda máxima for mais de 10 p.p. pior que a do IDIV.

## 9. Infraestrutura

- **Banco**: Neon (Postgres, plano grátis: 1 GB por projeto, verificado em 03/10/2026). Guardar só as contas usadas nos cálculos: lista editável na tabela `cvm_account` (cobre os planos de contas de empresa comum, banco e seguradora).
- **Demonstração usada**: consolidada; individual só quando a empresa não entrega consolidada.
- **Processamento**: Python em lotes no GitHub Actions (coleta diária, cálculos, recálculo disparado pela tela ao mudar configuração, 2–5 min).
- **Tela**: Next.js na Vercel. Lê resultados prontos do banco.
- **Simulador**: recalcula uma ação na hora (TypeScript), com teste automático de paridade contra o Python.
- **Login**: Google, lista de e-mails permitidos (inicialmente só o do usuário). Banco preparado para vários usuários.
- **PDFs**: Google Drive do usuário, uma pasta por empresa. Acesso só aos arquivos criados pelo app. App no Google Cloud publicado (não em modo teste).
- **Alertas**: só dentro do sistema por enquanto. Falha de coleta também gera e-mail automático do GitHub Actions. Toda tela mostra a data-base e a data de coleta de cada dado.

## 10. Regras de qualidade de dados

- Todo indicador exibe fonte, data-base e data de coleta.
- Escala da CVM (`ESCALA_MOEDA`: unidade vs mil) tratada e testada explicitamente.
- Dado ausente aparece como "indisponível", nunca como zero ou valor antigo sem aviso.
- Pelo menos 3 testes comparam valores contra números de balanços publicados, conferidos manualmente pelo usuário. **Feito (03/10/2026)**: lucro atribuído aos controladores em 2024 de WEG (R$ 6.042.593 mil), Itaú (R$ 41.085.000 mil) e BB Seguridade (R$ 8.703.353 mil), conferidos pelo usuário contra os balanços publicados (`pipeline/tests/test_cvm.py::test_lucro_controlador_por_plano_de_contas`).

## 11. Fases

1. Banco (Neon) + coleta CVM e cotações (GitHub Actions)
2. Indicadores, filtro, outliers
3. Preço teto (5 métodos), mediana, votação K, faixas
4. Backtest + critério de morte + validação
5. Tela Next.js + login + filtro + ficha da empresa + simulador
6. Carteira: lançamentos, extrato B3, preço médio, proventos
7. Alocação do aporte + alertas
8. Release em PDF no Google Drive

## 12. A verificar na implementação (não assumir)

- ~~Limite atual de armazenamento do Neon grátis.~~ **Verificado (03/10/2026)**: 1 GB por projeto (até 20 GB somando 100 projetos), 100 CU-hora/projeto, 5 GB de tráfego de saída/projeto. Carga completa 2010–2026 medida: **320 MB** (32% do limite), crescimento ~20 MB/ano; ver `docs/fase1.md`.
- ~~Atraso real entre a entrega à CVM e a disponibilidade nos Dados Abertos~~ **Verificado (03/10/2026)**: DFP/ITR/FCA são atualizados **semanalmente** (página oficial do conjunto de dados; arquivos regerados no domingo 27/09). Atraso de até ~7 dias corridos, mais que 1 dia útil. O cadastro de companhias é diário. **Detecção via RAD/ENET inviável**: desde 06/07/2026 a consulta externa mudou para `/ENETWeb/` e a listagem de documentos exige Google reCAPTCHA; automatizá-la exigiria contornar o CAPTCHA. **Pendente de decisão do usuário**: alternativa (ver `docs/fontes.md`).
- Os arquivos de demonstrações trazem só a versão mais recente de cada documento; o índice traz todas as versões com a data de entrega. Versões antigas só existem no banco se coletadas na época. **Decidido**: o backtest usa a data de entrega da versão guardada (seção 8).
- Cobertura dos releases entregues à CVM para as empresas da lista.
- Regras vigentes de tributação de dividendos (informativo; o sistema usa alíquotas configuráveis).
- Disponibilidade e limites da brapi/Yahoo no plano grátis.

## 13. Suposições feitas sem pergunta explícita (corrigir se discordar)

- Dívida/EBITDA não se aplica a bancos e seguradoras.
- Queda máxima de dividendo por ação: no máximo 3 de 10 anos.
- Gatilho do critério de morte conforme a seção 8.
- Python para coleta e cálculos; TypeScript só na tela e no simulador.

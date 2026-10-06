# Fase 3 — Preço teto (concluída no código e no Neon; pendem revisões do usuário)

**Estado (05/10/2026)**: 5 métodos (Bazin, Graham, Gordon, múltiplos, DCF), mediana, votação K e faixas, por papel (ON, PN, unit),
só para a lista acompanhada. 264 testes, lint limpo. Rodado no Neon em 05/10/2026 (`compute` com `reload_dfp` + `step=ceilings`):
18 empresas calculadas; banco do Neon em 431 MB. Regras na seção 5.1 da especificação; formatos do DFC em `docs/fontes.md`.

## Como operar

- Calcular: Actions → `compute`, `step=ceilings` (opcional `as_of=AAAA-MM-DD`). Ler: `ceilings_list` (e `ceilings_dcf` para o FCFE por conta).
  Local: `acoesb3 ceilings list [--cvm N] [--dcf]`.
- Crescimento do FCFE de uma empresa: `acoesb3 review dcf-growth --cvm N --growth 0.03` (ou `--clear`); no Actions, entrada `dcf_growth` (`codigo:fracao;codigo:limpar`).
- Tirar o DCF: `ceiling.dcf_enabled = false` em `app_config`. Todo parâmetro `ceiling.*` e `fcfe.*` fica lá.
- Empresa nova na lista acompanhada: recarregar as DFP (`reload_dfp`) para guardar o DFC detalhado dela.
- Código: `pipeline/acoesb3/ceiling.py` (métodos, puro), `fcfe.py` (FCFE, puro), `compute.build_ceilings` (banco), tabelas
  `ceiling_method`, `ceiling_result`, `ceiling_class`, `dcf_growth_override` (migrações 0013 e 0014).

## Resultado real de 05/10/2026 (preço = fechamento de 02/10/2026) — a conferir pelo usuário

Compra pela regra (preço < mediana e < teto em ≥ K métodos): BBAS3, SANB3/4/11, BBSE3, CMIG4, ISAE4, TAEE3. Dados insuficientes (< 3 métodos):
Sabesp (Graham e múltiplos excluídos por LPA/VPA ≤ 0, DCF sem crescimento) e TIM (1 método). Caixa Seguridade: sem Bazin/Gordon (abriu capital em 2021).

## Pendências que dependem do usuário

1. **Porto Seguro (16659) e Caixa Seguridade (23795) estão com plano `comum`** (a DVA delas é de empresa comum), então receberam Graham e DCF,
   contra a regra "seguradora: sem Graham e sem DCF, 3 métodos, K = 2". Correção: `acoesb3 review class --cvm N --plan seguradora`
   (muda também a escolha de lucro/PL do filtro dessas empresas; rodar `compute` inteiro depois).
2. **DCF sensível a um exercício atípico**: Sanepar teve FCFE de R$ 4,2 bi em 2025 contra ~R$ 0,5–0,9 bi antes (CFO de R$ 7,1 bi), o que
   eleva o DCF (R$ 16,71 contra teto mediano de R$ 6,76). Conferir com `ceilings_dcf`; usar `dcf_growth` ou `ceiling.dcf_enabled`.
   Cemig, Sabesp e TIM ficam sem DCF até o usuário informar o crescimento (ponta do FCFE ≤ 0).
3. **Valor por ação igual para ON e PN** (a especificação deixava em aberto; adotado por padrão): ISAE3 vs ISAE4 e ALUP3 vs ALUP4 mostram
   o mesmo teto. Se quiser teto distinto por classe, é preciso definir a regra (os proventos por classe do FRE não existem de 2025 em diante).
4. Os padrões `fcfe.*` foram validados nas contas reais de 11 empresas (2021 e 2024/2025); revisar o detalhe do DCF (`ceilings_dcf`) de cada uma.
5. Pendências da fase 2 continuam: outliers prioritários (`review list --priority`) e eventos suspeitos da lista.

## O que ficou de fora, e por quê

| Item | Motivo |
|---|---|
| Teto por classe com proventos distintos | Sem regra definida; FRE sem dividendos por classe em 2025+ |
| DCF levado da data do último exercício até a data-base | Não especificado; o valor é o do fim do último exercício |
| Retratos históricos do preço teto (fins de ano) | Pertence ao backtest (fase 4); `build_ceilings` já aceita `as_of`, mas só a lista acompanhada tem DFC detalhado |
| Preço teto fora da lista acompanhada | Decisão de 04/10/2026 |
| Cotação intradiária | Decisão: preço atual = último fechamento do COTAHIST |
| Tela e simulador (TypeScript) | Fase 5; o simulador exige teste de paridade com `ceiling.py` |

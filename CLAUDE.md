# AcoesB3

Sistema pessoal de carteira de ações B3: filtro de empresas perenes, preço teto por 5 métodos, alocação de aporte, alertas e backtest.

**Fonte da verdade: `docs/ESPECIFICACAO.md`.** Leia antes de qualquer tarefa. Não invente regra ausente dela: pergunte ao usuário. Se uma decisão mudar, atualize a especificação no mesmo commit.

## Idioma
- Converse com o usuário em português do Brasil.
- Código, nomes de variáveis e de tabelas em inglês; textos da interface em português.

## Arquitetura (ver seção 9 da especificação)
- `pipeline/` — Python: coleta (CVM, COTAHIST, cotação intradiária), indicadores, filtro, preço teto, backtest. Roda em lotes no GitHub Actions e grava no Neon (Postgres).
- `web/` — Next.js na Vercel: só lê resultados prontos do banco. Única lógica de cálculo em TypeScript: o simulador, que precisa de teste de paridade contra o Python.
- PDFs de releases: Google Drive do usuário (escopo `drive.file`), uma pasta por empresa.

## Regras inegociáveis
- Números financeiros vêm só da CVM Dados Abertos. Nunca extraia números de PDF.
- Trate `ESCALA_MOEDA` (unidade vs mil) explicitamente, com teste.
- Dado ausente = "indisponível". Nunca preencha com zero ou valor anterior sem aviso.
- Todo indicador guarda fonte, data-base e data de coleta.
- Backtest só usa dados disponíveis na data (data de entrega à CVM). Inclui empresas canceladas.
- Todo parâmetro numérico é configurável (tabela de configuração), nunca fixo no código.
- Não invente endpoints ou formatos de arquivo: verifique a fonte real antes de codar o parser.

## Segredos
- Nunca coloque credenciais no código nem peça que o usuário cole credenciais no chat.
- Segredos ficam no GitHub Actions / Vercel. Nomes: `NEON_DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `ALLOWED_EMAILS`.

## Fluxo de trabalho
- Uma fase da especificação por sessão (seção 11). Fase atual: **1**.
- Cada fase entrega: código, testes passando, e uma nota do que ficou de fora e por quê.
- Ao concluir uma fase, atualize "Fase atual" acima.
- Antes de push: rode os testes e o lint do pacote alterado.

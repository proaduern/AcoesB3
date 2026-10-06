-- Fase 3: DCF (FCFE). Contas do fluxo de caixa verificadas nos dados reais (DFP 2021 e 2024 das empresas da
-- lista, docs/fontes.md): só 6.01, 6.02 e 6.03 são padronizadas; as filhas mudam de código e de nome por
-- empresa e são classificadas pela descrição (fcfe.*). Para valer nos dados já carregados:
-- acoesb3 cvm --doc DFP --force (workflow compute com reload_dfp).
INSERT INTO cvm_account (statement, code, include_children, description, purpose) VALUES
 ('DFC_MI', '6.02', true, 'Caixa Líquido das Atividades de Investimento e contas filhas (nomes variam por empresa)', 'FCFE'),
 ('DFC_MD', '6.02', true, 'Caixa Líquido das Atividades de Investimento e contas filhas (nomes variam por empresa)', 'FCFE'),
 ('DFC_MI', '6.03', true, 'Caixa Líquido das Atividades de Financiamento e contas filhas (nomes variam por empresa)', 'FCFE'),
 ('DFC_MD', '6.03', true, 'Caixa Líquido das Atividades de Financiamento e contas filhas (nomes variam por empresa)', 'FCFE')
ON CONFLICT DO NOTHING;

-- Crescimento do FCFE informado para uma empresa (sobrescreve o histórico no DCF).
CREATE TABLE dcf_growth_override (
    cvm_code integer PRIMARY KEY,
    growth   numeric(8, 6) NOT NULL,
    note     text,
    set_at   timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_config (key, value, description) VALUES
 ('cvm.dfc_only_watchlist', 'true', 'Guarda as contas filhas do DFC (6.02.*, 6.03.*) só das empresas da lista acompanhada (economiza espaço no banco); empresa nova na lista exige recarregar as DFP'),
 ('ceiling.dcf_enabled', 'true', 'Inclui o DCF (FCFE) entre os métodos do preço teto'),
 ('ceiling.dcf_rate', '0.12', 'DCF: taxa de desconto'),
 ('ceiling.dcf_years', '5', 'DCF: anos projetados'),
 ('ceiling.dcf_terminal_growth', '0.04', 'DCF: crescimento da perpetuidade'),
 ('ceiling.dcf_history_years', '5', 'DCF: exercícios do histórico de FCFE (crescimento composto entre as pontas)'),
 ('ceiling.dcf_base_years', '3', 'DCF: o FCFE-base é a média dos últimos N exercícios'),
 ('ceiling.dcf_g_min', '0', 'DCF: crescimento histórico mínimo (não vale para o crescimento informado por empresa)'),
 ('ceiling.dcf_g_max', '0.05', 'DCF: crescimento histórico máximo (não vale para o crescimento informado por empresa)'),
 ('fcfe.capex_patterns', '["IMOBILIZADO", "INTANGIVE", "ATIVOS? (DE|DO|DA) (CONTRATO|CONTRATUAL|CONCESSAO)", "ATIVOS? CONTRATUA", "PROPRIEDADES? PARA INVESTIMENTO", "\\bPPP\\b"]', 'FCFE: contas de investimento (6.02.xx) que contam como capex; expressões regulares sobre a descrição, sem acento e em maiúsculas'),
 ('fcfe.inflow_patterns', '["DIVIDENDOS?.*RECEBID", "CAPITAL PROPRIO.*RECEBID"]', 'FCFE: contas de investimento (6.02.xx) que contam como dividendos e JCP recebidos de investidas'),
 ('fcfe.non_debt_patterns', '["DIVIDEND", "CAPITAL PROPRIO", "JCP", "JSCP", "\\bACOES\\b", "ACIONISTA", "CAPITAL(?! DE GIRO)", "AFAC", "TESOURARIA", "RESERVA", "PARTICIPACAO (SOCIETARIA|EM CONTROLADA)", "AQUISICAO DE (NEGOCIOS|PARTICIPACAO|CONTROLADA)", "RECESSO", "DISSIDENCIA", "GRUPAMENTO"]', 'FCFE: contas de financiamento (6.03.xx) que NÃO são dívida (acionistas e participações); todas as demais contam como fluxo de dívida')
ON CONFLICT DO NOTHING;

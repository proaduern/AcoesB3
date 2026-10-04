-- Descrição das contas (DS_CONTA) para achar o patrimônio líquido por NOME e não por código.
-- Banco do Brasil (2020+), por exemplo, não tem a conta 2.08: o PL de cada banco fica em um
-- código diferente do plano padrão. Guardada só nas contas lidas (ver cvm_account).
ALTER TABLE financial_line ADD COLUMN description text;

-- Contas de segundo nível do passivo/PL: uma delas é o PL ("Patrimônio Líquido...").
-- Os filhos do PL (para achar a participação dos não controladores) o carregador acrescenta
-- sozinho, olhando o nome.
INSERT INTO cvm_account (statement, code, include_children, description, purpose) VALUES
 ('BPP', '2.01', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.02', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.03', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.04', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.05', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.06', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.07', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.08', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.09', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.10', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.11', false, 'Passivo/PL, nível 2', 'achar o PL por nome'),
 ('BPP', '2.12', false, 'Passivo/PL, nível 2', 'achar o PL por nome')
ON CONFLICT DO NOTHING;

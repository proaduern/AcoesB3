"""FCFE a partir do DFC: contas filhas reais de 5 empresas da lista (DFP 2021, valores em R$ mil
como no arquivo; copiadas sem edição da saída da sonda do Actions de 05/10/2026)."""

import json
import re
from decimal import Decimal

import pytest

from acoesb3 import fcfe

D = Decimal

# Padrões como em migrations/0014_dcf_fcfe.sql (lidos de lá para o teste acompanhar a migração).
_SQL = open(
    __file__.replace("tests/test_fcfe.py", "migrations/0014_dcf_fcfe.sql"), encoding="utf-8"
).read()


def _cfg():
    return {k: json.loads(v) for k, v in re.findall(r"\('(fcfe\.[a-z_]+)', '(\[.*?\])', '", _SQL)}


RULES = fcfe.FcfeRules.from_config(_cfg())


def parse(raw: str):
    out = []
    for line in raw.strip().splitlines():
        code, rest = line.strip().split(None, 1)
        desc, value = rest.rsplit(None, 1)
        out.append((code, desc.strip(), D(value)))
    return out


ENGIE = """
6.01 Caixa Líquido Atividades Operacionais 1989161
6.02 Caixa Líquido Atividades de Investimento -339053
6.02.01 Dividendos recebidos de controladas em conjunto 715000
6.02.02 Aumento de capital em controladas em conjunto 0
6.02.06 Venda de títulos e valores mobiliários 32439
6.02.07 Aplicação no imobilizado e no intangível -1229753
6.02.08 Aquisição de investimento 0
6.02.09 Valor justo dos direitos dos projetos adquiridos 0
6.02.10 Pagamento de obrigações vinculadas à aquisição de ativos -11361
6.02.11 Recebimento pela alienação de subsidiária, líquido dos custos de venda 192914
6.02.12 Caixa e equivalentes de caixa de subsidiária alienada -38318
6.02.13 Indenização por descumprimentos contratuais 0
6.02.14 Outros 26
6.03 Caixa Líquido Atividades de Financiamento -1033476
6.03.01 Captação de empréstimos e financiamentos 3324359
6.03.02 Emissão de debêntures 762462
6.03.03 Ações preferenciais emitidas 0
6.03.04 Pagamento de empréstimos e financiamentos, líquido de hedge -1258671
6.03.05 Pagamento de debêntures, líquido de hedge -348039
6.03.06 Pagamento de parcelas de concessões -243432
6.03.07 Pagamento de dividendos e juros sobre o capital próprio -2792602
6.03.08 Pagamento de arrendamentos -19172
6.03.09 Depósitos vinculados ao serviço da dívida -457050
6.03.10 Outros -1331
"""

CEMIG = """
6.01 Caixa Líquido Atividades Operacionais 3683357
6.02 Caixa Líquido Atividades de Investimento 1371198
6.02.01 Em Títulos e Valores Mobiliários - Aplicação Financeira 2047952
6.02.02 Em Ativos Financeiros 0
6.02.03 Em Imobilizado -182518
6.02.04 Em Intangível -50849
6.02.05 Em Investimentos -56317
6.02.06 Em Ativos de Contrato - Infraestrutura de Distribuição e Gás -1798296
6.02.07 Caixa advindo de combinação de negócios 155
6.02.08 Mútuo com partes relacionadas 0
6.02.09 Fundos Vinculados 44479
6.02.10 Operações Descontinuadas 0
6.02.11 Alienação de participação societária 1366592
6.03 Caixa Líquido Atividades de Financiamento -5909744
6.03.01 Obtenção de Empréstimos, Financiamentos e Debêntures 13406
6.03.02 Pagamentos de Empréstimos, Financiamentos e Debêntures -4436672
6.03.03 Juros sobre Capital Próprio e Dividendos -1416333
6.03.04 Custo de transação rolagem de dívida 0
6.03.05 Reembolso de Ações por Dissidência de Acionistas 0
6.03.06 Aporte de Acionistas para Futuro Aumento de Capital 0
6.03.07 Aumento de Capital 0
6.03.08 Arrendamentos pagos -70145
"""

VIVO = """
6.01 Caixa Líquido Atividades Operacionais 18072600
6.02 Caixa Líquido Atividades de Investimento -8127768
6.02.01 Aquisições de Imobilizado e Intangível -9295484
6.02.02 Caixa Recebido na Venda de Ativo Imobilizado 760254
6.02.03 Resgate Liquido de Depósitos Judiciais 163323
6.02.04 Pagamento por Aporte de Capital em Controlada 0
6.02.05 Caixa recebido na venda de investimentos 244139
6.02.07 Dividendos e Juros Sobre o Capital Próprio Recebidos 0
6.03 Caixa Líquido Atividades de Financiamento -9258430
6.03.01 Pagamentos de Empréstimos, Financiamentos, Debêntures, Arrendamentos e Licenças 5G -3901147
6.03.02 Recebimento dos Instrumentos Financeiros Derivativos 47661
6.03.03 Pagamento dos Instrumentos Financeiros Derivativos -52623
6.03.04 Pagamentos de Dividendos e Juros Sobre o Capital Próprio -4901326
6.03.05 Pagamento por Aquisições de Ações para Tesouraria -495995
6.03.06 Recebimento de Recursos para Aumento de Capital em Controladas por Outros Acionistas 45000
6.03.07 Pagamentos de Grupamento de Ações 0
6.03.08 Captações de Empréstimos, Financiamentos, Debêntures e Arrendamento 0
6.03.09 Exercício do Direito de Recesso de Acionistas 0
6.03.10 Custos Diretos em Aumentos de Capital 0
"""

TIM = """
6.01 Caixa Líquido Atividades Operacionais 10078087
6.02.01 Ativos financeiros ao valor justo -2502030
6.02.02 Adições ao imobilizado e intangível. Efeitos da aquisição 5G sem impacto -5283707
6.02.03 Caixa recebido na venda de ativo imobilizado 0
6.02.04 Recebimento de arrendamento mercantil financeiro 47
6.02.06 Caixa proveniente da venda de 51% I-Systems (antiga FiberCo) (nota 1) 1096294
6.03.01 Novos Empréstimos 3062000
6.03.02 Amortização de Empréstimos -1710935
6.03.03 Dividendos e JSCP Pagos -1042976
6.03.04 Operações com derivativos 216197
6.03.05 Compra de ações em tesouraria, liquido de alienações -11069
6.03.06 Juros pagos - Empréstimos -78952
6.03.07 Pagamento Leasing -1179723
6.03.08 Juros pagos - Arrendamento -832928
6.03.09 Novos financiamentos licença 5G 843020
"""

SANEPAR = """
6.01 Caixa Líquido Atividades Operacionais 1701536
6.02.01 Aplicação no Imobilizado e Intangível -1320162
6.02.03 Aplicação no Investimento -950
6.03.01 Financiamentos Obtidos 799220
6.03.02 Amortizações de Financiamentos -469674
6.03.03 Pagamentos de Juros sobre Financiamentos -230741
6.03.04 Pagamentos de Arrendamentos Mercantis -78591
6.03.05 Custo na Captação de Recursos de Terceiros -12516
6.03.06 Depósitos Vinculados -11743
6.03.07 Pagamentos de Juros sobre Capital Próprio -267575
6.03.08 Gastos com Emissão de Ações 0
"""


def test_engie_2021_conferido_a_mao():
    f = fcfe.compute_fcfe(parse(ENGIE), RULES)
    assert f.capex == D(-1229753)  # 6.02.07
    assert f.inflow == D(715000)  # 6.02.01, dividendos de controladas em conjunto
    # dívida: 3.324.359 + 762.462 - 1.258.671 - 348.039 - 243.432 - 19.172 - 457.050 - 1.331
    assert f.debt == D(1759126)
    assert f.value == D(1989161) - D(1229753) + D(715000) + D(1759126) == D(3233534)
    # o que sobra do investimento (aplicações, alienação de subsidiária...) e os dividendos pagos
    # ficam fora; tudo fecha com o caixa de investimento (6.02) e o de financiamento (6.03):
    excluded = sum(D(v) for _, _, v in f.lines["excluded"])
    assert excluded == D(32439 - 11361 + 192914 - 38318 + 26) + D(-2792602)
    assert f.capex + f.inflow + D(175700) == D(-339053)  # 6.02 total do arquivo


def test_cemig_2021_alienacao_e_aplicacoes_nao_entram():
    f = fcfe.compute_fcfe(parse(CEMIG), RULES)
    assert f.capex == D(-182518 - 50849 - 1798296)  # imobilizado, intangível e ativo de contrato
    assert f.debt == D(13406 - 4436672 - 70145)  # JCP/dividendos e capital ficam fora
    assert f.value == D(3683357 - 2031663 - 4493411) == D(-2841717)


def test_vivo_2021_venda_de_imobilizado_reduz_o_capex_e_tesouraria_fica_fora():
    f = fcfe.compute_fcfe(parse(VIVO), RULES)
    assert f.capex == D(-9295484 + 760254)
    assert f.debt == D(-3901147 + 47661 - 52623)  # derivativos são fluxo de dívida
    assert f.value == D(5631261)
    excluded = {c for c, _, _ in f.lines["excluded"]}
    assert {"6.03.04", "6.03.05", "6.03.06", "6.03.07", "6.03.09", "6.03.10"} <= excluded


def test_tim_2021_individual_juros_e_leasing_sao_divida():
    f = fcfe.compute_fcfe(parse(TIM), RULES)
    assert f.capex == D(-5283707)  # ativos financeiros ao valor justo não são capex
    assert f.debt == D(3062000 - 1710935 + 216197 - 78952 - 1179723 - 832928 + 843020) == D(318679)
    assert f.value == D(10078087 - 5283707 + 318679) == D(5113059)


def test_sanepar_2021_juros_sobre_financiamento_nao_e_jcp():
    f = fcfe.compute_fcfe(parse(SANEPAR), RULES)
    # "Juros sobre Financiamentos" é juro de dívida; "Juros sobre Capital Próprio" não é
    assert f.debt == D(799220 - 469674 - 230741 - 78591 - 12516 - 11743) == D(-4045)
    assert f.value == D(1701536 - 1320162 - 4045) == D(377329)


def test_sem_caixa_operacional_ou_sem_detalhamento_fica_indisponivel():
    only_totals = parse("6.01 Caixa Líquido Atividades Operacionais 100\n6.02 Investimento -10")
    f = fcfe.compute_fcfe(only_totals, RULES)
    assert f.value is None and "detalhamento" in f.reason
    f = fcfe.compute_fcfe(parse("6.02.01 Imobilizado -10\n6.03.01 Empréstimos 5"), RULES)
    assert f.value is None and "6.01" in f.reason


def test_contas_de_terceiro_nivel_nao_contam_em_dobro():
    lines = parse(
        """
        6.01 Caixa Operacional 100
        6.02.01 Aquisição de Imobilizado -40
        6.02.01.01 Máquinas -25
        6.02.01.02 Prédios -15
        6.03.01 Captação de Empréstimos 10
        """
    )
    assert fcfe.compute_fcfe(lines, RULES).value == D(100 - 40 + 10)


@pytest.mark.parametrize(
    "desc,group",
    [
        (
            "Empréstimo de capital de giro - pagamento",
            "debt",
        ),  # "capital de giro" não é capital social
        ("Aumento de Capital", "excluded"),
        ("Dividendos e JCP pagos", "excluded"),
    ],
)
def test_classificacao_do_financiamento(desc, group):
    lines = [
        ("6.01", "Operacional", D(0)),
        ("6.02.01", "Imobilizado", D(0)),
        ("6.03.01", desc, D(1)),
    ]
    f = fcfe.compute_fcfe(lines, RULES)
    assert [c for c, _, _ in f.lines[group]].count("6.03.01") == 1

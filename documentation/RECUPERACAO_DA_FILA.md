# Recuperação da fila de publicação

Em 06/10/2026, uma execução meteorológica de 05/10 permaneceu `queued`,
sem runner atribuído. Ela ocupava o grupo `mphi-sync`, deixando a coleta
hidrológica de hoje em `pending`. O timeout do job não limita o tempo de
espera antes da atribuição de um runner.

O grupo compartilhado continua serializando checkout, commit e publicação
para impedir que clima e hidrologia publiquem snapshots em conflito.
As agendas normais continuam com `cancel-in-progress: false`.

O workflow **MPHI - recuperar fila de publicação** solicita explicitamente
a substituição da execução anterior e executa o mesmo pipeline oficial,
com checkout do estado mais recente, verificação append-only, coleta,
validação, commit e publicação no GitHub Pages. Não muda parâmetros do
modelo nem edita os registros históricos. A primeira publicação deste
workflow dispara a recuperação; depois, pode ser acionado em Actions.

Usar a recuperação quando a fila estiver travada, preferencialmente sem
job efetivamente executando. Ela cancela a execução anterior do mesmo grupo.
Não é uma agenda adicional nem promessa de execução em horário exato:
o GitHub pode atrasar agendamentos e atribuição de runners. Se a recuperação
também ficar `queued`, verificar o estado do GitHub Actions e a conta.

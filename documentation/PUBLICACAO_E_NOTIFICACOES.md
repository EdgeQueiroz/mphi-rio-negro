# Publicação sem duplicações e notificações

As agendas de reserva continuam consultando o Porto, recalculando apenas
quando houver observação nova/correção e verificando os ledgers append-only.
Depois da coleta, `scripts/pages_publication.py decide` compara os sete
arquivos hidrológicos locais com o site público, usando consultas únicas
sem cache. Se os dados já estiverem publicados, encerra com sucesso sem
preparar ou publicar outro artefato.

Uma medição, correção, previsão, aferição ou alteração dos sinais da bacia
continua exigindo publicação. Divergência ou indisponibilidade no site
também solicita publicação, recuperando inclusive falhas posteriores ao
commit. Alterações do projeto por push e recuperação explícita da fila
forçam publicação para disponibilizar alterações da interface/código.

O horário `checked_at` sozinho não exige republicação quando a medição
de hoje e o estado `current` já estão publicados. Todos os demais campos
continuam sendo comparados. Esse horário só pode diferir se o registro
público for válido, com fuso, do mesmo dia em Manaus e sem data futura.
Estados `waiting` e `error` mantêm comparação estrita, inclusive do
horário, para continuar mostrando consultas recentes e falhas da fonte.
A verificação posterior à publicação usa o mesmo contrato; nenhum dado
do modelo, previsão ou validação fica dispensado da comparação.

O teste da escolha de provedor meteorológico agora passa o instante da
fixture ao coletor. Em produção, o coletor continua usando o horário real
e rejeitando respostas meteorológicas antigas. As agendas de clima e a
estimativa meteorológica consultada ao abrir a página foram preservadas.

As preferências de email pertencem à conta do GitHub, não ao repositório.
Em Settings > Notifications > System > Actions, usar **Only notify for
failed workflows** para receber avisos de falhas, evitando os de sucesso
e cancelamento. A alteração vale para a conta e pode afetar outros projetos.
O código não modifica essa preferência pessoal nem descarta alertas reais.

Nenhum parâmetro ou limiar do MPHI v1.0, previsão histórica, registro de
validação ou calendário de coleta foi alterado por esta correção.

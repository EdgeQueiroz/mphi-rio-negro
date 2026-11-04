# MPHI — piloto transfronteiriço de observações (não operacional)

**Escopo:** o Rio Negro continua coberto pelas estações brasileiras já utilizadas no v2-alpha. O piloto acrescenta **Tabatinga 10100000 (Rio Solimões)** e prepara a ingestão de **Tamshiyacu (Amazonas), Requena (Ucayali) e San Regis (Marañón), Peru**. Não há estações colombianas nesta fase.

## Estado das fontes
- Tabatinga: acesso público legado ANA, **experimental e sujeito à indisponibilidade**. A ANA anunciou migração para API autenticada HidroWebservice; o prazo anunciado para o serviço antigo foi 30/06/2026. Fonte: https://www.ana.gov.br/telemetria1ws/Dados.aspx
- API atual ANA: https://www.snirh.gov.br/hidroweb/acesso-api (credenciais sob responsabilidade institucional).
- Peru: PHISIS confirma níveis e vazões, porém **não foi confirmada uma API aberta estável para as três séries**. Os dados precisam de documento oficial verificado e ingestão por CSV; sem isso, o estado permanece awaiting_documented_data. Fonte: https://www.senamhi.gob.pe/servicios/?p=monitoreo-hidrologico
- Fonte peruana complementar: https://www.dhn.mil.pe/portal/ (MGP Ríos).

## Componentes
- Coletor independente: scripts/crossborder_pilot.py
- Entrada documental: data/crossborder/peru_observations.csv (inicialmente só cabeçalho, **sem medições fabricadas**)
- Saída experimental: docs/data/crossborder_pilot.json
- Testes: tests/test_crossborder_pilot.py
- Workflow: .github/workflows/crossborder_pilot.yml (diário, somente após integração na branch principal; execução manual também disponível).

O coletor não importa nem modifica os artefatos de previsão update_mphi.py, latest.json, forecast_ledger.json, hydrologic_ledger.json, validation.json, score v1.0 ou a versão v2-alpha. Não gera previsões.

## Contrato CSV peruano

Uma linha por observação diária:
station,date,metric,value,unit,datum,source_url,source_reference

- station: pe:tamshiyacu, pe:requena ou pe:san-regis.
- date: AAAA-MM-DD **da observação**, não da publicação.
- metric: stage (cota) ou discharge (vazão).
- unit: cotas m, cm ou m_asl (metros acima do nível do mar); vazão m3/s.
- datum: **obrigatório** para stage, identificando inequivocamente o zero ou referência vertical; vazio para discharge. Se não for conhecido, não importar.
- source_url: HTTPS do SENAMHI, gob.pe ou Marinha do Peru (dhn.mil.pe), com a medição verificável.
- source_reference: número ou identificador auditável do boletim, tabela ou publicação.

O importador rejeita estações desconhecidas, datas futuras, domínios não oficiais, valores inválidos e unidades incompatíveis. Não converte vazão em cota. Não compara níveis absolutos entre réguas com referenciais distintos. A tendência só é calculada para uma série homogênea por intervalos exatos de 3/7 dias.

Medições antigas não são sobrescritas: conflitos são preservados para análise. Se a ANA falhar, os dados anteriores continuam, mas a indisponibilidade é identificada; nenhuma leitura nova é inventada. Leitura com mais de 3 dias recebe estado stale.

## Verificação offline

python -m unittest discover -s tests -p 'test_crossborder_pilot.py' -v

python scripts/crossborder_pilot.py

O workflow testa antes de coletar e só grava o arquivo de saída experimental.

## Gates científicos antes de eventual promoção

1. Obter séries com cobertura temporal suficiente e dados independentes de avaliação.
2. Medir defasagens de 1 a 45 dias usando janelas separadas de treino e teste; excluir vazamento temporal.
3. Estratificar cheia/vazante, separar sazonalidade e influências do remanso.
4. Medir falsos alertas, antecipação de reversões e MAE/bias/RMSE prospectivos em 7/15/30 dias.
5. Exigir melhoria consistente e aprovação humana antes de alterar qualquer previsão operacional.

## Pendências verificáveis
- Conferir por execução real se o endpoint legado ANA ainda responde para Tabatinga; a página pública não prova disponibilidade de dados.
- Solicitar a API nova da ANA e adaptar a integração após obtenção de credenciais.
- Obter acesso autorizado e atualizado às três séries peruanas; até lá a importação é **manual auditável**, não automática.
- Decidir se os indicadores experimentais devem aparecer no painel público somente depois de validação.

# Painel Rio Negro — MPHI v1.1

Site implantável do **Modelo Preditivo Hidrológico Uiara**.

## O que está pronto
- Dashboard responsivo em português.
- Cota, variação, velocidades 3/7/15/30d, drawdown e persistência.
- Score MPHI v1.0 e estados NORMAL / ATENÇÃO / ALTO.
- Projeções condicionais 7/15/30d.
- Referências sazonais.
- Gráfico sem dependências externas.
- Qualidade de dados: leituras inconsistentes não são corrigidas silenciosamente.
- Atualizador Python diário preparado para o Porto de Manaus.
- GitHub Actions às 08:05 de Manaus para atualizar os dados e publicar o site na mesma execução.
- Fallback manual local no navegador.

## Publicação no GitHub Pages
1. Vá a **Settings → Pages**.
2. Em **Build and deployment → Source**, escolha **GitHub Actions**.
3. Vá a **Settings → Actions → General → Workflow permissions** e confirme que o repositório permite ao workflow gravar conteúdo quando necessário. O workflow também declara `contents: write`, `pages: write` e `id-token: write`.
4. Vá a **Actions → Atualizar e publicar MPHI → Run workflow** e execute uma vez.
5. Quando a execução concluir, a URL publicada aparecerá no ambiente `github-pages` / na página de Settings → Pages.

## Funcionamento diário
O workflow agenda uma execução às **12:05 UTC**, equivalente a **08:05 em Manaus (UTC-4)**. Ele:
- consulta a fonte operacional;
- valida a leitura;
- recalcula o MPHI;
- grava `docs/data/latest.json`;
- preserva o último dado válido em caso de falha;
- publica o conteúdo de `/docs` no GitHub Pages.

## Atenção de produção
O fallback manual desta versão é **local ao navegador**, não autenticação real. Para edição remota segura, adote autenticação/backend antes de publicar uma área de manutenção para terceiros.

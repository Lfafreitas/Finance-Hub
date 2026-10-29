# Widget da carteira

Uma janelinha que fica na área de trabalho com, para cada moeda (sem somar
reais e dólares):

- patrimônio total;
- quanto os investimentos renderam desde o início (valor e %);
- variação do último pregão, com os ativos que mais se mexeram;
- linha dos últimos 30 dias do valor dos investimentos;
- as notícias rápidas da análise do dia (clique abre a notícia).

Ele lê o backend local (`127.0.0.1:8000`) a cada minuto e, quando as
cotações têm mais de 15 minutos, pede ao backend para buscar de novo (só os
códigos dos ativos saem do computador, como na tela Análises).

## Abrir

- **Windows:** dois cliques em "Abrir widget" na pasta Dashboard Financeiro
  (ou em `iniciar_widget.bat`, nesta pasta).
- **Linux:** `sh iniciar_widget.sh` (precisa do pacote `python3-tk`).

Se o backend estiver desligado, o widget liga sozinho usando o Python de
`backend\.venv` (o Postgres precisa estar rodando). Nesse caso, rodar o
`uvicorn` à mão dá "porta ocupada": é só porque ele já está ligado.

## Usar

- Arraste com o botão esquerdo para mudar de lugar (a posição é lembrada).
- Botão direito: atualizar, buscar cotações, abrir o dashboard, sempre por
  cima, modo compacto, notícias, opacidade, fechar.
- A bolinha no topo: verde = cotações recentes, amarela = buscando ou sem
  cotação automática, vermelha = backend desligado.

## Abrir junto com o computador

- **Windows:** rode `instalar_inicio_automatico_windows.bat` uma vez
  (desfazer: `remover_inicio_automatico_windows.bat`).
- **Linux:** `sh instalar_inicio_automatico_linux.sh`.

As preferências ficam em `%APPDATA%\carteira-widget\config.json` (Windows)
ou `~/.config/carteira-widget/config.json` (Linux).

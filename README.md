# Loot de Ofertas

MVP de curadoria e divulgação de ofertas gamers com links oficiais de afiliado.

## Painel local

O painel de monitoramento mostra conexão do bot, produtos coletados, fila,
avaliações, histórico de preços, publicações e logs. Inicie com:

```powershell
python -m uvicorn loot_ofertas.webapp:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000/`. No Windows, a tarefa
`LootDeOfertas-Dashboard` mantém o painel disponível após o login.

## O que já funciona

- Cadastro manual ou importação CSV de ofertas Magalu/Shopee.
- Ranking automático por relevância gamer, desconto, cupom e comissão.
- Identidade estável de produto e histórico de preços.
- Fila com intervalo mínimo, limites diários e bloqueio de repetição.
- Publicação em grupo ou canal do Telegram pela Bot API oficial.
- Fila de mensagens e link de compartilhamento para WhatsApp.

O projeto não raspa painéis protegidos e não inventa links de afiliado. O link deve ser gerado no painel oficial da loja. Pelando não está integrado porque a plataforma proíbe autopromoção e pode substituir links enviados pelos links próprios dela.

## Começar

```powershell
python -m loot_ofertas.cli init
python -m loot_ofertas.cli import-csv examples/ofertas.csv
python -m loot_ofertas.cli list
python -m loot_ofertas.cli queue-status
python -m loot_ofertas.cli publish telegram --dry-run
python -m loot_ofertas.cli publish whatsapp
```

Para capturar um anúncio público individual do Mercado Livre, salvar/atualizar
o produto no banco e gerar a mensagem sem enviar:

```powershell
python -m loot_ofertas.cli capture "LINK_DO_PRODUTO_MERCADO_LIVRE"
```

A mensagem fica em `outbox/captured/oferta-ID.txt`. Ao capturar novamente o
mesmo anúncio, o registro é atualizado e o novo preço entra no histórico. O
capturador rejeita outros domínios, páginas sem preço e respostas que não sejam
HTML. Use `--no-message` quando quiser atualizar apenas o banco.

Para adicionar uma oferta individual:

```powershell
python -m loot_ofertas.cli add --title "Mouse Gamer" --url "SEU_LINK_MAGALU" --price 99.90 --original-price 149.90 --commission 4 --store magalu --category "mouse gamer"
```

## Telegram

1. Crie o bot falando com `@BotFather`.
2. Adicione o bot ao grupo/canal e dê permissão para publicar.
3. Copie `.env.example` para `.env` ou defina as variáveis na sessão:

```powershell
$env:TELEGRAM_BOT_TOKEN="token-do-bot"
$env:TELEGRAM_CHAT_ID="@nome_do_canal"
python -m loot_ofertas.cli publish telegram
```

Nunca coloque tokens no Git.

## WhatsApp

A API oficial do WhatsApp Business é destinada a conversas autorizadas e não oferece um bot comum para publicar em grupos. Por segurança e conformidade, o MVP prepara cada mensagem em `outbox/whatsapp` e gera um link `wa.me` para o envio manual ao grupo.

Automação individual pela WhatsApp Business Platform poderá ser adicionada depois que houver conta empresarial, número aprovado, consentimento dos destinatários e modelos de mensagem aprovados.

## Próxima fase

- Conector oficial da Shopee após aprovação.
- Entrada de ofertas a partir de feed/API autorizado das lojas.
- Painel web para aprovar ofertas antes da publicação.
- Agendador com limites por canal e histórico de cliques/vendas.

## Comparação de mercado e promoções reais

O histórico próprio ajuda, mas não veta uma oferta boa. A decisão principal compara
o preço efetivo atual com o mesmo produto em outras lojas confiáveis. O sistema
classifica como `imperdivel`, `excelente`, `promocao`, `promocao_loja`, `potencial_promocao` ou
`preco_comum`. Ofertas não confirmadas não são publicadas automaticamente.

Atualize as ofertas salvas sem publicar:

```powershell
python -m loot_ofertas.cli monitor --limit 10
```

Adicione uma cotação concorrente encontrada em outra loja:

```powershell
python -m loot_ofertas.cli market-add 5 --store Amazon --price 499.90 --url "LINK"
```

Para comparação automatizada pelo Google Shopping, crie uma chave da SerpApi,
salve-a localmente como `SERPAPI_API_KEY` e execute:

```powershell
python -m loot_ofertas.cli monitor --limit 10 --google
```

O Windows pode executar a captura automaticamente a cada 30 minutos pela tarefa
`LootDeOfertas-Monitor`. O monitor apenas atualiza, compara e salva; ele não envia
mensagens.

A SerpApi é opcional e pode ser paga. Sem ela, o portfólio multi-loja e o histórico
continuam funcionando normalmente.

## Captura Magalu

O comando `capture` aceita links públicos do Magalu e do Magazine Você. Quando
`MAGALU_STORE_URL` aponta para sua loja real, links públicos do Magalu são convertidos
para a mesma rota dentro da sua loja de afiliado antes de serem salvos.

```powershell
python -m loot_ofertas.cli capture "LINK_MAGALU"
```

Para percorrer automaticamente as áreas de informática, games, tablets,
celulares e casa inteligente da loja Magazine Você:

```powershell
python -m loot_ofertas.cli discover-magalu --limit 50 --min-discount 10
```

O comando deduplica os produtos, salva o preço no histórico e prepara mensagem
somente quando o desconto da loja ou a comparação de mercado aprovar a oferta.
Games, celulares, tablets e casa inteligente são aceitos integralmente. Na área
de informática, o filtro mantém computadores, hardware, rede, armazenamento,
monitores e periféricos, descartando itens como mochilas, impressoras e toner.
Use `--include-all` para desativar esse filtro em uma execução manual.
Use `--google` apenas em execuções controladas, pois cada produto comparado consome
uma consulta da SerpApi. Se a leitura direta receber CAPTCHA, o capturador tenta o
navegador Python; `MAGALU_BROWSER_HEADLESS=false` permite uma sessão visível local.

## Descoberta Mercado Livre

O buscador usa o endpoint oficial de mais vendidos do Mercado Livre para descobrir
produtos novos em monitores, notebooks, computadores, componentes, armazenamento,
redes, tablets, celulares, consoles e acessórios gamers:

```powershell
python -m loot_ofertas.cli discover-meli --limit 30 --min-discount 10
```

Os itens são lidos pela API oficial, deduplicados e enviados ao mesmo histórico,
comparador e filtro de publicação da Magalu. O monitor do Windows executa as duas
descobertas automaticamente.

## Fila e controle de volume

O envio automático publica no máximo uma oferta por execução. Por padrão, a
fila respeita 20 minutos entre mensagens, funciona das 09:00 às 22:00, limita
15 mensagens por dia e 3 por categoria. Um produto fica bloqueado por 7 dias,
exceto quando o preço cai pelo menos 10% em relação à última publicação.

Confira o estado sem publicar:

```powershell
python -m loot_ofertas.cli queue-status --channel wppconnect
```

As regras podem ser alteradas no `.env`:

```dotenv
LOOT_MIN_INTERVAL_MINUTES=20
LOOT_DAILY_LIMIT=15
LOOT_CATEGORY_DAILY_LIMIT=3
LOOT_START_HOUR=9
LOOT_END_HOUR=22
LOOT_REPEAT_COOLDOWN_DAYS=7
LOOT_REPEAT_PRICE_DROP_PERCENT=10
LOOT_TIMEZONE=America/Sao_Paulo
```

## WPPConnect para grupos

O canal `wppconnect` elimina os cliques por Selenium/PyAutoGUI. Ele usa uma API
local baseada no WhatsApp Web e, portanto, não é uma integração oficial da Meta.
Use somente em grupos próprios e com participantes que aceitaram as ofertas.

1. Instale e inicie o WPPConnect Server pelo projeto oficial:
   https://github.com/wppconnect-team/wppconnect-server
2. Troque a `secretKey` padrão do servidor e gere o token da sessão:

```powershell
Invoke-RestMethod -Method Post "http://localhost:21465/api/loot-ofertas/SUA_CHAVE/generate-token"
```

3. Copie o valor `token` retornado para `WPP_TOKEN` no `.env`.
4. Inicie a sessão e escaneie o PNG gerado em WhatsApp > Aparelhos conectados:

```powershell
python -m loot_ofertas.cli whatsapp-setup
```

5. Confira os grupos e publique primeiro em modo de teste:

```powershell
python -m loot_ofertas.cli whatsapp-setup --list-groups
python -m loot_ofertas.cli publish wppconnect --dry-run
python -m loot_ofertas.cli publish wppconnect
```

Se houver dois grupos com o mesmo nome, copie o ID terminado em `@g.us` para
`WPP_GROUP_ID`. A sessão é persistida pelo servidor e normalmente o QR Code só é
necessário no primeiro login.

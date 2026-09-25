import os
import json
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from supabase import create_client

app = FastAPI()

# Fuso horário de Atibaia/SP (o servidor do Railway usa UTC)
TZ = ZoneInfo("America/Sao_Paulo")

# ─── Configurações ────────────────────────────────────────────────
WHATSAPP_TOKEN      = os.environ["WHATSAPP_TOKEN"]
WHATSAPP_PHONE_ID   = os.environ["WHATSAPP_PHONE_ID"]
VERIFY_TOKEN        = os.environ["VERIFY_TOKEN"]
OPENAI_API_KEY      = os.environ["OPENAI_API_KEY"]
SUPABASE_URL        = os.environ["SUPABASE_URL"]
SUPABASE_KEY        = os.environ["SUPABASE_KEY"]
NTFY_TOPIC          = os.environ["NTFY_TOPIC"]
NUMERO_FORNECEDORES = os.environ["NUMERO_FORNECEDORES"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Tabela de entrega ────────────────────────────────────────────
TABELA_ENTREGA = """
Taxas de entrega:
- Até 3 km: R$ 12,99
- De 3 a 4 km: R$ 14,99
- De 4 a 5 km: R$ 15,99
- De 5 a 6 km: R$ 17,99
- De 6 a 7 km: R$ 25,99
- Acima de 7 km: não realizamos entrega

Formas de pagamento na entrega: dinheiro, Pix ou maquininha do entregador (crédito/débito).
ATENÇÃO: vouchers (Alelo, Ticket, VR, Sodexo) NÃO são aceitos no delivery.
"""

# ─── Cardápio fixo ────────────────────────────────────────────────
CARDAPIO_FIXO = """
=== REFEIÇÕES (Pratos) ===
Todos acompanham arroz, feijão (exceto sábado), salada e opção de acompanhamento.
OBS: Aos SÁBADOS não servimos feijão nem porção de feijão.

CARNES:
- Bife à Milanesa — R$ 46,90
- Bife à Milanesa com Espaguete — R$ 51,90
- Parmegiana de Carne — R$ 52,90
- Parmegiana de Carne com Espaguete — R$ 52,90
- Bife Grelhado Acebolado — R$ 47,90
- Strogonoff de Carne — R$ 45,90
- Picadinho de Carne Acebolado — R$ 44,90

FRANGO:
- Frango à Milanesa — R$ 41,90
- Frango à Milanesa com Espaguete — R$ 46,90
- Frango à Parmegiana — R$ 47,90
- Frango à Parmegiana com Espaguete — R$ 47,90
- Frango Grelhado Acebolado — R$ 42,90
- Frango ao Maracujá — R$ 46,90
- Frango ao Molho de Limão e Gengibre — R$ 44,90
- Strogonoff de Frango — R$ 45,90

BERINGELA:
- Beringela à Milanesa — R$ 41,90
- Beringela à Milanesa com Espaguete — R$ 45,90
- Beringela à Parmegiana — R$ 47,90
- Beringela à Parmegiana com Espaguete — R$ 47,90

TILÁPIAS:
- Tilápia à Milanesa — R$ 47,90
- Tilápia à Milanesa com Espaguete — R$ 52,90
- Tilápia à Parmegiana — R$ 52,90
- Tilápia à Parmegiana com Espaguete — R$ 52,90
- Tilápia Grelhada — R$ 47,90
- Tilápia ao Maracujá — R$ 51,90
- Tilápia ao Molho de Limão e Gengibre — R$ 51,90

MASSAS E RISOTOS:
- Espaguete ao Sugo — R$ 38,90
- Espaguete na Manteiga e Sálvia — R$ 32,90
- Fettuccine ao Brócoli e Cogumelo — R$ 57,90
- Fettuccine ao Brócoli e Tirinhas de Carne — R$ 57,90
- Fettuccine ao Brócoli e Tirinhas de Frango — R$ 57,90
- Risoto de Limão Siciliano com Beringela à Milanesa — R$ 54,90
- Risoto de Limão Siciliano com Tilápia Grelhada — R$ 57,90
- Risoto de Limão Siciliano com Bife de Coração de Alcatra — R$ 64,90

OUTROS:
- Omelete com Arroz, Feijão e Salada — R$ 38,90 (sem feijão aos sábados)
- Feijoada — R$ 49,90 (disponível apenas às QUARTAS e SÁBADOS)
- Feijoada Quente sem Acompanhamentos — R$ 42,90 (quartas e sábados)

=== PORÇÕES ===
- Arroz (porção) — R$ 5,50
- Feijão (porção) — R$ 5,50 (não disponível aos sábados)
- Batata Frita Grande — R$ 18,00
- Batata Frita Pequena — R$ 9,00
- Farofa — R$ 5,50
- Salada Fresca do Dia — R$ 7,90
- Salada Primavera 270g — R$ 35,90
- Porção Creme de Milho — R$ 9,00
- Amendoa Laminada — R$ 3,50
- Queijo Parmesão — R$ 3,50
- Legumes (Cenoura e Abobrinha) — R$ 5,50
- Molho ao Sugo — R$ 7,50
- Ovo Frito — R$ 5,50
- Porção Extra de Couve — R$ 5,50

=== SUCOS (R$ 14,00 cada) ===
- Suco de Laranja
- Suco de Abacaxi
- Suco de Abacaxi com Hortelã
- Suco de Morango
- Limonada Suíça
- Limonada Suíça Adoçada
- Suco de Melancia
- Suco Frutas Vermelhas
- Suco Refrescante
- Suco Hidratante
- Suco Rejuvenecedor
- Suco Antigripal
- Suco Anticolesterol
- Suco Diurético
- Suco Anti-oxidante

Sucos especiais: R$ 16,00 / R$ 18,00
- Suco de Maracujá — R$ 16,00
- Suco Especial — R$ 18,00
- Vitamina (Suco com Leite) — R$ 18,00

=== REFRIGERANTES ===
Lata 350ml: R$ 6,90 (Coca-Cola, Coca Zero, Guaraná Antártica, Sprite, Sprite Zero, Schwepps Citrus, H2OH, Soda Limonada Antarctica, etc.)
- Coca-Cola 600ml — R$ 9,90
- Coca-Cola Zero 600ml — R$ 9,90
- H2OH Limão 500ml — R$ 9,90
- Coca-Cola Mini 220ml lata — R$ 4,40
- Gatorade 500ml — R$ 11,90
- Suco de Uva Garrafa — R$ 33,80
- Água 510ml — R$ 5,00
- Água com Gás — R$ 5,50
- Água de Coco 200ml — R$ 5,50
- Água Tônica Lata 350ml — R$ 6,90
- Limão Espremido — R$ 2,00

=== SORVETES / SOBREMESAS ===
- Picolé Chambinho — R$ 8,50
- Picolé Garoto Bombom — R$ 9,99
- Picolé Garoto Batom — R$ 5,90
- Picolé Garoto Crocante — R$ 15,90
- Picolé Choco Trio — R$ 9,99
- Picolé La Frutta Limão — R$ 7,50
- Picolé Mega Clássico — R$ 17,90
- Picolé Mega Pistache — R$ 18,90
- Picolé KitKat Chocolate — R$ 18,90
- Picolé Laka Oreo — R$ 18,90
- Picolé Lacta Diamante Negro — R$ 18,90
- Picolé Mega Trufa Branco — R$ 18,90
- Picolé Mega Amendoas — R$ 18,90
- Oreo Bits — R$ 21,00
- Chokito Bites — R$ 15,00
- Fini Dentadura — R$ 8,50
- Fini Tubes Morango — R$ 5,90
"""

# ─── Buscar prato da semana no Supabase ──────────────────────────
async def buscar_prato_semana() -> str:
    try:
        hoje = datetime.now(TZ).date()
        res = supabase.table("cardapio_semana").select("*").lte("data_inicio", str(hoje)).gte("data_fim", str(hoje)).execute()
        if res.data:
            pratos = [f"- {p['nome']} — R$ {p['preco']:.2f}" for p in res.data]
            return "PRATO(S) DA SEMANA:\n" + "\n".join(pratos)
    except Exception as e:
        print(f"Erro ao buscar prato da semana: {e}")
    return "PRATO DA SEMANA: Consulte com a equipe pelo número (11) 2427-3528"

# ─── Horário de funcionamento ─────────────────────────────────────
HORARIO = "Segunda a Sábado, das 11h às 15h15."

# ─── System prompt da Zara ────────────────────────────────────────
def montar_system_prompt(nome_cliente: str, prato_semana: str) -> str:
    agora = datetime.now(TZ)
    hora_atual = agora.strftime("%H:%M")
    dia_semana_num = agora.weekday()  # 0=segunda, 5=sábado, 6=domingo
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dia_semana = dias[dia_semana_num]
    eh_sabado = dia_semana_num == 5
    eh_quarta = dia_semana_num == 2
    dentro_horario = (
        dia_semana_num < 6 and
        agora.hour >= 11 and
        (agora.hour < 15 or (agora.hour == 15 and agora.minute <= 15))
    )

    status_cozinha = (
        "A cozinha está ABERTA agora."
        if dentro_horario
        else f"A cozinha está FECHADA agora (são {hora_atual} de {dia_semana}). "
             f"Informe o cliente que pode fazer o pedido para o próximo período de funcionamento "
             f"({HORARIO}) e registre normalmente."
    )

    aviso_feijao = ""
    if eh_sabado:
        aviso_feijao = "\n⚠️ HOJE É SÁBADO: Não servimos feijão nem porção de feijão. Não ofereça esses itens."

    aviso_feijoada = ""
    if not (eh_quarta or eh_sabado):
        aviso_feijoada = "\n⚠️ FEIJOADA: Hoje NÃO temos feijoada. Disponível apenas às quartas e sábados."

    return f"""Você é Zara, atendente do Afrika Restaurante em Atibaia-SP.
Seu atendimento deve ser caloroso, natural e parecer humano — use linguagem descontraída,
pode usar "tá", "ótimo", "perfeito", emojis com moderação. Nunca diga que é um robô ou IA.
Se alguém perguntar diretamente se você é humano ou IA, diga que é a atendente digital do Afrika.

CLIENTE: {nome_cliente if nome_cliente else "cliente"}
HOJE: {dia_semana}, {hora_atual}
STATUS: {status_cozinha}{aviso_feijao}{aviso_feijoada}

=== CARDÁPIO ===
{prato_semana}

{CARDAPIO_FIXO}

=== ENTREGA ===
{TABELA_ENTREGA}

=== REGRAS IMPORTANTES ===
1. Quando o cliente entrar em contato pela primeira vez, cumprimente e apresente as opções:
   - Pedir pelo MenuDino (site/app): afrikacafe.com.br
   - Pedir aqui pelo WhatsApp (você anota e repassa para a equipe)
   - Ligar: (11) 2427-3528

2. Se o cliente escolher pedir pelo WhatsApp, colete:
   - Tipo: DELIVERY, RETIRADA ou SALÃO (pedido adiantado para comer no local)
   - Nome do cliente (se ainda não souber)
   - Para DELIVERY: endereço completo e forma de pagamento (lembrar que voucher não é aceito)
   - Para RETIRADA: horário que vai buscar
   - Para SALÃO: horário de chegada. IMPORTANTE: o Afrika NÃO reserva mesa. Diga que o prato
     fica pronto no horário combinado — nunca fale em "mesa reservada".
   - Itens com todas as personalizações (molho à parte, sem cebola, sem salada, suco coado, etc.)

3. Antes de finalizar, SEMPRE confirme com o cliente o pedido completo com o preço de cada item
   e o TOTAL DOS ITENS (use os preços do cardápio). Para DELIVERY: NUNCA calcule nem chute a taxa
   de entrega, porque você não sabe a distância. Diga que a taxa (entre R$ 12,99 e R$ 25,99,
   conforme a distância) será confirmada pela equipe em seguida. Peça o bairro e um ponto de
   referência, nunca pergunte "de onde você está ligando".

4. Se perceber que é fornecedor ou assunto comercial:
   "Para assuntos com nosso setor de compras, o contato é {NUMERO_FORNECEDORES} 😊"

5. Se o cliente pedir atendimento humano:
   "Claro! Pode ligar aqui mesmo pelo WhatsApp ou no (11) 2427-3528 que alguém te atende 😊"

6. SOMENTE quando o cliente confirmar o pedido, responda com "Pedido anotado! Vou repassar para
   a equipe agora 😊" e, NO FINAL da mesma mensagem, inclua EXATAMENTE este bloco (o cliente não
   verá esse bloco, ele vai só para a cozinha):

[RESUMO]
TIPO: SALÃO ou RETIRADA ou DELIVERY
HORARIO: horário combinado (ou "o quanto antes")
NOME: nome do cliente
ITENS:
1x Nome do Prato (personalizações) — R$ 00,00
TOTAL ITENS: R$ 00,00
TAXA ENTREGA: a confirmar (só para delivery; senão "-")
PAGAMENTO: forma de pagamento (ou "no local")
ENDERECO: endereço completo (só para delivery; senão "-")
OBS: observações extras (ou "-")
[/RESUMO]

   Sempre feche o bloco com [/RESUMO]. Nunca escreva nada depois de [/RESUMO]. Nunca inclua o
   bloco antes de o cliente confirmar, e nunca o inclua duas vezes para o mesmo pedido.
"""

# ─── Histórico de conversas (em memória) ─────────────────────────
conversas: dict[str, list] = {}

# ─── Buscar cliente no Supabase ──────────────────────────────────
def buscar_cliente(telefone: str) -> dict | None:
    try:
        numero_limpo = telefone.replace("55", "", 1) if telefone.startswith("55") else telefone
        res = supabase.table("clientes").select("*").eq("celular", numero_limpo).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"Erro ao buscar cliente: {e}")
    return None

def salvar_pedido(telefone: str, nome_cliente: str, historico: str):
    try:
        supabase.table("pedidos_whatsapp").insert({
            "telefone": telefone,
            "nome_cliente": nome_cliente,
            "pedido": historico,
            "criado_em": datetime.now(TZ).isoformat(),
            "status": "aguardando"
        }).execute()
    except Exception as e:
        print(f"Erro ao salvar pedido: {e}")

# ─── Notificar equipe via Ntfy ────────────────────────────────────
async def notificar_equipe(mensagem: str, titulo: str = "🍽️ Novo Pedido - Afrika"):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                content=mensagem.encode("utf-8"),
                headers={
                    "Title": titulo.encode("utf-8"),
                    "Priority": "high",
                    "Tags": "fork_and_knife"
                }
            )
    except Exception as e:
        print(f"Erro ao notificar: {e}")

# ─── Corrigir 9º dígito de celulares brasileiros ─────────────────
# A Meta às vezes entrega o número sem o 9 (ex.: 55 11 8765-4321).
# Para responder, o número precisa estar com o 9 (55 11 98765-4321).
def normalizar_telefone(telefone: str) -> str:
    numero = "".join(c for c in telefone if c.isdigit())
    if numero.startswith("55") and len(numero) == 12 and numero[4] in "6789":
        numero = numero[:4] + "9" + numero[4:]
    return numero

# ─── Enviar mensagem WhatsApp ─────────────────────────────────────
async def enviar_mensagem(telefone: str, texto: str):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "text",
        "text": {"body": texto}
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            print(f"Erro ao enviar mensagem: {r.text}")

# ─── Chamar ChatGPT ───────────────────────────────────────────────
async def chamar_chatgpt(telefone: str, mensagem_usuario: str, nome_cliente: str) -> str:
    prato_semana = await buscar_prato_semana()

    if telefone not in conversas:
        conversas[telefone] = []

    conversas[telefone].append({"role": "user", "content": mensagem_usuario})
    historico = conversas[telefone][-20:]

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": montar_system_prompt(nome_cliente, prato_semana)},
            *historico
        ],
        "temperature": 0.7,
        "max_tokens": 600
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            timeout=30
        )
        data = r.json()
        resposta = data["choices"][0]["message"]["content"]

    # Detecta pedido finalizado pelo bloco [RESUMO]...[/RESUMO]
    resumo = None
    if "[RESUMO]" in resposta:
        inicio = resposta.index("[RESUMO]")
        fim = resposta.find("[/RESUMO]", inicio)
        if fim != -1:
            resumo = resposta[inicio + len("[RESUMO]"):fim].strip()
            depois = resposta[fim + len("[/RESUMO]"):]
        else:
            # Sem [/RESUMO]: o resumo termina na linha "OBS:"
            linhas = resposta[inicio + len("[RESUMO]"):].strip().splitlines()
            corte = next((i for i, l in enumerate(linhas) if l.strip().upper().startswith("OBS")), len(linhas) - 1)
            resumo = "\n".join(linhas[:corte + 1]).strip()
            depois = "\n".join(linhas[corte + 1:])
        resposta = (resposta[:inicio].strip() + "\n\n" + depois.strip()).strip()

    conversas[telefone].append({"role": "assistant", "content": resposta + ("\n(pedido registrado)" if resumo else "")})

    if resumo:
        campos = {}
        for linha in resumo.splitlines():
            if ":" in linha:
                chave, valor = linha.split(":", 1)
                campos[chave.strip().upper()] = valor.strip()
        tipo    = campos.get("TIPO", "PEDIDO")
        horario = campos.get("HORARIO", "")
        nome    = campos.get("NOME") or nome_cliente or telefone
        titulo  = f"🍽️ {tipo} — {horario} — {nome}"
        await notificar_equipe(f"{resumo}\n\nTelefone: {telefone}", titulo=titulo)
        salvar_pedido(telefone, nome, resumo)

    return resposta

# ─── Webhook GET (verificação da Meta) ───────────────────────────
@app.get("/webhook")
async def verificar_webhook(request: Request):
    params = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)

# ─── Webhook POST (mensagens recebidas) ──────────────────────────
@app.post("/webhook")
async def receber_mensagem(request: Request):
    body = await request.json()
    try:
        entry   = body["entry"][0]
        changes = entry["changes"][0]
        value   = changes["value"]

        if "statuses" in value:
            return {"status": "ok"}

        mensagens = value.get("messages", [])
        if not mensagens:
            return {"status": "ok"}

        msg      = mensagens[0]
        telefone = normalizar_telefone(msg["from"])
        tipo     = msg.get("type", "")

        if tipo != "text":
            await enviar_mensagem(
                telefone,
                "Olá! Por enquanto só consigo ler mensagens de texto. Pode me escrever o que precisa? 😊"
            )
            return {"status": "ok"}

        texto_recebido = msg["text"]["body"]
        cliente = buscar_cliente(telefone)
        nome_cliente = cliente["nome"] if cliente else ""

        resposta = await chamar_chatgpt(telefone, texto_recebido, nome_cliente)
        await enviar_mensagem(telefone, resposta)

    except Exception as e:
        print(f"Erro no webhook: {e}")

    return {"status": "ok"}

# ─── Health check ─────────────────────────────────────────────────
@app.get("/")
async def health():
    return {"status": "Zara online 🌍", "hora": datetime.now(TZ).strftime("%H:%M")}

# ─── Política de privacidade (exigida pela Meta) ─────────────────
POLITICA_PRIVACIDADE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Política de Privacidade — Afrika Restaurante</title>
<style>
  body { font-family: Arial, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; line-height: 1.6; color: #222; }
  h1 { font-size: 1.6em; } h2 { font-size: 1.15em; margin-top: 1.6em; }
</style>
</head>
<body>
<h1>Política de Privacidade — Afrika Restaurante</h1>
<p>Esta política explica como o Afrika Restaurante (Rua José Bim, 122, Centro, Atibaia-SP) trata os dados
de quem conversa com nosso atendimento pelo WhatsApp, em conformidade com a Lei Geral de Proteção de Dados (Lei nº 13.709/2018).</p>

<h2>1. Dados que coletamos</h2>
<p>Número de telefone do WhatsApp, nome (quando informado ou já cadastrado), conteúdo das mensagens trocadas
e informações do pedido, como itens, endereço de entrega, horário e forma de pagamento.</p>

<h2>2. Para que usamos</h2>
<p>Exclusivamente para responder suas dúvidas, registrar e preparar seus pedidos, realizar entregas
e melhorar nosso atendimento. Não enviamos propaganda sem sua autorização.</p>

<h2>3. Com quem compartilhamos</h2>
<p>Os dados são processados por serviços necessários ao funcionamento do atendimento: Meta (WhatsApp),
OpenAI (geração das respostas do atendimento digital), Supabase (armazenamento dos pedidos) e o serviço
de entrega quando o pedido é delivery. Não vendemos nem cedemos seus dados a terceiros para outros fins.</p>

<h2>4. Por quanto tempo guardamos</h2>
<p>Pelo tempo necessário para atender o pedido e cumprir obrigações legais e fiscais.</p>

<h2>5. Seus direitos</h2>
<p>Você pode pedir a qualquer momento acesso, correção ou exclusão dos seus dados, ou deixar de receber
mensagens, entrando em contato pelo telefone ou WhatsApp (11) 2427-3528.</p>

<h2>6. Alterações</h2>
<p>Esta política pode ser atualizada. A versão vigente estará sempre disponível neste endereço.</p>

<p><em>Última atualização: setembro de 2026.</em></p>
</body>
</html>"""

@app.get("/privacidade", response_class=HTMLResponse)
async def privacidade():
    return POLITICA_PRIVACIDADE

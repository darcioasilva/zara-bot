import os
import json
import hmac
import hashlib
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, Response
from supabase import create_client

app = FastAPI()

# ─── Configurações ────────────────────────────────────────────────
WHATSAPP_TOKEN        = os.environ["WHATSAPP_TOKEN"]          # Token da Meta
WHATSAPP_PHONE_ID     = os.environ["WHATSAPP_PHONE_ID"]       # Phone Number ID da Meta
VERIFY_TOKEN          = os.environ["VERIFY_TOKEN"]            # Token que você inventar para o webhook
OPENAI_API_KEY        = os.environ["OPENAI_API_KEY"]          # Chave da OpenAI
SUPABASE_URL          = os.environ["SUPABASE_URL"]
SUPABASE_KEY          = os.environ["SUPABASE_KEY"]
NTFY_TOPIC            = os.environ["NTFY_TOPIC"]              # Ex: "afrika-pedidos"
NUMERO_FORNECEDORES   = os.environ["NUMERO_FORNECEDORES"]     # Ex: "5511999999999"
APP_SECRET            = os.environ.get("APP_SECRET", "")      # App Secret da Meta (opcional mas recomendado)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Cardápio ─────────────────────────────────────────────────────
CARDAPIO_FIXO = """
ACOMPANHAMENTOS (sempre disponíveis):
- Arroz branco
- Feijão carioca
- Feijão preto
- Macarrão alho e óleo
- Purê de batata
- Farofa
- Salada verde (alface, tomate, pepino)
- Salada de beterraba
- Salada de cenoura

BEBIDAS:
- Suco de laranja (coado ou com polpa) - R$ 8,00
- Suco de limão - R$ 7,00
- Suco de maracujá - R$ 7,00
- Refrigerante lata (Coca, Guaraná, Sprite) - R$ 6,00
- Água mineral (com ou sem gás) - R$ 4,00

SOBREMESAS:
- Pudim - R$ 8,00
- Mousse de maracujá - R$ 8,00
- Arroz doce - R$ 6,00

PRATO EXECUTIVO inclui: prato principal + 2 acompanhamentos à escolha + salada
Preço do executivo: R$ 35,00 (*** SUBSTITUIR PELO VALOR REAL ***)
"""

# Prato da semana — atualizar toda semana via variável de ambiente ou banco
PRATO_DA_SEMANA = os.environ.get("PRATO_DA_SEMANA", "Frango ao Creme de Milho")

# ─── Tabela de entrega ────────────────────────────────────────────
TABELA_ENTREGA = """
Taxas de entrega (*** SUBSTITUIR PELOS VALORES REAIS ***):
- Até 2 km: R$ 5,00
- De 2 a 4 km: R$ 8,00
- De 4 a 6 km: R$ 12,00
- Acima de 6 km: não realizamos entrega

Pagamento na entrega: dinheiro, Pix ou maquininha (crédito/débito).
ATENÇÃO: vouchers (Alelo, Ticket, VR, Sodexo) NÃO são aceitos no delivery.
O entregador usa a maquininha do iFood.
"""

# ─── Horário de funcionamento ─────────────────────────────────────
HORARIO = "Segunda a Sábado, das 11h00 às 15h15."

# ─── System prompt da Zara ────────────────────────────────────────
def montar_system_prompt(nome_cliente: str) -> str:
    agora = datetime.now()
    hora_atual = agora.strftime("%H:%M")
    dia_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"][agora.weekday()]
    dentro_horario = (
        agora.weekday() < 6 and
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

    return f"""Você é Zara, atendente do Afrika Restaurante em Atibaia-SP.
Seu atendimento deve ser caloroso, natural e parecer humano — use linguagem descontraída,
pode usar "tá", "ótimo", "perfeito", emojis com moderação. Nunca diga que é um robô ou IA.

CLIENTE: {nome_cliente if nome_cliente else "cliente"}
HOJE: {dia_semana}, {hora_atual}
STATUS DA COZINHA: {status_cozinha}

=== CARDÁPIO ===
PRATO PRINCIPAL DA SEMANA: {PRATO_DA_SEMANA}
{CARDAPIO_FIXO}

=== ENTREGA ===
{TABELA_ENTREGA}

=== REGRAS IMPORTANTES ===
1. Quando o cliente entrar em contato, cumprimente e apresente as 3 opções:
   a) Pedir pelo MenuDino: https://menudino.com/afrika (*** SUBSTITUIR PELO LINK REAL ***)
   b) Pedir aqui pelo WhatsApp (você anota e repassa para a equipe)
   c) Ligar: (11) 2427-3528

2. Se o cliente escolher pedir pelo WhatsApp, colete:
   - Tipo de pedido: DELIVERY, RETIRADA ou SALÃO (adiantado)
   - Para DELIVERY: endereço completo, forma de pagamento (lembrar que voucher não é aceito)
   - Para RETIRADA: horário que vai buscar
   - Para SALÃO: horário de chegada e nome para a mesa
   - Itens do pedido com todas as personalizações (molho à parte, sem cebola, etc.)
   - Sempre confirme o pedido completo antes de finalizar

3. Se identificar que a pessoa é fornecedor ou fala sobre entregas de mercadoria,
   redirecione gentilmente: "Para assuntos com nosso setor de compras, o contato é {NUMERO_FORNECEDORES} 😊"

4. Se o cliente pedir atendimento humano, diga:
   "Claro! Você pode ligar aqui mesmo pelo WhatsApp ou no (11) 2427-3528 que alguém te atende 😊"

5. Registre TODAS as personalizações de pedido (molho à parte, suco coado, sem cebola, etc.)

6. Seja natural — um pequeno delay de resposta é normal, não precisa ser instantânea.
"""

# ─── Histórico de conversas (em memória) ─────────────────────────
conversas: dict[str, list] = {}

# ─── Buscar/criar cliente no Supabase ────────────────────────────
def buscar_cliente(telefone: str) -> dict | None:
    try:
        # Remove o código do país para buscar no Consumer (que salva só com DDD)
        numero_limpo = telefone.replace("55", "", 1) if telefone.startswith("55") else telefone
        res = supabase.table("clientes").select("*").eq("celular", numero_limpo).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"Erro ao buscar cliente: {e}")
    return None

def salvar_pedido(telefone: str, nome_cliente: str, pedido: dict):
    try:
        supabase.table("pedidos_whatsapp").insert({
            "telefone": telefone,
            "nome_cliente": nome_cliente,
            "pedido": json.dumps(pedido, ensure_ascii=False),
            "criado_em": datetime.now().isoformat(),
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
    if telefone not in conversas:
        conversas[telefone] = []

    conversas[telefone].append({"role": "user", "content": mensagem_usuario})

    # Limita histórico a 20 mensagens para economizar tokens
    historico = conversas[telefone][-20:]

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": montar_system_prompt(nome_cliente)},
            *historico
        ],
        "temperature": 0.7,
        "max_tokens": 500
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

    conversas[telefone].append({"role": "assistant", "content": resposta})

    # Verifica se a resposta indica que um pedido foi finalizado
    palavras_pedido = ["pedido anotado", "pedido registrado", "vou repassar", "anotei seu pedido"]
    if any(p in resposta.lower() for p in palavras_pedido):
        historico_texto = "\n".join([
            f"{'Cliente' if m['role'] == 'user' else 'Zara'}: {m['content']}"
            for m in conversas[telefone][-10:]
        ])
        await notificar_equipe(
            f"Cliente: {nome_cliente}\nTelefone: {telefone}\n\n{historico_texto}",
            titulo=f"🍽️ Pedido de {nome_cliente}"
        )
        salvar_pedido(telefone, nome_cliente, {"historico": historico_texto})

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
        entry    = body["entry"][0]
        changes  = entry["changes"][0]
        value    = changes["value"]

        # Ignora status de entrega (delivered, read, etc.)
        if "statuses" in value:
            return {"status": "ok"}

        mensagens = value.get("messages", [])
        if not mensagens:
            return {"status": "ok"}

        msg      = mensagens[0]
        telefone = msg["from"]
        tipo     = msg.get("type", "")

        # Só processa texto por enquanto
        if tipo != "text":
            await enviar_mensagem(
                telefone,
                "Olá! Por enquanto só consigo ler mensagens de texto. "
                "Pode me escrever o que precisa? 😊"
            )
            return {"status": "ok"}

        texto_recebido = msg["text"]["body"]

        # Busca nome do cliente no Supabase
        cliente = buscar_cliente(telefone)
        nome_cliente = cliente["nome"] if cliente else ""

        # Chama a Zara (ChatGPT)
        resposta = await chamar_chatgpt(telefone, texto_recebido, nome_cliente)

        # Envia resposta
        await enviar_mensagem(telefone, resposta)

    except Exception as e:
        print(f"Erro no webhook: {e}")

    return {"status": "ok"}

# ─── Health check ─────────────────────────────────────────────────
@app.get("/")
async def health():
    return {"status": "Zara online 🌍"}


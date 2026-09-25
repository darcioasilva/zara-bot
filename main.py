import os
import json
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import re
from supabase import create_client

app = FastAPI()

# Fuso horário de Atibaia/SP (o servidor do Railway usa UTC)
TZ = ZoneInfo("America/Sao_Paulo")

# ─── Fotos dos pratos (pasta "fotos" no repositório) ─────────────
URL_PUBLICA = os.environ.get("URL_PUBLICA", "https://web-production-069775.up.railway.app").rstrip("/")
FOTOS: dict[str, str] = {}
if os.path.isdir("fotos"):
    app.mount("/fotos", StaticFiles(directory="fotos"), name="fotos")
    try:
        with open("fotos/fotos.json", encoding="utf-8") as f:
            FOTOS = json.load(f)
    except Exception as e:
        print(f"Erro ao ler fotos.json: {e}")
LISTA_FOTOS = "\n".join(f"{cod} = {nome}" for cod, nome in FOTOS.items())

# ─── Configurações ────────────────────────────────────────────────
WHATSAPP_TOKEN      = os.environ["WHATSAPP_TOKEN"]
WHATSAPP_PHONE_ID   = os.environ["WHATSAPP_PHONE_ID"]
VERIFY_TOKEN        = os.environ["VERIFY_TOKEN"]
OPENAI_API_KEY      = os.environ["OPENAI_API_KEY"]
SUPABASE_URL        = os.environ["SUPABASE_URL"]
SUPABASE_KEY        = os.environ["SUPABASE_KEY"]
NTFY_TOPIC          = os.environ["NTFY_TOPIC"]
NUMERO_FORNECEDORES = os.environ["NUMERO_FORNECEDORES"]
# Números autorizados a mandar comandos (#acabou, #voltou, #esgotados), separados por vírgula
ADMIN_NUMEROS = {normal for normal in ("".join(c for c in n if c.isdigit()) for n in os.environ.get("ADMIN_NUMEROS", "").split(",")) if normal}

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
Todos os pratos acompanham SOMENTE arroz, feijão (exceto sábado) e salada.
Qualquer outro acompanhamento (batata frita, farofa, legumes, purê, ovo, creme de milho etc.)
é cobrado à parte, pelo preço da porção (veja PORÇÕES). As versões "com espaguete" já têm
preço próprio na lista.
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
- Batata Frita Pequena — R$ 9,00 avulsa | R$ 5,00 quando pedida JUNTO com um prato (preço promocional, 1 por prato)
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
    """Pratos da semana (seg-sex) e cardápio de sexta/sábado, de hoje até os próximos 7 dias."""
    try:
        from datetime import timedelta
        hoje = datetime.now(TZ).date()
        limite = hoje + timedelta(days=7)
        res = (supabase.table("cardapio_semana").select("*")
               .gte("data_fim", str(hoje)).lte("data_inicio", str(limite))
               .order("data_inicio").execute())
        if res.data:
            hoje_l, prox_l = [], []
            for p in res.data:
                ini = datetime.fromisoformat(str(p["data_inicio"])).date()
                fim = datetime.fromisoformat(str(p["data_fim"])).date()
                rotulo = "Cardápio de SEXTA/SÁBADO" if p.get("tipo") == "sexta_sabado" else "Prato da semana"
                linha = (f"- [{rotulo}] {p['nome']}"
                         + (f" ({p['descricao']})" if p.get("descricao") else "")
                         + f" — R$ {float(p['preco']):.2f}".replace(".", ",")
                         + f" — válido de {ini:%d/%m} a {fim:%d/%m}"
                         + (f" — código da foto: {p['foto_codigo']}" if p.get("foto_codigo") else ""))
                (hoje_l if ini <= hoje <= fim else prox_l).append(linha)
            texto = "PRATOS ESPECIAIS DISPONÍVEIS HOJE:\n" + ("\n".join(hoje_l) if hoje_l else "- nenhum hoje")
            if prox_l:
                texto += ("\n\nPRÓXIMOS PRATOS ESPECIAIS (só aceite pedido para as datas indicadas):\n"
                          + "\n".join(prox_l))
            return texto
    except Exception as e:
        print(f"Erro ao buscar prato da semana: {e}")
    return "PRATO DA SEMANA: Consulte com a equipe pelo número (11) 2427-3528"

# ─── Distância e taxa de entrega (Google Maps) ────────────────────
GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_KEY", "")
ENDERECO_RESTAURANTE = "Rua José Bim, 122, Centro, Atibaia - SP, Brasil"
FAIXAS_TAXA = [(3, 12.99), (4, 14.99), (5, 15.99), (6, 17.99), (7, 25.99)]  # (até km, taxa)
_cache_coord: dict[str, tuple] = {}

async def geocodificar(endereco: str):
    """Endereço -> (lat, lng, endereço formatado) ou None."""
    if endereco in _cache_coord:
        return _cache_coord[endereco]
    texto = endereco if "atibaia" in endereco.lower() else f"{endereco}, Atibaia - SP"
    async with httpx.AsyncClient() as client:
        r = await client.get("https://maps.googleapis.com/maps/api/geocode/json",
                             params={"address": texto, "key": GOOGLE_MAPS_KEY,
                                     "region": "br", "language": "pt-BR", "components": "country:BR"},
                             timeout=15)
    dados = r.json()
    if dados.get("status") != "OK" or not dados.get("results"):
        print(f"Geocoding sem resultado ({dados.get('status')}): {texto} {dados.get('error_message', '')}")
        return None
    res = dados["results"][0]
    # endereço vago demais (só cidade/bairro) não serve para calcular taxa
    tipos = set(res.get("types", []))
    if tipos & {"locality", "administrative_area_level_2", "administrative_area_level_1", "country"}:
        return None
    loc = res["geometry"]["location"]
    valor = (loc["lat"], loc["lng"], res.get("formatted_address", texto))
    _cache_coord[endereco] = valor
    return valor

async def calcular_taxa_entrega(endereco: str) -> dict:
    """Calcula a distância de carro do restaurante até o endereço e a taxa pela tabela."""
    if not GOOGLE_MAPS_KEY:
        return {"ok": False, "motivo": "cálculo indisponível; a equipe confirma a taxa"}
    try:
        origem = await geocodificar(ENDERECO_RESTAURANTE)
        destino = await geocodificar(endereco)
        if not origem or not destino:
            return {"ok": False, "motivo": "endereço não encontrado ou incompleto; peça rua, número e bairro"}
        corpo = {
            "origin": {"location": {"latLng": {"latitude": origem[0], "longitude": origem[1]}}},
            "destination": {"location": {"latLng": {"latitude": destino[0], "longitude": destino[1]}}},
            "travelMode": "DRIVE",
        }
        async with httpx.AsyncClient() as client:
            r = await client.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=corpo,
                                  headers={"X-Goog-Api-Key": GOOGLE_MAPS_KEY,
                                           "X-Goog-FieldMask": "routes.distanceMeters"}, timeout=15)
        rotas = r.json().get("routes") or []
        if not rotas:
            print(f"Routes sem resultado: {r.text[:300]}")
            return {"ok": False, "motivo": "não consegui calcular a rota; a equipe confirma a taxa"}
        km = rotas[0]["distanceMeters"] / 1000
        taxa = next((t for limite, t in FAIXAS_TAXA if km <= limite), None)
        base = {"endereco_encontrado": destino[2], "distancia_km": round(km, 1)}
        if taxa is None:
            return {"ok": True, "entrega": False, **base, "mensagem": "acima de 7 km: não realizamos entrega"}
        return {"ok": True, "entrega": True, **base, "taxa": f"R$ {taxa:.2f}".replace(".", ",")}
    except Exception as e:
        print(f"Erro ao calcular taxa: {e}")
        return {"ok": False, "motivo": "erro no cálculo; a equipe confirma a taxa"}

FERRAMENTA_PEDIDO = {
    "type": "function",
    "function": {
        "name": "registrar_pedido",
        "description": "Registra o pedido e avisa a cozinha. OBRIGATÓRIO chamar assim que o cliente confirmar "
                       "o pedido (ex.: 'sim', 'pode ser', 'ok', 'confirmo'). Sem esta chamada o pedido NÃO chega "
                       "à equipe. Chame uma única vez por pedido.",
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["SALÃO", "RETIRADA", "DELIVERY"]},
                "horario": {"type": "string", "description": "horário combinado ou 'o quanto antes'"},
                "nome": {"type": "string"},
                "itens": {"type": "array", "items": {"type": "string"},
                          "description": "um por linha: '1x Nome do Prato (personalizações) — R$ 00,00'"},
                "total_itens": {"type": "string", "description": "R$ 00,00"},
                "taxa_entrega": {"type": "string", "description": "valor calculado, 'a confirmar' ou '-'"},
                "distancia": {"type": "string", "description": "km ou '-'"},
                "total_com_entrega": {"type": "string", "description": "R$ 00,00 ou '-'"},
                "pagamento": {"type": "string"},
                "endereco": {"type": "string", "description": "só delivery; senão '-'"},
                "obs": {"type": "string"},
            },
            "required": ["tipo", "horario", "nome", "itens", "total_itens", "pagamento"],
        },
    },
}

FERRAMENTAS = [FERRAMENTA_PEDIDO, {
    "type": "function",
    "function": {
        "name": "calcular_taxa_entrega",
        "description": "Calcula a distância de carro do Afrika até o endereço do cliente e a taxa de entrega. "
                       "Use sempre que o cliente quiser DELIVERY e você tiver o endereço (rua, número e bairro).",
        "parameters": {
            "type": "object",
            "properties": {"endereco": {"type": "string", "description": "Rua, número, bairro (e cidade, se não for Atibaia)"}},
            "required": ["endereco"],
        },
    },
}]

# ─── Itens esgotados no dia ───────────────────────────────────────
def listar_esgotados() -> list[str]:
    try:
        hoje = str(datetime.now(TZ).date())
        res = supabase.table("esgotados").select("item").eq("data", hoje).execute()
        return [r["item"] for r in (res.data or [])]
    except Exception as e:
        print(f"Erro ao listar esgotados: {e}")
        return []

def eh_admin(telefone: str) -> bool:
    t = telefone[2:] if telefone.startswith("55") else telefone
    return any(a == telefone or a == t or a[2:] == t for a in ADMIN_NUMEROS)

async def tratar_comando(telefone: str, texto: str) -> str:
    """Comandos da equipe: #acabou <item>, #voltou <item>, #esgotados"""
    hoje = str(datetime.now(TZ).date())
    partes = texto.strip()[1:].split(None, 1)
    cmd = partes[0].lower() if partes else ""
    item = partes[1].strip() if len(partes) > 1 else ""
    try:
        if cmd in ("acabou", "esgotou") and item:
            supabase.table("esgotados").insert({"item": item, "data": hoje, "criado_por": telefone}).execute()
            return f"✅ Anotado: *{item}* esgotado hoje. A Zara não vai mais oferecer."
        if cmd in ("voltou", "tem") and item:
            atuais = supabase.table("esgotados").select("id,item").eq("data", hoje).execute().data or []
            removidos = [r for r in atuais if item.lower() in r["item"].lower() or r["item"].lower() in item.lower()]
            for r in removidos:
                supabase.table("esgotados").delete().eq("id", r["id"]).execute()
            if removidos:
                return "✅ Voltou ao cardápio: " + ", ".join(r["item"] for r in removidos)
            return f"Não encontrei *{item}* na lista de esgotados de hoje."
        if cmd in ("esgotados", "lista"):
            lista = listar_esgotados()
            return ("Esgotados hoje: " + ", ".join(lista)) if lista else "Nada esgotado hoje. 👍"
    except Exception as e:
        print(f"Erro no comando: {e}")
        return "Deu erro ao registrar o comando. Tente de novo."
    return "Comandos: #acabou <item> · #voltou <item> · #esgotados"

# ─── Horário de funcionamento ─────────────────────────────────────
HORARIO = "Segunda a Sábado, das 11h às 15h15."

# ─── System prompt da Zara ────────────────────────────────────────
def montar_system_prompt(nome_cliente: str, prato_semana: str, endereco: str = "") -> str:
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

    esgotados = listar_esgotados()
    aviso_esgotados = ""
    if esgotados:
        aviso_esgotados = ("\n⚠️ ESGOTADOS HOJE (não ofereça, não aceite pedido e não mande foto; se o cliente pedir, "
                           "diga com gentileza que acabou hoje e sugira outra opção): " + ", ".join(esgotados))

    return f"""Você é Zara, atendente do Afrika Restaurante em Atibaia-SP.
Seu atendimento deve ser caloroso, natural e parecer humano — use linguagem descontraída,
pode usar "tá", "ótimo", "perfeito", emojis com moderação. Nunca diga que é um robô ou IA.
Se alguém perguntar diretamente se você é humano ou IA, diga que é a atendente digital do Afrika.

CLIENTE: {nome_cliente if nome_cliente else "cliente"}
{("CLIENTE JÁ CADASTRADO: o nome dele é " + nome_cliente + ". Cumprimente pelo nome e NUNCA pergunte o nome.") if nome_cliente else "Cliente novo: pergunte o nome antes de fechar o pedido."}
{("ENDEREÇO CADASTRADO: " + endereco + ". Em pedido de DELIVERY, NÃO peça o endereço de novo: pergunte se é para entregar nesse endereço. Não fale o endereço antes de o cliente escolher delivery.") if endereco else ""}
HOJE: {dia_semana}, {hora_atual}
STATUS: {status_cozinha}{aviso_feijao}{aviso_feijoada}{aviso_esgotados}

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
   - Nome do cliente (SOMENTE se o cliente não estiver cadastrado — veja acima)
   - Para DELIVERY: endereço completo e forma de pagamento (lembrar que voucher não é aceito)
   - Para RETIRADA: horário que vai buscar
   - Para SALÃO: horário de chegada. IMPORTANTE: o Afrika NÃO reserva mesa. Diga que o prato
     fica pronto no horário combinado — nunca fale em "mesa reservada".
   - Itens com todas as personalizações (molho à parte, sem cebola, sem salada, suco coado, etc.)
   - NUNCA diga ou dê a entender que o cliente pode escolher um acompanhamento extra pelo mesmo
     preço. Ao apresentar um prato, diga que acompanha arroz, feijão e salada. Se o cliente pedir
     fritas, farofa ou outro acompanhamento, informe o preço da porção e some ao total.
   - OFERTA: sempre que o cliente escolher um prato (refeição), ofereça UMA vez, de forma leve,
     a batata frita pequena por apenas R$ 5,00 junto com o prato (avulsa ela custa R$ 9,00).
     Ex.: "Quer acrescentar uma porção pequena de fritas por só R$ 5,00?". Se o cliente recusar,
     não insista. No resumo, registre como "1x Batata Frita Pequena (com prato) — R$ 5,00".

3. Antes de finalizar, SEMPRE confirme com o cliente o pedido completo com o preço de cada item
   e o TOTAL (use os preços do cardápio). Para DELIVERY: assim que tiver o endereço (rua, número e
   bairro), use a ferramenta calcular_taxa_entrega. NUNCA calcule nem chute a taxa por conta própria.
   - Se a ferramenta devolver a taxa: informe a taxa e o TOTAL COM ENTREGA (itens + taxa).
   - Se devolver entrega=false (acima de 7 km): diga com gentileza que não entregamos nesse endereço
     e ofereça retirada.
   - Se der erro/endereço não encontrado: peça rua, número e bairro; se ainda assim falhar, diga que
     a equipe confirma a taxa em seguida.
   Nunca pergunte "de onde você está ligando".

4. Se perceber que é fornecedor ou assunto comercial:
   "Para assuntos com nosso setor de compras, o contato é {NUMERO_FORNECEDORES} 😊"

5. Se o cliente pedir atendimento humano:
   "Claro! Pode ligar aqui mesmo pelo WhatsApp ou no (11) 2427-3528 que alguém te atende 😊"

6. REGISTRO DO PEDIDO (MUITO IMPORTANTE): assim que o cliente CONFIRMAR o pedido, chame a
   ferramenta registrar_pedido com todos os dados. Sem essa chamada o pedido NÃO chega à cozinha.
   Depois de registrar, responda "Pedido anotado! Já repassei para a equipe 😊".
   Nunca diga que o pedido foi anotado/repassado sem ter chamado registrar_pedido.
   Nunca prometa tempo de preparo (ex.: "pronto em 5 minutos"); para SALÃO e RETIRADA, pergunte o
   horário e diga que o prato fica pronto nesse horário.

7. FOTOS: você pode enviar foto de um prato colocando no FINAL da mensagem a marcação
   [FOTO: código] usando os códigos da lista abaixo (ex.: [FOTO: 160]). O cliente não vê a
   marcação, só recebe a foto. Envie foto quando o cliente pedir, quando perguntar qual é o
   prato da semana/do dia (procure na lista o prato com nome igual ou mais parecido), ou quando
   ele estiver em dúvida entre pratos. No máximo 2 fotos por mensagem e não repita foto já
   enviada na conversa. Só use códigos que existem na lista; se o prato não tiver foto, não
   invente e não comente que falta foto.
   PROIBIDO escrever links, endereços de internet, markdown de imagem (como ![nome](link)) ou
   frases como "aqui está a foto". A ÚNICA forma de enviar foto é a marcação [FOTO: código].

   LISTA DE FOTOS DISPONÍVEIS (código = prato):
{LISTA_FOTOS}

"""

# ─── Histórico de conversas (em memória) ─────────────────────────
conversas: dict[str, list] = {}
FOTOS_PENDENTES: dict[str, list] = {}
ULTIMA_MSG: dict[str, datetime] = {}
HORAS_NOVA_CONVERSA = 6

def ler_ultima_msg(telefone: str):
    """Horário da última mensagem do cliente (guardado no Supabase, sobrevive a deploys)."""
    try:
        res = supabase.table("ultima_mensagem").select("quando").eq("telefone", telefone).execute()
        if res.data:
            return datetime.fromisoformat(str(res.data[0]["quando"]).replace("Z", "+00:00"))
    except Exception as e:
        print(f"Erro ao ler última mensagem: {e}")
    return ULTIMA_MSG.get(telefone)

def gravar_ultima_msg(telefone: str, quando: datetime):
    ULTIMA_MSG[telefone] = quando
    try:
        supabase.table("ultima_mensagem").upsert({"telefone": telefone, "quando": quando.isoformat()},
                                                  on_conflict="telefone").execute()
    except Exception as e:
        print(f"Erro ao gravar última mensagem: {e}")

def fotos_do_dia() -> list[str]:
    """Códigos das fotos dos pratos especiais válidos hoje (máx. 2)."""
    try:
        hoje = str(datetime.now(TZ).date())
        res = (supabase.table("cardapio_semana").select("foto_codigo,tipo,nome")
               .lte("data_inicio", hoje).gte("data_fim", hoje).order("tipo").execute())
        esg = [e.lower() for e in listar_esgotados()]
        return [p["foto_codigo"] for p in (res.data or [])
                if p.get("foto_codigo") in FOTOS
                and not any(e in p["nome"].lower() or p["nome"].lower() in e for e in esg)][:2]
    except Exception as e:
        print(f"Erro ao buscar fotos do dia: {e}")
        return []

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

def salvar_cliente(telefone: str, nome: str):
    """Grava ou atualiza o cliente (celular + nome) para a Zara reconhecer na próxima vez."""
    if not nome or nome == telefone:
        return
    try:
        numero_limpo = telefone.replace("55", "", 1) if telefone.startswith("55") else telefone
        supabase.table("clientes").upsert({
            "celular": numero_limpo,
            "nome": nome,
            "atualizado_em": datetime.now(TZ).isoformat()
        }, on_conflict="celular").execute()
    except Exception as e:
        print(f"Erro ao salvar cliente: {e}")

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
                    "Priority": "urgent",
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

async def enviar_foto(telefone: str, codigo: str):
    nome = FOTOS.get(codigo)
    if not nome:
        return
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "image",
        "image": {"link": f"{URL_PUBLICA}/fotos/{codigo}.jpg", "caption": nome}
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            print(f"Erro ao enviar foto {codigo}: {r.text}")

# ─── Chamar ChatGPT ───────────────────────────────────────────────
async def chamar_chatgpt(telefone: str, mensagem_usuario: str, nome_cliente: str, endereco: str = "") -> str:
    prato_semana = await buscar_prato_semana()

    if telefone not in conversas:
        conversas[telefone] = []

    conversas[telefone].append({"role": "user", "content": mensagem_usuario})
    historico = conversas[telefone][-20:]

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": montar_system_prompt(nome_cliente, prato_semana, endereco)},
            *historico
        ],
        "temperature": 0.7,
        "max_tokens": 600
    }

    payload["tools"] = FERRAMENTAS
    notas_taxa = []
    resumo = None
    async with httpx.AsyncClient() as client:
        for _ in range(3):  # no máximo 3 rodadas de ferramenta
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                timeout=30
            )
            data = r.json()
            msg_ia = data["choices"][0]["message"]
            chamadas = msg_ia.get("tool_calls") or []
            if not chamadas:
                resposta = msg_ia.get("content") or ""
                break
            payload["messages"].append(msg_ia)
            for ch in chamadas:
                try:
                    args = json.loads(ch["function"]["arguments"] or "{}")
                except Exception:
                    args = {}
                if ch["function"]["name"] == "registrar_pedido":
                    linhas = [
                        f"TIPO: {args.get('tipo', '-')}",
                        f"HORARIO: {args.get('horario', '-')}",
                        f"NOME: {args.get('nome') or nome_cliente or '-'}",
                        "ITENS:", *[str(x) for x in (args.get("itens") or [])],
                        f"TOTAL ITENS: {args.get('total_itens', '-')}",
                    ]
                    if args.get("tipo") == "DELIVERY":
                        linhas += [f"TAXA ENTREGA: {args.get('taxa_entrega', 'a confirmar')}",
                                   f"DISTANCIA: {args.get('distancia', '-')}",
                                   f"TOTAL COM ENTREGA: {args.get('total_com_entrega', '-')}",
                                   f"ENDERECO: {args.get('endereco', '-')}"]
                    linhas += [f"PAGAMENTO: {args.get('pagamento', '-')}", f"OBS: {args.get('obs') or '-'}"]
                    resumo = "\n".join(linhas)
                    resultado = {"ok": True, "mensagem": "pedido registrado e enviado para a cozinha"}
                    notas_taxa.append({"pedido_registrado": True})
                else:
                    resultado = await calcular_taxa_entrega(args.get("endereco", ""))
                    print(f"Taxa calculada para {args.get('endereco')}: {resultado}")
                    notas_taxa.append(resultado)
                payload["messages"].append({"role": "tool", "tool_call_id": ch["id"],
                                            "content": json.dumps(resultado, ensure_ascii=False)})
        else:
            payload.pop("tools", None)
            r = await client.post("https://api.openai.com/v1/chat/completions", json=payload,
                                  headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, timeout=30)
            resposta = r.json()["choices"][0]["message"].get("content") or ""

    # Fallback: pedido no bloco [RESUMO]...[/RESUMO] (formato antigo)
    if "[RESUMO]" in resposta and not resumo:
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

    # Extrai marcações [FOTO: código]
    fotos_pedidas = [c for c in re.findall(r"\[FOTO:\s*(\d+)\s*\]", resposta) if c in FOTOS][:2]
    resposta = re.sub(r"\[FOTO:[^\]]*\]", "", resposta)
    # Remove links/imagens em markdown e frases de "aqui está a foto" que o modelo às vezes inventa
    resposta = re.sub(r"!?\[[^\]]*\]\([^)]*\)", "", resposta)
    resposta = re.sub(r"https?://\S+", "", resposta)
    resposta = re.sub(r"(?im)^.*aqui (t[áa]|est[áa]) a foto.*$", "", resposta)
    resposta = re.sub(r"\n{3,}", "\n\n", resposta).strip()
    FOTOS_PENDENTES[telefone] = fotos_pedidas

    conversas[telefone].append({"role": "assistant", "content": resposta
        + ("\n(pedido registrado)" if resumo else "")
        + ("".join(f"\n(foto enviada: {FOTOS[c]})" for c in fotos_pedidas))
        + ("".join(f"\n(cálculo de entrega: {json.dumps(n, ensure_ascii=False)})" for n in notas_taxa))})

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
        salvar_cliente(telefone, nome)

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

        # Comandos da equipe (ex.: #acabou mignon)
        if texto_recebido.strip().startswith("#") and eh_admin(telefone):
            await enviar_mensagem(telefone, await tratar_comando(telefone, texto_recebido))
            return {"status": "ok"}
        cliente = buscar_cliente(telefone)
        nome_cliente = cliente["nome"] if cliente else ""
        endereco = ""
        if cliente and cliente.get("endereco"):
            endereco = cliente["endereco"] + (f" - {cliente['bairro']}" if cliente.get("bairro") else "") \
                       + (f" (ref.: {cliente['referencia']})" if cliente.get("referencia") else "")

        # Nova conversa? (primeira mensagem ou mais de 6h sem falar)
        agora = datetime.now(TZ)
        ultima = ler_ultima_msg(telefone)
        nova_conversa = ultima is None or (agora - ultima).total_seconds() > HORAS_NOVA_CONVERSA * 3600
        gravar_ultima_msg(telefone, agora)
        if nova_conversa:
            conversas.pop(telefone, None)

        resposta = await chamar_chatgpt(telefone, texto_recebido, nome_cliente, endereco)
        await enviar_mensagem(telefone, resposta)

        fotos = FOTOS_PENDENTES.pop(telefone, [])
        if nova_conversa:
            extras = [c for c in fotos_do_dia() if c not in fotos]
            fotos = (fotos + extras)[:2]
            if extras and telefone in conversas:
                conversas[telefone].append({"role": "assistant", "content":
                    "".join(f"(foto enviada: {FOTOS[c]})" for c in extras)})
        for codigo in fotos:
            await enviar_foto(telefone, codigo)

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


# ─── Painel de pedidos para o computador (alarme até confirmar) ───
PAINEL_CHAVE = os.environ.get("PAINEL_CHAVE", "")

def _chave_ok(chave: str) -> bool:
    return bool(PAINEL_CHAVE) and chave == PAINEL_CHAVE

@app.get("/painel/pedidos")
async def painel_pedidos(chave: str = ""):
    if not _chave_ok(chave):
        return JSONResponse({"erro": "chave inválida"}, status_code=403)
    try:
        desde = (datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)).isoformat()
        res = (supabase.table("pedidos_whatsapp").select("id,nome_cliente,telefone,pedido,criado_em,status")
               .gte("criado_em", desde).order("criado_em", desc=True).limit(30).execute())
        return {"pedidos": res.data or []}
    except Exception as e:
        print(f"Erro no painel: {e}")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/painel/recebido/{pedido_id}")
async def painel_recebido(pedido_id: str, chave: str = ""):
    if not _chave_ok(chave):
        return JSONResponse({"erro": "chave inválida"}, status_code=403)
    supabase.table("pedidos_whatsapp").update({"status": "recebido"}).eq("id", pedido_id).execute()
    return {"ok": True}

PAINEL_HTML = """<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pedidos Zara — Afrika</title>
<style>
 body{margin:0;font-family:Arial,sans-serif;background:#1d1d1d;color:#eee}
 header{display:flex;justify-content:space-between;align-items:center;padding:14px 20px;background:#2b2b2b}
 h1{font-size:22px;margin:0}
 #ativar{font-size:20px;padding:12px 22px;border:0;border-radius:8px;background:#e8a400;color:#000;cursor:pointer}
 #status{font-size:14px;color:#aaa}
 main{padding:16px;display:grid;gap:14px}
 .card{background:#2e2e2e;border-radius:10px;padding:16px;border-left:10px solid #555}
 .novo{border-left-color:#ff3b30;animation:pisca 1s infinite}
 @keyframes pisca{50%{background:#5a1a17}}
 .titulo{font-size:24px;font-weight:bold;margin-bottom:8px}
 pre{white-space:pre-wrap;font-size:20px;margin:0 0 12px;font-family:inherit}
 .ok{font-size:22px;padding:12px 26px;border:0;border-radius:8px;background:#34c759;color:#000;cursor:pointer}
 .rec{opacity:.55}
</style></head><body>
<header><h1>🍽️ Pedidos da Zara</h1><span id="status">carregando…</span>
<button id="ativar">🔔 Clique para ativar o som</button></header>
<main id="lista"></main>
<script>
const CHAVE = new URLSearchParams(location.search).get("chave") || "";
let ctx = null, alarme = null;
document.getElementById("ativar").onclick = () => {
  ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
  ctx.resume(); bip(); document.getElementById("ativar").textContent = "🔔 Som ativado";
};
function bip(){
  if(!ctx) return;
  [0,0.35,0.7].forEach(t=>{
    const o=ctx.createOscillator(), g=ctx.createGain();
    o.type="square"; o.frequency.value = t===0.35 ? 1320 : 880;
    g.gain.setValueAtTime(0.9, ctx.currentTime+t); g.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime+t+0.3);
    o.connect(g).connect(ctx.destination); o.start(ctx.currentTime+t); o.stop(ctx.currentTime+t+0.3);
  });
}
function tocar(liga){
  if(liga && !alarme){ bip(); alarme=setInterval(bip, 2000); }
  if(!liga && alarme){ clearInterval(alarme); alarme=null; }
}
function esc(t){return (t||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
async function receber(id){
  await fetch(`/painel/recebido/${id}?chave=${encodeURIComponent(CHAVE)}`,{method:"POST"}); carregar();
}
async function carregar(){
  try{
    const r = await fetch(`/painel/pedidos?chave=${encodeURIComponent(CHAVE)}`);
    const d = await r.json();
    if(!r.ok){ document.getElementById("status").textContent = d.erro || "erro"; return; }
    const pend = d.pedidos.filter(p=>p.status==="aguardando");
    document.getElementById("lista").innerHTML = d.pedidos.map(p=>{
      const hora = new Date(p.criado_em).toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});
      const novo = p.status==="aguardando";
      return `<div class="card ${novo?"novo":"rec"}"><div class="titulo">${hora} — ${esc(p.nome_cliente||p.telefone)}</div>
        <pre>${esc(p.pedido)}\nTelefone: ${esc(p.telefone)}</pre>
        ${novo?`<button class="ok" onclick="receber('${p.id}')">✅ Recebido</button>`:"<i>recebido</i>"}</div>`;
    }).join("") || "<p>Nenhum pedido hoje ainda.</p>";
    document.getElementById("status").textContent = `${pend.length} pendente(s) · atualizado ${new Date().toLocaleTimeString("pt-BR")}`;
    tocar(pend.length>0);
  }catch(e){ document.getElementById("status").textContent = "sem conexão — tentando de novo"; }
}
carregar(); setInterval(carregar, 10000);
</script></body></html>"""

@app.get("/painel", response_class=HTMLResponse)
async def painel(chave: str = ""):
    if not _chave_ok(chave):
        return HTMLResponse("<h2>Acesso negado</h2>", status_code=403)
    return PAINEL_HTML

"""main.py – Bot Telegram de venda de SMS via HeroSMS + Mercado Pago + CryptoBot."""
import json
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import configs
import database as db
import pagamentos
from herosms import HeroSMS

# ── Inicialização ─────────────────────────────────────────────────────────────

herosms = HeroSMS(configs.HEROSMS_API_KEY)
db.initialize_database()

# ── Catálogo em memória (carregado uma vez na inicialização) ──────────────────

def _load_countries() -> list[dict]:
    """Carrega países da API HeroSMS."""
    raw = herosms.get_countries()
    countries = herosms.extract_country_list(raw)
    
    # Reordena com Brasil em primeiro
    brazil = next((c for c in countries if c["name"].lower() == "brazil"), None)
    if brazil:
        countries_reordered = [brazil] + [c for c in countries if c["name"].lower() != "brazil"]
        return countries_reordered
    return countries


def _load_services() -> list[dict]:
    """Carrega serviços da API HeroSMS, com populares em primeiro."""
    raw = herosms.get_services()
    services = herosms.extract_service_list(raw)
    
    # Serviços mais utilizados (códigos de serviços populares)
    # go=Google, fb=Facebook, tg=Telegram, wp=163COM, ig=Instagram, li=Baidu, vi=Viber
    POPULAR_SERVICES = ["go", "fb", "tg", "wp", "ig", "li", "vi"]
    
    # Separa serviços populares dos demais
    popular = []
    others = []
    
    for service in services:
        if service["code"] in POPULAR_SERVICES:
            popular.append(service)
        else:
            others.append(service)
    
    # Ordena populares pela ordem definida e demais por ordem alfabética
    popular_sorted = [next((s for s in popular if s["code"] == code), None) for code in POPULAR_SERVICES]
    popular_sorted = [s for s in popular_sorted if s is not None]
    
    # Combina: populares primeiro + demais em ordem alfabética
    return popular_sorted + sorted(others, key=lambda s: s["name"].lower())


COUNTRIES: list[dict] = _load_countries()
SERVICES: list[dict] = _load_services()
print(f"✓ Países carregados: {len(COUNTRIES)}")
print(f"✓ Serviços carregados: {len(SERVICES)}")


# ── Menus (teclados inline) ───────────────────────────────────────────────────

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Perfil", callback_data="perfil")],
        [InlineKeyboardButton("💰 Adicionar saldo", callback_data="add_saldo")],
        [InlineKeyboardButton("📩 Receber SMS", callback_data="receber_sms")],
        [InlineKeyboardButton("🤝 Afiliado", callback_data="afiliado")],
    ])


def back_menu(target: str = "voltar") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Voltar", callback_data=target)]
    ])


def deposit_method_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 PIX (Mercado Pago)", callback_data="deposit_pix")],
        [InlineKeyboardButton("₿ Cripto (USDT)", callback_data="deposit_crypto")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="voltar")],
    ])


def purchase_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Comprar", callback_data="comprar")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="voltar")],
    ])


def post_purchase_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♻️ Ver SMS recebido", callback_data="ver_status")],
        [InlineKeyboardButton("❌ Cancelar serviço", callback_data="cancelar_servico")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="voltar")],
    ])


def _paginated_menu(
    items: list[dict],
    page: int,
    callback_prefix: str,
    back_callback: str,
) -> InlineKeyboardMarkup:
    """Menu paginado genérico."""
    start = page * configs.ITEMS_PER_PAGE
    end = start + configs.ITEMS_PER_PAGE
    page_items = items[start:end]

    rows = []
    for i in range(0, len(page_items), 2):
        row = []
        for item in page_items[i : i + 2]:
            label = item["name"]
            data = f"{callback_prefix}{item['code']}"
            row.append(InlineKeyboardButton(label, callback_data=data))
        rows.append(row)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"{callback_prefix}page_{page - 1}"))
    if end < len(items):
        nav.append(InlineKeyboardButton("➡️ Próximo", callback_data=f"{callback_prefix}page_{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🔙 Voltar", callback_data=back_callback)])
    return InlineKeyboardMarkup(rows)


def _capitalize_first_letter(text: str) -> str:
    return text.strip().capitalize() if isinstance(text, str) else text


def countries_menu(page: int) -> InlineKeyboardMarkup:
    """Menu de países com Brasil destacado em primeira linha."""
    rows = []
    
    # Primeira linha: apenas Brasil
    brazil = COUNTRIES[0]  # Brasil é o primeiro após reordenação
    rows.append([
        InlineKeyboardButton(
            f"🇧🇷 {_capitalize_first_letter(brazil['name'])}",
            callback_data=f"country_{brazil['code']}"
        )
    ])
    
    # Resto dos países com paginação
    other_countries = COUNTRIES[1:]
    capitalized_countries = [
        {**country, "name": _capitalize_first_letter(country["name"])}
        for country in other_countries
    ]
    
    # Paginação dos demais países (8 por página)
    start = page * configs.ITEMS_PER_PAGE
    end = start + configs.ITEMS_PER_PAGE
    page_items = capitalized_countries[start:end]
    
    # Adiciona 2 por linha
    for i in range(0, len(page_items), 2):
        row = []
        for item in page_items[i : i + 2]:
            row.append(InlineKeyboardButton(item["name"], callback_data=f"country_{item['code']}"))
        rows.append(row)
    
    # Navegação
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Anterior", callback_data="country_page_0" if page == 1 else f"country_page_{page - 1}"))
    if end < len(capitalized_countries):
        nav.append(InlineKeyboardButton("➡️ Próximo", callback_data=f"country_page_{page + 1}"))
    if nav:
        rows.append(nav)
    
    rows.append([InlineKeyboardButton("🔙 Voltar", callback_data="receber_sms")])
    return InlineKeyboardMarkup(rows)


def services_menu(page: int) -> InlineKeyboardMarkup:
    """Menu de serviços com populares em primeiro."""
    return _paginated_menu(SERVICES, page, "service_", "receber_sms")


# ── Helpers de contexto ───────────────────────────────────────────────────────

def _find_by_code(items: list[dict], code: str) -> dict | None:
    """Busca item por código em lista de dicts."""
    return next((i for i in items if i.get("code") == code), None)


# ── Formatadores de Mensagem ──────────────────────────────────────────────────

def format_insufficient_balance(balance: float, needed: float) -> str:
    """Formata mensagem elegante de saldo insuficiente."""
    deficit = needed - balance
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️  *SALDO INSUFICIENTE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *Seu saldo:*\n"
        f"   R$ {balance:.2f}\n\n"
        f"💵 *Valor necessário:*\n"
        f"   R$ {needed:.2f}\n\n"
        f"📊 *Diferença:*\n"
        f"   R$ {deficit:.2f}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💳 Clique em \"Adicionar saldo\" para recarregar"
    )


def format_sms_received(phone_number: str, service: str, sms_text: str, received_at: str | None = None) -> str:
    """Formata mensagem elegante de SMS recebido."""
    timestamp = received_at or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ *SMS RECEBIDO COM SUCESSO*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 *Número:*\n"
        f"   `{phone_number}`\n\n"
        f"🔍 *Serviço:*\n"
        f"   {service}\n\n"
        f"🕐 *Data/Hora:*\n"
        f"   {timestamp}\n\n"
        f"💬 *Mensagem:*\n"
        f"   `{sms_text}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


# ── /start ────────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    record = db.get_or_create_user(user.id, user.first_name)

    if context.args and context.args[0] != str(user.id):
        db.set_referred_by(user.id, int(context.args[0]))

    context.user_data["balance"] = record["balance"]

    await update.message.reply_text(
        f"👋 Olá, *{user.first_name}*!\nBem-vindo à nossa loja de SMS.",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


# ── Perfil ────────────────────────────────────────────────────────────────────

async def show_profile(query, context):
    user = query.from_user
    record = db.get_user(user.id)
    if not record:
        await query.answer("Usuário não encontrado.", show_alert=True)
        return

    referrals = db.count_referrals(user.id)
    joined = record["created_at"][:10]

    await query.edit_message_text(
        f"👤 *Seu Perfil*\n\n"
        f"📛 Nome: {user.first_name}\n"
        f"🆔 ID: `{user.id}`\n"
        f"📅 Cadastro: {joined}\n"
        f"👥 Indicações: {referrals}\n"
        f"💰 Saldo: R$ {record['balance']:.2f}",
        reply_markup=back_menu(),
        parse_mode="Markdown",
    )


# ── Adicionar saldo ───────────────────────────────────────────────────────────

async def show_deposit_methods(query, context):
    await query.edit_message_text(
        "💰 *Adicionar Saldo*\n\nEscolha o método de pagamento:",
        reply_markup=deposit_method_menu(),
        parse_mode="Markdown",
    )


async def ask_deposit_amount_pix(query, context):
    context.user_data["deposit_method"] = "pix"
    context.user_data["awaiting_deposit_amount"] = True
    await query.edit_message_text(
        f"💳 *PIX — Mercado Pago*\n\n"
        f"Digite o valor em R$ que deseja depositar.\n"
        f"Mínimo: R$ {configs.MIN_DEPOSIT_BRL:.2f}",
        reply_markup=back_menu("add_saldo"),
        parse_mode="Markdown",
    )


async def ask_deposit_amount_crypto(query, context):
    context.user_data["deposit_method"] = "crypto"
    context.user_data["awaiting_deposit_amount"] = True
    await query.edit_message_text(
        f"₿ *CryptoBot — USDT*\n\n"
        f"Digite o valor em USDT que deseja depositar.\n"
        f"Mínimo: {configs.MIN_DEPOSIT_USDT:.2f} USDT",
        reply_markup=back_menu("add_saldo"),
        parse_mode="Markdown",
    )


async def handle_deposit_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_deposit_amount"):
        return

    raw = update.message.text.replace(",", ".").strip()
    method = context.user_data.get("deposit_method", "pix")
    user_id = update.effective_user.id

    try:
        amount = float(raw)
    except ValueError:
        await update.message.reply_text("❌ Digite um número válido.")
        return

    if method == "pix":
        await _process_pix_deposit(update, context, user_id, amount)
    else:
        await _process_crypto_deposit(update, context, user_id, amount)


async def _process_pix_deposit(update, context, user_id: int, amount_brl: float):
    if amount_brl < configs.MIN_DEPOSIT_BRL:
        await update.message.reply_text(f"❌ Valor mínimo: R$ {configs.MIN_DEPOSIT_BRL:.2f}")
        return

    result = pagamentos.create_pix_charge(amount_brl, user_id)
    response = result.get("response", {})

    if "id" not in response:
        await update.message.reply_text("❌ Erro ao gerar PIX. Tente novamente.")
        return

    interaction = response.get("point_of_interaction")
    if not interaction:
        await update.message.reply_text(
            "❌ PIX indisponível. Verifique se sua conta Mercado Pago aceita PIX."
        )
        return

    payment_id = response["id"]
    qr_code = interaction["transaction_data"]["qr_code"]

    context.user_data["awaiting_deposit_amount"] = False
    db.register_payment(str(payment_id), user_id, amount_brl, "pix")

    await update.message.reply_text(
        f"💳 *PIX gerado com sucesso!*\n\n"
        f"🆔 Pedido: `{payment_id}`\n"
        f"💰 Valor: R$ {amount_brl:.2f}\n"
        f"⏰ Expira em: {configs.PIX_EXPIRATION_MINUTES} minutos\n\n"
        f"🔑 *Copia e cola:*\n`{qr_code}`\n\n"
        f"Seu saldo será creditado automaticamente após o pagamento.",
        parse_mode="Markdown",
    )

    context.application.create_task(
        pagamentos.watch_pix_expiration(payment_id, user_id, context.bot)
    )


async def _check_pending_pix_payments(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verifica pagamentos PIX pendentes a cada minuto."""
    approved = pagamentos.process_pending_pix_payments()
    for payment_id, user_id, amount in approved:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ Pagamento confirmado!\n"
                    f"Saldo de R$ {amount:.2f} adicionado ao seu cadastro."
                ),
            )
            print(
                f"[PIX POLLING] pagamento aprovado user={user_id} id={payment_id} valor={amount:.2f}"
            )
        except Exception as exc:
            print(f"[PIX POLLING] falha ao notificar user={user_id}: {exc}")


async def _process_crypto_deposit(update, context, user_id: int, amount_usdt: float):
    if amount_usdt < configs.MIN_DEPOSIT_USDT:
        await update.message.reply_text(f"❌ Valor mínimo: {configs.MIN_DEPOSIT_USDT:.2f} USDT")
        return

    try:
        invoice = pagamentos.create_crypto_invoice(amount_usdt, user_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao criar fatura cripto: {e}")
        return

    invoice_id = str(invoice["invoice_id"])
    pay_url = invoice["pay_url"]
    brl_equiv = herosms.usd_to_brl(amount_usdt)

    context.user_data["awaiting_deposit_amount"] = False
    db.register_payment(invoice_id, user_id, brl_equiv, "crypto")

    await update.message.reply_text(
        f"₿ *Fatura cripto criada!*\n\n"
        f"💵 Valor: {amount_usdt:.2f} USDT\n"
        f"💰 Equivalente: ≈ R$ {brl_equiv:.2f}\n\n"
        f"👇 Clique abaixo para pagar via CryptoBot:\n{pay_url}\n\n"
        f"Seu saldo será creditado automaticamente após confirmação.",
        parse_mode="Markdown",
    )


# ── Receber SMS — seleção de país ─────────────────────────────────────────────

async def show_countries(query, context, page: int = 0):
    await query.edit_message_text(
        "🌍 Selecione o país:",
        reply_markup=countries_menu(page),
    )


async def handle_country_selected(query, context, country_code: str):
    country = _find_by_code(COUNTRIES, country_code)
    if not country:
        await query.answer("País não encontrado.", show_alert=True)
        return

    context.user_data["country"] = country
    context.user_data["services"] = SERVICES

    await query.edit_message_text(
        f"🌍 País: *{country['name']}*\n\n📱 Escolha o serviço:",
        reply_markup=services_menu(page=0),
        parse_mode="Markdown",
    )


# ── Receber SMS — seleção de serviço e confirmação de preço ──────────────────

async def handle_service_selected(query, context, service_code: str):
    service = _find_by_code(SERVICES, service_code)
    country = context.user_data.get("country")

    if not service or not country:
        await query.answer("Sessão expirada. Comece novamente.", show_alert=True)
        return

    # Busca preço dinamicamente (tenta API, fallback para padrão)
    try:
        country_id = int(country.get("code", 1))
        price_usd = herosms.get_service_price(service_code, country_id)
    except Exception as e:
        print(f"[ERRO] Ao buscar preço do serviço {service_code}: {e}")
        price_usd = 0.5  # Fallback
    
    # Calcula preço de venda
    sell_price = herosms.calculate_sell_price_brl(price_usd)
    
    # Cria cópia do serviço com preço atualizado (não modifica original)
    service_with_price = {**service, "price_usd": price_usd}
    context.user_data["selected_service"] = service_with_price
    context.user_data["sell_price"] = sell_price

    record = db.get_user(query.from_user.id)
    balance = record["balance"] if record else 0.0

    cost_brl = herosms.usd_to_brl(price_usd)

    await query.edit_message_text(
        f"📋 *Resumo da compra*\n\n"
        f"🌍 País: {country['name']}\n"
        f"📱 Serviço: {service['name']}\n\n"
        f"🏷 Seu preço: *R$ {sell_price:.2f}*\n\n"
        f"💰 Seu saldo: R$ {balance:.2f}",
        reply_markup=purchase_confirm_menu(),
        parse_mode="Markdown",
    )


# ── Compra de número ──────────────────────────────────────────────────────────

async def handle_purchase(query, context):
    """Handler para compra de número via HeroSMS."""
    user_id = query.from_user.id
    
    try:
        # 1. Valida dados da sessão
        record = db.get_user(user_id)
        service = context.user_data.get("selected_service")
        country = context.user_data.get("country")
        sell_price = context.user_data.get("sell_price")

        if not all([service, country, sell_price, record]):
            print(f"[COMPRA FALHOU] user={user_id} Dados faltando: service={bool(service)} country={bool(country)} sell_price={bool(sell_price)} record={bool(record)}")
            await query.answer("Sessão expirada. Comece novamente.", show_alert=True)
            return

        # 2. Valida saldo
        if record["balance"] < sell_price:
            print(f"[COMPRA FALHOU] user={user_id} Saldo insuficiente: tem R${record['balance']:.2f}, precisa R${sell_price:.2f}")
            await query.answer(
                format_insufficient_balance(record["balance"], sell_price),
                show_alert=True,
                parse_mode="Markdown",
            )
            return

        # 3. Tenta comprar número
        print(f"[COMPRA] user={user_id} Tentando comprar {service['name']} em {country['name']}...")
        try:
            number_data = herosms.get_number(
                service=service["code"],
                country=int(country["code"]),
            )
        except Exception as e:
            print(f"[COMPRA FALHOU] user={user_id} Erro ao chamar get_number(): {e}")
            await query.answer(f"❌ Erro ao comprar número: {e}", show_alert=True)
            return

        # 4. Valida resposta
        if isinstance(number_data, str):
            print(f"[COMPRA FALHOU] user={user_id} Resposta string: {number_data}")
            await query.answer("❌ Nenhum número disponível no momento.", show_alert=True)
            return
        
        if not isinstance(number_data, dict):
            print(f"[COMPRA FALHOU] user={user_id} Tipo inválido: {type(number_data)}")
            await query.answer("❌ Resposta inválida da API.", show_alert=True)
            return
        
        if "error" in number_data or number_data.get("status") == "no":
            print(f"[COMPRA FALHOU] user={user_id} Erro na resposta: {number_data}")
            await query.answer("❌ Nenhum número disponível no momento.", show_alert=True)
            return
        
        if not number_data.get("phoneNumber") or (not number_data.get("activationId") and not number_data.get("id")):
            print(f"[COMPRA FALHOU] user={user_id} Resposta incompleta: {number_data}")
            await query.answer("❌ Resposta da API incompleta.", show_alert=True)
            return

        # 5. Debita saldo
        phone_number = number_data.get("phoneNumber")
        activation_id = str(number_data.get("activationId") or number_data.get("id"))
        
        debited = db.debit_balance(user_id, sell_price)
        if not debited:
            print(f"[COMPRA FALHOU] user={user_id} Erro ao debitar saldo")
            await query.answer("❌ Falha ao debitar saldo. Tente novamente.", show_alert=True)
            return

        # 6. Salva compra
        db.save_purchase(
            user_id=user_id,
            activation_id=activation_id,
            phone_number=phone_number,
            service=service["name"],
            country=country["name"],
            price_brl=sell_price,
        )

        # 7. Atualiza contexto
        context.user_data["balance"] = record["balance"] - sell_price
        new_balance = context.user_data["balance"]

        # 8. Log de sucesso
        print(
            f"[COMPRA ✓] user={user_id} serviço={service['name']} "
            f"país={country['name']} número={phone_number} preço=R${sell_price:.2f}"
        )

        # 9. Responde ao usuário
        await query.edit_message_text(
            f"✅ *Número comprado com sucesso!*\n\n"
            f"📱 Número: `{phone_number}`\n"
            f"📋 Serviço: {service['name']}\n"
            f"💵 Pago: R$ {sell_price:.2f}\n"
            f"💰 Saldo restante: R$ {new_balance:.2f}\n\n"
            f"Aguarde o SMS chegar e clique em *Ver SMS recebido*.",
            parse_mode="Markdown",
            reply_markup=post_purchase_menu(),
        )
        
    except Exception as e:
        print(f"[ERRO CRÍTICO] handle_purchase user={user_id}: {e}")
        import traceback
        traceback.print_exc()
        try:
            await query.answer(f"❌ Erro interno: {e}", show_alert=True)
        except:
            pass


# ── Ver status / SMS recebido ─────────────────────────────────────────────────

async def handle_view_status(query, context):
    last = db.get_last_purchase(query.from_user.id)

    if not last or not last["activation_id"]:
        await query.answer("Nenhuma compra ativa.", show_alert=True)
        return

    try:
        status_data = herosms.get_status(last["activation_id"])
    except Exception as e:
        await query.answer(f"❌ Erro ao consultar status: {e}", show_alert=True)
        return

    # HeroSMS retorna SMS em campo "sms"
    sms_text = status_data.get("sms", "")
    if sms_text:
        # Formata mensagem elegante do SMS recebido
        content = format_sms_received(
            phone_number=last['phone_number'],
            service=last['service'],
            sms_text=sms_text,
            received_at=None  # Deixa datetime automático
        )
    else:
        content = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ *AGUARDANDO SMS*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📱 *Número:*\n"
            f"   `{last['phone_number']}`\n\n"
            "🔍 *Serviço:*\n"
            f"   {last['service']}\n\n"
            "💬 *Mensagem:*\n"
            "   Nenhuma mensagem recebida ainda.\n"
            "   Tente novamente em alguns instantes.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    await query.edit_message_text(
        content,
        parse_mode="Markdown",
        reply_markup=post_purchase_menu(),
    )


# ── Cancelar serviço ──────────────────────────────────────────────────────────

async def handle_cancel_service(query, context):
    last = db.get_last_purchase(query.from_user.id)

    if not last or not last["activation_id"]:
        await query.answer("Nenhuma compra ativa para cancelar.", show_alert=True)
        return

    if not _cancel_window_elapsed(last["purchased_at"]):
        remaining = _seconds_remaining(last["purchased_at"])
        m, s = divmod(int(remaining), 60)
        await query.answer(
            f"⏳ Aguarde {m}m {s}s para poder cancelar.",
            show_alert=True,
        )
        return

    try:
        herosms.cancel_order(last["activation_id"])
    except Exception as e:
        await query.answer(f"❌ Erro ao cancelar: {e}", show_alert=True)
        return

    db.credit_balance(query.from_user.id, last["price_brl"])
    context.user_data["balance"] = context.user_data.get("balance", 0.0) + last["price_brl"]

    print(
        f"[CANCELAMENTO] user={query.from_user.id} número={last['phone_number']} "
        f"reembolso=R${last['price_brl']:.2f}"
    )

    await query.edit_message_text(
        f"✅ *Serviço cancelado!*\n\n"
        f"💰 Reembolso: R$ {last['price_brl']:.2f}\n"
        f"💰 Saldo atual: R$ {context.user_data['balance']:.2f}",
        parse_mode="Markdown",
        reply_markup=back_menu(),
    )


def _cancel_window_elapsed(purchased_at_iso: str) -> bool:
    elapsed = (datetime.now() - datetime.fromisoformat(purchased_at_iso)).total_seconds()
    return elapsed >= configs.CANCEL_TIMEOUT_SECONDS


def _seconds_remaining(purchased_at_iso: str) -> float:
    elapsed = (datetime.now() - datetime.fromisoformat(purchased_at_iso)).total_seconds()
    return configs.CANCEL_TIMEOUT_SECONDS - elapsed


# ── Afiliado ──────────────────────────────────────────────────────────────────

async def show_affiliate(query):
    user = query.from_user
    referrals = db.count_referrals(user.id)
    link = f"https://t.me/{configs.BOT_USERNAME}?start={user.id}"

    await query.edit_message_text(
        f"🤝 *Programa de Afiliados*\n\n"
        f"🔗 Seu link:\n`{link}`\n\n"
        f"👥 Pessoas indicadas: {referrals}",
        reply_markup=back_menu(),
        parse_mode="Markdown",
    )


# ── Dispatcher de callbacks ───────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    match data:
        case "perfil":
            await show_profile(query, context)

        case "add_saldo":
            await show_deposit_methods(query, context)

        case "deposit_pix":
            await ask_deposit_amount_pix(query, context)

        case "deposit_crypto":
            await ask_deposit_amount_crypto(query, context)

        case "receber_sms":
            await show_countries(query, context)

        case "comprar":
            await handle_purchase(query, context)

        case "cancelar_servico":
            await handle_cancel_service(query, context)

        case "ver_status":
            await handle_view_status(query, context)

        case "afiliado":
            await show_affiliate(query)

        case "voltar":
            await query.edit_message_text("🏠 Menu principal:", reply_markup=main_menu())

        case _ if data.startswith("country_page_"):
            page = int(data.split("_")[-1])
            await show_countries(query, context, page)

        case _ if data.startswith("country_"):
            code = data.removeprefix("country_")
            await handle_country_selected(query, context, code)

        case _ if data.startswith("service_page_"):
            page = int(data.split("_")[-1])
            await query.edit_message_text(
                "📱 Escolha o serviço:",
                reply_markup=services_menu(page),
            )

        case _ if data.startswith("service_"):
            code = data.removeprefix("service_")
            await handle_service_selected(query, context, code)


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(configs.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deposit_amount_input)
    )

    app.job_queue.run_repeating(
        _check_pending_pix_payments,
        interval=60,
        first=60,
    )

    print("🤖 Bot SMS iniciado com HeroSMS + SQLite + MP PIX + CryptoBot")
    print("🔄 Verificação de PIX pendentes ativa a cada 60 segundos")
    app.run_polling()


if __name__ == "__main__":
    main()

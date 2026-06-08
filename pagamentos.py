import asyncio
from datetime import datetime, timedelta

import mercadopago
import requests

import configs
import database as db

mp_sdk = mercadopago.SDK(configs.MP_ACCESS_TOKEN)

CRYPTOBOT_BASE_URL = "https://pay.crypt.bot/api"
CRYPTOBOT_HEADERS  = {"Crypto-Pay-API-Token": configs.CRYPTOBOT_API_TOKEN}
IS_MP_SANDBOX      = configs.MP_ACCESS_TOKEN.startswith("TEST-")


# ── Mercado Pago — PIX ────────────────────────────────────────────────────────

def create_pix_charge(amount_brl: float, user_id: int) -> dict:
    if IS_MP_SANDBOX:
        return _create_pix_sandbox(amount_brl, user_id)
    return _create_pix_production(amount_brl, user_id)


def _create_pix_production(amount_brl: float, user_id: int) -> dict:
    unique_ref = f"pix_{user_id}_{int(datetime.now().timestamp())}"

    payload = {
        "transaction_amount": float(amount_brl),
        "description": "Recarga de saldo",
        "payment_method_id": "pix",
        "external_reference": unique_ref,
        "payer": {
            "email": f"user{user_id}@spicysoda.com",
            "first_name": "Usuario",
            "last_name": "Bot",
            "identification": {"type": "CPF", "number": "00000000000"},
        },
    }

    result = mp_sdk.payment().create(payload)
    response = result.get("response", {})

    if "id" not in response:
        cause   = response.get("cause", [{}])
        mp_code = cause[0].get("code", "?") if cause else "?"
        mp_desc = cause[0].get("description", response.get("message", str(response))) if cause else str(response)
        print(f"[MP PIX ERRO] user={user_id} code={mp_code} desc={mp_desc} body={response}")

    return result


def _create_pix_sandbox(amount_brl: float, user_id: int) -> dict:
    """
    Simula resposta de PIX para desenvolvimento com token TEST-.
    O Mercado Pago bloqueia PIX em sandbox com código 23, independente
    do formato da data. Use isto para testar o fluxo do bot localmente.
    Substitua pelo token APP_USR-... de produção para ir ao ar.
    """
    fake_id = int(datetime.now().timestamp())
    fake_qr = (
        f"00020126580014br.gov.bcb.pix0136SANDBOX-{fake_id}"
        f"-USER-{user_id}5204000053039865802BR5925Bot SMS"
        f"6009SAOPAULO62290525{fake_id}6304ABCD"
    )

    print(f"[MP SANDBOX] PIX simulado — user={user_id} valor=R${amount_brl:.2f} id={fake_id}")

    return {
        "status": 201,
        "response": {
            "id": fake_id,
            "status": "pending",
            "external_reference": f"pix_{user_id}_{fake_id}",
            "point_of_interaction": {
                "transaction_data": {
                    "qr_code": fake_qr,
                    "qr_code_base64": "",
                }
            },
        },
    }


def cancel_pix_charge(payment_id: int) -> None:
    if not IS_MP_SANDBOX:
        mp_sdk.payment().update(payment_id, {"status": "cancelled"})


def get_pix_status(payment_id: int) -> str:
    if IS_MP_SANDBOX:
        payment = db.get_payment(str(payment_id))
        return payment["status"] if payment else "unknown"
    result = mp_sdk.payment().get(payment_id)
    return result["response"].get("status", "unknown")


def process_pending_pix_payments() -> list[tuple[int, int, float]]:
    approved = []
    payments = db.list_pending_payments("pix")
    for payment in payments:
        payment_id = int(payment["external_id"])
        status = get_pix_status(payment_id)
        if status == "approved":
            success = db.credit_balance(payment["user_id"], payment["amount"])
            if success:
                db.update_payment_status(payment["external_id"], "approved")
                approved.append((payment_id, payment["user_id"], payment["amount"]))
    return approved


async def watch_pix_expiration(payment_id: int, user_id: int, bot) -> None:
    await asyncio.sleep(configs.PIX_EXPIRATION_MINUTES * 60)

    payment = db.get_payment(str(payment_id))
    if payment and payment["status"] == "pending":
        cancel_pix_charge(payment_id)
        db.update_payment_status(str(payment_id), "expired")
        await bot.send_message(
            chat_id=user_id,
            text="⏰ Seu PIX expirou. Gere um novo quando quiser.",
        )


# ── CryptoBot ─────────────────────────────────────────────────────────────────

def _cryptobot_request(method: str, endpoint: str, payload: dict | None = None) -> dict:
    url = f"{CRYPTOBOT_BASE_URL}/{endpoint}"
    fn  = requests.post if method == "POST" else requests.get
    response = fn(url, headers=CRYPTOBOT_HEADERS, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"CryptoBot API error: {data}")
    return data["result"]


def create_crypto_invoice(amount_usdt: float, user_id: int) -> dict:
    return _cryptobot_request("POST", "createInvoice", {
        "currency_type": "crypto",
        "asset": "USDT",
        "amount": str(round(amount_usdt, 2)),
        "description": f"Saldo — user {user_id}",
        "payload": str(user_id),
        "expires_in": 3600,
    })


def get_invoice_status(invoice_id: int) -> str:
    invoices = _cryptobot_request("GET", f"getInvoices?invoice_ids={invoice_id}")
    items = invoices.get("items", [])
    return items[0]["status"] if items else "unknown"


def list_paid_invoices() -> list[dict]:
    result = _cryptobot_request("GET", "getInvoices?status=paid")
    return result.get("items", [])


def handle_cryptobot_webhook(payload: dict) -> tuple[int, float] | None:
    if payload.get("update_type") != "invoice_paid":
        return None

    invoice    = payload.get("payload", {})
    invoice_id = str(invoice.get("invoice_id"))
    user_id    = int(invoice.get("payload", 0))
    amount     = float(invoice.get("amount", 0))

    existing = db.get_payment(invoice_id)
    if existing and existing["status"] != "pending":
        return None

    return user_id, amount

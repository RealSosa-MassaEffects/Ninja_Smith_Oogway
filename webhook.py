from flask import Flask, request
from pagamentos import load_pagamentos, save_pagamentos, sdk
from db import credit_saldo   # importa direto do módulo de dados

app = Flask(__name__)


@app.route("/webhook_mp", methods=["POST"])
def webhook_mp():
    data = request.json or {}
    if data.get("type") != "payment":
        return "ok", 200

    payment_id = data["data"]["id"]
    payment = sdk.payment().get(payment_id).get("response", {})

    if payment.get("status") == "approved":
        pagamentos = load_pagamentos()
        reg = pagamentos.get(str(payment_id))
        if reg and reg["status"] == "pending":
            credit_saldo(reg["user_id"], reg["valor"])
            reg["status"] = "approved"
            save_pagamentos(pagamentos)

    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

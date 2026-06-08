"""db.py – persistência de usuários (JSON com write-safe via tmp+replace)."""
import json, os, threading
from datetime import datetime

USERS_FILE = "data/users.json"
_LOCK = threading.Lock()


def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        corrupt = USERS_FILE + ".corrupt"
        os.replace(USERS_FILE, corrupt)
        print(f"[db] arquivo corrompido movido para {corrupt}: {e}")
        return {}


def save_users(users: dict):
    with _LOCK:
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
        tmp = USERS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        os.replace(tmp, USERS_FILE)


def get_or_create_user(user) -> dict:
    users = load_users()
    uid = str(user.id)
    if uid not in users:
        users[uid] = {
            "name": user.first_name,
            "saldo": 0.0,
            "first_use": datetime.now().strftime("%d/%m/%Y"),
            "created_at": datetime.now().isoformat(),
            "compras": [],
        }
        save_users(users)
    return users[uid]


def credit_saldo(user_id, valor: float) -> bool:
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        return False
    users[uid]["saldo"] = round(users[uid]["saldo"] + valor, 2)
    save_users(users)
    return True


def salvar_compra(user_id, activation_id, phone_number, preco, pais, servico):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        return False
    users[uid].setdefault("compras", []).append(
        {
            "activation_id": activation_id,
            "phone_number": phone_number,
            "preco": preco,
            "pais": pais,
            "servico": servico,
            "purchased_at": datetime.now().isoformat(),
        }
    )
    save_users(users)
    return True


def obter_ultima_compra(user_id) -> dict | None:
    users = load_users()
    compras = users.get(str(user_id), {}).get("compras", [])
    return compras[-1] if compras else None

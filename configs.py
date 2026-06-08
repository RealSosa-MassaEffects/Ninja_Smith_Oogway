# ── APIs externas ─────────────────────────────────────────────────────────────
HEROSMS_API_KEY     = "0720102d5ed6edcA595A6dd4b395e7A7"          # https://5sim.net/settings/api
MP_ACCESS_TOKEN     = "APP_USR-2124619520875136-050217-83006ef8039b1618a94dbd56024efe1b-449482248"   # Mercado Pago → Credenciais
CRYPTOBOT_API_TOKEN = "SUA_CHAVE_CRYPTOBOT_AQUI"     # @CryptoBot → /pay → criar app

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN      = "7982853718:AAFZLp5wkBnGzaSw5liin-puE9aUDH1lzAw"                # @BotFather
BOT_USERNAME   = "@NumberNinja00_bot"
ADMIN_USER_IDS = [5384467590]

# ── Banco de dados ────────────────────────────────────────────────────────────
DATABASE_PATH = "data/bot.db"

# ── Regras de negócio ─────────────────────────────────────────────────────────
MARKUP                 = 0.40   # 40% de lucro sobre o custo do HeroSMS
ITEMS_PER_PAGE         = 8      # Botões por página nos menus
MIN_DEPOSIT_BRL        = 5.0    # Depósito mínimo via Mercado Pago (R$)
MIN_DEPOSIT_USDT       = 1.0    # Depósito mínimo via CryptoBot (USDT)
PIX_EXPIRATION_MINUTES = 5      # Tempo de vida do QR Code PIX
CANCEL_TIMEOUT_SECONDS = 120    # Janela de cancelamento após compra de número

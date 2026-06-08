"""HeroSMS API Client - Gerenciador de números virtuais para SMS."""
import json
import re
import requests

import configs

BASE_URL = "https://hero-sms.com/stubs/handler_api.php"
EXCHANGE_URL = "https://api.exchangerate-api.com/v4/latest/USD"


class HeroSMS:
    """Cliente para API HeroSMS - compra e gerenciamento de números virtuais."""

    def __init__(self, api_key: str):
        """
        Inicializa cliente HeroSMS.
        
        Args:
            api_key: Chave de API do HeroSMS
        """
        self.api_key = api_key
        self._headers = {
            "Accept": "application/json",
        }

    # ── Requisição base ───────────────────────────────────────────────────────

    def _get(self, **params) -> dict | str | list:
        """
        Faz requisição GET à API HeroSMS.
        
        Args:
            **params: Parâmetros da requisição (incluindo action)
            
        Returns:
            dict, str ou list dependendo da resposta da API
            
        Raises:
            requests.HTTPError: Se status HTTP for erro
        """
        try:
            response = requests.get(
                BASE_URL,
                params={"api_key": self.api_key, **params},
                headers=self._headers,
                timeout=30,
            )
            response.raise_for_status()
            
            try:
                return response.json()
            except ValueError:
                # API pode retornar texto simples em alguns casos
                return response.text
        except requests.RequestException as e:
            print(f"[HeroSMS] Erro na requisição: {e}")
            raise

    # ── Conta e Saldo ─────────────────────────────────────────────────────────

    def get_balance(self) -> dict:
        """
        Obtém saldo da conta.
        
        Returns:
            dict com informações de saldo
        """
        return self._get(action="getBalance")

    # ── Catálogo: Países ──────────────────────────────────────────────────────

    def get_countries(self) -> dict:
        """
        Obtém lista de países disponíveis.
        
        Returns:
            dict com países: {id: {eng: "Country Name", ...}, ...}
        """
        return self._get(action="getCountries")

    @staticmethod
    def extract_country_list(raw: dict) -> list[dict]:
        """
        Extrai lista de países do retorno da API.
        
        Args:
            raw: Resposta bruta de getCountries()
            
        Returns:
            Lista ordenada: [{"code": "1", "name": "Brazil"}, ...]
        """
        if not isinstance(raw, dict):
            return []
        
        countries = []
        for api_id, info in raw.items():
            if isinstance(info, dict) and info.get("eng"):
                countries.append({
                    "code": str(api_id),
                    "name": info.get("eng", str(api_id))
                })
        
        return sorted(countries, key=lambda c: c["name"].lower())

    # ── Catálogo: Serviços ────────────────────────────────────────────────────

    def get_services(self) -> list | dict:
        """
        Obtém lista de serviços disponíveis.
        
        Nota: HeroSMS pode retornar em múltiplos formatos
        (dict, list, string JSON ou CSV).
        
        Returns:
            list ou dict de serviços
        """
        resp = self._get(action="getServicesList")
        
        # Trata múltiplos formatos de retorno
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            try:
                parsed = json.loads(resp)
                return parsed if isinstance(parsed, (dict, list)) else [resp]
            except json.JSONDecodeError:
                # Trata CSV ou formato delimitado
                return [s.strip() for s in re.split(r"[,;\n\r]+", resp) if s.strip()]
        
        return []

    @staticmethod
    def _format_service_name(code: str) -> str:
        """
        Formata código de serviço em nome legível.
        
        Args:
            code: Código do serviço (ex: "google", "whatsapp_business")
            
        Returns:
            Nome formatado (ex: "Google", "Whatsapp Business")
        """
        return code.replace("_", " ").replace("-", " ").title()

    @staticmethod
    def extract_service_list(raw: dict | list) -> list[dict]:
        """
        Extrai lista de serviços do retorno da API.
        
        Args:
            raw: Resposta bruta de getServices() - pode ser:
                 - dict com chave "services" contendo list/dict
                 - list direto de serviços
                 - dict onde keys são códigos de serviço
            
        Returns:
            Lista ordenada: [{"code": "google", "name": "Google", ...}, ...]
        """
        # Se é dict com chave "services" (resposta encapsulada da API)
        if isinstance(raw, dict) and "services" in raw:
            services_data = raw["services"]
        else:
            services_data = raw
        
        # Se é uma lista de dicts com "code" e "name"
        if isinstance(services_data, list):
            services = []
            for item in services_data:
                if isinstance(item, dict) and "code" in item and "name" in item:
                    services.append({
                        "code": item["code"],
                        "name": item["name"],
                        "price_usd": float(item.get("cost", 0)),
                    })
            return sorted(services, key=lambda s: s["name"].lower())
        
        # Se é um dict onde keys são códigos (formato antigo)
        if isinstance(services_data, dict):
            services = []
            for code, info in services_data.items():
                if isinstance(info, dict):
                    name = info.get("name") or info.get("Name") or HeroSMS._format_service_name(code)
                    services.append({
                        "code": code,
                        "name": name,
                        "price_usd": float(info.get("cost", 0)),
                    })
            return sorted(services, key=lambda s: s["name"].lower())
        
        return []

    def get_service_price(self, service_code: str, country_id: int | None = None) -> float:
        """
        Obtém preço de um serviço. Tenta API primeiro, fallback para preço padrão.
        
        Args:
            service_code: Código do serviço
            country_id: ID do país (opcional)
            
        Returns:
            Preço em USD
        """
        # Tenta buscar da API (com tratamento de erro)
        try:
            prices = self.get_prices(country=country_id, service=service_code)
            if isinstance(prices, dict) and prices:
                # Tenta extrair o preço da resposta
                if country_id and str(country_id) in prices:
                    country_prices = prices[str(country_id)]
                    if isinstance(country_prices, dict):
                        if service_code in country_prices:
                            price_data = country_prices[service_code]
                            if isinstance(price_data, dict):
                                return float(price_data.get("cost", 1.5))
                            else:
                                return float(price_data) if price_data else 1.5
            return 1.5  # Valor padrão se API retorna vazio (≈ R$ 7.50)
        except Exception as e:
            print(f"[HeroSMS] Erro ao buscar preço de {service_code}: {e}")
            # Fallback: usa preço padrão configurável ($1.50 USD ≈ R$ 7.50)
            return 1.5

    # ── Catálogo: Preços ──────────────────────────────────────────────────────

    def get_prices(self, country: int | None = None, service: str | None = None) -> dict:
        """
        Obtém tabela de preços.
        
        Args:
            country: ID do país (opcional)
            service: Código do serviço (opcional)
            
        Returns:
            dict com estrutura: {country_id: {service: {cost: price, ...}, ...}, ...}
        """
        params = {"action": "getPrices"}
        
        if country is not None:
            params["country"] = country
        if service is not None:
            params["service"] = service
        
        return self._get(**params)

    # ── Números Virtuais: Compra ──────────────────────────────────────────────

    def get_number(
        self,
        service: str,
        country: int = 0,
        operator: str = "any",
    ) -> dict:
        """
        Compra um número virtual.
        
        Args:
            service: Código do serviço (ex: "google")
            country: ID do país
            operator: Operadora (padrão: "any")
            
        Returns:
            dict com: {activationId, phoneNumber, operator, product, ...}
        """
        return self._get(
            action="getNumberV2",
            service=service,
            country=country,
            operator=operator,
        )

    # ── Números Virtuais: Status ──────────────────────────────────────────────

    def get_status(self, activation_id: str | int) -> dict:
        """
        Obtém status de um número comprado.
        
        Args:
            activation_id: ID da ativação
            
        Returns:
            dict com: {verificationType, sms, call, status, ...}
                verificationType: 0=Aguardando, 1=SMS, 2=Ligação
        """
        return self._get(action="getStatusV2", id=activation_id)

    def set_status(self, activation_id: str | int, status: int) -> dict:
        """
        Muda status de um número.
        
        Args:
            activation_id: ID da ativação
            status: Novo status:
                1 = SMS recebido
                3 = Refund
                6 = Finalizar
                8 = Cancelar
            
        Returns:
            dict com resposta da API
        """
        return self._get(action="setStatus", id=activation_id, status=status)

    def finish_order(self, activation_id: str | int) -> dict:
        """
        Finaliza um pedido (status = 6).
        
        Args:
            activation_id: ID da ativação
            
        Returns:
            dict com resposta da API
        """
        return self.set_status(activation_id, 6)

    def cancel_order(self, activation_id: str | int) -> dict:
        """
        Cancela um pedido (status = 8).
        
        Args:
            activation_id: ID da ativação
            
        Returns:
            dict com resposta da API
        """
        return self.set_status(activation_id, 8)

    def refund_order(self, activation_id: str | int) -> dict:
        """
        Pede reembolso de um pedido (status = 3).
        
        Args:
            activation_id: ID da ativação
            
        Returns:
            dict com resposta da API
        """
        return self.set_status(activation_id, 3)

    # ── Câmbio ────────────────────────────────────────────────────────────────

    @staticmethod
    def get_exchange_rate_usd_to_brl() -> float:
        """
        Obtém taxa de câmbio atual USD → BRL.
        
        Returns:
            Taxa de câmbio (ex: 5.25)
            
        Raises:
            requests.RequestException: Se não conseguir obter taxa
        """
        response = requests.get(EXCHANGE_URL, timeout=10)
        response.raise_for_status()
        rates = response.json()
        return rates["rates"]["BRL"]

    def usd_to_brl(self, value_usd: float) -> float:
        """
        Converte valor de USD para BRL.
        
        Args:
            value_usd: Valor em dólares
            
        Returns:
            Valor em reais
        """
        rate = self.get_exchange_rate_usd_to_brl()
        return value_usd * rate

    # ── Cálculo de Preços com Markup ──────────────────────────────────────────

    def calculate_sell_price_brl(self, cost_usd: float) -> float:
        """
        Calcula preço de venda em BRL com markup aplicado.
        
        Args:
            cost_usd: Custo em USD
            
        Returns:
            Preço de venda em reais com markup: cost_brl * (1 + MARKUP)
        """
        cost_brl = self.usd_to_brl(cost_usd)
        return round(cost_brl * (1 + configs.MARKUP), 2)

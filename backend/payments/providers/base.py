from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    name = ""

    @abstractmethod
    def create_payment(self, payment):
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(self, request):
        raise NotImplementedError

    def get_status(self, payment):
        return payment.status

    def refund(self, payment, amount=None):
        raise NotImplementedError("El proveedor todavía no implementa reembolsos.")

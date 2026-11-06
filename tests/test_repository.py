from payment_gateway.models import Payment, PaymentState, utc_now
from payment_gateway.repository import ReceiptRepository


def test_receipt_round_trip_and_queries():
    repository = ReceiptRepository()
    payment = Payment("pay_1", "order_1", "customer_1", 100, "USD", PaymentState.PENDING, utc_now(), utc_now())

    repository.save_payment(payment)

    assert repository.get_payment("pay_1") == payment
    assert repository.find_by_order("order_1") == [payment]
    assert repository.find_by_customer("customer_1") == [payment]


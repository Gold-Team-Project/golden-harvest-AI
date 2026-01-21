from enum import Enum

class DocumentType(Enum):
    INBOUND = "입고"
    OUTBOUND = "출고"
    PURCHASE = "발주"
    SALES = "주문"
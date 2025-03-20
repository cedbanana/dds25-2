from dataclasses import dataclass, field
import enum
from typing import List, Tuple
from proto import order_pb2, stock_pb2, payment_pb2, common_pb2


@dataclass
class Order:
    id: str
    paid: bool
    items: List[Tuple[str, int]] = field(default_factory=list)
    user_id: str = ""
    total_cost: int = 0

    def to_proto(self) -> order_pb2.Order:
        proto_items = []
        for id, quantity in self.items:
            proto_item = stock_pb2.Item(
                id=id,
                stock=quantity,  # using the "stock" field to represent quantity here
                price=0,
            )
            proto_items.append(proto_item)
        return order_pb2.Order(
            id=self.id,
            paid=self.paid,
            items=proto_items,
            user_id=self.user_id,
            total_cost=self.total_cost,
        )

    @classmethod
    def from_proto(cls, proto: order_pb2.Order) -> "Order":
        # Convert a protobuf Order message into our internal Order model.
        items = [(item.id, item.stock) for item in proto.items]
        return cls(
            id=proto.id,
            paid=proto.paid,
            items=items,
            user_id=proto.user_id,
            total_cost=proto.total_cost,
        )


@dataclass
class Stock:
    id: str
    stock: int
    price: int

    def to_proto(self) -> stock_pb2.Item:
        return stock_pb2.Item(id=self.id, stock=self.stock, price=self.price)

    @classmethod
    def from_proto(cls, proto: stock_pb2.Item) -> "Stock":
        return cls(id=proto.id, stock=proto.stock, price=proto.price)


@dataclass
class User:
    id: str
    credit: int

    def to_proto(self) -> payment_pb2.User:
        return payment_pb2.User(id=self.id, credit=self.credit)

    @classmethod
    def from_proto(cls, proto: payment_pb2.User) -> "User":
        return cls(id=proto.id, credit=proto.credit)


class TransactionStatus(enum.Enum):
    PENDING = 0
    SUCCESS = 1
    FAILURE = 2


@dataclass
class Transaction:
    tid: str
    status: TransactionStatus

    def to_proto(self) -> common_pb2.TransactionStatus:
        return common_pb2.TransactionStatus(
            tid=self.tid, success=self.status == TransactionStatus.SUCCESS
        )

    @classmethod
    def from_proto(cls, proto: common_pb2.TransactionStatus) -> "Transaction":
        return cls(
            tid=proto.tid,
            status=TransactionStatus.SUCCESS
            if proto.success
            else TransactionStatus.FAILURE,
        )

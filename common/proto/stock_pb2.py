# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: proto/stock.proto
# Protobuf Python Version: 5.29.2
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    2,
    '',
    'proto/stock.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from proto import common_pb2 as proto_dot_common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x11proto/stock.proto\x12\x05stock\x1a\x12proto/common.proto\"0\n\x04Item\x12\n\n\x02id\x18\x01 \x01(\t\x12\r\n\x05stock\x18\x02 \x01(\x05\x12\r\n\x05price\x18\x03 \x01(\x05\"\"\n\x11\x43reateItemRequest\x12\r\n\x05price\x18\x01 \x01(\x05\"%\n\x12\x43reateItemResponse\x12\x0f\n\x07item_id\x18\x01 \x01(\t\"\x1e\n\x0bItemRequest\x12\x0f\n\x07item_id\x18\x01 \x01(\t\"4\n\x0fStockAdjustment\x12\x0f\n\x07item_id\x18\x01 \x01(\t\x12\x10\n\x08quantity\x18\x02 \x01(\x05\"S\n\x17StockAdjustmentResponse\x12)\n\x06status\x18\x01 \x01(\x0b\x32\x19.common.OperationResponse\x12\r\n\x05price\x18\x02 \x01(\x05\"1\n\x13\x42ulkStockAdjustment\x12\x1a\n\x05items\x18\x01 \x03(\x0b\x32\x0b.stock.Item\"\\\n\x1b\x42ulkStockAdjustmentResponse\x12)\n\x06status\x18\x01 \x01(\x0b\x32\x19.common.OperationResponse\x12\x12\n\ntotal_cost\x18\x02 \x01(\x05\x32\xad\x03\n\x0cStockService\x12+\n\x08\x46indItem\x12\x12.stock.ItemRequest\x1a\x0b.stock.Item\x12=\n\x08\x41\x64\x64Stock\x12\x16.stock.StockAdjustment\x1a\x19.common.OperationResponse\x12\x45\n\x0bRemoveStock\x12\x16.stock.StockAdjustment\x1a\x1e.stock.StockAdjustmentResponse\x12K\n\tBulkOrder\x12\x1a.stock.BulkStockAdjustment\x1a\".stock.BulkStockAdjustmentResponse\x12L\n\nBulkRefund\x12\x1a.stock.BulkStockAdjustment\x1a\".stock.BulkStockAdjustmentResponse\x12O\n\x17UpdateTransactionStatus\x12\x19.common.TransactionStatus\x1a\x19.common.TransactionStatusb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'proto.stock_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_ITEM']._serialized_start=48
  _globals['_ITEM']._serialized_end=96
  _globals['_CREATEITEMREQUEST']._serialized_start=98
  _globals['_CREATEITEMREQUEST']._serialized_end=132
  _globals['_CREATEITEMRESPONSE']._serialized_start=134
  _globals['_CREATEITEMRESPONSE']._serialized_end=171
  _globals['_ITEMREQUEST']._serialized_start=173
  _globals['_ITEMREQUEST']._serialized_end=203
  _globals['_STOCKADJUSTMENT']._serialized_start=205
  _globals['_STOCKADJUSTMENT']._serialized_end=257
  _globals['_STOCKADJUSTMENTRESPONSE']._serialized_start=259
  _globals['_STOCKADJUSTMENTRESPONSE']._serialized_end=342
  _globals['_BULKSTOCKADJUSTMENT']._serialized_start=344
  _globals['_BULKSTOCKADJUSTMENT']._serialized_end=393
  _globals['_BULKSTOCKADJUSTMENTRESPONSE']._serialized_start=395
  _globals['_BULKSTOCKADJUSTMENTRESPONSE']._serialized_end=487
  _globals['_STOCKSERVICE']._serialized_start=490
  _globals['_STOCKSERVICE']._serialized_end=919
# @@protoc_insertion_point(module_scope)

# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: proto/order.proto
# Protobuf Python Version: 5.29.0
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
    0,
    '',
    'proto/order.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from proto import stock_pb2 as proto_dot_stock__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x11proto/order.proto\x12\x05order\x1a\x11proto/stock.proto\"b\n\x05Order\x12\n\n\x02id\x18\x01 \x01(\t\x12\x0c\n\x04paid\x18\x02 \x01(\x05\x12\x1a\n\x05items\x18\x03 \x03(\x0b\x32\x0b.stock.Item\x12\x0f\n\x07user_id\x18\x04 \x01(\t\x12\x12\n\ntotal_cost\x18\x05 \x01(\x05\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'proto.order_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_ORDER']._serialized_start=47
  _globals['_ORDER']._serialized_end=145
# @@protoc_insertion_point(module_scope)

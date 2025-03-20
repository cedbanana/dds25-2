# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: proto/payment.proto
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
    'proto/payment.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from proto import common_pb2 as proto_dot_common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x13proto/payment.proto\x12\x07payment\x1a\x12proto/common.proto\"\"\n\x04User\x12\n\n\x02id\x18\x01 \x01(\t\x12\x0e\n\x06\x63redit\x18\x02 \x01(\x05\"2\n\x0f\x41\x64\x64\x46undsRequest\x12\x0f\n\x07user_id\x18\x01 \x01(\t\x12\x0e\n\x06\x61mount\x18\x02 \x01(\x05\"1\n\x0ePaymentRequest\x12\x0f\n\x07user_id\x18\x01 \x01(\t\x12\x0e\n\x06\x61mount\x18\x02 \x01(\x05\"1\n\x0fPaymentResponse\x12\x0f\n\x07success\x18\x01 \x01(\x08\x12\r\n\x05\x65rror\x18\x02 \x01(\t\"\"\n\x0f\x46indUserRequest\x12\x0f\n\x07user_id\x18\x01 \x01(\t\"/\n\x10\x46indUserResponse\x12\x1b\n\x04user\x18\x01 \x01(\x0b\x32\r.payment.User2\xa8\x02\n\x0ePaymentService\x12?\n\x08\x41\x64\x64\x46unds\x12\x18.payment.AddFundsRequest\x1a\x19.common.OperationResponse\x12\x43\n\x0eProcessPayment\x12\x17.payment.PaymentRequest\x1a\x18.payment.PaymentResponse\x12?\n\x08\x46indUser\x12\x18.payment.FindUserRequest\x1a\x19.payment.FindUserResponse\x12O\n\x17UpdateTransactionStatus\x12\x19.common.TransactionStatus\x1a\x19.common.TransactionStatusb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'proto.payment_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_USER']._serialized_start=52
  _globals['_USER']._serialized_end=86
  _globals['_ADDFUNDSREQUEST']._serialized_start=88
  _globals['_ADDFUNDSREQUEST']._serialized_end=138
  _globals['_PAYMENTREQUEST']._serialized_start=140
  _globals['_PAYMENTREQUEST']._serialized_end=189
  _globals['_PAYMENTRESPONSE']._serialized_start=191
  _globals['_PAYMENTRESPONSE']._serialized_end=240
  _globals['_FINDUSERREQUEST']._serialized_start=242
  _globals['_FINDUSERREQUEST']._serialized_end=276
  _globals['_FINDUSERRESPONSE']._serialized_start=278
  _globals['_FINDUSERRESPONSE']._serialized_end=325
  _globals['_PAYMENTSERVICE']._serialized_start=328
  _globals['_PAYMENTSERVICE']._serialized_end=624
# @@protoc_insertion_point(module_scope)

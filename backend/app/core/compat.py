"""
Cross-database compatibility types.
Uses native PostgreSQL types when available, falls back to SQLite-compatible types.
"""

import uuid
import json
from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy.dialects import postgresql


class GUID(TypeDecorator):
    """Platform-independent UUID type. Uses PostgreSQL UUID, falls back to CHAR(36)."""
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(str(value))
        return value


class JSONType(TypeDecorator):
    """Platform-independent JSON type. Uses PostgreSQL JSONB, falls back to TEXT with JSON serialization."""
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value  # JSONB handles it natively
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value

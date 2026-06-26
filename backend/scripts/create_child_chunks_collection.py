#!/usr/bin/env python3
"""Create the Milvus child chunk collection used by the RAG retriever.

Run from the backend directory:
    python scripts/create_child_chunks_collection.py

The script reads backend/.env through app.core.config and creates the collection
named by RAG_MILVUS_COLLECTION, with vector dimension RAG_MILVUS_DIM.
"""

from __future__ import annotations

import sys


def _field_summary(collection) -> str:
    lines: list[str] = []
    for field in collection.schema.fields:
        extra = ""
        if getattr(field, "params", None):
            extra = f" {field.params}"
        primary = " primary" if getattr(field, "is_primary", False) else ""
        lines.append(f"  - {field.name}: {field.dtype}{primary}{extra}")
    return "\n".join(lines)


def main() -> int:
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

    from app.core.config import get_settings

    settings = get_settings()
    alias = "rag_create_child_chunks"
    collection_name = settings.milvus_collection

    print("=== Milvus child_chunks collection setup ===")
    print(f"Milvus: {settings.milvus_host}:{settings.milvus_port}")
    print(f"Collection: {collection_name}")
    print(f"Embedding dim: {settings.milvus_dim}")

    connections.connect(
        alias=alias,
        host=settings.milvus_host,
        port=str(settings.milvus_port),
        timeout=10,
    )

    if utility.has_collection(collection_name, using=alias):
        collection = Collection(collection_name, using=alias)
        vector_fields = [field for field in collection.schema.fields if field.name == "embedding"]
        if vector_fields:
            existing_dim = int(vector_fields[0].params.get("dim", 0))
            if existing_dim != settings.milvus_dim:
                raise RuntimeError(
                    f"Collection exists but embedding dim is {existing_dim}, "
                    f"expected {settings.milvus_dim}. Drop/recreate manually if this is intentional."
                )
        print("Collection already exists; schema:")
        print(_field_summary(collection))
        connections.disconnect(alias)
        return 0

    fields = [
        FieldSchema(
            name="child_chunk_id",
            dtype=DataType.VARCHAR,
            is_primary=True,
            max_length=128,
            description="Unique child chunk ID",
        ),
        FieldSchema(
            name="parent_chunk_id",
            dtype=DataType.VARCHAR,
            max_length=128,
            description="Linked MySQL parent_chunk.parent_chunk_id",
        ),
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=8192,
            description="Child chunk text used for retrieval display/debug",
        ),
        FieldSchema(
            name="doc_id",
            dtype=DataType.VARCHAR,
            max_length=128,
            description="Source document ID",
        ),
        FieldSchema(
            name="kb_id",
            dtype=DataType.VARCHAR,
            max_length=128,
            description="Knowledge-base ID",
        ),
        FieldSchema(
            name="chunk_index",
            dtype=DataType.INT64,
            description="Child chunk index inside its parent chunk",
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=settings.milvus_dim,
            description="Embedding vector",
        ),
    ]
    schema = CollectionSchema(
        fields=fields,
        description="RAG child chunk vectors; parent text is stored in MySQL parent_chunk.",
        enable_dynamic_field=False,
    )
    collection = Collection(
        name=collection_name,
        schema=schema,
        using=alias,
        consistency_level="Bounded",
    )

    collection.create_index(
        field_name="embedding",
        index_params={
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 128},
        },
    )
    collection.flush()

    print("Collection created successfully; schema:")
    print(_field_summary(collection))
    connections.disconnect(alias)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

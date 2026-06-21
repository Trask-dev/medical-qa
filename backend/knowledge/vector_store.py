"""
向量数据库集成：InMemory / Milvus Lite / Milvus Remote
支持余弦相似度、欧氏距离，配置从 .env 读取
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── 配置 ──────────────────────────────

@dataclass
class VectorStoreConfig:
    backend: str = "memory"
    milvus_uri: str = "./data/milvus_lite.db"
    milvus_token: str = ""
    collection_name: str = "medical_knowledge"
    vector_dim: int = 1536
    metric_type: str = "COSINE"
    index_type: str = "IVF_FLAT"
    nlist: int = 128


def load_vector_config() -> VectorStoreConfig:
    return VectorStoreConfig(
        backend=os.getenv("VECTOR_BACKEND", "memory"),
        milvus_uri=os.getenv("MILVUS_URI", "./data/milvus_lite.db"),
        milvus_token=os.getenv("MILVUS_TOKEN", ""),
        collection_name=os.getenv("MILVUS_COLLECTION", "medical_knowledge"),
        vector_dim=int(os.getenv("VECTOR_DIM", "1536")),
        metric_type=os.getenv("VECTOR_METRIC", "COSINE"),
        nlist=int(os.getenv("VECTOR_NLIST", "128")),
    )


# ── 抽象接口 ──────────────────────────

class VectorStore(ABC):
    config: VectorStoreConfig

    @abstractmethod
    async def create_collection(self) -> None: ...

    @abstractmethod
    async def insert(self, vectors: list[list[float]], metadata: list[dict]) -> list[str]: ...

    @abstractmethod
    async def search(self, query_vector: list[float], top_k: int = 10,
                     filters: dict | None = None) -> list[dict]: ...

    @abstractmethod
    async def update(self, id: str, vector: list[float], metadata: dict) -> bool: ...

    @abstractmethod
    async def delete(self, ids: list[str]) -> int: ...

    @abstractmethod
    async def count(self) -> int: ...


# ── Milvus 实现 ───────────────────────

class MilvusVectorStore(VectorStore):
    def __init__(self, config: VectorStoreConfig | None = None) -> None:
        self.config = config or load_vector_config()
        self._col = None

    @property
    def _collection(self):
        if self._col is None:
            self._col = self._init_milvus()
        return self._col

    def _init_milvus(self):
        try:
            from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType
            is_remote = ":" in self.config.milvus_uri.replace("./", "").replace("\\", "")
            if is_remote:
                connections.connect(
                    alias="default",
                    uri=self.config.milvus_uri,
                    token=self.config.milvus_token or None,
                )
            else:
                local_path = self.config.milvus_uri
                os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
                connections.connect(alias="default", uri=local_path)

            if not self._collection_exists(Collection):
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
                    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self.config.vector_dim),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                    FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=512),
                    FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=1024),
                    FieldSchema(name="authority_score", dtype=DataType.FLOAT),
                    FieldSchema(name="freshness_score", dtype=DataType.FLOAT),
                    FieldSchema(name="publish_year", dtype=DataType.INT32),
                ]
                schema = CollectionSchema(fields, description="Medical knowledge base")
                col = Collection(name=self.config.collection_name, schema=schema)
                index_params = {
                    "metric_type": self.config.metric_type,
                    "index_type": self.config.index_type,
                    "params": {"nlist": self.config.nlist},
                }
                col.create_index(field_name="vector", index_params=index_params)
                col.load()
                logger.info("Milvus collection '%s' created with %s index", self.config.collection_name, self.config.index_type)
                return col

            col = Collection(name=self.config.collection_name)
            col.load()
            logger.info("Milvus collection '%s' loaded, count=%d", self.config.collection_name, col.num_entities)
            return col

        except ImportError:
            logger.warning("pymilvus not installed, falling back to InMemoryVectorStore")
            return None

    def _collection_exists(self, Collection) -> bool:
        from pymilvus import utility
        return utility.has_collection(self.config.collection_name)

    async def create_collection(self) -> None:
        self._collection

    async def insert(self, vectors: list[list[float]], metadata: list[dict]) -> list[str]:
        col = self._collection
        if col is None:
            return await _fallback_store(config=self.config).insert(vectors, metadata)
        ids = [m.get("knowledge_entry_id", f"ke_{i}") for i, m in enumerate(metadata)]
        rows = [
            ids,
            vectors,
            [m.get("content", "") for m in metadata],
            [m.get("source", "") for m in metadata],
            [m.get("source_type", "") for m in metadata],
            [m.get("title", "") for m in metadata],
            [m.get("authority_score", 0.5) for m in metadata],
            [m.get("freshness_score", 1.0) for m in metadata],
            [m.get("publish_year", 2024) for m in metadata],
        ]
        col.insert(rows)
        col.flush()
        logger.info("Inserted %d vectors into Milvus", len(ids))
        return ids

    async def search(self, query_vector: list[float], top_k: int = 10,
                     filters: dict | None = None) -> list[dict]:
        col = self._collection
        if col is None:
            return await _fallback_store(config=self.config).search(query_vector, top_k)
        expr = _build_filter_expr(filters) if filters else None
        results = col.search(
            data=[query_vector], anns_field="vector",
            param={"metric_type": self.config.metric_type, "params": {"nprobe": 16}},
            limit=top_k, expr=expr,
            output_fields=["content", "source", "source_type", "title",
                           "authority_score", "freshness_score", "publish_year"],
        )
        output = []
        for hits in results:
            for h in hits:
                output.append({
                    "id": h.id, "score": h.distance if self.config.metric_type == "IP" else 1 - h.distance,
                    "metadata": {
                        "content": h.entity.get("content", ""),
                        "source": h.entity.get("source", ""),
                        "source_type": h.entity.get("source_type", ""),
                        "title": h.entity.get("title", ""),
                        "authority_score": h.entity.get("authority_score", 0.5),
                        "freshness_score": h.entity.get("freshness_score", 1.0),
                        "publish_year": h.entity.get("publish_year", 2024),
                    },
                })
        return output

    async def update(self, id: str, vector: list[float], metadata: dict) -> bool:
        col = self._collection
        if col is None:
            return False
        try:
            col.delete(f'id == "{id}"')
            await self.insert([vector], [metadata])
            return True
        except Exception as e:
            logger.error("Milvus update failed for %s: %s", id, e)
            return False

    async def delete(self, ids: list[str]) -> int:
        col = self._collection
        if col is None:
            return await _fallback_store(config=self.config).delete(ids)
        expr = " || ".join(f'id == "{i}"' for i in ids)
        col.delete(expr)
        col.flush()
        return len(ids)

    async def count(self) -> int:
        col = self._collection
        if col is None:
            return await _fallback_store(config=self.config).count()
        col.flush()
        return col.num_entities


# ── 内存实现 (降级) ───────────────────

class InMemoryVectorStore(VectorStore):
    def __init__(self, config: VectorStoreConfig | None = None) -> None:
        self.config = config or load_vector_config()
        self._store: dict[str, tuple[list[float], dict]] = {}
        self._counter = 0

    async def create_collection(self) -> None: pass

    async def insert(self, vectors: list[list[float]], metadata: list[dict]) -> list[str]:
        ids = []
        for vec, meta in zip(vectors, metadata):
            self._counter += 1
            vid = meta.get("knowledge_entry_id", f"ke_{self._counter}")
            self._store[vid] = (vec, meta)
            ids.append(vid)
        return ids

    async def search(self, query_vector: list[float], top_k: int = 10,
                     filters: dict | None = None) -> list[dict]:
        metric = self.config.metric_type
        results = []
        for vid, (vec, meta) in self._store.items():
            score = _cosine_similarity(query_vector, vec) if metric == "COSINE" else _euclidean_score(query_vector, vec)
            results.append({"id": vid, "score": score, "metadata": meta})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def update(self, id: str, vector: list[float], metadata: dict) -> bool:
        self._store[id] = (vector, metadata)
        return True

    async def delete(self, ids: list[str]) -> int:
        removed = 0
        for vid in ids:
            if vid in self._store:
                del self._store[vid]
                removed += 1
        return removed

    async def count(self) -> int:
        return len(self._store)


# ── 工厂 ──────────────────────────────

_fallback_store: InMemoryVectorStore | None = None


def _fallback_store(config: VectorStoreConfig | None = None) -> InMemoryVectorStore:
    global _fallback_store
    if _fallback_store is None:
        _fallback_store = InMemoryVectorStore(config)
    return _fallback_store


def get_vector_store(backend: str = "") -> VectorStore:
    config = load_vector_config()
    backend = backend or config.backend
    if backend == "milvus":
        store = MilvusVectorStore(config)
        if store._collection is not None:
            return store
        logger.info("Milvus unavailable, falling back to memory store")
    return InMemoryVectorStore(config)


# ── 距离计算 ──────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x ** 2 for x in a) ** 0.5
    nb = sum(x ** 2 for x in b) ** 0.5
    return max(0.0, dot / (na * nb + 1e-10))


def _euclidean_score(a: list[float], b: list[float]) -> float:
    dist = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
    return 1.0 / (1.0 + dist)


def _build_filter_expr(filters: dict) -> str:
    parts = []
    for k, v in filters.items():
        if isinstance(v, str):
            parts.append(f'{k} == "{v}"')
        elif isinstance(v, (int, float)):
            parts.append(f"{k} == {v}")
    return " && ".join(parts) if parts else ""

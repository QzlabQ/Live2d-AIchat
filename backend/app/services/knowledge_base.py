from __future__ import annotations

import hashlib
import math
import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import KnowledgeDoc

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SHEET_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

SUPPORTED_SUFFIXES = {".docx", ".pdf", ".txt", ".md", ".xlsx"}
TEMP_FILE_PREFIXES = ("~$",)
NOISE_PATTERNS = (
    re.compile(r"第\s*\d+\s*页"),
    re.compile(r"版权(?:所有)?[:：]?\s*.*"),
    re.compile(r"_{5,}"),
)


class KnowledgeSkipFile(RuntimeError):
    """Raised when a source file should be skipped during knowledge import."""


class KnowledgeDependencyError(RuntimeError):
    """Raised when an optional dependency required by the knowledge pipeline is missing."""


@dataclass(slots=True)
class ParsedKnowledgeDocument:
    filename: str
    source_path: Path
    title: str
    category: str
    text: str
    source_kind: str
    metadata: dict[str, str | int | float | bool]


@dataclass(slots=True)
class KnowledgeChunk:
    text: str
    metadata: dict[str, str | int | float | bool]


@dataclass(slots=True)
class ImportedKnowledgeDoc:
    doc_id: str
    filename: str
    category: str
    chunk_count: int


@dataclass(slots=True)
class VectorStoreHit:
    chunk_id: str
    text: str
    metadata: dict[str, str | int | float | bool]
    distance: float | None


@dataclass(slots=True)
class KnowledgeImportReport:
    imported: list[ImportedKnowledgeDoc]
    skipped: list[tuple[str, str]]
    errors: list[tuple[str, str]]
    collection_count: int


def clean_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\u3000", " ").replace("\xa0", " ").strip()
    for pattern in NOISE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def infer_category(filename: str) -> str:
    normalized = filename.lower()

    if any(token in normalized for token in ("faq", "常见问题", "问答")):
        return "faq"
    if any(token in normalized for token in ("路线", "路书", "攻略", "导览", "指南", "游览")):
        return "route"
    if any(token in normalized for token in ("设施", "停车", "交通", "服务", "游客中心")):
        return "facility"
    if any(token in normalized for token in ("历史", "文化", "沿革", "渊源")):
        return "history"
    return "scenery"


class KnowledgeDocumentParser:
    def discover_files(self, source: Path) -> list[Path]:
        source = source.expanduser()
        if not source.exists():
            raise FileNotFoundError(f"Knowledge source path does not exist: {source}")

        if source.is_file():
            if self.is_supported(source):
                return [source]
            raise KnowledgeSkipFile(f"Unsupported file suffix: {source.suffix}")

        files = [path for path in source.rglob("*") if path.is_file() and self.is_supported(path)]
        return sorted(files)

    @staticmethod
    def is_supported(path: Path) -> bool:
        return (
            path.suffix.lower() in SUPPORTED_SUFFIXES
            and not any(path.name.startswith(prefix) for prefix in TEMP_FILE_PREFIXES)
        )

    def parse(self, path: Path) -> ParsedKnowledgeDocument:
        suffix = path.suffix.lower()
        if suffix == ".docx":
            return self._parse_docx(path)
        if suffix in {".txt", ".md"}:
            return self._parse_text(path)
        if suffix == ".xlsx":
            return self._parse_xlsx(path)
        if suffix == ".pdf":
            return self._parse_pdf(path)
        raise KnowledgeSkipFile(f"Unsupported file suffix: {suffix}")

    def _parse_docx(self, path: Path) -> ParsedKnowledgeDocument:
        with ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))

        lines: list[str] = []
        for paragraph in root.findall(".//w:p", WORD_NS):
            fragments = [node.text for node in paragraph.findall(".//w:t", WORD_NS) if node.text]
            line = "".join(fragments).strip()
            if line:
                lines.append(line)

        if not lines:
            raise KnowledgeSkipFile("Document does not contain readable text paragraphs.")

        title = lines[0]
        text = clean_text("\n".join(lines))
        return ParsedKnowledgeDocument(
            filename=path.name,
            source_path=path.resolve(),
            title=title,
            category=infer_category(path.name),
            text=text,
            source_kind="docx",
            metadata={"source_kind": "docx"},
        )

    def _parse_text(self, path: Path) -> ParsedKnowledgeDocument:
        content: str | None = None
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                content = path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            raise KnowledgeSkipFile("Unable to decode text file with utf-8 or gb18030.")

        text = clean_text(content)
        if not text:
            raise KnowledgeSkipFile("Text file is empty after cleanup.")

        title = text.splitlines()[0].strip() or path.stem
        return ParsedKnowledgeDocument(
            filename=path.name,
            source_path=path.resolve(),
            title=title,
            category=infer_category(path.name),
            text=text,
            source_kind="text",
            metadata={"source_kind": "text"},
        )

    def _parse_pdf(self, path: Path) -> ParsedKnowledgeDocument:
        try:
            import fitz  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency based
            raise KnowledgeDependencyError(
                "PDF parsing requires PyMuPDF. Install backend/requirements.knowledge.txt first."
            ) from exc

        document = fitz.open(path)
        try:
            pages = [page.get_text("text") for page in document]
        finally:
            document.close()

        text = clean_text("\n\n".join(filter(None, pages)))
        if not text:
            raise KnowledgeSkipFile("PDF does not contain extractable text.")

        title = text.splitlines()[0].strip() or path.stem
        return ParsedKnowledgeDocument(
            filename=path.name,
            source_path=path.resolve(),
            title=title,
            category=infer_category(path.name),
            text=text,
            source_kind="pdf",
            metadata={"source_kind": "pdf"},
        )

    def _parse_xlsx(self, path: Path) -> ParsedKnowledgeDocument:
        workbook_rows = self._extract_xlsx_rows(path)
        if not workbook_rows:
            raise KnowledgeSkipFile("Workbook does not contain readable rows.")

        sheet_name, rows = workbook_rows[0]
        header = rows[0]
        normalized_header = {str(cell).strip().lower() for cell in header}

        if {"tourist_id", "user_nickname", "attraction_name", "attraction_content"}.issubset(
            normalized_header
        ):
            raise KnowledgeSkipFile(
                "Workbook is a tourist behavior dataset and is not suitable for scenic QA knowledge import."
            )

        if {"景区名称", "景点名称", "详细介绍"}.issubset({str(cell).strip() for cell in header}):
            blocks = self._build_structured_scenic_blocks(rows)
            if not blocks:
                raise KnowledgeSkipFile("Structured workbook does not contain scenic rows.")

            title = sheet_name.strip() or path.stem
            text = clean_text(f"{title}\n\n" + "\n\n".join(blocks))
            return ParsedKnowledgeDocument(
                filename=path.name,
                source_path=path.resolve(),
                title=title,
                category=infer_category(path.name),
                text=text,
                source_kind="xlsx",
                metadata={"source_kind": "xlsx", "sheet_name": sheet_name},
            )

        raise KnowledgeSkipFile("Workbook format is unsupported for Phase 1 knowledge import.")

    @staticmethod
    def _build_structured_scenic_blocks(rows: list[list[str]]) -> list[str]:
        header = [str(cell).strip() for cell in rows[0]]
        blocks: list[str] = []

        for row in rows[1:]:
            record = {
                header[index]: (row[index] if index < len(row) else "")
                for index in range(len(header))
            }
            spot_name = str(record.get("景点名称", "")).strip()
            if not spot_name:
                continue

            parts: list[str] = []
            for key, value in record.items():
                normalized = str(value).strip()
                if normalized:
                    parts.append(f"{key}：{normalized}")

            if parts:
                blocks.append("\n".join(parts))

        return blocks

    @staticmethod
    def _extract_xlsx_rows(path: Path) -> list[tuple[str, list[list[str]]]]:
        with ZipFile(path) as archive:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.findall("main:si", SHEET_NS):
                    text = "".join(node.text or "" for node in item.findall(".//main:t", SHEET_NS))
                    shared_strings.append(text)

            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            relationship_map = {
                item.attrib["Id"]: item.attrib["Target"]
                for item in relationships
                if item.attrib.get("Id")
            }

            extracted: list[tuple[str, list[list[str]]]] = []
            sheets = workbook.find("main:sheets", SHEET_NS)
            if sheets is None:
                return extracted

            for sheet in sheets:
                name = sheet.attrib.get("name", "").strip() or "Sheet"
                relationship_id = sheet.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                if not relationship_id:
                    continue

                target = relationship_map.get(relationship_id)
                if not target:
                    continue

                xml_root = ET.fromstring(archive.read(f"xl/{target}"))
                sheet_data = xml_root.find("main:sheetData", SHEET_NS)
                if sheet_data is None:
                    continue

                rows: list[list[str]] = []
                for row in sheet_data.findall("main:row", SHEET_NS):
                    values: list[str] = []
                    for cell in row.findall("main:c", SHEET_NS):
                        value_node = cell.find("main:v", SHEET_NS)
                        if value_node is None:
                            values.append("")
                            continue

                        raw_value = value_node.text or ""
                        if cell.attrib.get("t") == "s" and raw_value.isdigit():
                            values.append(shared_strings[int(raw_value)])
                        else:
                            values.append(raw_value)

                    if any(str(value).strip() for value in values):
                        rows.append(values)

                if rows:
                    extracted.append((name, rows))

            return extracted


class KnowledgeTextChunker:
    separators = ["\n\n", "\n", "。", "！", "？", "；", "，", "、", " "]

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(self, doc_id: str, document: ParsedKnowledgeDocument) -> list[KnowledgeChunk]:
        raw_chunks = self._split_text(document.text)
        chunks: list[KnowledgeChunk] = []

        for index, text in enumerate(raw_chunks):
            metadata: dict[str, str | int | float | bool] = {
                "doc_id": doc_id,
                "filename": document.filename,
                "title": document.title,
                "category": document.category,
                "source_kind": document.source_kind,
                "chunk_index": index,
                "source_path": document.source_path.as_posix(),
            }
            metadata.update(document.metadata)
            chunks.append(KnowledgeChunk(text=text, metadata=metadata))

        return chunks

    def _split_text(self, text: str) -> list[str]:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=self.separators,
                length_function=len,
            )
            return [clean_text(chunk) for chunk in splitter.split_text(text) if clean_text(chunk)]
        except ImportError:
            return self._fallback_split(text)

    def _fallback_split(self, text: str) -> list[str]:
        content = text.strip()
        if not content:
            return []

        if len(content) <= self.chunk_size:
            return [content]

        chunks: list[str] = []
        start = 0
        total_length = len(content)

        while start < total_length:
            tentative_end = min(start + self.chunk_size, total_length)
            end = tentative_end

            if tentative_end < total_length:
                candidate = content[start:tentative_end]
                lower_bound = max(int(len(candidate) * 0.6), 1)
                for separator in self.separators:
                    index = candidate.rfind(separator)
                    if index >= lower_bound:
                        end = start + index + len(separator)
                        break

            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= total_length:
                break

            next_start = max(0, end - self.chunk_overlap)
            while next_start < total_length and content[next_start].isspace():
                next_start += 1

            if next_start <= start:
                next_start = end
            start = next_start

        return chunks


class HashEmbeddingService:
    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        values = [0.0] * self.dimension
        if not text:
            return values

        for token in re.findall(r"\w+|[\u4e00-\u9fff]", text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = struct.unpack(">Q", digest)[0] % self.dimension
            values[index] += 1.0

        norm = math.sqrt(sum(value * value for value in values))
        if norm > 0:
            values = [value / norm for value in values]
        return values


class BgeM3EmbeddingService:
    def __init__(self, model_name: str, device: str, batch_size: int) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - dependency based
            raise KnowledgeDependencyError(
                "bge-m3 embedding requires sentence-transformers. Install backend/requirements.knowledge.txt first."
            ) from exc

        try:
            self.model = SentenceTransformer(model_name, device=device)
        except Exception as exc:  # pragma: no cover - network / local model dependent
            raise KnowledgeDependencyError(
                "Failed to load bge-m3. If the online download is unstable, download the full "
                "BAAI/bge-m3 model snapshot to a local directory and point "
                "KNOWLEDGE_EMBEDDING_MODEL to that directory."
            ) from exc
        self.batch_size = batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()


def build_embedding_service(settings: Settings) -> HashEmbeddingService | BgeM3EmbeddingService:
    engine = settings.knowledge_embedding_engine.strip().lower()
    if engine == "hash":
        return HashEmbeddingService()
    if engine == "bge-m3":
        return BgeM3EmbeddingService(
            model_name=settings.knowledge_embedding_model,
            device=settings.knowledge_embedding_device,
            batch_size=settings.knowledge_embedding_batch_size,
        )
    raise ValueError(f"Unsupported knowledge embedding engine: {settings.knowledge_embedding_engine}")


class KnowledgeVectorStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        try:
            import chromadb  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency based
            raise KnowledgeDependencyError(
                "ChromaDB support requires chromadb. Install backend/requirements.knowledge.txt first."
            ) from exc

        base_dir = Path(self.settings.knowledge_base_dir).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(base_dir))
        self._collection = None

    def collection(self):
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name=self.settings.knowledge_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def upsert_chunks(self, doc_id: str, chunks: list[KnowledgeChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk count does not match embedding count.")

        ids = [f"{doc_id}:{index}" for index in range(len(chunks))]
        documents = [chunk.text for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        self.collection().upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    def delete_document(self, doc_id: str) -> None:
        self.collection().delete(where={"doc_id": doc_id})

    def reset(self) -> None:
        try:
            self._client.delete_collection(self.settings.knowledge_collection_name)
        except Exception:
            pass
        self._collection = None

    def count(self) -> int:
        return int(self.collection().count())

    def query_chunks(self, query_embedding: list[float], n_results: int) -> list[VectorStoreHit]:
        if n_results <= 0:
            return []

        if self.count() == 0:
            return []

        payload = self.collection().query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        ids = payload.get("ids", [[]])[0]
        documents = payload.get("documents", [[]])[0]
        metadatas = payload.get("metadatas", [[]])[0]
        distances = payload.get("distances", [[]])[0]

        hits: list[VectorStoreHit] = []
        for index, chunk_id in enumerate(ids):
            hits.append(
                VectorStoreHit(
                    chunk_id=str(chunk_id),
                    text=str(documents[index]) if index < len(documents) else "",
                    metadata=metadatas[index] if index < len(metadatas) and metadatas[index] else {},
                    distance=float(distances[index]) if index < len(distances) and distances[index] is not None else None,
                )
            )
        return hits


class KnowledgeImporter:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self.parser = KnowledgeDocumentParser()
        self.chunker = KnowledgeTextChunker(
            chunk_size=self.settings.knowledge_chunk_size,
            chunk_overlap=self.settings.knowledge_chunk_overlap,
        )
        self._vector_store: KnowledgeVectorStore | None = None

    @property
    def vector_store(self) -> KnowledgeVectorStore:
        if self._vector_store is None:
            self._vector_store = KnowledgeVectorStore(self.settings)
        return self._vector_store

    async def import_source(self, source: Path, reset: bool = False) -> KnowledgeImportReport:
        paths = self.parser.discover_files(source)
        if reset:
            await self._reset_all()

        report = KnowledgeImportReport(imported=[], skipped=[], errors=[], collection_count=0)
        embedder = build_embedding_service(self.settings)

        async with self.session_factory() as db:
            for path in paths:
                try:
                    parsed = self.parser.parse(path)
                except KnowledgeSkipFile as exc:
                    report.skipped.append((path.name, str(exc)))
                    continue
                except Exception as exc:
                    report.errors.append((path.name, str(exc)))
                    continue

                knowledge_doc: KnowledgeDoc | None = None
                try:
                    await self._delete_existing_by_filename(db, parsed.filename)

                    knowledge_doc = KnowledgeDoc(
                        filename=parsed.filename,
                        category=parsed.category,
                        stored_path=str(parsed.source_path),
                        status="processing",
                        chunk_count=0,
                        error_message="",
                    )
                    db.add(knowledge_doc)
                    await db.commit()
                    await db.refresh(knowledge_doc)

                    imported = await self._process_document_row(db, knowledge_doc, parsed, embedder=embedder)
                    report.imported.append(imported)
                except Exception as exc:
                    await db.rollback()
                    if knowledge_doc is not None:
                        await self._mark_doc_error(db, knowledge_doc.id, str(exc))
                    report.errors.append((parsed.filename, str(exc)))

        report.collection_count = self.vector_store.count()
        return report

    async def import_existing_document(
        self,
        doc_id: str,
        source: Path,
        *,
        filename: str,
        category: str,
    ) -> ImportedKnowledgeDoc:
        parsed = self.parser.parse(source)
        parsed = ParsedKnowledgeDocument(
            filename=filename,
            source_path=parsed.source_path,
            title=parsed.title,
            category=category,
            text=parsed.text,
            source_kind=parsed.source_kind,
            metadata=parsed.metadata,
        )
        embedder = build_embedding_service(self.settings)

        async with self.session_factory() as db:
            knowledge_doc = await db.get(KnowledgeDoc, doc_id)
            if knowledge_doc is None:
                raise RuntimeError(f"Knowledge document not found: {doc_id}")

            try:
                imported = await self._process_document_row(db, knowledge_doc, parsed, embedder=embedder)
            except Exception as exc:
                await db.rollback()
                await self._mark_doc_error(db, doc_id, str(exc))
                raise
        return imported

    async def delete_document(self, doc_id: str, db: AsyncSession) -> KnowledgeDoc | None:
        document = await db.get(KnowledgeDoc, doc_id)
        if document is None:
            return None

        self.vector_store.delete_document(doc_id)
        self._remove_stored_file(document.stored_path)
        await db.delete(document)
        await db.commit()
        return document

    async def _reset_all(self) -> None:
        self.vector_store.reset()
        async with self.session_factory() as db:
            await db.execute(delete(KnowledgeDoc))
            await db.commit()

    async def _delete_existing_by_filename(self, db: AsyncSession, filename: str) -> None:
        result = await db.execute(select(KnowledgeDoc).where(KnowledgeDoc.filename == filename))
        existing_docs = list(result.scalars())
        if not existing_docs:
            return

        for document in existing_docs:
            self.vector_store.delete_document(document.id)
            self._remove_stored_file(document.stored_path)
            await db.delete(document)
        await db.commit()

    async def _process_document_row(
        self,
        db: AsyncSession,
        knowledge_doc: KnowledgeDoc,
        parsed: ParsedKnowledgeDocument,
        *,
        embedder,
    ) -> ImportedKnowledgeDoc:
        chunks = self.chunker.chunk_document(knowledge_doc.id, parsed)
        if not chunks:
            raise RuntimeError("No chunks were produced after splitting.")

        embeddings = embedder.embed_documents([chunk.text for chunk in chunks])
        self.vector_store.delete_document(knowledge_doc.id)
        self.vector_store.upsert_chunks(knowledge_doc.id, chunks, embeddings)

        knowledge_doc.filename = parsed.filename
        knowledge_doc.category = parsed.category
        knowledge_doc.stored_path = str(parsed.source_path)
        knowledge_doc.chunk_count = len(chunks)
        knowledge_doc.status = "ready"
        knowledge_doc.error_message = ""
        await db.commit()
        await db.refresh(knowledge_doc)

        return ImportedKnowledgeDoc(
            doc_id=knowledge_doc.id,
            filename=knowledge_doc.filename,
            category=knowledge_doc.category,
            chunk_count=knowledge_doc.chunk_count,
        )

    async def _mark_doc_error(self, db: AsyncSession, doc_id: str, error_message: str) -> None:
        document = await db.get(KnowledgeDoc, doc_id)
        if document is None:
            return
        document.status = "error"
        document.error_message = error_message
        await db.commit()

    @staticmethod
    def _remove_stored_file(stored_path: str) -> None:
        if not stored_path:
            return
        try:
            candidate = Path(stored_path)
            if candidate.exists() and candidate.is_file():
                candidate.unlink()
        except OSError:
            return

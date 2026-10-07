import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "lantern/1.0"

ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
CIK_RE = re.compile(r"^\d{10}$")
BLOCK_ID_RE = re.compile(r"^p\d{4}_b\d{3}$")

BlockType = Literal["Text", "Title", "List", "Table", "Figure", "Footnote"]


class Table(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str]
    rows: list[list[Optional[str]]]
    raw_cells: list[list[Optional[str]]]
    scale: Optional[str] = None

    @model_validator(mode="after")
    def check_rectangular(self):
        width = len(self.columns)
        for i, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(
                    f"rows[{i}] has {len(row)} cells, columns has {width}"
                )
        return self


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(alias="schema")

    doc_id: str
    company: str
    cik: str
    ticker: str

    form: str
    fiscal_year: int
    fiscal_period: str

    page: int
    section: Optional[str] = None

    block_id: str
    block_type: BlockType

    bbox: list[float]
    units: Literal["pt"]
    origin: Literal["top-left"]

    text: Optional[str] = None
    table: Optional[Table] = None

    extractor: str
    extractor_version: str

    ocr: bool
    ocr_conf: Optional[float] = None

    @field_validator("schema_version")
    @classmethod
    def check_schema_version(cls, v):
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema must be {SCHEMA_VERSION}, got {v}")
        return v

    @field_validator("doc_id")
    @classmethod
    def check_doc_id(cls, v):
        if not ACCESSION_RE.match(v):
            raise ValueError(f"doc_id must be NNNNNNNNNN-YY-NNNNNN, got {v}")
        return v

    @field_validator("cik")
    @classmethod
    def check_cik(cls, v):
        if not CIK_RE.match(v):
            raise ValueError(f"cik must be 10 digits zero-padded, got {v}")
        return v

    @field_validator("block_id")
    @classmethod
    def check_block_id(cls, v):
        if not BLOCK_ID_RE.match(v):
            raise ValueError(f"block_id must look like p0045_b003, got {v}")
        return v

    @field_validator("page")
    @classmethod
    def check_page(cls, v):
        if v < 1:
            raise ValueError(f"page is 1-based, got {v}")
        return v

    @field_validator("bbox")
    @classmethod
    def check_bbox(cls, v):
        if len(v) != 4:
            raise ValueError(f"bbox must have 4 values, got {len(v)}")
        x0, top, x1, bottom = v
        if x1 <= x0:
            raise ValueError(f"bbox x1 must exceed x0, got x0={x0} x1={x1}")
        if bottom <= top:
            raise ValueError(
                f"bbox bottom must exceed top in top-left origin, "
                f"got top={top} bottom={bottom}"
            )
        return v

    @field_validator("ocr_conf")
    @classmethod
    def check_ocr_conf(cls, v):
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError(f"ocr_conf must be between 0 and 1, got {v}")
        return v

    @model_validator(mode="after")
    def check_payload(self):
        if self.text is None and self.table is None:
            raise ValueError(f"{self.block_id}: both text and table are null")
        if self.block_type == "Table" and self.table is None:
            raise ValueError(f"{self.block_id}: block_type Table but table is null")
        if self.ocr and self.ocr_conf is None:
            raise ValueError(f"{self.block_id}: ocr is true but ocr_conf is null")
        return self

    def to_jsonl(self):
        return json.dumps(self.model_dump(by_alias=True), ensure_ascii=False)


def validate_record(obj):
    return Block.model_validate(obj)


def validate_jsonl(path):
    ok = 0
    errors = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                validate_record(json.loads(line))
                ok += 1
            except Exception as e:
                errors.append((i, str(e)))
    return ok, errors
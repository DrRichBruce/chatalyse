from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


GENE_COL_CANDIDATES = (
    "gene",
    "genes",
    "gene_symbol",
    "symbol",
    "hgnc_symbol",
    "ensembl",
    "ensembl_gene_id",
    "gene_id",
)


@dataclass(frozen=True)
class DataProfile:
    n_rows: int
    n_cols: int
    columns: list[str]
    gene_col_guess: Optional[str]


def guess_gene_column(df: pd.DataFrame) -> Optional[str]:
    cols = [c for c in df.columns if isinstance(c, str)]
    lower = {c.lower().strip(): c for c in cols}
    for cand in GENE_COL_CANDIDATES:
        if cand in lower:
            return lower[cand]
    return None


def profile_dataframe(df: pd.DataFrame) -> DataProfile:
    return DataProfile(
        n_rows=int(df.shape[0]),
        n_cols=int(df.shape[1]),
        columns=[str(c) for c in df.columns.tolist()],
        gene_col_guess=guess_gene_column(df),
    )


def read_table(upload) -> pd.DataFrame:
    """
    Read CSV/XLSX into a DataFrame with reasonable defaults.
    `upload` is the Streamlit UploadedFile.
    """
    name = getattr(upload, "name", "") or ""
    if name.lower().endswith(".csv"):
        # Let pandas infer delimiter; keep strings as strings.
        return pd.read_csv(upload, low_memory=False)
    if name.lower().endswith((".xlsx", ".xls")):
        # Requires openpyxl for xlsx
        return pd.read_excel(upload, engine=None)
    raise ValueError("Unsupported file type. Please upload a .csv or .xlsx file.")


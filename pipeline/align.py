"""
LaBSE semantic alignment module.

Aligns English source terms with target-language phrases using
sentence-transformers/LaBSE embeddings and cosine similarity.
"""

from __future__ import annotations

import os
from collections import OrderedDict

import numpy as np
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

load_dotenv()


class LaBSEAligner:
    """Aligns source terms to target-language phrases via LaBSE embeddings."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/LaBSE",
        target_cache_size: int = 2048,
    ) -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        # LRU cache: target_text(s) → (candidate_phrases, candidate_embeddings)
        # Avoids re-encoding identical target texts seen across different source terms
        # or duplicate product descriptions within the dataset.
        self._target_cache: OrderedDict[str, tuple[list[str], np.ndarray]] = OrderedDict()
        self._target_cache_size = target_cache_size

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> SentenceTransformer:
        """Lazy-load the LaBSE model (singleton per instance)."""
        if self._model is None:
            token = os.getenv("HF_TOKEN")
            self._model = SentenceTransformer(self._model_name, token=token)
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(self, texts: list[str]) -> np.ndarray:
        """Batch-encode *texts* and return L2-normalised embeddings.

        Args:
            texts: Strings to encode.

        Returns:
            Float32 array of shape ``(len(texts), embedding_dim)``.
        """
        if not texts:
            return np.empty((0,), dtype=np.float32)

        model = self._load_model()
        embeddings: np.ndarray = model.encode(
            texts,
            batch_size=64,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,  # ensures unit vectors for cosine sim
        )
        return embeddings

    def extract_target_phrases(self, text: str, max_ngram: int = 4) -> list[str]:
        """Extract candidate phrases from *text* via sliding n-gram window.

        Splits on whitespace and generates all contiguous token spans of
        length 1 … *max_ngram*.  Duplicate phrases are removed while
        preserving first-occurrence order.

        Args:
            text:      Target-language text to window over.
            max_ngram: Maximum number of tokens per candidate phrase.

        Returns:
            Unique candidate phrases (order-preserving).
        """
        if not text or not text.strip():
            return []

        tokens = text.split()
        seen: set[str] = set()
        phrases: list[str] = []

        for n in range(1, max_ngram + 1):
            for start in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[start : start + n])
                if phrase not in seen:
                    seen.add(phrase)
                    phrases.append(phrase)

        return phrases

    def _get_candidate_embeddings(
        self, target_texts: list[str]
    ) -> tuple[list[str], np.ndarray]:
        """Return (candidate_phrases, embeddings) for *target_texts*, using LRU cache.

        Avoids re-encoding the same target text if it appears in multiple pairs
        (e.g. duplicate boilerplate descriptions or the same text across locales).
        """
        cache_key = "\x00".join(target_texts)

        if cache_key in self._target_cache:
            self._target_cache.move_to_end(cache_key)  # mark as recently used
            return self._target_cache[cache_key]

        # Build unique candidate phrase list across all target texts
        all_candidates: list[str] = []
        seen_candidates: set[str] = set()
        for text in target_texts:
            for phrase in self.extract_target_phrases(text):
                if phrase not in seen_candidates:
                    seen_candidates.add(phrase)
                    all_candidates.append(phrase)

        candidate_embeddings = (
            self.encode(all_candidates)
            if all_candidates
            else np.empty((0,), dtype=np.float32)
        )

        # Evict oldest entry when at capacity (LRU eviction)
        if len(self._target_cache) >= self._target_cache_size:
            self._target_cache.popitem(last=False)

        self._target_cache[cache_key] = (all_candidates, candidate_embeddings)
        return all_candidates, candidate_embeddings

    def align_terms(
        self,
        source_terms: list[str],
        target_texts: list[str],
        threshold: float = 0.75,
    ) -> list[dict]:
        """Align each source term to candidate phrases from *target_texts*.

        For every source term the method:
        1. Retrieves (cached) n-gram candidates + embeddings from target texts.
        2. Encodes ALL source terms in a single batch (was: one call per term).
        3. Computes the full similarity matrix in one operation.
        4. Collects pairs whose similarity meets *threshold*.

        Args:
            source_terms:  English terms to align.
            target_texts:  Target-language texts to mine for matching phrases.
            threshold:     Minimum cosine similarity to include a pair.

        Returns:
            List of ``{"source_term": str, "target_term": str, "labse_score": float}``,
            one entry per (source_term, target_phrase) pair that meets the threshold.
        """
        if not source_terms or not target_texts:
            return []

        # Candidates: retrieved from cache or computed once
        all_candidates, candidate_embeddings = self._get_candidate_embeddings(target_texts)

        if not all_candidates:
            return []

        # Encode ALL source terms in one batch — previously this was one encode()
        # call per term inside a loop, causing N separate model forward passes.
        source_embeddings = self.encode(source_terms)  # (S, D)

        # Full similarity matrix in one shot: (S, C)
        all_sims: np.ndarray = cosine_similarity(source_embeddings, candidate_embeddings)

        results: list[dict] = []
        for i, term in enumerate(source_terms):
            sims = all_sims[i]
            for idx, score in enumerate(sims):
                if float(score) >= threshold:
                    results.append(
                        {
                            "source_term": term,
                            "target_term": all_candidates[idx],
                            "labse_score": float(score),
                        }
                    )

        return results

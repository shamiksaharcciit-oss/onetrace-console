"""The embedder: a local ONNX model run in-process (the default), or an OpenAI-compatible endpoint of the
user's own. No hosted provider is offered or named.

**The local model.** Its files are fetched by GET at the pinned revision with no token, only when a
person turns neighbours on and confirms (`fetch`), into the store's `neighbours/models/` folder. Every
file is checked by its sha256 before every use (`check`): a mismatch, or a file missing, refuses, naming
the file. The maximum length is the model's own sentence-transformers configuration
(`sentence_bert_config.json`, at the same revision), never a number written here, and the pooling its
own `1_Pooling/config.json`, checked against the pooling pinned below. It runs on onnxruntime,
tokenizers and numpy, with no torch, on the CPU.

**An endpoint of the user's own.** `POST <base url>/embeddings` with `{"model", "input"}`, as the
OpenAI-compatible servers a person runs take it; no key is sent and none can be set. What such a server
does not say of itself (its files, its engine, its dtype) is `not observed` in the record, never filled in.

Each call returns the vectors and what its model-call records state (`Batch`). `batches` writes them.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

#: The local embedders, each pinned to one immutable revision of its repository.
#: Each file's sha256, checked before the file is kept: model.onnx's is the repository's LFS sha256 for it;
#: the four small files' are of their bytes as fetched at that same revision on 2026-10-28.


@dataclass(frozen=True)
class Model:
    name: str
    repo: str
    revision: str
    pooling: str                  # "mean" or "cls", as the model's 1_Pooling/config.json must say
    licence: str                  # what the model's card states, and nothing more
    files: dict = field(default_factory=dict)

    @property
    def requested(self) -> str:
        return f"{self.repo}@{self.revision}"


ONNX = "onnx/model.onnx"
TOKENIZER = "tokenizer.json"
ST_CONFIG = "sentence_bert_config.json"
POOLING = "1_Pooling/config.json"
MODULES = "modules.json"

MODELS = {
    "all-MiniLM-L6-v2": Model(
        "all-MiniLM-L6-v2", "sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        "mean", "apache-2.0, as its card states",
        {ONNX: "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452",
         TOKENIZER: "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
         ST_CONFIG: "fc1993fde0a95c24ec6c022539d41cf6e2f7c9721e5415d6fb6897472a9cd4b7",
         POOLING: "4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23",
         MODULES: "84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf"}),
    "bge-small-en-v1.5": Model(
        "bge-small-en-v1.5", "BAAI/bge-small-en-v1.5", "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        "cls", "mit, as its card states",
        {ONNX: "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
         TOKENIZER: "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
         ST_CONFIG: "84e39fda68ccbff05bfa723ae9c0e70e23e2ec373b76e0f8c6e71af72a693cbf",
         POOLING: "d1caf60c96f5fba2157c0c26b76d80818fad6cf0b8eb5e73ec372ff9818eba5c",
         MODULES: "84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf"}),
}
DEFAULT = "all-MiniLM-L6-v2"
ALTERNATE = "bge-small-en-v1.5"
#: Where the files are fetched from, at the pinned revision: a GET, no token, no other header.
URL = "https://huggingface.co/{repo}/resolve/{revision}/{path}"
#: The largest one fetched file can be: model.onnx is about 90 MB (MiniLM) and 133 MB (bge-small).
MOST_BYTES = 256 * 1024 * 1024
#: Each text, as sent to the tokenizer: the console's cut before the model's own maximum length, so a
#: very long kept input costs no more than the model reads.
MOST_CHARS = 32_000
#: The longest a call to an endpoint can take, in seconds.
ENDPOINT_SECONDS = 60


class Refused(ValueError):
    """The embedder cannot be used, said in words: a file missing or not matching its sha256, by name."""


# ------------------------------------------------------------------------------- the files

def folder(root: Path, model: Model) -> Path:
    """The model's files under `root` (the store's neighbours/models/), at its revision."""
    return Path(root) / f"{model.repo.replace('/', '_')}@{model.revision}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(root: Path, model: Model) -> dict[str, str]:
    """Every file of `model` under `root` present and matching its pinned sha256: {path: sha256}.
    Otherwise `Refused`, naming the file."""
    where = folder(root, model)
    for path, want in sorted(model.files.items()):
        p = where / path
        if not p.is_file():
            raise Refused(f"{model.name}: {path} is not here; turn neighbours on again to fetch it")
        got = _sha256(p)
        if got != want:
            raise Refused(f"{model.name}: {path} has sha256 {got}, not the pinned {want}; it is not used")
    return dict(model.files)


def _get(url: str) -> bytes:
    """One GET of `url`, no token and no header of ours, at most MOST_BYTES."""
    import urllib.request
    request = urllib.request.Request(url, headers={"User-Agent": "onetrace-console"})
    with urllib.request.urlopen(request, timeout=120) as response:          # noqa: S310 - https, pinned
        data = response.read(MOST_BYTES + 1)
    if len(data) > MOST_BYTES:
        raise Refused(f"{url} is larger than {MOST_BYTES} bytes")
    return data


def fetch(root: Path, model: Model, get=_get) -> dict[str, str]:
    """Fetch each file of `model` not already here and matching, checking its sha256 before it is kept:
    a mismatch refuses by the file's name and keeps nothing of it. {path: sha256} once all match."""
    from onetrace_console.store import _atomic_write
    where = folder(root, model)
    for path, want in sorted(model.files.items()):
        p = where / path
        if p.is_file() and _sha256(p) == want:
            continue
        data = get(URL.format(repo=model.repo, revision=model.revision, path=path))
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            raise Refused(f"{model.name}: {path} as fetched has sha256 {got}, not the pinned {want}; "
                          f"it was not kept")
        p.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(p, data)
    return check(root, model)


# ------------------------------------------------------------------------------- a batch

@dataclass
class Batch:
    """One call's vectors, L2-normalised, one per text in order, and what its records state: `shared`
    the fields every row's record holds, `rows` each row's own."""
    vectors: list                 # list of numpy float32 arrays
    shared: dict
    rows: list


def _vo():
    from onetrace.model_call import declared, not_applicable, not_observed, observed
    return declared, not_applicable, not_observed, observed


def _runtime_cpu() -> dict:
    """runtime.*: no torch is used; the GPU fields are not applicable on a CPU run."""
    _d, not_applicable, _n, _o = _vo()
    out = {"runtime.torch": not_applicable("onnxruntime, with no torch")}
    for k in ("runtime.cuda", "runtime.gpu_name", "runtime.compute_capability", "runtime.driver"):
        out[k] = not_applicable("a CPU run")
    return out


def _tokens_digest(ids) -> str:
    from onetrace.model_call.canonical import token_root
    return token_root(ids)


def usable_cpus() -> int:
    """The CPUs this process can run on (its affinity, where the platform says), at least one."""
    import os
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


class Local:
    """The local ONNX model, in-process, on the CPU. Its files are checked before it is loaded."""

    kind = "local"
    API = "onnxruntime.InferenceSession.run"

    def __init__(self, root: Path, model: Model):
        files = check(root, model)
        where = folder(root, model)
        self.model, self.root = model, Path(root)
        from onetrace_console.bounded_json import load_json_bounded
        st = load_json_bounded((where / ST_CONFIG).read_text(encoding="utf-8"), ST_CONFIG)
        pooling = load_json_bounded((where / POOLING).read_text(encoding="utf-8"), POOLING)
        said = "cls" if pooling.get("pooling_mode_cls_token") else "mean" if pooling.get("pooling_mode_mean_tokens") else ""
        if said != model.pooling:
            raise Refused(f"{model.name}: {POOLING} says pooling {said or 'of another kind'}, not the pinned "
                          f"{model.pooling}")
        self.max_length = int(st["max_seq_length"])
        import onnxruntime
        from tokenizers import Tokenizer
        from onetrace.model_call import manifest_digest
        self.tokenizer = Tokenizer.from_file(str(where / TOKENIZER))
        self.tokenizer.enable_truncation(max_length=self.max_length)
        pad = self.tokenizer.token_to_id("[PAD]")
        self.tokenizer.enable_padding(pad_id=0 if pad is None else pad, pad_token="[PAD]")
        options = onnxruntime.SessionOptions()
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        #: The threads named, from the CPUs this process can run on: left unset, onnxruntime counts the
        #: host's CPUs, and on a container allowed fewer it starts a thread per host CPU and fails to pin them.
        self.threads = usable_cpus()
        options.intra_op_num_threads, options.inter_op_num_threads = self.threads, 1
        self.session = onnxruntime.InferenceSession(str(where / ONNX), sess_options=options,
                                                    providers=["CPUExecutionProvider"])
        self.input_names = [i.name for i in self.session.get_inputs()]
        self.output = self.session.get_outputs()[0]
        self.engine_version = onnxruntime.__version__
        self.files_digest = manifest_digest(files)
        self.tokenizer_digest = manifest_digest({TOKENIZER: files[TOKENIZER]})

    def identity(self) -> dict:
        """The record's fields that describe the embedder, the same for every call it serves."""
        declared, not_applicable, not_observed, observed = _vo()
        dtype = {"tensor(float)": "float32", "tensor(float16)": "float16"}.get(self.output.type, self.output.type)
        return {
            "call.kind": "self-hosted", "call.api": self.API, "credential": "absent",
            "model.requested": declared(self.model.requested, "the console's pinned embedder: repository and revision"),
            "model.reported": not_observed("an ONNX file states no model name"),
            "model.files_digest": observed(self.files_digest, "the sha256 of each of the model's files, each checked "
                                                              "before use"),
            "tokenizer.digest": observed(self.tokenizer_digest, "the sha256 of tokenizer.json, checked before use"),
            "provider.fingerprint": not_applicable("self-hosted"),
            "engine.name": observed("onnxruntime", "a constant written by the console's embedder"),
            "engine.version": observed(self.engine_version, "onnxruntime.__version__"),
            "dtype": observed(dtype, "the model's output tensor type, InferenceSession.get_outputs()[0].type"),
            "attention_backend": not_observed("onnxruntime does not say which attention kernel it ran"),
            "engine.settings.providers": observed(self.session.get_providers(), "InferenceSession.get_providers()"),
            "engine.settings.intra_op_threads": observed(self.threads, "SessionOptions.intra_op_num_threads, set "
                                                                       "from the CPUs this process can use"),
            "engine.settings.max_length": observed(self.max_length, f"{ST_CONFIG} max_seq_length, at the pinned revision"),
            "engine.settings.pooling": observed(self.model.pooling, f"{POOLING}, at the pinned revision"),
            "engine.settings.normalise": declared("l2", "the console's embedder divides each vector by its length"),
            "batch.batch_invariant": not_observed("onnxruntime does not say whether a row's result depends on "
                                                  "the batch"),
            **_runtime_cpu(),
        }

    def embed(self, texts: list[str]) -> Batch:
        import numpy as np
        declared, not_applicable, not_observed, observed = _vo()
        #: Every file by its sha256 before each use: a file changed since it was loaded refuses.
        if check(self.root, self.model) != self.model.files:     # pragma: no cover - check raises first
            raise Refused(f"{self.model.name}: its files changed")
        encodings = self.tokenizer.encode_batch([t[:MOST_CHARS] for t in texts])
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.input_names:
            feed["token_type_ids"] = np.array([e.type_ids for e in encodings], dtype=np.int64)
        hidden = self.session.run([self.output.name], {k: v for k, v in feed.items() if k in self.input_names})[0]
        if self.model.pooling == "cls":
            pooled = hidden[:, 0, :]
        else:
            m = mask[:, :, None].astype(hidden.dtype)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        vectors = [v.astype(np.float32) for v in pooled / np.clip(norms, 1e-12, None)]
        size, width = ids.shape
        unpadded = [[i for i, keep in zip(e.ids, e.attention_mask) if keep] for e in encodings]
        digests = [_tokens_digest(u) for u in unpadded]
        shared = {**self.identity(),
                  "batch.size": observed(size, "input_ids.shape[0] as the session received it"),
                  "batch.executed_size": observed(size, "input_ids.shape[0]: onnxruntime runs the batch as given"),
                  "batch.padded_width": observed(width, "input_ids.shape[1] as the session received it"),
                  "batch.fillers": observed(0, "the console's embedder adds no filler rows"),
                  "input.request_digest": not_applicable("self-hosted: no request body"),
                  "output.token_ids_digest": not_applicable("an embedding: nothing is generated"),
                  "output.text_digest": not_applicable("an embedding: no text is generated"),
                  "output.finish": not_applicable("an embedding: nothing is generated")}
        rows = [{"batch.position": observed(j, "the row index"),
                 "batch.members": observed([d for i, d in enumerate(digests) if i != j],
                                           "token-id digests of the other rows"),
                 "input.token_ids_digest": observed(digests[j], "the row's unpadded token ids")}
                for j in range(len(texts))]
        return Batch(vectors, shared, rows)


_LOOPBACK = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)")


def endpoint_problem(base_url: str, model: str) -> str | None:
    """Why an endpoint can't be named, or None: an http(s) address with no user or query, and a model."""
    from urllib.parse import urlsplit
    if not isinstance(base_url, str) or not re.match(r"https?://[^\s/]+", base_url or ""):
        return "the endpoint is an http:// or https:// address, such as http://127.0.0.1:8000/v1"
    parts = urlsplit(base_url)
    if parts.username or parts.password or parts.query or parts.fragment:
        return "the endpoint's address holds no user, password, query or fragment"
    if not isinstance(model, str) or not model.strip() or len(model) > 200 or any(ord(c) < 32 for c in model):
        return "the endpoint needs the name of the model it serves"
    return None


def _post_json(url: str, body: dict) -> dict:
    import urllib.request
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "onetrace-console"})
    with urllib.request.urlopen(request, timeout=ENDPOINT_SECONDS) as response:   # noqa: S310 - the user's own
        raw = response.read(64 * 1024 * 1024)
    from onetrace_console.bounded_json import load_json_bounded
    return load_json_bounded(raw, "the endpoint's answer")


class Endpoint:
    """An OpenAI-compatible embedding endpoint the user named. No key is sent."""

    kind = "endpoint"
    API = "POST /embeddings (OpenAI-compatible)"

    def __init__(self, base_url: str, model: str, post=None):
        problem = endpoint_problem(base_url, model)
        if problem:
            raise Refused(problem)
        self.base_url, self.model_name, self._post = base_url.rstrip("/"), model.strip(), post

    def identity(self) -> dict:
        declared, not_applicable, not_observed, observed = _vo()
        hidden = "an endpoint the user named: not exposed by it"
        return {
            "call.kind": "self-hosted", "call.api": self.API, "credential": "absent",
            "model.requested": declared(self.model_name, "the model named for the endpoint on the setup page"),
            "model.reported": not_observed("not read yet"),
            "model.files_digest": not_observed(hidden), "tokenizer.digest": not_observed(hidden),
            "provider.fingerprint": not_observed(hidden),
            "engine.name": not_observed(hidden), "engine.version": not_observed(hidden),
            "dtype": not_observed(hidden), "attention_backend": not_observed(hidden),
            "engine.settings.base_url": declared(self.base_url, "the endpoint named on the setup page"),
            "engine.settings.normalise": declared("l2", "the console's embedder divides each vector by its length"),
            "batch.batch_invariant": not_observed(hidden),
            **{k: not_observed(hidden) for k in ("runtime.torch", "runtime.cuda", "runtime.gpu_name",
                                                 "runtime.compute_capability", "runtime.driver")},
        }

    def embed(self, texts: list[str]) -> Batch:
        import numpy as np
        from onetrace.model_call.canonical import cj, sha
        declared, not_applicable, not_observed, observed = _vo()
        hidden = "an endpoint the user named: not exposed by it"
        request = {"model": self.model_name, "input": [t[:MOST_CHARS] for t in texts]}
        body = (self._post or _post_json)(f"{self.base_url}/embeddings", request)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise Refused(f"the endpoint answered with {len(data) if isinstance(data, list) else 'no'} "
                          f"embeddings for {len(texts)} texts")
        rows_in = sorted(data, key=lambda d: int(d.get("index", 0)) if isinstance(d, dict) else 0)
        vectors = []
        for d in rows_in:
            v = np.asarray(d.get("embedding") if isinstance(d, dict) else None, dtype=np.float32)
            if v.ndim != 1 or not v.size or not np.all(np.isfinite(v)):
                raise Refused("the endpoint answered with an embedding that is not a list of numbers")
            vectors.append(v / max(float(np.linalg.norm(v)), 1e-12))
        shared = {**self.identity(),
                  "model.reported": observed(body["model"], "the response's model field")
                  if isinstance(body.get("model"), str) and body["model"]
                  else not_observed("the response carries no model field"),
                  "batch.size": observed(len(texts), "the request's input list"),
                  "batch.executed_size": not_observed(hidden), "batch.padded_width": not_observed(hidden),
                  "batch.fillers": not_observed(hidden),
                  "input.request_digest": observed(sha(cj(request)), "the canonical request body; no credential, no "
                                                                     "header"),
                  "output.token_ids_digest": not_applicable("an embedding: nothing is generated"),
                  "output.text_digest": not_applicable("an embedding: no text is generated"),
                  "output.finish": not_applicable("an embedding: nothing is generated")}
        rows = [{"batch.position": observed(j, "the row index in the request's input list"),
                 "batch.members": not_observed("the endpoint's token ids are not exposed"),
                 "input.token_ids_digest": not_observed("the endpoint's token ids are not exposed")}
                for j in range(len(texts))]
        return Batch(vectors, shared, rows)


def loopback(base_url: str) -> bool:
    """The endpoint is on this machine's loopback address."""
    return bool(_LOOPBACK.match(base_url or ""))


def models_root(store) -> Path:
    from onetrace_console.neighbours import FOLDER
    return Path(store.root) / FOLDER / "models"


#: The local models loaded in this process, by (models folder, name): loaded once, each file checked
#: then; `Local.embed` checks every file again before each batch it embeds.
_LOADED: dict[tuple[str, str], Local] = {}


def make(store, chosen: dict):
    """The embedder a setting names: {"kind": "local", "model": <name>} or {"kind": "endpoint", ...}."""
    if chosen.get("kind") == "endpoint":
        return Endpoint(str(chosen.get("base_url", "")), str(chosen.get("model", "")))
    model = MODELS.get(str(chosen.get("model", "")))
    if model is None:
        raise Refused(f"no local embedder is named {chosen.get('model')!r}; the console has "
                      + " and ".join(MODELS))
    key = (str(models_root(store)), model.name)
    if key not in _LOADED:
        _LOADED[key] = Local(models_root(store), model)
    return _LOADED[key]

"""P1, the demo store's refund-policy Q&A: a small retrieval pipeline, recorded with onetrace.

    load_docs --> split --> embed --> retrieve --> answer

It answers questions about the returns and refunds of an example shop. The shop is made up
for this demo, and so are its policies: no real company, brand or person is named.

NOTHING HERE CONTACTS A NETWORK OR A HOSTED MODEL. The embedder is a hashed bag of words
(each lower-cased word's sha256, folded into one of 256 buckets, counted). The retriever ranks
chunks by the integer dot product of those counts, ties broken by chunk id. The answerer is
extractive: for each question it quotes, verbatim, the sentence of the retrieved text that
shares the most words with the question. Every value is a string or a count, so the run is
the same on every machine.

The one setting the demo's headline comparison changes is `chunk_size`: 1024 characters in the
baseline, 512 in the candidate. Every setting is recorded with `ctx.constant`, which is where
onetrace keeps setting values (an instrument's own config is kept as a digest only), so a
comparison can show which setting differs.

`fault` makes a stage fail on purpose, and the error it records says so: "answer-last", the
answer stage raises, so the run's last attempt failed. A retry isn't shown here: this run is a
straight line, and onetrace records each declared stage of a straight-line run once, in order
(a retried stage needs a run recorded as a graph, as P2 and P3 are).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from onetrace.emit import Instrument, Recorder

from onetrace_console.bounded_json import load_json_bounded

STAGES = ["load_docs", "split", "embed", "retrieve", "answer"]

SHOP = "the example shop (made up for this demo)"

#: The shop's policy pages. Written for this demo; they describe no real shop.
DOCUMENTS = [
    {"id": "returns-window",
     "text": "Returns at the example shop. You can return most items within 30 days of delivery. "
             "The item must be unused and in its original packaging, with all tags attached. "
             "Gifts can be returned without a receipt if you have the order number; the refund "
             "then goes to the person who paid. Items marked final sale cannot be returned. "
             "To start a return, open your order page and choose Return an item, then print the "
             "label we email to you. Drop the parcel at any post office within 7 days of printing "
             "the label. If you miss the 30-day return window, contact us: we can sometimes offer "
             "store credit for items returned within 45 days, but this is not guaranteed."},
    {"id": "refund-timing",
     "text": "Refunds. Once your return reaches our warehouse we inspect it within 3 working days. "
             "If it passes inspection, we refund the original payment method. Card refunds "
             "usually appear within 5 to 10 working days, depending on your bank. If the card you "
             "paid with has expired or been cancelled, your bank normally passes the refund to "
             "your new card; if it cannot, we will issue store credit instead. Return shipping is "
             "free when you use our label. If you send the parcel another way, you pay for that "
             "shipping and we do not refund it. The original delivery charge is refunded only "
             "when the whole order is returned."},
    {"id": "damaged-items",
     "text": "Damaged or wrong items. If your order arrives damaged, take a photo of the item and "
             "the packaging and send it to us within 14 days of delivery. We will send a "
             "replacement at no cost, or refund you in full, including the delivery charge, if you "
             "prefer. You do not need to send a damaged item back unless we ask for it. If we sent "
             "you the wrong item, we pay for the return and send the right one as soon as it is in "
             "stock. Orders can be cancelled free of charge until they are dispatched. After an "
             "order has shipped it cannot be cancelled, but you can return it once it arrives."},
    {"id": "exceptions",
     "text": "Exceptions. Sale items are refundable within 14 days, unless they are marked final "
             "sale. Opened electronics can be returned within 14 days only if they are faulty; "
             "unopened electronics follow the normal 30-day window. Digital items, such as gift "
             "cards and downloadable patterns, are not refundable once the code has been sent. "
             "Personalised items are made for you and cannot be returned unless they arrive "
             "damaged. We do not charge a restocking fee on any return. Items returned without "
             "their original packaging may be refunded at a reduced amount after inspection."},
    {"id": "exchanges-and-credit",
     "text": "Exchanges and store credit. To exchange an item for a different size or colour, "
             "start a return and choose Exchange; we hold the new item for you for 7 days while "
             "your return travels. Exchanges are free, and you can exchange an item once. If the "
             "size you want is out of stock, we refund you instead. You can choose store credit "
             "instead of a refund on any return: store credit is issued as soon as your return is "
             "scanned at the post office, and it never expires. Store credit cannot be turned "
             "back into money, except where the law requires it."},
    {"id": "international-and-in-person",
     "text": "International and in-person orders. Customers outside the country can return items "
             "within 30 days, but international return shipping is paid by the customer and is "
             "not refunded. Customs charges paid on delivery are refunded only when the whole "
             "order is returned. Items bought in person at one of our market stalls can be "
             "returned by mail using the receipt number instead of an order number. Refunds for "
             "in-person purchases paid in cash are made as store credit or by bank transfer, "
             "whichever you choose. International refunds are made in the currency you paid in."},
]

#: Six question sets: one per day of the demo's week, the same questions in the baseline and
#: the candidate of each day.
QUESTION_SETS = {
    "1": ["How long do I have to return an item?",
          "Who pays for return shipping?",
          "Can I return a gift without a receipt?"],
    "2": ["When will my refund arrive?",
          "Are sale items refundable?",
          "Can I exchange an item for a different size?"],
    "3": ["What if my order arrives damaged?",
          "Is the delivery charge refunded?",
          "Can I cancel an order after it has shipped?"],
    "4": ["Can I return opened electronics?",
          "How do I start a return?",
          "Is there a restocking fee?"],
    "5": ["Can I get store credit instead of a refund?",
          "What happens to my refund if my card has expired?",
          "Are digital items refundable?"],
    "6": ["How are international returns handled?",
          "Can I return an item bought in person by mail?",
          "What if I miss the return window?"],
}

#: The settings of the two configurations the demo compares.
BASELINE = {"chunk_size": "1024", "overlap": "64", "top_k": "4"}
CANDIDATE = {"chunk_size": "512", "overlap": "64", "top_k": "4"}

BUCKETS = 256
EMBEDDER = f"hashed bag of words, sha256 of each lower-cased word, {BUCKETS} buckets"

#: Words too common to tell two texts apart; left out of the embedding and of the answer's match.
STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i if in is it its my of on once "
    "or our the then there this to was we what when where which who will with you your".split())

ANSWER_FAULT = ("set by the demo to show a failed last attempt: the answer stage raises this "
                "instead of running, and is not retried; nothing else went wrong")


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


def embed_text(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for w in words(text):
        bucket = str(int(hashlib.sha256(w.encode("utf-8")).hexdigest()[:8], 16) % BUCKETS)
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def split_text(doc_id: str, text: str, size: int, overlap: int) -> list[dict]:
    """Windows of at most `size` characters, each cut back to the last space inside it, the next
    starting `overlap` characters before the cut."""
    chunks, start, n = [], 0, 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            space = text.rfind(" ", start + 1, end)
            if space > start:
                end = space
        n += 1
        chunks.append({"id": f"{doc_id}#{n}", "doc": doc_id, "text": text[start:end].strip()})
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
        while start < len(text) and text[start - 1] != " ":
            start += 1
    return chunks


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;:])\s+", text) if s.strip()]


def main(out_dir, run_id: str, settings: dict, question_set: str, *, fault: str = "",
         sign_with=None) -> None:
    """Record one run into `out_dir`: the question set's questions, answered with `settings`."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    docs_path = out / "documents.json"
    docs_path.write_text(json.dumps(DOCUMENTS, sort_keys=True), encoding="utf-8")
    questions_path = out / "questions.json"
    questions_path.write_text(json.dumps(QUESTION_SETS[question_set], sort_keys=True),
                              encoding="utf-8")
    size, overlap, top_k = int(settings["chunk_size"]), int(settings["overlap"]), int(settings["top_k"])

    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", sign_with=sign_with,
                   anchor_reason="a demo record; anchoring is not part of this demo")

    def load_docs(ctx):
        ctx.constant("shop", SHOP)
        docs = load_json_bounded(ctx.read_external(docs_path, "application/json", name="documents",
                                                   trust_class="operator-authored"), "documents")
        return ctx.write_json("documents.json", {"documents": docs})

    def split(ctx, loaded):
        ctx.read_receipt("load_docs")
        docs = ctx.read_json(loaded)["documents"]
        ctx.constant("chunk_size", settings["chunk_size"])
        ctx.constant("overlap", settings["overlap"])
        chunks = [c for d in docs for c in split_text(d["id"], d["text"], size, overlap)]
        return ctx.write_json("chunks.json", {"chunks": chunks})

    def embed(ctx, chunked):
        ctx.read_receipt("split")
        chunks = ctx.read_json(chunked)["chunks"]
        ctx.constant("embedder", EMBEDDER)
        vectors = {c["id"]: {b: str(n) for b, n in sorted(embed_text(c["text"]).items())}
                   for c in chunks}
        return ctx.write_json("vectors.json", {"vectors": vectors})

    def retrieve(ctx, chunked, embedded):
        ctx.read_receipt("embed")
        ctx.read_receipt("split")
        chunks = ctx.read_json(chunked)["chunks"]
        vectors = ctx.read_json(embedded)["vectors"]
        questions = load_json_bounded(ctx.read_external(questions_path, "application/json",
                                                        name="questions",
                                                        trust_class="operator-authored"), "questions")
        ctx.constant("top_k", settings["top_k"])
        hits = []
        for q in questions:
            qv = embed_text(q)
            scored = sorted(((-sum(n * int(vectors[c["id"]].get(b, "0")) for b, n in qv.items()),
                              c["id"]) for c in chunks))
            hits.append({"question": q, "chunks": [cid for _, cid in scored[:top_k]]})
        return ctx.write_json("hits.json", {"hits": hits})

    def answer(ctx, chunked, found):
        ctx.read_receipt("retrieve")
        if fault == "answer-last":
            raise RuntimeError(ANSWER_FAULT)
        text = {c["id"]: c["text"] for c in ctx.read_json(chunked)["chunks"]}
        answers = []
        for hit in ctx.read_json(found)["hits"]:
            asked = set(words(hit["question"]))
            best = (0, "", "")
            for cid in hit["chunks"]:
                for s in sentences(text[cid]):
                    score = len(asked & set(words(s)))
                    if score > best[0]:
                        best = (score, s, cid)
            answers.append({"question": hit["question"], "answer": best[1] or "(no sentence matched)",
                            "quoted_from": best[2]})
        return ctx.write_json("answers.json", {"answers": answers})

    loaded = rec.run_node("load_docs", None, Instrument("policy-pages", "reader", "1.0.0",
                                                        {"source": "documents.json"}), load_docs)
    chunked = rec.run_node("split", None, Instrument("char-splitter", "splitter", "1.0.0",
                                                     {"chunk_size": settings["chunk_size"],
                                                      "overlap": settings["overlap"]}),
                           split, loaded)
    embedded = rec.run_node("embed", None, Instrument("hashed-bow", "embedder", "1.0.0",
                                                      {"buckets": str(BUCKETS)}), embed, chunked)
    found = rec.run_node("retrieve", None, Instrument("dot-product", "retriever", "1.0.0",
                                                      {"top_k": settings["top_k"]}),
                         retrieve, chunked, embedded)
    try:
        rec.run_node("answer", None, Instrument("extractive", "answerer", "1.0.0",
                                                {"method": "best-matching sentence, quoted"}),
                     answer, chunked, found)
    except RuntimeError:
        if fault != "answer-last":
            raise
        # recorded as an error and kept; the run closes with its last attempt failed
    rec.close()

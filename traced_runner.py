"""
Traced pipeline runner.

This module does NOT change any decisioning/extraction logic. It calls the
exact same functions defined in pipeline.py (run_tier1, run_tier2, run_tier3,
validate_extraction, merge_extractions, match_invoice, make_decision,
draft_vendor_email, ...) in the exact same order that pipeline.process_invoice
does. The only thing added here is an `emit()` callback fired between steps,
so a UI can render each stage of the pipeline as it actually happens (live
running / done / skipped), instead of only seeing the final JSON result.

The escalation control-flow below (which tier runs, when to stop) is
duplicated from pipeline.extract_invoice() ONLY so we can emit progress
between Tier 1 -> 2 -> 3 as they happen; the thresholds and the underlying
per-tier functions are imported from pipeline.py, not reimplemented.
"""
import time
import uuid

import pipeline as P

STAGE_ORDER = [
    "ingest", "tier1", "validate1", "escalate1",
    "tier2", "validate2", "escalate2",
    "tier3", "validate3",
    "match", "decision", "correspondence", "ledger",
]

STAGE_TITLES = {
    "ingest": "Ingest file",
    "tier1": "Tier 1 — Native PDF extraction",
    "validate1": "Validate Tier 1 extraction",
    "escalate1": "Escalation gate (Tier 1 → Tier 2)",
    "tier2": "Tier 2 — OCR + Text LLM",
    "validate2": "Validate Tier 2 extraction",
    "escalate2": "Escalation gate (Tier 2 → Tier 3)",
    "tier3": "Tier 3 — Vision LLM",
    "validate3": "Validate final extraction",
    "match": "PO matching engine",
    "decision": "Decision engine",
    "correspondence": "Vendor correspondence",
    "ledger": "Record to ledger / history",
}

# Small pacing delay so fast/offline stages are still visible as "live" in a
# screen recording rather than flashing instantly. Real LLM calls (Tier 2/3
# with an API key) already take real wall-clock time and don't need this.
PACE_SECONDS = 0.35


def _pace():
    time.sleep(PACE_SECONDS)


def run_traced(file_path, store, correspondence_store, emit, corrected_fields=None,
                reply_body=None, reprocess_of=None):
    """
    Runs one invoice through the full pipeline, calling emit(event_dict) at
    each stage boundary. Returns the same result dict shape as
    pipeline.process_invoice().

    If `reprocess_of` (a source_file with an open correspondence thread) is
    given, this instead performs the vendor-reply reprocessing path
    (pipeline.apply_vendor_reply_and_reprocess), still narrated stage by stage.
    """
    for sid in STAGE_ORDER:
        emit({"stage": sid, "status": "pending", "title": STAGE_TITLES[sid]})

    if reprocess_of:
        return _run_reprocess(reprocess_of, correspondence_store, store,
                               corrected_fields or {}, reply_body or "", emit)

    emit({"stage": "ingest", "status": "running", "title": STAGE_TITLES["ingest"]})
    _pace()
    is_pdf = file_path.lower().endswith(".pdf")
    kind = "PDF" if is_pdf else "image"
    emit({"stage": "ingest", "status": "done", "title": STAGE_TITLES["ingest"],
          "detail": [f"Received {kind} input: {file_path.rsplit('/', 1)[-1]}"]})

    trace_all = []
    best_so_far = P.InvoiceExtraction(source_file=file_path, extraction_tier="NONE")
    final_extraction, final_validation = None, None

    if is_pdf:
        emit({"stage": "tier1", "status": "running", "title": STAGE_TITLES["tier1"]})
        _pace()
        tier1_result, doc = P.run_tier1(file_path)
        has_native_text = doc["has_native_text"]

        if not has_native_text:
            emit({"stage": "tier1", "status": "skipped", "title": STAGE_TITLES["tier1"],
                  "detail": ["No native text layer found (scanned/image-based PDF) — nothing to extract here."]})
            emit({"stage": "validate1", "status": "skipped", "title": STAGE_TITLES["validate1"]})
            emit({"stage": "escalate1", "status": "done", "title": STAGE_TITLES["escalate1"],
                  "detail": ["Skipping straight to Tier 2 (OCR + LLM)."]})
        else:
            best_so_far = tier1_result
            emit({"stage": "tier1", "status": "done", "title": STAGE_TITLES["tier1"],
                  "detail": [f"Extracted via {tier1_result.extraction_tier}."],
                  "payload": {"extraction": tier1_result.to_dict()}})

            emit({"stage": "validate1", "status": "running", "title": STAGE_TITLES["validate1"]})
            _pace()
            v1 = P.validate_extraction(best_so_far)
            emit({"stage": "validate1", "status": "done", "title": STAGE_TITLES["validate1"],
                  "detail": [f"Confidence {v1.confidence_score:.0f}/100, valid={v1.is_valid}, "
                             f"{len(v1.issues)} issue(s)."],
                  "payload": {"validation": v1.to_dict()}})

            if v1.is_valid and v1.confidence_score >= P.TIER1_CONFIDENCE_THRESHOLD:
                emit({"stage": "escalate1", "status": "done", "title": STAGE_TITLES["escalate1"],
                      "detail": [f"Confidence {v1.confidence_score:.0f} >= threshold "
                                 f"{P.TIER1_CONFIDENCE_THRESHOLD:.0f} — STOPPING at Tier 1 "
                                 "(no OCR/LLM cost incurred)."]})
                for sid in ["tier2", "validate2", "escalate2", "tier3", "validate3"]:
                    emit({"stage": sid, "status": "skipped", "title": STAGE_TITLES[sid],
                          "detail": ["Not needed — Tier 1 already cleared the confidence bar."]})
                final_extraction, final_validation = best_so_far, v1
            else:
                reasons = "; ".join(f"[{i.severity}] {i.field}: {i.message}" for i in v1.issues) \
                    or "confidence below threshold"
                emit({"stage": "escalate1", "status": "done", "title": STAGE_TITLES["escalate1"],
                      "detail": [f"Tier 1 insufficient ({reasons}) — escalating to Tier 2."]})
    else:
        emit({"stage": "tier1", "status": "skipped", "title": STAGE_TITLES["tier1"],
              "detail": ["Image input — Tier 1 (native PDF text) is not applicable."]})
        emit({"stage": "validate1", "status": "skipped", "title": STAGE_TITLES["validate1"]})
        emit({"stage": "escalate1", "status": "done", "title": STAGE_TITLES["escalate1"],
              "detail": ["Going straight to Tier 2 (OCR + LLM)."]})

    if final_extraction is None:
        emit({"stage": "tier2", "status": "running", "title": STAGE_TITLES["tier2"],
              "detail": ["Running Tesseract OCR" + (" and calling gpt-4o-mini..." if P.os.environ.get("OPENAI_API_KEY") else " (no API key set — regex fallback on OCR text)...")]})
        tier2_raw = P.run_tier2(file_path)
        tier2_result = P.merge_extractions(tier2_raw, best_so_far)
        best_so_far = tier2_result
        emit({"stage": "tier2", "status": "done", "title": STAGE_TITLES["tier2"],
              "detail": [f"Extracted via {tier2_result.extraction_tier}."],
              "payload": {"extraction": tier2_result.to_dict()}})

        emit({"stage": "validate2", "status": "running", "title": STAGE_TITLES["validate2"]})
        _pace()
        v2 = P.validate_extraction(best_so_far)
        emit({"stage": "validate2", "status": "done", "title": STAGE_TITLES["validate2"],
              "detail": [f"Confidence {v2.confidence_score:.0f}/100, valid={v2.is_valid}, "
                         f"{len(v2.issues)} issue(s)."],
              "payload": {"validation": v2.to_dict()}})

        if v2.is_valid and v2.confidence_score >= P.TIER2_CONFIDENCE_THRESHOLD:
            emit({"stage": "escalate2", "status": "done", "title": STAGE_TITLES["escalate2"],
                  "detail": [f"Confidence {v2.confidence_score:.0f} >= threshold "
                             f"{P.TIER2_CONFIDENCE_THRESHOLD:.0f} — STOPPING at Tier 2."]})
            emit({"stage": "tier3", "status": "skipped", "title": STAGE_TITLES["tier3"],
                  "detail": ["Not needed — Tier 2 already cleared the confidence bar."]})
            emit({"stage": "validate3", "status": "skipped", "title": STAGE_TITLES["validate3"]})
            final_extraction, final_validation = best_so_far, v2
        else:
            reasons = "; ".join(f"[{i.severity}] {i.field}: {i.message}" for i in v2.issues) \
                or "confidence below threshold"
            emit({"stage": "escalate2", "status": "done", "title": STAGE_TITLES["escalate2"],
                  "detail": [f"Tier 2 insufficient ({reasons}) — escalating to Tier 3 "
                             "(Vision LLM), the last automated tier."]})

            emit({"stage": "tier3", "status": "running", "title": STAGE_TITLES["tier3"],
                  "detail": ["Calling vision-capable gpt-4o-mini on the page image..." if P.os.environ.get("OPENAI_API_KEY")
                              else ["No API key set — no offline substitute for vision reasoning; returning empty/flagged result."]]})
            tier3_raw = P.run_tier3(file_path)
            tier3_result = P.merge_extractions(tier3_raw, best_so_far)
            emit({"stage": "tier3", "status": "done", "title": STAGE_TITLES["tier3"],
                  "detail": [f"Extracted via {tier3_result.extraction_tier}."],
                  "payload": {"extraction": tier3_result.to_dict()}})

            emit({"stage": "validate3", "status": "running", "title": STAGE_TITLES["validate3"]})
            _pace()
            v3 = P.validate_extraction(tier3_result)
            emit({"stage": "validate3", "status": "done", "title": STAGE_TITLES["validate3"],
                  "detail": [f"Final confidence {v3.confidence_score:.0f}/100, valid={v3.is_valid}, "
                             f"{len(v3.issues)} issue(s). This is the last automated attempt — "
                             "if still low, downstream decisioning routes to human review."],
                  "payload": {"validation": v3.to_dict()}})
            final_extraction, final_validation = tier3_result, v3
    # else Tier 1 already finalized: mark tier2/3 stages already emitted as skipped above

    extraction, validation = final_extraction, final_validation

    emit({"stage": "match", "status": "running", "title": STAGE_TITLES["match"]})
    _pace()
    match = P.match_invoice(extraction, store)
    emit({"stage": "match", "status": "done", "title": STAGE_TITLES["match"],
          "detail": [f"Match status: {match.match_status}"] + match.reasoning,
          "payload": {"match": match.to_dict()}})

    emit({"stage": "decision", "status": "running", "title": STAGE_TITLES["decision"]})
    _pace()
    decision = P.make_decision(extraction, validation, match, store)
    emit({"stage": "decision", "status": "done", "title": STAGE_TITLES["decision"],
          "detail": [f"Decision: {decision.decision}"] + decision.reasoning_trail,
          "payload": {"decision": P.asdict(decision)}})

    correspondence_block = None
    needs_outreach = correspondence_store is not None and P.needs_vendor_correspondence(decision)

    if needs_outreach:
        emit({"stage": "correspondence", "status": "running", "title": STAGE_TITLES["correspondence"]})
        _pace()
        draft = P.draft_vendor_email(extraction, match, decision)
        thread = correspondence_store.open_thread(
            source_file=file_path, vendor_name=extraction.vendor_name,
            reason=draft["trigger_reason"], subject=draft["subject"], body=draft["body"],
            original_extraction=extraction,
        )
        correspondence_block = thread.to_dict()
        emit({"stage": "correspondence", "status": "done", "title": STAGE_TITLES["correspondence"],
              "detail": [f"Drafted and logged outbound email — {draft['reason_code']}. "
                         f"Thread {thread.correspondence_id}."],
              "payload": {"correspondence": correspondence_block}})
        emit({"stage": "ledger", "status": "skipped", "title": STAGE_TITLES["ledger"],
              "detail": ["Not recorded yet — invoice is awaiting a vendor reply, "
                         "to avoid a later corrected resubmission being flagged as a duplicate."]})
    else:
        emit({"stage": "correspondence", "status": "skipped", "title": STAGE_TITLES["correspondence"],
              "detail": ["Not needed for this outcome."]})
        emit({"stage": "ledger", "status": "running", "title": STAGE_TITLES["ledger"]})
        _pace()
        store.record_invoice(
            invoice_number=extraction.invoice_number,
            vendor_name=extraction.vendor_name,
            amount=extraction.total_amount,
            po_number=match.matched_po["po_number"] if match.matched_po else extraction.po_number,
        )
        emit({"stage": "ledger", "status": "done", "title": STAGE_TITLES["ledger"],
              "detail": ["Recorded into procurement history / PO ledger."]})

    return {
        "source_file": file_path,
        "extraction": extraction.to_dict(),
        "validation": validation.to_dict(),
        "match": match.to_dict(),
        "decision": P.asdict(decision),
        "correspondence": correspondence_block,
        "pipeline_trace": trace_all,
    }


def _run_reprocess(source_file, correspondence_store, po_store, corrected_fields, reply_body, emit):
    for sid in STAGE_ORDER:
        skip_narr = "Not part of the vendor-reply reprocessing path."
        if sid in ("validate3", "match", "decision", "ledger"):
            continue
        emit({"stage": sid, "status": "skipped", "title": STAGE_TITLES[sid], "detail": [skip_narr]})

    emit({"stage": "validate3", "status": "running", "title": "Validate corrected extraction"})
    _pace()
    thread = correspondence_store.thread_for(source_file)
    original = thread.original_extraction
    corrected = P.InvoiceExtraction(source_file=source_file,
                                     extraction_tier=f"{original.extraction_tier}+VENDOR_REPLY")
    for f in P._SCALAR_FIELDS:
        corrected.core_fields[f] = corrected_fields.get(f, original.core_fields.get(f))
    corrected.line_items = corrected_fields.get("line_items") or original.line_items
    corrected.extra_fields = dict(original.extra_fields)
    corrected.extraction_metadata = dict(original.extraction_metadata)
    corrected.tax_mode = original.tax_mode
    corrected.raw_text_sample = original.raw_text_sample
    corrected.extraction_notes = list(original.extraction_notes) + [
        f"Field(s) corrected/added via vendor correspondence {thread.correspondence_id}: "
        f"{', '.join(corrected_fields.keys())}."
    ]
    correspondence_store.log_vendor_reply(thread.correspondence_id, reply_body, corrected_fields)
    validation = P.validate_extraction(corrected)
    emit({"stage": "validate3", "status": "done", "title": "Validate corrected extraction",
          "detail": [f"Confidence {validation.confidence_score:.0f}/100 after vendor-supplied correction.",
                     f"Vendor reply logged on thread {thread.correspondence_id}."],
          "payload": {"validation": validation.to_dict()}})

    emit({"stage": "match", "status": "running", "title": STAGE_TITLES["match"]})
    _pace()
    match = P.match_invoice(corrected, po_store)
    emit({"stage": "match", "status": "done", "title": STAGE_TITLES["match"],
          "detail": [f"Match status: {match.match_status}"] + match.reasoning,
          "payload": {"match": match.to_dict()}})

    emit({"stage": "decision", "status": "running", "title": STAGE_TITLES["decision"]})
    _pace()
    decision = P.make_decision(corrected, validation, match, po_store)
    emit({"stage": "decision", "status": "done", "title": STAGE_TITLES["decision"],
          "detail": [f"Decision: {decision.decision}"] + decision.reasoning_trail,
          "payload": {"decision": P.asdict(decision)}})

    still_needs_followup = P.needs_vendor_correspondence(decision)
    resolution = f"Vendor supplied {', '.join(corrected_fields.keys())} -> reprocessed to {decision.decision}."
    if still_needs_followup:
        resolution += (" NOTE: reprocessing still flags this for vendor input — a real system would "
                        "open a follow-up thread rather than close this one.")
    correspondence_store.resolve(thread.correspondence_id, resolution)
    emit({"stage": "correspondence", "status": "done", "title": STAGE_TITLES["correspondence"],
          "detail": [resolution], "payload": {"correspondence": thread.to_dict()}})

    emit({"stage": "ledger", "status": "running", "title": STAGE_TITLES["ledger"]})
    _pace()
    po_store.record_invoice(
        invoice_number=corrected.invoice_number, vendor_name=corrected.vendor_name,
        amount=corrected.total_amount,
        po_number=match.matched_po["po_number"] if match.matched_po else corrected.po_number,
    )
    emit({"stage": "ledger", "status": "done", "title": STAGE_TITLES["ledger"],
          "detail": ["Recorded into procurement history / PO ledger."]})

    return {
        "source_file": source_file,
        "extraction": corrected.to_dict(),
        "validation": validation.to_dict(),
        "match": match.to_dict(),
        "decision": P.asdict(decision),
        "correspondence": thread.to_dict(),
        "pipeline_trace": [f"Reprocessed after vendor reply on correspondence thread {thread.correspondence_id}."],
    }

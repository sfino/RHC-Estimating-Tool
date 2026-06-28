import json
import os
import uuid
import decimal
import urllib.request
import urllib.error
from datetime import datetime, timezone

import boto3

dynamodb = boto3.resource("dynamodb")


def _table():
    return dynamodb.Table(os.environ["PROJECTS_TABLE"])


# ── Router ────────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if method == "OPTIONS":
        return _resp(200, {})

    path   = event.get("rawPath", "").strip("/")
    parts  = path.split("/")

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return _resp(400, {"error": "Invalid JSON body"})

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    try:
        # Claude routes
        if path == "read-drawing":
            return _resp(200, _read_drawing(api_key, body))

        if path == "estimate":
            return _resp(200, _estimate(api_key, body))

        # Project routes
        if parts[0] == "projects":
            if len(parts) == 1:
                if method == "GET":
                    return _resp(200, _list_projects())
                if method == "POST":
                    return _resp(200, _create_project(body))

            if len(parts) == 2:
                if method == "GET":
                    return _resp(200, _get_project(parts[1]))

            if len(parts) == 3:
                pid, sub = parts[1], parts[2]
                if sub == "drawing" and method == "POST":
                    return _resp(200, _save_drawing(pid, body))
                if sub == "estimate" and method == "POST":
                    return _resp(200, _save_estimate(pid, body))

        return _resp(404, {"error": "Not found"})

    except Exception as e:
        print(f"Error [{method} /{path}]: {e}")
        return _resp(500, {"error": str(e)})


# ── Project CRUD ──────────────────────────────────────────────────────────────

def _list_projects():
    result = _table().scan()
    items  = result.get("Items", [])
    items.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
    return items


def _create_project(body):
    project = {
        "projectId": str(uuid.uuid4()),
        "name":      body.get("name", "Untitled Project"),
        "address":   body.get("address", ""),
        "type":      body.get("type", "Kitchen Remodel"),
        "sqft":      body.get("sqft", ""),
        "status":    "active",
        "createdAt": _now(),
        "drawings":  [],
        "estimates": [],
    }
    _table().put_item(Item=_to_dynamo(project))
    return project


def _get_project(project_id):
    result = _table().get_item(Key={"projectId": project_id})
    item   = result.get("Item")
    if not item:
        raise Exception("Project not found")
    return _from_dynamo(item)


def _save_drawing(project_id, drawing):
    entry = {**drawing, "id": str(uuid.uuid4()), "savedAt": _now()}
    _table().update_item(
        Key={"projectId": project_id},
        UpdateExpression="SET drawings = list_append(if_not_exists(drawings, :empty), :d)",
        ExpressionAttributeValues={":d": [_to_dynamo(entry)], ":empty": []},
    )
    return entry


def _save_estimate(project_id, estimate):
    entry = {**estimate, "id": str(uuid.uuid4()), "savedAt": _now()}
    _table().update_item(
        Key={"projectId": project_id},
        UpdateExpression="SET estimates = list_append(if_not_exists(estimates, :empty), :e)",
        ExpressionAttributeValues={":e": [_to_dynamo(entry)], ":empty": []},
    )
    return entry


# ── Claude helpers ────────────────────────────────────────────────────────────

def _claude(api_key, messages, max_tokens=2000):
    if not api_key or api_key == "placeholder":
        raise Exception("Anthropic API key not configured. Set ANTHROPIC_API_KEY in Lambda environment variables.")

    payload = json.dumps({
        "model":      "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "messages":   messages,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise Exception(f"Anthropic {e.code}: {body}")

    return "".join(c.get("text", "") for c in data["content"])


def _parse_json(text):
    return json.loads(text.replace("```json", "").replace("```", "").strip())


def _read_drawing(api_key, body):
    file_data  = body["fileData"]
    media_type = body["mediaType"]
    is_pdf     = media_type == "application/pdf"

    media_block = {
        "type": "document" if is_pdf else "image",
        "source": {"type": "base64", "media_type": media_type, "data": file_data},
    }

    prompt = (
        "This is a contractor's handwritten construction drawing with material notes. "
        "Extract every material, product, connector, hardware item, and structural member "
        "you can see — including product codes (like 'LUS20HZ'), lumber sizes, fastener "
        "specs, and any quantities written. If a quantity is not written, leave it null.\n\n"
        "Return ONLY valid JSON:\n"
        '{"jobType":"<type>","scale":"<scale or null>","items":['
        '{"description":"<name>","spec":"<code/size>","quantity":<n or null>,"unit":"<ea/lf/sf/etc>","notes":"<if unclear>"}],'
        '"drawingNotes":"<scope observations>","confidence":"<low/medium/high>"}'
    )

    text = _claude(api_key, [{"role": "user", "content": [
        media_block, {"type": "text", "text": prompt}
    ]}], max_tokens=2000)

    return _parse_json(text)


def _estimate(api_key, body):
    job_type   = body.get("type", "")
    sqft       = body.get("sqft", "")
    desc       = body.get("desc", "standard scope")
    comps      = body.get("comparableJobs", [])
    quals      = body.get("qualifiers", {})
    match_info = body.get("compMatchInfo", {})

    # Build qualifier summary for the new job
    qual_parts = []
    if quals.get("finishLevel"):
        qual_parts.append(f"Finish Level: {quals['finishLevel']}")
    if quals.get("demoScope"):
        qual_parts.append(f"Demo Scope: {quals['demoScope']}")
    if quals.get("layoutChange") is not None:
        qual_parts.append(f"Layout Change: {'Yes' if quals['layoutChange'] else 'No'}")
    if quals.get("homeAge"):
        qual_parts.append(f"Home Age: {quals['homeAge']}")
    if quals.get("cabinetType"):
        qual_parts.append(f"Cabinet Type: {quals['cabinetType']}")
    qual_str = " | ".join(qual_parts) if qual_parts else "none specified"

    # Build comp lines, flagging qualifier differences
    def _comp_line(j):
        line = (
            f"  - {j['name']}: {j['sqft']} sqft | "
            f"Actual {j['actHours']} hrs / ${j['actMaterials']}"
        )
        diffs = []
        for field, label in [("finishLevel","Finish"),("demoScope","Demo"),
                              ("homeAge","Age"),("cabinetType","Cabinets")]:
            jv, qv = j.get(field), quals.get(field)
            if qv and jv != qv:
                diffs.append(f"{label}: comp={jv}, new={qv}")
        jlc, qlc = j.get("layoutChange"), quals.get("layoutChange")
        if qlc is not None and jlc != qlc:
            diffs.append(f"Layout: comp={'changed' if jlc else 'same'}, new={'changed' if qlc else 'same'}")
        if diffs:
            line += f" [QUALIFIER DIFF — {'; '.join(diffs)}]"
        return line

    comp_summary = "\n".join(_comp_line(j) for j in comps) or "  No comparable jobs yet."

    exact_count = match_info.get("exactCount", len(comps))
    total       = match_info.get("total", len(comps))
    relaxed     = match_info.get("relaxed", False)
    relax_note  = (
        f"\nOnly {exact_count} exact qualifier match(es) found out of {total} "
        f"total jobs of this type. The comps below include near-matches — "
        f"weight QUALIFIER DIFF items accordingly.\n"
    ) if relaxed else ""

    prompt = (
        f"You are a construction estimating AI for a remodeling contractor.\n\n"
        f"NEW JOB\n"
        f"  Type: {job_type}\n"
        f"  Sqft: {sqft}\n"
        f"  Notes: {desc}\n"
        f"  Qualifiers: {qual_str}\n"
        f"{relax_note}\n"
        f"COMPARABLE COMPLETED JOBS "
        f"({exact_count} exact qualifier match, {total} total of this type):\n"
        f"{comp_summary}\n\n"
        f"Calibrate your estimate against the comps. For any comp marked "
        f"[QUALIFIER DIFF], reason about whether that difference pushes hours "
        f"and materials up or down relative to that comp before settling on ranges.\n\n"
        'Return ONLY valid JSON — no markdown, no explanation:\n'
        '{"estHours":<n>,"estHoursLow":<n>,"estHoursHigh":<n>,'
        '"estMaterials":<n>,"estMaterialsLow":<n>,"estMaterialsHigh":<n>,'
        '"confidence":<1-10>,"rationale":"<2-3 sentences referencing specific comps>",'
        '"risks":["<r1>","<r2>","<r3>"],"comparablesUsed":<n>}'
    )

    text = _claude(api_key, [{"role": "user", "content": prompt}], max_tokens=1000)
    return _parse_json(text)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()


def _to_dynamo(obj):
    """Recursively convert floats to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return decimal.Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(i) for i in obj]
    return obj


def _from_dynamo(obj):
    """Recursively convert Decimal back to float for JSON serialization."""
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _from_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_dynamo(i) for i in obj]
    return obj


def _resp(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type":                     "application/json",
            "Access-Control-Allow-Origin":       "*",
            "Access-Control-Allow-Headers":      "Content-Type",
            "Access-Control-Allow-Methods":      "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(_from_dynamo(body)),
    }

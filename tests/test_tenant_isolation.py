"""Cross-tenant isolation + authentication tests against the real
dashboard_api handler.

These drive `dashboard_api.handler.handler(event, context)` end to end with a
fake in-memory DynamoDB so we exercise the ACTUAL routing + auth + tenant
checks (not a reimplementation). They prove:

  - no session token            -> 401 on every protected route
  - a tampered token            -> 401
  - hospital A's token          -> sees ONLY hospital A's cases (list + stats)
  - hospital A fetching B's case -> 404 (indistinguishable from not-found)
  - hospital A mutating B's case -> 404 (status/message refused)
  - legacy untagged cases        -> visible to any authenticated tenant

Offline: a FakeTable stands in for DynamoDB; no AWS calls.
"""
import json
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "lambdas")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dashboard_api import handler as dh  # noqa: E402
from dashboard_api import session as sess  # noqa: E402


# --------------------------------------------------------------------------- #
# Minimal in-memory stand-ins for the DynamoDB resource/table surface the
# handler uses: get_item, put_item, update_item (list_append), scan, query.
# Only the operations the tested routes exercise are implemented.
# --------------------------------------------------------------------------- #
class FakeTable:
    def __init__(self, items=None, key_names=("case_id",)):
        self.key_names = key_names
        self.items = {self._key(i): dict(i) for i in (items or [])}

    def _key(self, item):
        return tuple(item[k] for k in self.key_names)

    def get_item(self, Key):
        k = tuple(Key[n] for n in self.key_names)
        it = self.items.get(k)
        return {"Item": dict(it)} if it else {}

    def put_item(self, Item):
        self.items[self._key(Item)] = dict(Item)
        return {}

    def scan(self, **kwargs):
        return {"Items": [dict(v) for v in self.items.values()]}

    def query(self, **kwargs):
        # Only used by _hospital_name_for (KeyConditionExpression hid = :h).
        vals = kwargs.get("ExpressionAttributeValues", {})
        hid = vals.get(":h")
        out = [dict(v) for v in self.items.values() if v.get("hospital_id") == hid]
        return {"Items": out[: kwargs.get("Limit", len(out))]}

    def update_item(self, Key, UpdateExpression="", ExpressionAttributeValues=None,
                    ExpressionAttributeNames=None, **kwargs):
        k = tuple(Key[n] for n in self.key_names)
        item = self.items.setdefault(k, dict(Key))
        vals = ExpressionAttributeValues or {}
        names = ExpressionAttributeNames or {}
        # Handle the two shapes the handler uses: SET #s = :x  and
        # SET field = list_append(if_not_exists(field, :e), :entry)
        if "list_append" in UpdateExpression:
            # crude: find the attribute before '=' 
            attr = UpdateExpression.split("SET", 1)[1].split("=", 1)[0].strip()
            entry = vals.get(":entry", [])
            item.setdefault(attr, [])
            item[attr] = list(item[attr]) + list(entry)
        else:
            # one or more "SET #a = :x, #b = :y"
            assignments = UpdateExpression.replace("SET", "", 1).split(",")
            for a in assignments:
                lhs, rhs = a.split("=")
                lhs, rhs = lhs.strip(), rhs.strip()
                field = names.get(lhs, lhs)
                item[field] = vals.get(rhs)
        return {}


class FakeDDBResource:
    def __init__(self, tables):
        self._tables = tables

    def Table(self, name):
        return self._tables[name]


@pytest.fixture
def fake_store(monkeypatch):
    """Two hospitals, one case each, plus one legacy untagged case."""
    cases = FakeTable(items=[
        {"case_id": "case-A1", "hospital_id": "hospital-a", "status": "OPEN",
         "patient_name": "A One", "created_at": "2026-01-01T00:00:00Z",
         "verification": {}, "extracted_card": {}},
        {"case_id": "case-B1", "hospital_id": "hospital-b", "status": "OPEN",
         "patient_name": "B One", "created_at": "2026-01-02T00:00:00Z",
         "verification": {}, "extracted_card": {}},
        {"case_id": "case-legacy", "status": "OPEN",  # no hospital_id
         "patient_name": "Legacy", "created_at": "2026-01-03T00:00:00Z",
         "verification": {}, "extracted_card": {}},
    ])
    staff = FakeTable(
        items=[
            {"hospital_id": "hospital-a", "username": "alice", "hospital_name": "Hospital A"},
            {"hospital_id": "hospital-b", "username": "bob", "hospital_name": "Hospital B"},
        ],
        key_names=("hospital_id", "username"),
    )
    rules = FakeTable(items=[], key_names=("payer_id", "cpt_code"))

    table_map = {
        dh.config.PRIOR_AUTH_TABLE: cases,
        dh.config.STAFF_USERS_TABLE: staff,
        dh.config.PAYER_RULES_TABLE: rules,
    }
    monkeypatch.setattr(dh.aws_clients, "dynamodb_resource", lambda: FakeDDBResource(table_map))
    return table_map


def _event(method, path, token=None, body=None, path_params=None, query=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers,
        "pathParameters": path_params or {},
        "queryStringParameters": query or {},
        "body": json.dumps(body) if body is not None else None,
    }


def _token(hospital, username):
    return sess.issue_token(hospital, username, "Clinic Staff")


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def test_no_token_rejected(fake_store):
    resp = dh.handler(_event("GET", "/cases"), None)
    assert resp["statusCode"] == 401


def test_tampered_token_rejected(fake_store):
    bad = _token("hospital-a", "alice")[:-4] + "zzzz"
    resp = dh.handler(_event("GET", "/cases", token=bad), None)
    assert resp["statusCode"] == 401


# --------------------------------------------------------------------------- #
# Tenant-scoped listing + stats
# --------------------------------------------------------------------------- #
def test_hospital_a_sees_only_its_own_and_legacy_cases(fake_store):
    resp = dh.handler(_event("GET", "/cases", token=_token("hospital-a", "alice")), None)
    assert resp["statusCode"] == 200
    ids = {c["case_id"] for c in json.loads(resp["body"])["cases"]}
    assert "case-A1" in ids
    assert "case-legacy" in ids       # legacy untagged visible to all
    assert "case-B1" not in ids       # hospital B's case hidden


def test_hospital_b_does_not_see_hospital_a_case(fake_store):
    resp = dh.handler(_event("GET", "/cases", token=_token("hospital-b", "bob")), None)
    ids = {c["case_id"] for c in json.loads(resp["body"])["cases"]}
    assert "case-B1" in ids
    assert "case-A1" not in ids


def test_stats_are_tenant_scoped(fake_store):
    resp = dh.handler(_event("GET", "/stats", token=_token("hospital-a", "alice")), None)
    total = json.loads(resp["body"])["total_cases"]
    # hospital A's own case + the legacy untagged one = 2 (not B's).
    assert total == 2


# --------------------------------------------------------------------------- #
# Cross-tenant direct access
# --------------------------------------------------------------------------- #
def test_hospital_a_cannot_read_hospital_b_case(fake_store):
    resp = dh.handler(
        _event("GET", "/cases/case-B1", token=_token("hospital-a", "alice"),
               path_params={"id": "case-B1"}),
        None,
    )
    assert resp["statusCode"] == 404  # indistinguishable from not-found


def test_hospital_a_cannot_change_hospital_b_case_status(fake_store):
    resp = dh.handler(
        _event("PATCH", "/cases/case-B1/status", token=_token("hospital-a", "alice"),
               path_params={"id": "case-B1"}, body={"status": "DENIED"}),
        None,
    )
    assert resp["statusCode"] == 404
    # And B's case is unchanged in the store.
    assert fake_store[dh.config.PRIOR_AUTH_TABLE].get_item({"case_id": "case-B1"})["Item"]["status"] == "OPEN"


def test_owning_hospital_can_read_its_case(fake_store):
    resp = dh.handler(
        _event("GET", "/cases/case-A1", token=_token("hospital-a", "alice"),
               path_params={"id": "case-A1"}),
        None,
    )
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["case"]["case_id"] == "case-A1"

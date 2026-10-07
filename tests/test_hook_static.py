"""sql/ddl/45_hook_static.sql on a local DuckDB: the static CSVs are copied to a
temporary folder standing in for /opt/duckdb/static, and s3://hydroc-raw/ is
pointed at another one."""

import shutil
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "sql" / "ddl" / "45_hook_static.sql"
NAMES = ("sources", "datasets", "business_domains", "business_concepts", "hooks")


@pytest.fixture
def static(tmp_path):
    """Copy of data/static that a test may edit."""
    folder = tmp_path / "static"
    shutil.copytree(ROOT / "data" / "static", folder)
    return folder


def load(static, tmp_path):
    bucket = tmp_path / "raw"
    for name in NAMES:
        (bucket / "metadata" / name).mkdir(parents=True, exist_ok=True)
    sql = (
        SCRIPT.read_text(encoding="utf-8")
        .replace("/opt/duckdb/static/", static.as_posix() + "/")
        .replace("s3://hydroc-raw/", bucket.as_posix() + "/")
    )
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS hook")
    con.execute("CREATE SCHEMA hook.metadata")
    con.execute(sql)
    return con


def test_hooks_derive_key_sets(static, tmp_path):
    con = load(static, tmp_path)
    rows = con.execute(
        "SELECT id, business_concept_id, dataset_id, hook_expression_dev, hook_expression_prod, "
        "hook_encoding, key_set, key_set_binary FROM hook.metadata.hooks"
    ).fetchall()
    # dataset 1 is Sodir (source 8), business concept 1 is field, in business
    # domain 1 (sup); dataset 2 (Sodir fields) shares the key set and its encoding
    assert rows == [
        (1, 1, 1, "prfInformationCarrier", "prfNpdidInformationCarrier", "integer",
         "no_sodir.sup.field", b"\x08\x01\x01"),
        (2, 1, 2, "fldName", "fldNpdidField", "integer", "no_sodir.sup.field", b"\x08\x01\x01"),
    ]


def test_business_domains_and_concepts(static, tmp_path):
    con = load(static, tmp_path)
    assert con.execute("SELECT id, code, name FROM hook.metadata.business_domains").fetchall() == [
        (1, "sup", "Supply"),
    ]
    assert con.execute("SELECT id, code, business_domain_id FROM hook.metadata.business_concepts").fetchall() == [
        (1, "field", 1),
    ]


DOMAINS = "id,code,name,description\n"
CONCEPTS = "id,code,name,description,business_domain_id\n"


@pytest.mark.parametrize("domains, error", [
    ("1,sup,Supply,x\n1,dem,Demand,x\n", "duplicate id 1"),
    ("1,sup,Supply,x\n2,sup,Supply again,x\n", "duplicate code sup"),
    ("1,su,Supply,x\n", "code su must be exactly 3"),
    ("1,supp,Supply,x\n", "code supp must be exactly 3"),
    ("1,SUP,Supply,x\n", "code SUP must be exactly 3"),
    ("1,s.p,Supply,x\n", "code s.p must be exactly 3"),
    ("1,sup,,x\n", "empty name"),
    ("256,sup,Supply,x\n", "must fit in one byte"),
])
def test_invalid_business_domains_fail(static, tmp_path, domains, error):
    (static / "business_domains.csv").write_text(DOMAINS + domains, encoding="utf-8")
    with pytest.raises(duckdb.Error, match=error):
        load(static, tmp_path)


@pytest.mark.parametrize("concepts, error", [
    ("1,field,Field,x,1\n1,well,Well,x,1\n", "duplicate id 1"),
    ("1,field,Field,x,1\n2,field,Field again,x,1\n", "duplicate code field"),
    ("1,,Field,x,1\n", "empty code"),
    ("1,field,Field,x,\n", "empty business_domain_id"),
    ("1,field,Field,x,99\n", "unknown business_domain_id 99"),
])
def test_invalid_business_concepts_fail(static, tmp_path, concepts, error):
    (static / "business_concepts.csv").write_text(CONCEPTS + concepts, encoding="utf-8")
    with pytest.raises(duckdb.Error, match=error):
        load(static, tmp_path)


HEADER = "id,business_concept_id,dataset_id,hook_expression_dev,hook_expression_prod,hook_encoding\n"


def test_empty_encoding_defaults_to_bigint(static, tmp_path):
    (static / "hooks.csv").write_text(HEADER + "1,1,1,a,b,\n", encoding="utf-8")
    con = load(static, tmp_path)
    assert con.execute("SELECT hook_encoding FROM hook.metadata.hooks").fetchone()[0] == "bigint"


@pytest.mark.parametrize("hooks, error", [
    ("1,1,1,a,b,integer\n1,1,1,a,b,integer\n", "duplicate id 1"),
    ("1,1,99,a,b,integer\n", "unknown dataset_id 99"),
    ("1,99,1,a,b,integer\n", "unknown business_concept_id 99"),
    ("1,1,1,,b,integer\n", "empty hook_expression_dev"),
    ("1,1,1,a,,integer\n", "empty hook_expression_prod"),
    ("1,1,1,a,b,float\n", "unknown hook_encoding float"),
    # same key set (no_sodir.field), different encodings
    ("1,1,1,a,b,integer\n2,1,1,a,b,varchar\n", "different hook_encoding"),
])
def test_invalid_hooks_fail(static, tmp_path, hooks, error):
    (static / "hooks.csv").write_text(HEADER + hooks, encoding="utf-8")
    with pytest.raises(duckdb.Error, match=error):
        load(static, tmp_path)


def test_ids_above_one_byte_fail(static, tmp_path):
    with (static / "business_concepts.csv").open("a", encoding="utf-8") as fh:
        fh.write("256,big,Big,Too large for one byte,1\n")
    (static / "hooks.csv").write_text(HEADER + "1,256,1,a,b,integer\n", encoding="utf-8")
    with pytest.raises(duckdb.Error, match="must fit in one byte"):
        load(static, tmp_path)

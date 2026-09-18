import csv

from projects import odoo


def _quote(
    name: str,
    *,
    amount_total: float,
    state: str = "sent",
    create_date: str = "2024-01-01 12:00:00",
    quote_id: int | None = None,
):
    return {
        'id': quote_id or hash((name, create_date)) & 0xFFFF,
        'name': name,
        'amount_total': amount_total,
        'state': state,
        'create_date': create_date,
    }


def test_add_quote_ids_selects_highest_under_cap(tmp_path, monkeypatch):
    csv_path = tmp_path / "customers.csv"
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(["Customer"])
        writer.writerow(["Alice"])
        writer.writerow(["Bob"])

    lookup = {
        'Alice': [
            _quote('SO001', amount_total=64000, create_date="2024-03-01 09:00:00"),
            _quote('SO002', amount_total=49000, create_date="2024-04-01 10:00:00"),
            _quote('SO003', amount_total=30000, state='draft', create_date="2024-02-01 11:00:00"),
        ],
        'Bob': [],
    }

    monkeypatch.setattr(odoo, "_find_quotes_for_customer", lambda name: lookup.get(name, []))

    result = odoo.add_quote_ids(
        csvfile=str(csv_path),
        name_col="Customer",
        quote_col="Quote",
    )

    with csv_path.open('r', newline='', encoding='utf-8') as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["Customer", "Quote"],
        ["Alice", "SO002"],
        ["Bob", "XX"],
    ]
    assert result['matched_rows'] == 1
    assert result['quotes_added'] == 1
    assert result['skipped_rows'] == 0


def test_add_quote_ids_skip_missing_rows(tmp_path, monkeypatch):
    csv_path = tmp_path / "customers.csv"
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(["Customer"])
        writer.writerow(["Alice"])
        writer.writerow(["Charlie"])

    lookup = {
        'Alice': [],
        'Charlie': [
            _quote('SO010', amount_total=12000, create_date="2024-05-01 08:00:00"),
        ],
    }

    monkeypatch.setattr(odoo, "_find_quotes_for_customer", lambda name: lookup.get(name, []))

    result = odoo.add_quote_ids(
        csvfile=str(csv_path),
        name_col="Customer",
        skip_missing=True,
    )

    with csv_path.open('r', newline='', encoding='utf-8') as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["Customer", "Quotation"],
        ["Charlie", "SO010"],
    ]
    assert result['matched_rows'] == 1
    assert result['quotes_added'] == 1
    assert result['skipped_rows'] == 1
    assert result['rows'] == 2


def test_add_quote_ids_uses_filler_when_cap_filters_all(tmp_path, monkeypatch):
    csv_path = tmp_path / "customers.csv"
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(["Customer"])
        writer.writerow(["Dana"])

    lookup = {
        'Dana': [
            _quote('SO020', amount_total=52000, create_date="2024-04-01 09:00:00"),
            _quote('SO021', amount_total=51000, create_date="2024-04-02 09:00:00"),
        ],
    }

    monkeypatch.setattr(odoo, "_find_quotes_for_customer", lambda name: lookup.get(name, []))

    result = odoo.add_quote_ids(
        csvfile=str(csv_path),
        name_col="Customer",
        quote_cap=50_000,
        filler="N/A",
    )

    with csv_path.open('r', newline='', encoding='utf-8') as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["Customer", "Quotation"],
        ["Dana", "N/A"],
    ]
    assert result['matched_rows'] == 0
    assert result['quotes_added'] == 0
    assert result['skipped_rows'] == 0

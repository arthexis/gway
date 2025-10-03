# file: projects/odoo.py

import csv
import re
import unicodedata
from pathlib import Path
from xmlrpc import client
from datetime import datetime, timedelta
from gway import gw


_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9']+")


def _strip_accents(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize('NFKD', value)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def _tokenize_name(name: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.finditer(name or ""):
        token = match.group(0).strip()
        if not token:
            continue
        canonical = _strip_accents(token).lower()
        if len(canonical) <= 1:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        tokens.append(token)
    return tokens


def _resolve_csv_path(csvfile: str) -> Path:
    if not csvfile:
        gw.abort("A CSV file name is required")

    raw_value = str(csvfile).strip()
    if not raw_value:
        gw.abort("A CSV file name is required")

    path = Path(raw_value)
    if path.suffix.lower() != ".csv":
        path = path.with_suffix(".csv")

    attempts: list[str] = []

    def _check(candidate: Path) -> Path | None:
        attempts.append(str(candidate))
        if candidate.exists():
            return candidate.resolve()
        return None

    if path.is_absolute():
        resolved = _check(path)
        if resolved:
            return resolved
    else:
        cwd_candidate = Path.cwd() / path
        resolved = _check(cwd_candidate)
        if resolved:
            return resolved

        base_candidate = Path(gw.base_path) / path
        resolved = _check(base_candidate)
        if resolved:
            return resolved

    client_name = gw.find_value('CLIENT', fallback=None)
    if not client_name:
        client_name = gw.find_value('client', fallback=None)
    if not client_name:
        client_name = gw.context.get('CLIENT') or gw.context.get('client')

    relative_target = Path(*[part for part in path.parts if part not in ('..', '.')])
    work_root = Path(gw.base_path) / "work"
    if client_name:
        client_candidate = work_root / str(client_name) / relative_target
        resolved = _check(client_candidate)
        if resolved:
            return resolved

    work_candidate = work_root / relative_target
    resolved = _check(work_candidate)
    if resolved:
        return resolved

    gw.abort(
        "CSV file not found. Checked: " + ", ".join(attempts)
    )



def _quote_sort_key(quote: dict) -> tuple[str, str]:
    create_date = quote.get('create_date') or ""
    name = quote.get('name') or ""
    return (create_date, name)


def _find_quotes_for_customer(name: str) -> list[str]:
    normalized_name = (name or "").strip()
    if not normalized_name:
        return []

    tokens = _tokenize_name(normalized_name)
    canonical_tokens = {_strip_accents(token).lower() for token in tokens}
    if not canonical_tokens and normalized_name:
        canonical_tokens = {_strip_accents(normalized_name).lower()}

    search_terms: list[str] = []
    seen_terms: set[str] = set()

    for candidate in (normalized_name, _strip_accents(normalized_name)):
        candidate = candidate.strip()
        if not candidate:
            continue
        canonical = _strip_accents(candidate).lower()
        if canonical in seen_terms:
            continue
        seen_terms.add(canonical)
        search_terms.append(candidate)

    for token in tokens:
        for variant in (token, _strip_accents(token)):
            if not variant:
                continue
            canonical = _strip_accents(variant).lower()
            if len(canonical) <= 1 or canonical in seen_terms:
                continue
            seen_terms.add(canonical)
            search_terms.append(variant)

    fields = ['id', 'name', 'state', 'partner_id', 'create_date']
    domain_base = [('state', '!=', 'cancel')]
    quotes_by_id: dict[int, dict] = {}

    for term in search_terms:
        domain = domain_base + [('partner_id.name', 'ilike', term)]
        results = execute_kw(
            [domain], {'fields': fields},
            model='sale.order', method='search_read'
        )
        for quote in results:
            quote_id = quote.get('id')
            if not quote_id:
                continue
            stored = quotes_by_id.get(quote_id)
            if stored is None:
                partner_field = quote.get('partner_id') or []
                partner_id = None
                partner_name = ""
                if isinstance(partner_field, (list, tuple)) and partner_field:
                    partner_id = partner_field[0]
                    if len(partner_field) > 1 and isinstance(partner_field[1], str):
                        partner_name = partner_field[1]
                elif isinstance(partner_field, int):
                    partner_id = partner_field
                stored = dict(quote)
                stored['_partner_id'] = partner_id
                stored['_partner_name'] = partner_name
                stored['_matched_terms'] = set()
                quotes_by_id[quote_id] = stored
            stored['_matched_terms'].add(term)

    if not quotes_by_id:
        return []

    partners: dict[object, dict] = {}
    for quote in quotes_by_id.values():
        partner_key = quote.get('_partner_id')
        partner_name = quote.get('_partner_name') or ""
        if partner_key is None:
            partner_key = partner_name
        group = partners.setdefault(partner_key, {
            'partner_name': partner_name,
            'quotes': [],
            'matched_terms': set(),
            'latest_date': "",
            'sent_count': 0,
        })
        group['quotes'].append(quote)
        group['matched_terms'].update(
            _strip_accents(term).lower()
            for term in quote.get('_matched_terms', set())
        )
        quote_date = quote.get('create_date') or ""
        if quote_date > group['latest_date']:
            group['latest_date'] = quote_date
        if quote.get('state') == 'sent':
            group['sent_count'] += 1

    for group in partners.values():
        partner_tokens = {
            _strip_accents(token).lower()
            for token in _tokenize_name(group.get('partner_name') or "")
        }
        group['token_overlap'] = len(canonical_tokens & partner_tokens)

    best_group = max(
        partners.values(),
        key=lambda grp: (
            grp.get('token_overlap', 0),
            len(grp.get('matched_terms', set())),
            grp.get('sent_count', 0),
            grp.get('latest_date', ""),
            grp.get('partner_name') or "",
        )
    )

    quotes = best_group['quotes']
    sent_quotes = [quote for quote in quotes if quote.get('state') == 'sent']
    if len(sent_quotes) == 1:
        quotes_to_use = sent_quotes
    elif len(sent_quotes) > 1:
        quotes_to_use = sent_quotes
    else:
        quotes_to_use = quotes

    ordered = sorted(quotes_to_use, key=_quote_sort_key, reverse=True)
    return [quote.get('name', '') for quote in ordered if quote.get('name')]


def execute_kw(*args, model: str, method: str, **kwargs) -> dict:
    """
    A generic function to directly interface with Odoo's execute_kw method.

    Parameters:
        model (str): The Odoo model to interact with (e.g., 'sale.order').
        method (str): The method to call on the model (e.g., 'read', 'write').
        args (list): Positional arguments to pass to the method.
        kwargs (dict): Keyword arguments to pass to the method.

    Returns:
        dict: The result of the execute_kw call.
    """
    url = gw.resolve("[ODOO_BASE_URL]")
    db_name = gw.resolve("[ODOO_DB_NAME]")
    username = gw.resolve("[ODOO_ADMIN_USER]")
    password = gw.resolve("[ODOO_ADMIN_PASSWORD]")

    gw.info(f"Odoo Execute: {model=} {method=} @ {url=} {db_name=} {username=}")
    if url.startswith("[") or "ODOO_BASE_URL" in url:
        gw.abort("Odoo XML-RPC url not configured. Please set ODOO_BASE_URL correctly.")
    try:
        common_client = client.ServerProxy(f"{url}/xmlrpc/2/common")
    except Exception as e:
        gw.exception(f"Error with ServerProxy setup", e)
        raise
    gw.debug(f"ServerProxy client: {common_client}")
    try:
        uid = common_client.authenticate(db_name, username, password, {})
    except Exception as e:
        gw.error(f"Error with Odoo authentication: {e}")
        print(f"( Did you forget to specify the correct --client? )")
        raise

    try:
        models_client = client.ServerProxy(f"{url}/xmlrpc/2/object")
        for reserved in ("db_name", "uid", "password", "model", "method"):
            gw.warning(f"Removing reserved keyword: {reserved}")
            kwargs.pop(reserved, None)
        gw.debug(f"Model client call execute_kw {model}.{method} with {args=} {kwargs=}")
        result = models_client.execute_kw(db_name, uid, password, model, method, *args, **kwargs)
        return result
    except Exception as e:
        gw.error(f"Error executing {model}.{method}: {e}")
        raise


def fetch_quotes(
    *,
    state='draft',
    older_than=None,
    salesperson=None,
    customer=None,
    tag=None,
    ws_tag=None,
    **kwargs
):
    """
    Fetch quotes/quotations from Odoo with optional filters.

    Parameters:
        state (str): Filter quotations by their state. Default is 'draft'.
        older_than (int, optional): Filter quotations older than a specific number of days.
        salesperson (str, optional): Filter quotations by the salesperson's name or part of it.
        customer (str, optional): Filter quotations by the customer's name or part of it.
        tag (str | int, optional): Filter quotations by tag name or id.
        ws_tag (str | int, optional): Filter quotations by tag containing whitespace.
        kwargs (list, optional): Additional domain filters for the query.

    Returns:
        dict: The fetched quotations.
    """
    model = 'sale.order'
    method = 'search_read'

    domain_filter = [('state', '=', state)]
    if older_than:
        cutoff_date = (datetime.now() - timedelta(days=older_than)).strftime('%Y-%m-%d')
        domain_filter.append(('create_date', '<=', cutoff_date))
    if salesperson:
        domain_filter.append(('user_id.name', 'ilike', salesperson))
    if customer:
        domain_filter.append(('partner_id.name', 'ilike', customer))
    if ws_tag and not tag:
        tag = ws_tag
    if tag:
        try:
            tag_id = int(tag)
            domain_filter.append(('tag_ids', 'in', [tag_id]))
        except (TypeError, ValueError):
            domain_filter.append(('tag_ids.name', 'ilike', tag))
    if kwargs:
        domain_filter.extend(kwargs)
    fields_to_fetch = ['name', 'amount_total', 'create_date', 'user_id', 'partner_id']
    try:
        result = execute_kw(
            [domain_filter], {'fields': fields_to_fetch},
            model=model, method=method
        )
        return result
    except Exception as e:
        gw.error(f"Error fetching quotations: {e}")
        raise


def fetch_products(*, name=None, latest_quotes=None):
    """
    Fetch the list of non-archived products from Odoo.
    If a name is provided, use it as a partial filter on the product name.
    """
    model = 'product.product'
    method = 'search_read'
    domain_filter = [('active', '=', True)]  # Non-archived products have active=True
    if name:
        domain_filter.append(('name', 'ilike', name))
    
    fields_to_fetch = ['name', 'list_price']  # Add fields as needed
    result = execute_kw(
        [domain_filter], {'fields': fields_to_fetch},
        model=model, method=method
    )
    return result


def fetch_quote_tags(*, name=None):
    """Fetch available quotation tags."""
    model = 'crm.tag'
    method = 'search_read'

    domain_filter = []
    if name:
        domain_filter.append(('name', 'ilike', name))

    fields_to_fetch = ['id', 'name']
    try:
        result = execute_kw(
            [domain_filter], {'fields': fields_to_fetch},
            model=model, method=method
        )
        return result
    except Exception as e:
        gw.error(f"Error fetching quote tags: {e}")
        raise


def split_ws_quote_tags():
    """Split tags containing spaces into separate tags on all matching quotes."""
    updated = []
    tags = fetch_quote_tags(name=' ')
    for tag in tags:
        name = tag.get('name', '')
        if ' ' not in name:
            continue
        left, right = name.split(' ', 1)
        new_ids = []
        for part in (left, right):
            existing = execute_kw(
                [[('name', '=', part)]], {'fields': ['id']},
                model='crm.tag', method='search_read',
            )
            if existing:
                new_ids.append(existing[0]['id'])
            else:
                new_id = execute_kw([
                    {'name': part}
                ], model='crm.tag', method='create')
                new_ids.append(new_id)
        quotes = fetch_quotes(tag=tag['id'])
        for quote in quotes:
            ops = [(3, tag['id'])] + [(4, nid) for nid in new_ids]
            execute_kw(
                [[quote['id']], {'tag_ids': ops}],
                model='sale.order', method='write',
            )
            updated.append({'quote': quote['id'], 'removed': tag['id'], 'added': new_ids})
    return updated


def fetch_customers(
    *,
    name=None,
    email=None,
    phone=None,
    country=None,
    latest_quotes=None,
    **kwargs
):
    """
    Fetch customers from Odoo with optional filters.

    Parameters:
        name (str, optional): Filter customers by their name or part of it.
        email (str, optional): Filter customers by their email address or part of it.
        phone (str, optional): Filter customers by their phone number or part of it.
        country (str, optional): Filter customers by their country name or part of it.
        **kwargs: Additional filters to be applied, passed as key-value pairs.

    Returns:
        dict: The fetched customers.
    """

    model = 'res.partner'
    method = 'search_read'

    # Start with an empty domain filter
    domain_filter = []

    if name:
        domain_filter.append(('name', 'ilike', name))
    if email:
        domain_filter.append(('email', 'ilike', email))
    if phone:
        domain_filter.append(('phone', 'ilike', phone))
    if country:
        domain_filter.append(('country_id.name', 'ilike', country))
    for field, value in kwargs.items():
        domain_filter.append((field, 'ilike', value))

    fields_to_fetch = ['name', 'create_date']
    try:
        result = execute_kw(
            [domain_filter], {'fields': fields_to_fetch},
            model=model, method=method
        )
        return result
    except Exception as e:
        gw.error(f"Error fetching customers: {e}")
        raise


def fetch_order(order_id):
    """
    Fetch the details of a specific order by its ID from Odoo, including all line details.
    """
    order_model = 'sale.order'
    order_method = 'read'
    line_model = 'sale.order.line'
    line_method = 'search_read'
    
    order_fields = ['name', 'amount_total', 'partner_id', 'state']
    line_fields = ['product_id', 'name', 'price_unit', 'product_uom_qty']
    
    # Check if order_id is a string that starts with 'S' and fetch by name instead of ID
    if isinstance(order_id, str) and order_id.startswith('S'):
        order_domain_filter = [('name', '=', order_id)]
        order_result = execute_kw(
            order_model, 'search_read', [order_domain_filter], {'fields': order_fields})
        if order_result:
            order_id = order_result[0]['id']
        else:
            return {'error': 'Order not found.'}
    else:
        order_result = execute_kw(
            [[order_id]], {'fields': order_fields},
            model=order_model, method=order_method,
        )

    line_domain_filter = [('order_id', '=', order_id)]
    line_result = execute_kw(
        [line_domain_filter], {'fields': line_fields},
        model=line_model, method=line_method,
    )
    
    result = {
        'order_info': order_result,
        'line_details': line_result
    }
    
    return result
        

def fetch_templates(*, name=None, active=True, **kwargs):
    """
    Fetch available quotation templates from Odoo with optional filters.

    Parameters:
        name (str, optional): Filter templates by name or part of it.
        active (bool): Whether to include only active templates. Defaults to True.
        **kwargs: Additional filters as key-value pairs.

    Returns:
        dict: The fetched quotation templates.
    """
    model = 'sale.order.template'
    method = 'search_read'
    
    domain_filter = []
    if name:
        domain_filter.append(('name', 'ilike', name))
    if active is not None:
        domain_filter.append(('active', '=', active))
    for field, value in kwargs.items():
        domain_filter.append((field, '=', value))

    fields_to_fetch = ['name', 'number_of_days', 'active']
    
    try:
        result = execute_kw(
            [domain_filter], {'fields': fields_to_fetch},
            model=model, method=method
        )
        return result
    except Exception as e:
        gw.error(f"Error fetching quotation templates: {e}")
        raise


def create_quote(*, customer, template_id, validity=None, notes=None):
    """
    Create a new quotation using a specified template and customer name.

    Parameters:
        customer (str): The name (or partial name) of the customer to link to the quote.
        template_id (int): The ID of the quotation template to use.
        validity (str, optional): The expiration date for the quote in 'YYYY-MM-DD' format.
        notes (str, optional): Internal notes or message to include in the quote.

    Returns:
        dict: The created quotation details.
    """
    # Step 1: Lookup the customer ID
    customer_result = fetch_customers(name=customer)
    if not customer_result:
        return {'error': f"No customer found matching name: {customer}"}
    
    customer_id = customer_result[0]['id']

    # Step 2: Create the quote using the template
    model = 'sale.order'
    method = 'create'

    values = {
        'partner_id': customer_id,
        'sale_order_template_id': template_id,
    }

    if validity:
        values['validity_date'] = validity
    if notes:
        values['note'] = notes

    try:
        quote_id = execute_kw(
            [values], {},
            model=model, method=method
        )
    except Exception as e:
        gw.error(f"Error creating quote: {e}")
        raise

    # Step 3: Return full quote details
    return fetch_order(quote_id)


def send_chat(message: str, *, username: str = "[ODOO_USERNAME]") -> bool:
    """
    Send a chat message to an Odoo user by username.
    """
    user_info = get_user_info(username=username)
    if not user_info:
        return False

    user_id = user_info["id"]
    return execute_kw(
        model="mail.channel",
        method="message_post",
        kwargs={
            "partner_ids": [(4, user_id)],
            "body": message,
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_comment",
        },
    )


def read_chat(*, 
        unread: bool = True, 
        username: str = "[ODOO_USERNAME]", 
    ) -> list[dict]:
    """
    Read chat messages from an Odoo user by username.
    If unread is True, only return unread messages.
    """
    username = gw.resolve(username) if isinstance(username, str) else username
    user_info = get_user_info(username=username)
    if not user_info: return []

    user_id = user_info["id"]
    domain = [["author_id", "=", user_id]]
    if unread:
        domain.append(["message_read", "=", False])

    messages = execute_kw(
        model="mail.message",
        method="search_read",
        domain=domain,
        fields=["id", "body", "date", "author_id", "message_type"],
    )
    return messages


def get_user_info(*, username: str) -> dict:
    """Retrieve Odoo user information by username."""
    user_data = execute_kw(
        model="res.users",
        method="search_read",
        domain=[["login", "=", username]],
        fields=["id", "name", "login"],
    )
    if not user_data:
        gw.error(f"User not found: {username}")
        return None
    return user_data[0]  # Return the first (and likely only) match.



def find_quotes(
    *,
    product,
    quantity: int = 1,
    state: str = 'draft',
    tag=None,
    **kwargs
):
    """
    Find all sale quotes that contain a given product (by id or name substring) with at least the given quantity.

    Parameters:
        product (str or int): Product ID or partial name.
        quantity (int): Minimum quantity of the product in the quote. Default is 1.
        state (str): Odoo sale order state (default: 'draft' for quotations).
        tag (str | int, optional): Filter quotations by tag name or id.
        **kwargs: Additional domain filters for sale.order.

    Returns:
        list: List of matching sale orders (quotes) with product line details.
    """
    gw.info(f"Finding quotes for {product=} {quantity=}")
    # Step 1: Resolve product id if necessary
    product_id = None

    # Try converting product to integer (for id)
    try:
        product_id = int(product)
        product_name = None
    except (ValueError, TypeError):
        # Search by product name substring
        results = fetch_products(name=product)
        if not results:
            return {"error": f"No products found matching: {product}"}
        if len(results) > 1:
            return {
                "error": f"Ambiguous product name '{product}', matches: " +
                         ", ".join([f"{p['id']}: {p['name']}" for p in results])
            }
        product_id = results[0]['id']
        product_name = results[0]['name']
        gw.info(f"Resolved product '{product}' to id {product_id} ('{product_name}')")
    
    # Step 2: Find sale order lines matching product + min quantity
    line_model = 'sale.order.line'
    line_method = 'search_read'
    domain_lines = [
        ('product_id', '=', product_id),
        ('product_uom_qty', '>=', quantity)
    ]
    line_fields = ['order_id', 'product_id', 'product_uom_qty', 'name']
    sale_lines = execute_kw(
        [domain_lines],
        {'fields': line_fields},
        model=line_model,
        method=line_method
    )
    if not sale_lines:
        return {"result": [], "info": f"No quotes found with product {product_id} and quantity >= {quantity}"}
    
    # Step 3: Collect all order_ids found in lines
    order_ids = list(set(l['order_id'][0] if isinstance(l['order_id'], (list, tuple)) else l['order_id'] for l in sale_lines))
    if not order_ids:
        return {"result": [], "info": f"No matching quotes found."}
    
    # Step 4: Fetch quotes for those order_ids with optional state filter
    order_model = 'sale.order'
    order_method = 'search_read'
    domain_orders = [('id', 'in', order_ids)]
    if state:
        domain_orders.append(('state', '=', state))
    if tag:
        try:
            tag_id = int(tag)
            domain_orders.append(('tag_ids', 'in', [tag_id]))
        except (TypeError, ValueError):
            domain_orders.append(('tag_ids.name', 'ilike', tag))
    # Add any extra filters from kwargs
    for key, value in kwargs.items():
        domain_orders.append((key, '=', value))
    fields_to_fetch = ['name', 'amount_total', 'create_date', 'user_id', 'partner_id', 'state']

    quotes = execute_kw(
        [domain_orders],
        {'fields': fields_to_fetch},
        model=order_model,
        method=order_method
    )

    # Step 5: Attach relevant line(s) for each quote
    quote_lines_by_order = {}
    for line in sale_lines:
        oid = line['order_id'][0] if isinstance(line['order_id'], (list, tuple)) else line['order_id']
        quote_lines_by_order.setdefault(oid, []).append({
            "product_id": line['product_id'],
            "qty": line['product_uom_qty'],
            "line_name": line['name'],
        })
    # Attach to each quote
    for quote in quotes:
        quote['matching_lines'] = quote_lines_by_order.get(quote['id'], [])

    return quotes


def add_quote_ids(
    *,
    csvfile: str,
    name_col: str | int | None = None,
    quote_col: str = "Quotation",
) -> dict:
    """Add quotation identifiers to a CSV file based on customer names.

    Parameters:
        csvfile (str): Path or name of the CSV file to update.
        name_col (str | int | None): Column containing customer names. Accepts
            a header label or a 1-based column number. Defaults to the first
            column when omitted.
        quote_col (str): Header to use for the quotation column. Defaults to
            ``"Quotation"``.

    Returns:
        dict: Summary including counts of processed rows and matched quotations.
    """
    csv_path = _resolve_csv_path(csvfile)
    gw.info(f"Annotating {csv_path} with quotation identifiers")

    with csv_path.open('r', newline='', encoding='utf-8-sig') as handle:
        sample = handle.read(2048)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            has_header = False
        reader = csv.reader(handle, dialect)
        rows = [list(row) for row in reader]

    quote_column_name = str(quote_col).strip() if quote_col is not None else ""
    if not quote_column_name:
        quote_column_name = "Quotation"

    if not rows:
        gw.warning(f"CSV file {csv_path} is empty; nothing to annotate")
        return {
            'csv_path': str(csv_path),
            'rows': 0,
            'matched_rows': 0,
            'quotes_added': 0,
            'quote_column': quote_column_name,
        }

    def _string_to_int(value: str) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    force_header = False
    if isinstance(name_col, str):
        stripped = name_col.strip()
        if stripped:
            force_header = _string_to_int(stripped) is None

    if rows and force_header:
        has_header = True

    if has_header and rows:
        header_row = rows[0][:]
        data_rows = [row[:] for row in rows[1:]]
    else:
        header_row = None
        data_rows = [row[:] for row in rows]

    def resolve_name_index(value) -> int:
        if value is None:
            return 0
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return 0
            numeric = _string_to_int(stripped)
            if numeric is None:
                if header_row is None:
                    gw.abort(
                        "name_col expects a header label but the CSV has no header row"
                    )
                lowered = [(col or "").strip().lower() for col in header_row]
                target = stripped.lower()
                if target in lowered:
                    return lowered.index(target)
                gw.abort(f"Column '{stripped}' not found in CSV header")
            value = numeric
        try:
            index = int(value)
        except (TypeError, ValueError):
            gw.abort(f"Invalid name_col value: {value}")
        if index < 0:
            gw.abort("name_col cannot be negative")
        return index - 1 if index > 0 else 0

    name_index = resolve_name_index(name_col)

    if header_row is not None and name_index >= len(header_row):
        gw.abort(
            f"name_col index {name_index} is outside the header range ({len(header_row)} columns)"
        )

    if header_row is not None:
        normalized_header = [(col or "").strip().lower() for col in header_row]
        try:
            quote_index = normalized_header.index(quote_column_name.lower())
            header_row[quote_index] = quote_column_name
        except ValueError:
            header_row.append(quote_column_name)
            quote_index = len(header_row) - 1
    else:
        quote_index = max((len(row) for row in data_rows), default=0)

    processed_rows: list[list[str]] = []
    if header_row is not None:
        processed_rows.append(header_row)

    quote_cache: dict[str, list[str]] = {}
    matched_rows = 0
    quotes_added = 0

    for row in data_rows:
        row_data = list(row)
        raw_name = row_data[name_index] if name_index < len(row_data) else ""
        customer_name = str(raw_name).strip() if raw_name is not None else ""
        if customer_name:
            cache_key = _strip_accents(customer_name).lower() or customer_name.lower()
            cached = quote_cache.get(cache_key)
            if cached is None:
                cached = _find_quotes_for_customer(customer_name)
                quote_cache[cache_key] = cached
            quotes = cached
        else:
            quotes = []

        if quotes:
            matched_rows += 1
            quotes_added += len(quotes)
            quote_value = " ".join(quotes)
        else:
            quote_value = ""

        target_index = quote_index if quote_index is not None else len(row_data)
        while len(row_data) <= target_index:
            row_data.append("")
        row_data[target_index] = quote_value
        processed_rows.append(row_data)

    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, dialect)
        writer.writerows(processed_rows)

    total_rows = len(data_rows)
    gw.info(
        f"Updated {csv_path}: matched {matched_rows}/{total_rows} rows, "
        f"recorded {quotes_added} quotations in column '{quote_column_name}'"
    )

    return {
        'csv_path': str(csv_path),
        'rows': total_rows,
        'matched_rows': matched_rows,
        'quotes_added': quotes_added,
        'quote_column': quote_column_name,
        'name_column_index': name_index,
        'quote_column_index': quote_index,
    }


def fetch_projects(*, name=None):
    """Fetch projects by partial name."""
    model = 'project.project'
    method = 'search_read'

    domain_filter = []
    if name:
        domain_filter.append(('name', 'ilike', name))

    fields_to_fetch = ['name']
    result = execute_kw(
        [domain_filter], {'fields': fields_to_fetch},
        model=model, method=method
    )
    return result


def create_task(
    *,
    title: str | None = None,
    project: str | int = '[ODOO_DEFAULT_PROJECT]',
    customer: str | None = None,
    phone: str | None = None,
    notes: str | None = None,
    new_customer: bool = False,
):
    """Create an Odoo project task with optional customer creation.

    If ``title`` is not provided but ``customer`` is, the task title defaults
    to the customer name.
    """

    # Resolve default project value from environment
    if isinstance(project, str):
        project_resolved = gw.resolve(project)
    else:
        project_resolved = project

    # Determine project_id
    try:
        project_id = int(project_resolved)
    except (ValueError, TypeError):
        projects = fetch_projects(name=project_resolved)
        if not projects:
            return {'error': f"Project not found: {project_resolved}"}
        if len(projects) > 1:
            gw.warning(f"Multiple projects match '{project_resolved}', using first")
        project_id = projects[0]['id']

    # Handle customer lookup / creation
    customer_id = None
    if customer:
        if new_customer:
            values = {'name': customer}
            if phone:
                values['phone'] = phone
            if notes:
                values['comment'] = notes
            customer_id = execute_kw(
                [values], {},
                model='res.partner', method='create'
            )
        else:
            result = fetch_customers(name=customer)
            if not result:
                return {'error': f"Customer not found: {customer}"}
            customer_id = result[0]['id']

    if title is None:
        if customer:
            title = customer
        else:
            return {'error': 'title or customer required'}

    description_parts = []
    if phone:
        description_parts.append(f"Phone: {phone}")
    if notes:
        description_parts.append(notes)
    description = '\n'.join(description_parts)

    task_vals = {
        'name': title,
        'project_id': project_id,
    }
    if customer_id:
        task_vals['partner_id'] = customer_id
    if description:
        task_vals['description'] = description

    task_id = execute_kw(
        [task_vals], {},
        model='project.task', method='create'
    )
    task = execute_kw(
        [[task_id]], {'fields': ['id', 'name', 'project_id', 'partner_id', 'description']},
        model='project.task', method='read'
    )
    return task

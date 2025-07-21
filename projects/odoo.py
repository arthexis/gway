# file: projects/odoo.py

from xmlrpc import client
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
from gway import gw


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
        gw.halt("Odoo XML-RPC url not configured. Please set ODOO_BASE_URL correctly.")
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


chatbot_log: list[dict] = []

def setup_chatbot_app(*, 
            path="/chatbot", username="[ODOO_USERNAME]", alias="Operator", apps=None
        ):
    """
    Create a FastAPI app (or append to existing ones) serving a chatbot UI and logic.
    """

    last_seen = {}
    username = gw.resolve(username) if isinstance(username, str) else username

    def log_msg(direction, msg):
        chatbot_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "direction": direction,
            "message": msg,
        })

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def poll_messages():
            while True:
                try:
                    messages = read_chat(username=username)
                    for msg in messages:
                        msg_id = msg["id"]
                        if msg_id not in last_seen:
                            log_msg("in", msg["body"])
                            last_seen[msg_id] = True
                    await asyncio.sleep(5)
                except Exception as e:
                    gw.error(f"Chatbot polling error: {e}")
                    await asyncio.sleep(10)
        asyncio.create_task(poll_messages())
        yield

    app = FastAPI(lifespan=lifespan)

    @app.get(path, response_class=HTMLResponse)
    async def ui(request: Request):
        messages = read_chat(username=username, unread=False)
        html = f"""
        <html>
        <head>
            <title>Chatbot Interface</title>
            <style>
                body {{ font-family: sans-serif; padding: 1rem; }}
                .log {{ background: #f9f9f9; padding: 1em; margin-bottom: 1em; border: 1px solid #ccc; }}
                .incoming {{ color: darkblue; }}
                .outgoing {{ color: darkgreen; }}
                form {{ margin-top: 1em; }}
            </style>
        </head>
        <body>
            <h1>Chatbot: {username}</h1>
            <div class="log">
        """
        for msg in reversed(messages[-20:]):
            cls = "incoming" if msg["author_id"][1] != alias else "outgoing"
            html += f"<div class='{cls}'><b>{msg['author_id'][1]}</b>: {msg['body']}</div>"
        html += f"""
            </div>
            <form method="post">
                <label>Alias: <input name="alias" value="{alias}" /></label><br />
                <textarea name="body" rows="3" cols="60" placeholder="Type response..."></textarea><br/>
                <button type="submit">Send</button>
            </form>
        </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=200)

    @app.post(path)
    async def post_message(alias: str = Form(...), body: str = Form(...)):
        if body.strip():
            send_chat(body, username=username)
            log_msg("out", body)
        return RedirectResponse(url=path, status_code=303)

    if apps is None:
        return [app]
    elif isinstance(apps, list):
        return apps + [app]
    else:
        return [apps, app]

# projects/odoo.py

def find_quotes(
    *,
    product,
    quantity: int = 1,
    state: str = 'draft',
    **kwargs
):
    """
    Find all sale quotes that contain a given product (by id or name substring) with at least the given quantity.

    Parameters:
        product (str or int): Product ID or partial name.
        quantity (int): Minimum quantity of the product in the quote. Default is 1.
        state (str): Odoo sale order state (default: 'draft' for quotations).
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

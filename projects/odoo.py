from xmlrpc import client
from datetime import datetime, timedelta
from gway import Gateway

gway = Gateway()

#---------------------------------------------------------------------------------------
# Odoo functions for interacting with the Odoo API
#---------------------------------------------------------------------------------------

def execute(
        *args, model: str, method: str, 
        url : str = "[ODOO_BASE_URL]", 
        db_name : str = "[ODOO_DB_NAME]",
        username : str = "[ODOO_ADMIN_USER]",
        password : str = "[ODOO_ADMIN_PASSWORD]",
        **kwargs
    ) -> dict:
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
    gway.logger.debug(f"Odoo Execute: {model=} {method=} @ {url=} {db_name=} {username=} {password=}")
    try:
        common_client = client.ServerProxy(f"{url}/xmlrpc/2/common")
    except Exception as e:
        gway.logger.exception(f"Error with ServerProxy setup", e)
        raise
    gway.logger.debug(f"ServerProxy client: {common_client}")
    try:
        uid = common_client.authenticate(db_name, username, password, {})
    except Exception as e:
        gway.logger.error(f"Error with Odoo authentication: {e}")
        gway.print(f"( Did you forget to specify the correct --client? )")
        raise

    try:
        models_client = client.ServerProxy(f"{url}/xmlrpc/2/object")
        for reserved in ("db_name", "uid", "password", "model", "method"):
            gway.logger.warning(f"Removing reserved keyword: {reserved}")
            kwargs.pop(reserved, None)
        gway.logger.debug(f"Executing {model}.{method} with args: {args} and kwargs: {kwargs}")
        result = models_client.execute_kw(db_name, uid, password, model, method, *args, **kwargs)
        return result
    except Exception as e:
        gway.logger.error(f"Error executing {model}.{method}: {e}")
        raise


def fetch_quotes(
    *,
    state='draft',
    older_than=None,
    salesperson=None,
    customer=None,
    **kwargs
):
    """
    Fetch quotes/quotations from Odoo with optional filters.

    Parameters:
        state (str): Filter quotations by their state. Default is 'draft'.
        older_than (int, optional): Filter quotations older than a specific number of days.
        salesperson (str, optional): Filter quotations by the salesperson's name or part of it.
        customer (str, optional): Filter quotations by the customer's name or part of it.
        kwargs (list, optional): Additional domain filters for the query.

    Returns:
        dict: The fetched quotations.
    """
    # TODO: If salesperson is not specified, use the current user as default (ODOO_ADMIN_USER). 
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
    if kwargs:
        domain_filter.extend(kwargs)
    fields_to_fetch = ['name', 'amount_total', 'create_date', 'user_id', 'partner_id']
    try:
        result = gway.odoo.execute(
            [domain_filter], {'fields': fields_to_fetch},
            model=model, method=method
        )
        return result
    except Exception as e:
        gway.logger.error(f"Error fetching quotations: {e}")
        raise


def fetch_products(*, name=None, latest_quotes=None):
    """
    Fetch the list of non-archived products from Odoo.
    If a name is provided, use it as a partial filter on the product name.
    """
    # TODO: If latest_quotes is a number, also fetch the latest quotes that use this product.
    model = 'product.product'
    method = 'search_read'
    domain_filter = [('active', '=', True)]  # Non-archived products have active=True
    if name:
        domain_filter.append(('name', 'ilike', name))
    
    fields_to_fetch = ['name', 'list_price']  # Add fields as needed
    result = gway.odoo.execute(
        [domain_filter], {'fields': fields_to_fetch},
        model=model, method=method
    )
    return result


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
    # TODO: If latest_quotes is a number, also fetch the latest quotes for this customer.

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
        result = gway.odoo.execute(
            [domain_filter], {'fields': fields_to_fetch},
            model=model, method=method
        )
        return result
    except Exception as e:
        gway.logger.error(f"Error fetching customers: {e}")
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
        order_result = gway.odoo.execute(
            order_model, 'search_read', [order_domain_filter], {'fields': order_fields})
        if order_result:
            order_id = order_result[0]['id']
        else:
            return {'error': 'Order not found.'}
    else:
        order_result = gway.odoo.execute(
            [[order_id]], {'fields': order_fields},
            model=order_model, method=order_method,
        )

    line_domain_filter = [('order_id', '=', order_id)]
    line_result = gway.odoo.execute(
        [line_domain_filter], {'fields': line_fields},
        model=line_model, method=line_method,
    )
    
    result = {
        'order_info': order_result,
        'line_details': line_result
    }
    
    return result
        

def send_chat(message: str, *, username: str = "[ODOO_USERNAME]") -> bool:
    """
    Send a chat message to an Odoo user by username.
    """
    user_info = gway.odoo.get_user_info(username=username)
    if not user_info:
        return False

    user_id = user_info["id"]
    return gway.odoo.execute(
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
    user_info = gway.odoo.get_user_info(username=username)
    if not user_info: return []

    user_id = user_info["id"]
    domain = [["author_id", "=", user_id]]
    if unread:
        domain.append(["message_read", "=", False])

    messages = gway.odoo.execute(
        model="mail.message",
        method="search_read",
        domain=domain,
        fields=["id", "body", "date", "author_id", "message_type"],
    )
    return messages


def get_user_info(*, username: str) -> dict:
    """Retrieve Odoo user information by username."""
    user_data = gway.odoo.execute(
        model="res.users",
        method="search_read",
        domain=[["login", "=", username]],
        fields=["id", "name", "login"],
    )
    if not user_data:
        gway.logger.error(f"User not found: {username}")
        return None
    return user_data[0]  # Return the first (and likely only) match.


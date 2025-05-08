import json
import os

from gway import gw, requires


@requires("bottle")
def start_api(
        host: str = "[CHAT_API_HOST|localhost]", 
        port: int = "[CHAT_API_PORT|8081]", 
        debug: bool = False
    ):
    from bottle import Bottle, request, response, run, abort
    gw.info(f"{host}:{port}")
    app = Bottle()

    @app.get("/chat/functions")
    def get_functions():
        fnames = request.query.get("function_names")
        if not fnames:
            response.status = 400
            return {"error": "Missing 'function_names' parameter"}

        try:
            functions = gw.describe_functions(fnames.split(" - "))
            return functions
        except Exception as e:
            gw.exception("Error describing functions")
            response.status = 500
            return {"error": str(e)}

    @app.post("/chat/functions")
    def run_functions():
        data = request.json or {}
        fnames = data.get("function_names")
        args = data.get("args", [])
        kwargs = data.get("kwargs", {})

        if not fnames:
            response.status = 400
            return {"error": "Missing 'function_names'"}

        try:
            results = gw.run(fnames, args=args, kwargs=kwargs)
            return {"result": results}
        except Exception as e:
            gw.exception("Function execution failed")
            response.status = 500
            return {"error": str(e)}

    @app.post("/chat/authorize")
    def authorize():
        data = request.json or {}
        token = data.get("bearer_token_or_email")
        if not token:
            response.status = 400
            return {"error": "Missing bearer_token_or_email"}
        # Here you'd implement real token logic
        return {"status": "authorized", "token": token}

    @app.get("/chat/products/<product_id>")
    def get_product(product_id):
        product_path = gw.resource("temp", "products", product_id, "product.json")
        if not os.path.exists(product_path):
            abort(404, "Product not found")
        with open(product_path) as f:
            return json.load(f)

    @app.get("/chat/products/<product_id>/files")
    def get_product_files(product_id):
        product_dir = gw.resource("temp", "products", product_id)
        if not os.path.isdir(product_dir):
            abort(404, "No files found")
        # return a list of files (or ZIP, or first file)
        files = os.listdir(product_dir)
        return {"files": files}

    run(app, host=host, port=int(port), debug=debug)


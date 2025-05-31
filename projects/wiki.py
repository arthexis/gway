from gway import gw

def query(query_text: str):
    """
    Fetch data from Wikidata using either a SPARQL query or natural language.
    Returns clean, user-friendly results. Logs all key steps to `gw.info`.
    """
    import requests

    endpoint_url = "https://query.wikidata.org/sparql"
    headers = {"User-Agent": "Mozilla/5.0"}

    COMMON_PROPERTIES = {
        "capital": "P36",
        "birthplace": "P19",
        "birth date": "P569",
        "death date": "P570",
        "country": "P17",
        "instance of": "P31",
        "located in": "P131",
        "continent": "P30",
        "currency": "P38",
        "head of government": "P6",
        "head of state": "P35",
        "official language": "P37",
        "area": "P2046",
        "highest point": "P610",
        "lowest point": "P1589",
        "population": "P1082",
        "time zone": "P421",
        "flag image": "P41",
        "anthem": "P85",
        "inception": "P571",
        "ISO code": "P297",
        "calling code": "P474",
        "GDP": "P2131",
        "native language": "P103",
        "motto": "P1451",
        "founder": "P112",
        "academic discipline": "P2578",
        "religion": "P140",
        "occupation": "P106",
        "educated at": "P69",
        "employer": "P108",
        "position held": "P39",
        "award received": "P166",
        "genre": "P136",
        "author": "P50",
        "notable work": "P800",
        "publication date": "P577",
        "publisher": "P123",
        "director": "P57",
        "producer": "P162",
        "composer": "P86",
        "cast member": "P161",
        "narrator": "P2438",
        "screenwriter": "P58",
        "based on": "P144",
        "publication place": "P291",
        "written in": "P407",
        "part of": "P361",
        "subclass of": "P279",
        "language of work": "P364",
        "family name": "P734",
        "given name": "P735",
        "ethnic group": "P172",
        "residence": "P551",
        "work location": "P937",
        "military rank": "P410",
        "conflict": "P607",
        "military branch": "P241",
        "political party": "P102",
        "member of": "P463",
        "affiliation": "P1416",
        "website": "P856",
        "image": "P18",
        "logo image": "P154",
        "coat of arms": "P94",
        "shield image": "P2910",
        "nickname": "P1449",
        "short name": "P1813",
        "twitter username": "P2002",
        "instagram username": "P2003",
        "youtube channel": "P2397",
        "facebook ID": "P2013",
        "IMDb ID": "P345",
        "MusicBrainz artist ID": "P434",
        "discography": "P358",
        "has part": "P527",
        "part of the series": "P179",
        "season": "P4908",
        "episode number": "P433",
        "publication": "P1433",
        "series ordinal": "P1545",
        "coordinate location": "P625",
        "located on terrain feature": "P706",
        "elevation above sea level": "P2044",
        "climate": "P3984",
        "heritage designation": "P1435",
        "UNESCO World Heritage Site": "P757",
        "official name": "P1448",
        "postal code": "P281",
        "bordering country": "P47",
        "neighboring municipality": "P206",
        "lake inflow": "P200",
        "lake outflow": "P201",
        "river mouth": "P403",
        "source of the river": "P947",
        "flow rate": "P2225",
        "basin size": "P2053",
        "length": "P2043",
    }

    def looks_like_sparql(text: str) -> bool:
        return text.strip().lower().startswith(("select", "ask", "construct", "describe", "prefix"))

    def resolve_entity_label_to_qid(label: str) -> str | None:
        """Resolve a label to a QID via Wikidata's search API."""
        search_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbsearchentities",
            "search": label,
            "language": "en",
            "format": "json",
            "type": "item"
        }
        try:
            res = requests.get(search_url, params=params, headers=headers)
            res.raise_for_status()
            hits = res.json().get("search", [])
            if hits:
                qid = hits[0]["id"]
                gw.info(f"Resolved '{label}' → {qid}")
                return qid
            gw.info(f"No entity found for '{label}'")
        except requests.RequestException as e:
            gw.info(f"Error resolving label '{label}': {e}")
        return None

    def parse_natural_query(nl: str) -> str:
        nl = nl.lower().strip()
        for prop_label, pid in COMMON_PROPERTIES.items():
            if prop_label in nl:
                parts = nl.split(prop_label)
                entity_label = parts[1] if len(parts) > 1 else parts[0]
                entity_label = entity_label.strip(" of ").strip()
                if not entity_label:
                    continue
                qid = resolve_entity_label_to_qid(entity_label)
                if not qid:
                    return ""
                return f"""
                SELECT ?answerLabel WHERE {{
                  wd:{qid} wdt:{pid} ?answer.
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
                }} LIMIT 10
                """
        return ""

    original_text = query_text.strip()
    gw.info(f"Input received: {original_text}")

    if looks_like_sparql(original_text):
        sparql_query = original_text
        gw.info("Detected SPARQL input.")
    else:
        sparql_query = parse_natural_query(original_text)
        if not sparql_query:
            return {"answers": [], "message": "Could not interpret input."}
        gw.info(f"Auto-generated SPARQL:\n{sparql_query.strip()}")

    try:
        response = requests.get(endpoint_url, params={"query": sparql_query, "format": "json"}, headers=headers)
        gw.info(f"Query URL: {response.url}")
        response.raise_for_status()
        results = response.json().get("results", {}).get("bindings", [])
        answers = [row["answerLabel"]["value"] for row in results if "answerLabel" in row]
        if answers:
            return {"answers": answers}
        return {"answers": [], "message": "No results found."}
    except requests.RequestException as e:
        gw.info(f"SPARQL query failed: {e}")
        return {"answers": [], "error": str(e)}

fetch = query
ask = query

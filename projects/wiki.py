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
        "dissolved": "P576",
        "mass": "P2067",
        "height": "P2048",
        "width": "P2049",
        "depth": "P2192",
        "diameter": "P2386",
        "spouse": "P26",
        "child": "P40",
        "sibling": "P3373",
        "father": "P22",
        "mother": "P25",
        "doctoral advisor": "P184",
        "doctoral student": "P185",
        "work period": "P2031",
        "work period end": "P2032",
        "drafted by": "P647",
        "sexual orientation": "P91",
        "eye color": "P1340",
        "hair color": "P1884",
        "blood type": "P1221",
        "voice actor": "P725",
        "animator": "P694",
        "screenplay by": "P58",
        "costume designer": "P2515",
        "cinematographer": "P344",
        "editor": "P1040",
        "executive producer": "P1431",
        "soundtrack album": "P959",
        "ISBN-13": "P212",
        "ISSN": "P236",
        "OCLC control number": "P243",
        "LCCN": "P1144",
        "archives at": "P485",
        "collection": "P195",
        "inventory number": "P217",
        "accession number": "P528",
        "exhibition history": "P608",
        "street address": "P6375",
        "coordinate precision": "P5823",
        "longitude": "P6251",
        "latitude": "P6250",
        "elevation": "P2044",
        "geonames ID": "P1566",
        "OpenStreetMap relation ID": "P402",
        "Commons category": "P373",
        "Commons gallery": "P935",
        "Wikivoyage banner": "P948",
        "Wikimedia disambiguation page": "P9351",
        "Encyclopædia Britannica Online ID": "P1417",
        "VIAF ID": "P214",
        "GND ID": "P227",
        "Library of Congress authority ID": "P244",
        "NKCR AUT ID": "P691",
        "MusicBrainz place ID": "P1004",
        "IMDb episode ID": "P345",
        "Rotten Tomatoes ID": "P1258",
        "TMDb ID": "P4947",
        "AllMusic artist ID": "P1728",
        "Discogs artist ID": "P1953",
        "band member": "P527",
        "instrument": "P1303",
        "musical genre": "P136",
        "voice type": "P412",
        "number of episodes": "P1113",
        "number of seasons": "P2437",
        "first aired": "P580",
        "last aired": "P582",
        "air date": "P577",
        "TV network": "P449",
        "production company": "P272",
        "filming location": "P915",
        "set in period": "P2408",
        "narrative location": "P840",
        "based on work": "P144",
        "influenced by": "P737",
        "influenced": "P737",
        "theory": "P101",
        "field of work": "P101",
        "research interest": "P2578",
        "notable student": "P802",
        "notable idea": "P800",
        "fictional universe": "P1444",
        "narrative universe": "P1434",
        "event": "P793",
        "organized by": "P664",
        "participant": "P710",
        "winner": "P1346",
        "ranking": "P1352",
        "award nomination": "P1411",
        "judges": "P1731",
        "sports season": "P3450",
        "sports league": "P118",
        "sports team": "P54",
        "league record": "P1350"
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
